from __future__ import annotations

import contextlib
import functools
import http.server
import os
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.runtime.services.local_graph_sim_server_html import (
    _build_layout_html_map,
    _extract_lv_defaults_from_ui_html,
    _extract_merged_lv_defaults,
)
from app.runtime.services.local_graph_sim_server_http import _LocalSimRequestHandler
from app.runtime.services.local_graph_sim_server_web_assets import ensure_local_sim_web_assets_exist
from app.runtime.services.local_graph_simulator import (
    GraphMountSpec,
    LocalGraphSimResourceMountSpec,
    LocalGraphSimSession,
    build_local_graph_sim_session,
    stable_layout_index_from_html_stem,
)

_DEFAULT_LOCAL_HTTP_PORT = 17890
_LOCAL_HTTP_PORT_ENV = "AYAYA_LOCAL_HTTP_PORT"
_LOCAL_HTTP_PORT_ENV_ALIAS = "AYAYA_LOCAL_SIM_PORT"


def _parse_preferred_local_http_port() -> int:
    for env_name in (_LOCAL_HTTP_PORT_ENV_ALIAS, _LOCAL_HTTP_PORT_ENV):
        raw = str(os.environ.get(env_name, "") or "").strip()
        if raw.isdigit():
            value = int(raw)
            if 0 <= value <= 65535:
                return int(value)
    return int(_DEFAULT_LOCAL_HTTP_PORT)


def get_preferred_local_sim_http_port() -> int:
    """返回本地测试 HTTP server 的“首选端口”。

    说明：
    - 默认端口为 17890（与 UI Workbench / shape-editor 一致）；
    - 可通过环境变量 `AYAYA_LOCAL_HTTP_PORT` 覆盖；
    - 兼容 `AYAYA_LOCAL_SIM_PORT` 作为别名覆盖（优先级更高）；
    - 返回值允许为 0（表示“让系统分配临时端口”）。
    """
    return int(_parse_preferred_local_http_port())


def _is_port_listening(*, host: str, port: int) -> bool:
    if port <= 0:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.05)
        return sock.connect_ex((host, int(port))) == 0


def _choose_local_http_port(*, host: str, preferred_port: int, scan_count: int = 50) -> int:
    """
    端口策略（与 UI Workbench / shape-editor 一致）：
    - 优先使用固定端口（默认 17890，可用环境变量 AYAYA_LOCAL_HTTP_PORT 覆盖；兼容 AYAYA_LOCAL_SIM_PORT 别名）
    - 若端口已被占用（已有服务在监听），则向上顺延扫描一段端口
    - 扫描不到则回退为 0（让系统分配临时端口）
    """
    preferred = int(preferred_port) if int(preferred_port) > 0 else int(get_preferred_local_sim_http_port())
    if preferred <= 0:
        return 0
    max_port = min(65535, preferred + max(1, int(scan_count)))
    for port in range(preferred, max_port + 1):
        if not _is_port_listening(host=host, port=port):
            return int(port)
    return 0


@dataclass(slots=True)
class LocalGraphSimServerConfig:
    workspace_root: Path | None
    graph_code_file: Path
    ui_html_file: Path
    owner_entity_name: str = "自身实体"
    player_entity_name: str = "玩家1"
    present_player_count: int = 1
    host: str = "127.0.0.1"
    port: int = 0
    auto_emit_signal_id: str = ""
    auto_emit_signal_params: dict[str, Any] = field(default_factory=dict)
    extra_graph_mounts: list[GraphMountSpec] = field(default_factory=list)
    resource_mounts: list[LocalGraphSimResourceMountSpec] = field(default_factory=list)


class _LocalSimThreadingHttpServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    # Windows 下 `SO_REUSEADDR` 可能导致“多个进程同时绑定同一端口”，从而出现请求被随机分发、
    # “一键重启 404 / 状态离线”等诡异现象；因此优先使用独占绑定。
    #
    # 非 Windows（无 SO_EXCLUSIVEADDRUSE）时允许复用地址，便于快速 stop/start。
    allow_reuse_address = not hasattr(socket, "SO_EXCLUSIVEADDRUSE")

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class LocalGraphSimServer:
    """本地测试 HTTP Server（浏览器预览 + 点击注入 + UI patch 回显）。"""

    def __init__(self, config: LocalGraphSimServerConfig) -> None:
        self._config = config
        self._lock = threading.RLock()
        self._session: LocalGraphSimSession | None = None
        self._bootstrap_patches: list[dict[str, Any]] = []
        self._last_action: dict[str, Any] | None = None
        self._last_validation_report: dict[str, Any] | None = None
        self._layout_html_by_index: dict[int, Path] = {}
        self._current_layout_index: int = 0
        self._auto_emit_signal_pending: bool = False
        # 会话代数：用于避免“重启后旧线程写入 bootstrap_patches / 清 pending”造成状态污染
        self._session_generation: int = 0
        self._httpd: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int = 0
        self._clock = _LocalSimClock()

    def _sync_player_layouts_to_current_layout_index(self) -> None:
        """
        将 server 的 current_layout_index 同步写入 GameRuntime（离线 UI 语义）：
        - 节点图侧常用 `获取玩家当前界面布局` 做“当前页门控”；
        - 本地 HTTP 预览的 UI 页面本身不直接改变运行态；
        - 因此需要在 server 侧把“当前预览页”映射为运行态的 player layout，避免点击一直被 layout=0 过滤。
        """
        session = self._session
        if session is None:
            return
        idx = int(self._current_layout_index)
        game = session.game
        for p in game.get_present_player_entities():
            game.ui_current_layout_by_player[str(p.entity_id)] = int(idx)

    def get_sim_time(self) -> float:
        """返回本地测试会话的“虚拟时间”（可暂停）。用于驱动 GameRuntime.tick(now=...)。"""
        return float(self._clock.now())

    @contextlib.contextmanager
    def locked(self) -> Any:
        """获取 server 内部锁的上下文管理器（避免 HTTP 层穿透访问 `_lock`）。"""
        with self._lock:
            yield

    def is_paused(self) -> bool:
        return bool(self._clock.is_paused)

    def set_paused(self, paused: bool) -> None:
        self._clock.set_paused(bool(paused))

    def advance_sim_time(self, dt: float) -> float:
        """仅在 paused 时推进虚拟时间，用于单步调试。"""
        return float(self._clock.advance(float(dt)))

    @property
    def session(self) -> LocalGraphSimSession:
        if self._session is None:
            raise RuntimeError("LocalGraphSimSession 未初始化")
        return self._session

    def start(self) -> None:
        if self._httpd is not None:
            return

        ensure_local_sim_web_assets_exist()

        ui_file = Path(self._config.ui_html_file).resolve()
        if not ui_file.is_file():
            raise FileNotFoundError(str(ui_file))

        self._bootstrap_patches = []
        self._last_action = None
        self._last_validation_report = None
        self._auto_emit_signal_pending = False
        self._clock.reset()
        self._layout_html_by_index = _build_layout_html_map(ui_file)
        self._current_layout_index = int(stable_layout_index_from_html_stem(ui_file.stem))

        self._session = build_local_graph_sim_session(
            workspace_root=self._config.workspace_root,
            graph_code_file=Path(self._config.graph_code_file).resolve(),
            owner_entity_name=self._config.owner_entity_name,
            player_entity_name=self._config.player_entity_name,
            present_player_count=int(self._config.present_player_count),
            extra_graph_mounts=list(self._config.extra_graph_mounts or []),
            resource_mounts=list(self._config.resource_mounts or []),
        )
        self._session_generation += 1
        self._sync_player_layouts_to_current_layout_index()

        # UI HTML 默认值：用于在本地测试中补齐 lv.* 对应的“关卡实体自定义变量”默认结构，
        # 避免节点图对字典写 key 时因为变量不存在而变成 no-op（导致倒计时/文本不刷新）。
        lv_defaults = _extract_merged_lv_defaults(entry_ui_file=ui_file, layout_html_by_index=self._layout_html_by_index)
        if lv_defaults:
            self._session.game.set_ui_lv_defaults(lv_defaults)
            if isinstance(self._session.sim_notes, dict):
                self._session.sim_notes["ui_lv_defaults_keys"] = sorted([str(k) for k in lv_defaults.keys()])
                self._session.sim_notes["ui_lv_defaults_count"] = int(len(lv_defaults.keys()))

        # 启动即跑一遍 validate-graphs（报告写入 last_validation_report，供监控面板展示/回放导出前确认）。
        self.validate_now()

        from app.runtime.services.local_graph_sim_server_http_facade import LocalGraphSimHttpFacade

        handler_factory = functools.partial(
            _LocalSimRequestHandler,
            entry_ui_html_file=ui_file,
            http_facade=LocalGraphSimHttpFacade(server=self),
        )
        host = str(self._config.host or "127.0.0.1")
        preferred_port = int(self._config.port or 0)
        if preferred_port < 0:
            preferred_port = 0
        port = _choose_local_http_port(host=host, preferred_port=preferred_port)
        httpd = _LocalSimThreadingHttpServer((host, port), handler_factory)
        self._httpd = httpd
        self.port = int(httpd.server_address[1])
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        self._thread = thread
        thread.start()

        auto_sid = str(self._config.auto_emit_signal_id or "").strip()
        if auto_sid:
            self._auto_emit_signal_pending = True
            session_gen = int(self._session_generation)

            def _emit_auto_signal() -> None:
                with self._lock:
                    if session_gen != self._session_generation:
                        return
                    patches = self.session.emit_signal(
                        signal_id=auto_sid,
                        params=dict(self._config.auto_emit_signal_params or {}),
                    )
                    self._bootstrap_patches = list(patches)
                    self._capture_layout_switch_from_patches(patches)
                    self._auto_emit_signal_pending = False

            threading.Thread(target=_emit_auto_signal, daemon=True).start()

    def restart(self) -> None:
        """重建模拟会话（相当于“重新启动”本地测试），并重置面板相关状态。"""
        if self._httpd is None:
            raise RuntimeError("server 未启动")

        ui_file = Path(self._config.ui_html_file).resolve()
        if not ui_file.is_file():
            raise FileNotFoundError(str(ui_file))

        with self._lock:
            self._bootstrap_patches = []
            self._last_action = None
            self._last_validation_report = None
            self._auto_emit_signal_pending = False
            self._clock.reset()
            self._layout_html_by_index = _build_layout_html_map(ui_file)
            self._current_layout_index = int(stable_layout_index_from_html_stem(ui_file.stem))

            self._session = build_local_graph_sim_session(
                workspace_root=self._config.workspace_root,
                graph_code_file=Path(self._config.graph_code_file).resolve(),
                owner_entity_name=self._config.owner_entity_name,
                player_entity_name=self._config.player_entity_name,
                present_player_count=int(self._config.present_player_count),
                extra_graph_mounts=list(self._config.extra_graph_mounts or []),
                resource_mounts=list(self._config.resource_mounts or []),
            )
            self._session_generation += 1
            self._sync_player_layouts_to_current_layout_index()

            lv_defaults = _extract_merged_lv_defaults(entry_ui_file=ui_file, layout_html_by_index=self._layout_html_by_index)
            if lv_defaults:
                self._session.game.set_ui_lv_defaults(lv_defaults)
                if isinstance(self._session.sim_notes, dict):
                    self._session.sim_notes["ui_lv_defaults_keys"] = sorted([str(k) for k in lv_defaults.keys()])
                    self._session.sim_notes["ui_lv_defaults_count"] = int(len(lv_defaults.keys()))

            self.validate_now()

            auto_sid = str(self._config.auto_emit_signal_id or "").strip()
            if not auto_sid:
                return

            self._auto_emit_signal_pending = True
            session_gen = int(self._session_generation)

            def _emit_auto_signal() -> None:
                with self._lock:
                    if session_gen != self._session_generation:
                        return
                    patches = self.session.emit_signal(
                        signal_id=auto_sid,
                        params=dict(self._config.auto_emit_signal_params or {}),
                    )
                    self._bootstrap_patches = list(patches)
                    self._capture_layout_switch_from_patches(patches)
                    self._auto_emit_signal_pending = False

            threading.Thread(target=_emit_auto_signal, daemon=True).start()

    def stop(self) -> None:
        httpd = self._httpd
        thread = self._thread
        if httpd is None:
            return
        httpd.shutdown()
        httpd.server_close()
        self._httpd = None
        self._thread = None
        self.port = 0
        if thread is not None:
            thread.join(timeout=1.0)

    def drain_bootstrap_patches(self) -> list[dict[str, Any]]:
        with self._lock:
            patches = list(self._bootstrap_patches)
            self._bootstrap_patches = []
            return patches

    def set_last_action(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._last_action = dict(payload)

    def get_last_action(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._last_action) if isinstance(self._last_action, dict) else None

    def validate_now(
        self,
        *,
        strict_entity_wire_only: bool = False,
        disable_cache: bool = False,
        disable_composite_struct_check: bool = False,
    ) -> dict[str, Any]:
        """
        对当前会话已挂载的节点图源码执行引擎校验（validate-graphs 口径）。
        返回结构化报告（issues + summary + targets）。
        """
        from engine.validate.graph_validation_orchestrator import (
            ValidateGraphsOrchestrationOptions,
            collect_validate_graphs_engine_issues,
        )

        session = self.session
        targets: list[Path] = []
        mounted = getattr(session, "mounted_graphs", None)
        if isinstance(mounted, list) and mounted:
            for g in mounted:
                p = Path(str(getattr(g, "graph_code_file", "") or "")).resolve()
                if p.is_file():
                    targets.append(p)
        if not targets:
            p2 = Path(session.graph_code_file).resolve()
            if p2.is_file():
                targets.append(p2)

        uniq: list[Path] = []
        seen: set[str] = set()
        for p in targets:
            key = p.as_posix().casefold()
            if key in seen:
                continue
            seen.add(key)
            uniq.append(p)
        targets = uniq

        options = ValidateGraphsOrchestrationOptions(
            strict_entity_wire_only=bool(strict_entity_wire_only),
            use_cache=bool(not disable_cache),
            enable_composite_struct_check=bool(not disable_composite_struct_check),
        )
        issues = collect_validate_graphs_engine_issues(targets, session.workspace_root, options=options)
        payload = {
            "ok": True,
            "targets": [str(p) for p in targets],
            "options": {
                "strict_entity_wire_only": bool(strict_entity_wire_only),
                "disable_cache": bool(disable_cache),
                "disable_composite_struct_check": bool(disable_composite_struct_check),
            },
            "summary": {
                "total": int(len(issues)),
                "errors": int(sum(1 for i in issues if str(getattr(i, "level", "")) == "error")),
                "warnings": int(sum(1 for i in issues if str(getattr(i, "level", "")) == "warning")),
                "infos": int(sum(1 for i in issues if str(getattr(i, "level", "")) == "info")),
            },
            "issues": [i.to_dict() if hasattr(i, "to_dict") else dict(i) for i in issues],
        }
        with self._lock:
            self._last_validation_report = dict(payload)
        return payload

    def get_last_validation_report(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._last_validation_report) if isinstance(self._last_validation_report, dict) else None

    @property
    def current_layout_index(self) -> int:
        return int(self._current_layout_index)

    def set_current_layout_index(self, layout_index: int) -> None:
        with self._lock:
            self._current_layout_index = int(layout_index)
            self._sync_player_layouts_to_current_layout_index()

    def get_layout_html_file(self, layout_index: int) -> Path | None:
        return self._layout_html_by_index.get(int(layout_index))

    def get_all_layouts(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for idx, path in sorted(self._layout_html_by_index.items(), key=lambda kv: (kv[0], str(kv[1]))):
            items.append(
                {
                    "layout_index": int(idx),
                    "html_stem": str(Path(path).stem),
                    "html_file": str(Path(path)),
                }
            )
        return items

    def _capture_layout_switch_from_patches(self, patches: list[dict[str, Any]]) -> None:
        for p in patches:
            if not isinstance(p, dict):
                continue
            if str(p.get("op") or "") != "switch_layout":
                continue
            idx = p.get("layout_index", None)
            if isinstance(idx, int):
                self._current_layout_index = int(idx)

    def capture_layout_switch_from_patches(self, patches: list[dict[str, Any]]) -> None:
        """从 UI patches 中同步 current_layout_index（避免 HTTP 层穿透调用私有方法）。"""
        self._capture_layout_switch_from_patches(patches)

    def get_host(self) -> str:
        return str(self._config.host or "127.0.0.1")

    def get_workspace_root(self) -> Path | None:
        return self._config.workspace_root

    def get_auto_emit_signal_id(self) -> str:
        return str(self._config.auto_emit_signal_id or "")

    def is_auto_emit_signal_pending(self) -> bool:
        return bool(self._auto_emit_signal_pending)

    def get_url(self) -> str:
        if self.port <= 0:
            raise RuntimeError("server 未启动")
        return f"http://{self._config.host}:{self.port}/"


__all__ = [
    "get_preferred_local_sim_http_port",
    "LocalGraphSimServerConfig",
    "LocalGraphSimServer",
]


class _LocalSimClock:
    """
    本地测试虚拟时钟（可暂停）：
    - now() 单调递增（与 time.monotonic 对齐）
    - 暂停期间虚拟时间不前进；恢复后不会“补账触发”定时器
    """

    def __init__(self) -> None:
        self._paused: bool = False
        self._paused_virtual_now: float = 0.0
        self._paused_started_real: float = 0.0
        self._paused_total: float = 0.0

    @property
    def is_paused(self) -> bool:
        return bool(self._paused)

    def reset(self) -> None:
        self._paused = False
        self._paused_virtual_now = 0.0
        self._paused_started_real = 0.0
        self._paused_total = 0.0

    def now(self) -> float:
        real_now = float(time.monotonic())
        if self._paused:
            return float(self._paused_virtual_now)
        return float(real_now - float(self._paused_total))

    def set_paused(self, paused: bool) -> None:
        want = bool(paused)
        if want == self._paused:
            return
        real_now = float(time.monotonic())
        if want:
            self._paused_virtual_now = float(real_now - float(self._paused_total))
            self._paused_started_real = float(real_now)
            self._paused = True
            return
        # resume
        elapsed = float(real_now - float(self._paused_started_real))
        if elapsed < 0:
            elapsed = 0.0
        self._paused_total = float(self._paused_total) + float(elapsed)
        self._paused = False

    def advance(self, dt: float) -> float:
        """仅在暂停状态下推进虚拟时间，用于单步调试。返回推进后的虚拟时间。"""
        if not self._paused:
            raise RuntimeError("advance 仅允许在 paused 状态下调用")
        delta = float(dt)
        if delta < 0:
            raise ValueError("dt 必须 >= 0")
        self._paused_virtual_now = float(self._paused_virtual_now) + float(delta)
        return float(self._paused_virtual_now)
