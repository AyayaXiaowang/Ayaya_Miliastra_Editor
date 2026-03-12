from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from .._cli_subprocess import run_cli_with_progress

BASE_GIL_CONFLICT_SCAN_DECODE_MAX_DEPTH = 16
BASE_GIL_CONFLICT_SCAN_STDERR_TAIL_MAX_LINES = 240
BASE_GIL_CONFLICT_SCAN_STDERR_TAIL_DIALOG_MAX_LINES = 120
_EXIT_CODE_OK = 0
_EXIT_CODE_ERROR = 1


@dataclass(frozen=True, slots=True)
class BaseGilConflictsScanResult:
    exit_code: int
    report: dict[str, object] | None
    stderr_tail: list[str]


def make_base_gil_conflicts_scan_worker_cls(*, QtCore: Any) -> type:
    # 延迟定义 QThread（避免模块顶层 import PyQt6）。
    class _Worker(QtCore.QThread):  # type: ignore[misc]
        progress_changed = QtCore.pyqtSignal(int, int, str)
        succeeded = QtCore.pyqtSignal(object)  # dict report
        failed = QtCore.pyqtSignal(int, object)  # exit_code, stderr_tail(list[str])

        def __init__(
            self,
            *,
            command: Sequence[str],
            cwd: Path,
            report_file: Path,
            parent: object | None = None,
        ) -> None:
            # 构造扫描 worker（仅保存参数，不做 IO）。
            super().__init__(parent)
            self._command = list(command)
            self._cwd = Path(cwd).resolve()
            self._report_file = Path(report_file).resolve()

        def run(self) -> None:
            # 在子线程内运行子进程并解析进度行，输出 JSON 报告供 UI 使用。
            import json
            import traceback

            try:
                result = run_cli_with_progress(
                    command=self._command,
                    cwd=self._cwd,
                    on_progress=lambda c, t, l: self.progress_changed.emit(int(c), int(t), str(l)),
                    stderr_tail_max_lines=BASE_GIL_CONFLICT_SCAN_STDERR_TAIL_MAX_LINES,
                )
                if int(result.exit_code) != _EXIT_CODE_OK:
                    self.failed.emit(int(result.exit_code), list(result.stderr_tail))
                    return

                if not self._report_file.is_file():
                    raise FileNotFoundError(str(self._report_file))
                obj = json.loads(self._report_file.read_text(encoding="utf-8"))
                if not isinstance(obj, dict):
                    raise TypeError("base gil conflicts report must be dict")
                self.succeeded.emit(dict(obj))
            except Exception:
                self.failed.emit(_EXIT_CODE_ERROR, [traceback.format_exc()])

    return _Worker


def run_base_gil_conflicts_scan_blocking(
    *,
    QtCore: Any,
    main_window: Any,
    command: Sequence[str],
    cwd: Path,
    report_file: Path,
    set_busy: Callable[[bool], None],
    on_progress: Callable[[int, int, str], None] | None,
) -> BaseGilConflictsScanResult:
    """在 UI 线程阻塞等待扫描完成（用 QEventLoop 保持界面响应并转发进度）。"""
    WorkerCls = make_base_gil_conflicts_scan_worker_cls(QtCore=QtCore)
    loop = QtCore.QEventLoop()

    state: dict[str, object] = {
        "exit_code": _EXIT_CODE_ERROR,
        "report": None,
        "stderr_tail": [],
    }

    def _handle_progress(c: int, t: int, label: str) -> None:
        # 将扫描进度转发到 UI 层回调。
        if on_progress is not None:
            on_progress(int(c), int(t), str(label))

    worker = WorkerCls(
        command=list(command),
        cwd=Path(cwd),
        report_file=Path(report_file),
        parent=main_window,
    )

    worker.progress_changed.connect(_handle_progress)
    worker.succeeded.connect(lambda obj: (state.__setitem__("exit_code", _EXIT_CODE_OK), state.__setitem__("report", dict(obj)), loop.quit()))
    worker.failed.connect(
        lambda exit_code, stderr_tail: (
            state.__setitem__("exit_code", int(exit_code)),
            state.__setitem__("report", None),
            state.__setitem__("stderr_tail", list(stderr_tail) if isinstance(stderr_tail, list) else [str(stderr_tail)]),
            loop.quit(),
        )
    )
    worker.finished.connect(worker.deleteLater)

    set_busy(True)
    _handle_progress(0, 0, "启动扫描…")
    worker.start()
    loop.exec()
    set_busy(False)

    exit_code_raw = state.get("exit_code")
    # 注意：exit_code=0 是合法成功值，不能用 `x or fallback`（否则 0 会被当成 false 覆盖成错误码）。
    exit_code = _EXIT_CODE_ERROR if exit_code_raw is None else int(exit_code_raw)
    return BaseGilConflictsScanResult(
        exit_code=int(exit_code),
        report=(state.get("report") if isinstance(state.get("report"), dict) else None),
        stderr_tail=[str(x) for x in list(state.get("stderr_tail") or [])],
    )

