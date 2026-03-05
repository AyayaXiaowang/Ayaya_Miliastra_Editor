from __future__ import annotations

import threading
import time
import sys
import traceback
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Iterable, List, Optional, Tuple

from PyQt6 import QtCore


@dataclass(frozen=True, slots=True)
class ThreadStackSample:
    """一次线程调用栈采样（用于定位 GIL 争用/后台线程耗时）。"""

    thread_name: str
    thread_ident: int
    top_frame: str
    stack: List[str]


@dataclass(frozen=True, slots=True)
class UiStallEvent:
    """一次 UI 主线程卡顿事件（事件循环被阻塞）。"""

    start_ts_s: float
    end_ts_s: float
    duration_ms: float
    threshold_ms: float
    captured_stack: List[str]
    top_frame: str
    other_threads: List[ThreadStackSample]


@dataclass(frozen=True, slots=True)
class PerfSpanEvent:
    """一次命名耗时段记录（可用于定位高耗时逻辑）。"""

    name: str
    start_ts_s: float
    end_ts_s: float
    duration_ms: float
    thread_name: str


class AppPerformanceMonitor(QtCore.QObject):
    """全局性能监控（UI 卡顿 watchdog + 命名耗时段）。

    核心诉求：
    - 当用户“感觉卡顿”时，直接在 UI 内看到：卡了多久、卡在什么调用栈；
    - 默认关闭：避免引入额外开销与噪音；
    - 不依赖第三方库（psutil 等），仅使用标准库 + Qt。
    """

    stall_event_added = QtCore.pyqtSignal(object)  # UiStallEvent
    span_added = QtCore.pyqtSignal(object)  # PerfSpanEvent

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AppPerformanceMonitor")

        self._lock = threading.Lock()
        self._enabled: bool = False

        self._heartbeat_timer = QtCore.QTimer(self)
        self._heartbeat_timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self._heartbeat_timer.setInterval(50)
        self._heartbeat_timer.timeout.connect(self._on_heartbeat_tick)

        self._last_heartbeat_ts_s: float = 0.0
        self._heartbeat_intervals_ms: Deque[float] = deque(maxlen=240)

        self._stall_threshold_ms: float = 250.0
        self._capture_stacks: bool = True
        self._stall_events: Deque[UiStallEvent] = deque(maxlen=50)

        self._span_events: Deque[PerfSpanEvent] = deque(maxlen=200)

        # 事件序号：仅在 stall/span/clear 发生变化时递增，用于 UI 避免高频重绘大段文本。
        self._event_seq: int = 0

        self._stop_event = threading.Event()
        self._watchdog_thread: threading.Thread | None = None

    def is_enabled(self) -> bool:
        return bool(self._enabled)

    def configure(
        self,
        *,
        stall_threshold_ms: float | int | None = None,
        capture_stacks: bool | None = None,
        heartbeat_interval_ms: int | None = None,
    ) -> None:
        with self._lock:
            if stall_threshold_ms is not None:
                self._stall_threshold_ms = float(stall_threshold_ms)
            if capture_stacks is not None:
                self._capture_stacks = bool(capture_stacks)

        if heartbeat_interval_ms is not None:
            self._heartbeat_timer.setInterval(int(heartbeat_interval_ms))

    def _ensure_watchdog_thread_running(self) -> None:
        """确保 watchdog 线程处于运行态。

        说明：
        - watchdog 在线程内执行采样与 stall 判定；若线程异常退出（或被 stop 终止）但 UI 仍认为 enabled，
          监控将进入“僵尸态”（enabled=True 但不再产生 stall 事件）。
        - 本方法在主线程调用：若线程不在运行则重建并启动。
        """
        t = self._watchdog_thread
        if t is not None and t.is_alive():
            return
        self._stop_event.clear()
        new_thread = threading.Thread(
            target=self._watchdog_loop,
            name="AppPerfWatchdog",
            daemon=True,
        )
        self._watchdog_thread = new_thread
        new_thread.start()

    def start(self) -> None:
        # 说明：start 必须是“幂等且自愈”的。
        # - UI 侧可能会重复调用 start（设置页/悬浮面板开关等）；
        # - watchdog 线程可能因未捕获异常退出；
        # - 心跳 QTimer 也可能因外部 stop/parent 关系变化进入非预期状态；
        # 若仅以 `_enabled` 作为唯一判定，会导致 enabled=True 但不再产生事件的僵尸态。
        if self._enabled:
            # enabled 但 timer 被停掉：按“重启心跳”口径重置基线，避免把停用期间误判为一次超长 stall。
            if not self._heartbeat_timer.isActive():
                with self._lock:
                    self._last_heartbeat_ts_s = 0.0
                    self._heartbeat_intervals_ms.clear()
                self._stop_event.clear()
                self._heartbeat_timer.start()
            self._ensure_watchdog_thread_running()
            return

        self._enabled = True
        with self._lock:
            # 启用监控时清空心跳基线，避免把“停用期间”误判为一次超长 stall。
            self._last_heartbeat_ts_s = 0.0
            self._heartbeat_intervals_ms.clear()
        self._stop_event.clear()
        self._heartbeat_timer.start()
        self._ensure_watchdog_thread_running()

    def stop(self) -> None:
        if not self._enabled:
            return
        self._enabled = False
        self._heartbeat_timer.stop()
        self._stop_event.set()

    def clear_events(self) -> None:
        with self._lock:
            self._stall_events.clear()
            self._span_events.clear()
            self._event_seq += 1

    def record_span(self, name: str, dt_ms: float, *, start_ts_s: float | None = None) -> None:
        if not self._enabled:
            return
        key = str(name or "").strip()
        if key == "":
            return

        end_ts = float(time.perf_counter())
        start_ts = float(start_ts_s) if start_ts_s is not None else float(end_ts - float(dt_ms) / 1000.0)
        event = PerfSpanEvent(
            name=key,
            start_ts_s=float(start_ts),
            end_ts_s=float(end_ts),
            duration_ms=float(dt_ms),
            thread_name=str(threading.current_thread().name),
        )
        with self._lock:
            self._span_events.append(event)
            self._event_seq += 1
        self.span_added.emit(event)

    def scope(self, name: str) -> "_PerfSpanScope":
        return _PerfSpanScope(self, str(name or ""))

    def get_snapshot(self) -> dict:
        with self._lock:
            intervals = list(self._heartbeat_intervals_ms)
            last_heartbeat = float(self._last_heartbeat_ts_s)
            threshold_ms = float(self._stall_threshold_ms)
            capture_stacks = bool(self._capture_stacks)
            stalls = list(self._stall_events)
            spans = list(self._span_events)
            event_seq = int(self._event_seq)

        now = float(time.perf_counter())
        gap_ms = 0.0
        if last_heartbeat > 0.0:
            gap_ms = float((now - last_heartbeat) * 1000.0)

        avg_interval = float(sum(intervals) / float(len(intervals))) if intervals else 0.0
        max_interval = float(max(intervals)) if intervals else 0.0

        return {
            "enabled": bool(self._enabled),
            "heartbeat_gap_ms": float(gap_ms),
            "heartbeat_interval_avg_ms": float(avg_interval),
            "heartbeat_interval_max_ms": float(max_interval),
            "stall_threshold_ms": float(threshold_ms),
            "capture_stacks": bool(capture_stacks),
            "stall_events": stalls,
            "span_events": spans,
            "event_seq": int(event_seq),
        }

    def format_report_text(
        self,
        *,
        max_stalls: int = 6,
        max_spans: int = 16,
        max_span_groups: int = 12,
        include_live_metrics: bool = True,
        include_full_stacks_for_recent: bool = True,
        include_other_threads: bool = True,
    ) -> str:
        snap = self.get_snapshot()
        enabled = bool(snap.get("enabled"))
        gap_ms = float(snap.get("heartbeat_gap_ms") or 0.0)
        avg_ms = float(snap.get("heartbeat_interval_avg_ms") or 0.0)
        max_ms = float(snap.get("heartbeat_interval_max_ms") or 0.0)
        threshold_ms = float(snap.get("stall_threshold_ms") or 0.0)
        capture_stacks = bool(snap.get("capture_stacks"))

        stalls: List[UiStallEvent] = list(snap.get("stall_events") or [])
        spans: List[PerfSpanEvent] = list(snap.get("span_events") or [])
        now = float(time.perf_counter())

        lines: List[str] = []
        lines.append("全局性能监控（UI卡顿/耗时段）")
        lines.append("")
        lines.append(f"- enabled: {enabled}")
        if bool(include_live_metrics):
            lines.append(
                f"- heartbeat gap: {gap_ms:.1f}ms (avg_interval={avg_ms:.1f}ms, max_interval={max_ms:.1f}ms)"
            )
        lines.append(f"- stall threshold: {threshold_ms:.0f}ms")
        lines.append(f"- capture stacks: {capture_stacks}")
        lines.append(f"- stalls: {len(stalls)}")
        lines.append(f"- spans: {len(spans)}")
        lines.append("")

        if stalls:
            lines.append("最近卡顿（越靠后越新）：")
            recent = stalls[-int(max(1, max_stalls)) :]
            for i, ev in enumerate(recent, start=1):
                age_s = float(max(0.0, now - float(ev.end_ts_s)))
                lines.append(
                    f"{i:>2}. dur={ev.duration_ms:>7.1f}ms  end_ago={age_s:>6.2f}s  top={ev.top_frame}"
                )
            lines.append("")

            if bool(include_full_stacks_for_recent) and bool(capture_stacks):
                lines.append("卡顿堆栈（最近卡顿，采样于卡顿期间；越靠后越新）：")
                for i, ev in enumerate(recent, start=1):
                    age_s = float(max(0.0, now - float(ev.end_ts_s)))
                    lines.append(
                        f"[stall {i}] dur={ev.duration_ms:.1f}ms  end_ago={age_s:.2f}s  top={ev.top_frame}"
                    )
                    if ev.captured_stack:
                        lines.append("主线程堆栈：")
                        lines.extend([line.rstrip("\n") for line in list(ev.captured_stack)])
                    if bool(include_other_threads) and ev.other_threads:
                        lines.append("")
                        lines.append("其它线程堆栈（同一时刻采样；用于排查 GIL 争用/后台重活）：")
                        for sample in list(ev.other_threads):
                            lines.append(f"[thread] {sample.thread_name}  top={sample.top_frame}")
                            lines.extend([line.rstrip("\n") for line in list(sample.stack)])
                            lines.append("")
                        if lines and lines[-1] == "":
                            lines.pop()
                    lines.append("")

        if spans:
            # -------- 聚合统计（按 max_ms 降序）
            grouped: Dict[str, Dict[str, float | int | str]] = {}
            for ev in spans:
                key = str(ev.name or "").strip()
                if key == "":
                    continue
                row = grouped.get(key)
                if row is None:
                    grouped[key] = {
                        "count": 1,
                        "total_ms": float(ev.duration_ms),
                        "max_ms": float(ev.duration_ms),
                        "last_ms": float(ev.duration_ms),
                        "last_end_ts_s": float(ev.end_ts_s),
                        "last_thread": str(ev.thread_name),
                    }
                else:
                    row["count"] = int(row.get("count") or 0) + 1
                    row["total_ms"] = float(row.get("total_ms") or 0.0) + float(ev.duration_ms)
                    row["max_ms"] = float(max(float(row.get("max_ms") or 0.0), float(ev.duration_ms)))
                    row["last_ms"] = float(ev.duration_ms)
                    row["last_end_ts_s"] = float(ev.end_ts_s)
                    row["last_thread"] = str(ev.thread_name)

            if grouped:
                lines.append("耗时段聚合（按 max_ms 降序）：")
                rows: List[Tuple[float, float, int, float, float, str, str]] = []
                for name, row in grouped.items():
                    count = int(row.get("count") or 0)
                    total_ms = float(row.get("total_ms") or 0.0)
                    max_ms_value = float(row.get("max_ms") or 0.0)
                    last_ms = float(row.get("last_ms") or 0.0)
                    last_end_ts_s = float(row.get("last_end_ts_s") or 0.0)
                    last_thread = str(row.get("last_thread") or "")
                    avg_ms_value = float(total_ms / float(count)) if count > 0 else 0.0
                    last_age_s = float(max(0.0, now - last_end_ts_s)) if last_end_ts_s > 0.0 else 0.0
                    rows.append((max_ms_value, avg_ms_value, count, last_ms, last_age_s, last_thread, name))
                rows.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
                top_groups = rows[: int(max(1, max_span_groups))]
                for i, (max_ms_value, avg_ms_value, count, last_ms, last_age_s, last_thread, name) in enumerate(
                    top_groups, start=1
                ):
                    lines.append(
                        f"{i:>2}. max={max_ms_value:>7.1f}ms  avg={avg_ms_value:>7.1f}ms  n={count:>3d}  "
                        f"last={last_ms:>7.1f}ms  last_ago={last_age_s:>6.2f}s  {name}  ({last_thread})"
                    )
                lines.append("")

            lines.append("最近耗时段（按结束时间，越靠后越新）：")
            recent_spans = spans[-int(max(1, max_spans)) :]
            for i, ev in enumerate(recent_spans, start=1):
                age_s = float(max(0.0, now - float(ev.end_ts_s)))
                lines.append(
                    f"{i:>2}. {ev.duration_ms:>7.1f}ms  end_ago={age_s:>6.2f}s  {ev.name}  ({ev.thread_name})"
                )
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _on_heartbeat_tick(self) -> None:
        # 若 watchdog 线程异常退出，心跳 tick 可以把监控从“僵尸态”拉回（无需用户手动重启）。
        if self._enabled:
            self._ensure_watchdog_thread_running()
        now = float(time.perf_counter())
        with self._lock:
            prev = float(self._last_heartbeat_ts_s)
            self._last_heartbeat_ts_s = now
        if prev > 0.0:
            dt_ms = float((now - prev) * 1000.0)
            with self._lock:
                self._heartbeat_intervals_ms.append(dt_ms)

    def _watchdog_loop(self) -> None:
        main_ident = threading.main_thread().ident
        poll_s = 0.05

        in_stall = False
        stall_start_ts_s = 0.0
        stall_stack: List[str] = []
        stall_top_frame = ""
        stall_other_threads: List[ThreadStackSample] = []

        while not self._stop_event.is_set():
            if not self._enabled:
                time.sleep(poll_s)
                continue

            now = float(time.perf_counter())
            with self._lock:
                last_hb = float(self._last_heartbeat_ts_s)
                threshold_ms = float(self._stall_threshold_ms)
                capture_stacks = bool(self._capture_stacks)

            if last_hb <= 0.0:
                time.sleep(poll_s)
                continue

            gap_ms = float((now - last_hb) * 1000.0)
            if gap_ms >= threshold_ms:
                if not in_stall:
                    in_stall = True
                    stall_start_ts_s = float(last_hb)
                    stall_stack = []
                    stall_top_frame = ""
                    stall_other_threads = []
                    if capture_stacks and main_ident is not None:
                        frames_by_ident = sys._current_frames()
                        thread_names = {
                            int(t.ident): str(t.name)
                            for t in list(threading.enumerate())
                            if t.ident is not None
                        }

                        frame = frames_by_ident.get(int(main_ident))
                        if frame is not None:
                            stall_stack = list(traceback.format_stack(frame))
                            stall_top_frame = _format_top_frame_from_stack(stall_stack)

                        # 同时采样其它线程：当主线程栈只剩 qapplication.exec() 时，常见原因是其它线程长期持有 GIL。
                        workspace_hint = "Graph_Generater"
                        samples: List[ThreadStackSample] = []
                        for ident, other_frame in frames_by_ident.items():
                            if int(ident) == int(main_ident):
                                continue
                            name = thread_names.get(int(ident), f"Thread-{int(ident)}")
                            if str(name) == "AppPerfWatchdog":
                                continue
                            stack_lines = list(traceback.format_stack(other_frame))
                            top = _format_top_frame_from_stack(stack_lines)
                            is_relevant = any(workspace_hint in str(line) for line in stack_lines)
                            if not is_relevant:
                                continue
                            samples.append(
                                ThreadStackSample(
                                    thread_name=str(name),
                                    thread_ident=int(ident),
                                    top_frame=str(top or ""),
                                    stack=[line.rstrip("\n") for line in stack_lines],
                                )
                            )
                        # 仅保留少量最相关线程，避免报告过长
                        stall_other_threads = samples[:4]
                time.sleep(poll_s)
                continue

            # gap < threshold: 若刚结束一次卡顿，则在“恢复后”落盘事件（只记录一次）
            if in_stall:
                in_stall = False
                end_ts_s = float(last_hb)
                duration_ms = float((end_ts_s - float(stall_start_ts_s)) * 1000.0)
                if duration_ms >= threshold_ms:
                    event = UiStallEvent(
                        start_ts_s=float(stall_start_ts_s),
                        end_ts_s=float(end_ts_s),
                        duration_ms=float(duration_ms),
                        threshold_ms=float(threshold_ms),
                        captured_stack=list(stall_stack),
                        top_frame=str(stall_top_frame or ""),
                        other_threads=list(stall_other_threads),
                    )
                    with self._lock:
                        self._stall_events.append(event)
                        self._event_seq += 1
                    self.stall_event_added.emit(event)
            time.sleep(poll_s)


class _PerfSpanScope:
    def __init__(self, monitor: AppPerformanceMonitor, name: str) -> None:
        self._monitor = monitor
        self._name = str(name or "").strip()
        self._t0 = 0.0

    def __enter__(self) -> "_PerfSpanScope":
        self._t0 = float(time.perf_counter())
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._name != "":
            t1 = float(time.perf_counter())
            self._monitor.record_span(self._name, float((t1 - self._t0) * 1000.0), start_ts_s=self._t0)
        return False


def _format_top_frame_from_stack(stack_lines: Iterable[str]) -> str:
    lines = [str(x).rstrip("\n") for x in list(stack_lines or []) if str(x).strip()]
    if not lines:
        return ""
    # traceback.format_stack 的最后几行通常包含真正的调用点（file/line/function）
    tail = lines[-4:]
    for line in reversed(tail):
        text = line.strip()
        if text.startswith('File "'):
            return text
    return tail[-1].strip() if tail else ""


_shared_monitor: AppPerformanceMonitor | None = None


def get_shared_performance_monitor() -> AppPerformanceMonitor:
    global _shared_monitor
    if _shared_monitor is None:
        _shared_monitor = AppPerformanceMonitor()
    return _shared_monitor

