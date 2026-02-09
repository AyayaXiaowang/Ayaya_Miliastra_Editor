from __future__ import annotations

"""
UI 启动装配管线（bootstrap）。

设计目标：
- 让 `app.cli.run_app` 只负责 CLI 参数解析与 workspace_root 推导；
- 将“启动顺序约束（OCR -> PyQt6）+ 诊断基础设施（看门狗/异常钩子/日志落盘）”
  收敛到本模块，避免入口膨胀为巨函数。
"""

import faulthandler
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Optional, TextIO

from engine.configs.settings import settings
from engine.utils.logging.logger import log_debug, log_info, log_warn
from app.common.private_extension_loader import ensure_private_extensions_loaded
from app.common.private_extension_registry import run_bootstrap_hooks, run_main_window_hooks

__all__ = [
    "UiRunConfig",
    "run_ui_app",
]


class _TeeTextIO:
    """将写入同时复制到两个 TextIO（stdout/stderr tee 到文件）。"""

    def __init__(self, primary_stream: TextIO, secondary_stream: TextIO) -> None:
        self._primary_stream = primary_stream
        self._secondary_stream = secondary_stream

    def write(self, text: str) -> int:
        written = self._primary_stream.write(text)
        self._secondary_stream.write(text)
        return written

    def flush(self) -> None:
        self._primary_stream.flush()
        self._secondary_stream.flush()

    def isatty(self) -> bool:  # pragma: no cover - 仅透传属性
        primary_isatty = getattr(self._primary_stream, "isatty", None)
        return bool(primary_isatty()) if callable(primary_isatty) else False

    def __getattr__(self, item: str):
        return getattr(self._primary_stream, item)


@dataclass(frozen=True, slots=True)
class UiRunConfig:
    workspace_root: Path
    qt_args: list[str]
    safety_notice_text: str

    enable_ocr_preload: bool
    enable_ui_freeze_watchdog: bool
    show_safety_notice_dialog: bool

    log_file_path: Optional[Path]


@dataclass(slots=True)
class _LogTeeHandle:
    log_file_path: Path
    log_file_stream: TextIO
    original_stdout: Optional[TextIO]
    original_stderr: Optional[TextIO]

    def close(self) -> None:
        self.log_file_stream.flush()
        self.log_file_stream.close()


def _get_runtime_cache_root(workspace_root: Path) -> Path:
    runtime_cache_root_text = str(getattr(settings, "RUNTIME_CACHE_ROOT", "app/runtime/cache") or "app/runtime/cache")
    runtime_cache_root_path = Path(runtime_cache_root_text)
    return runtime_cache_root_path if runtime_cache_root_path.is_absolute() else (workspace_root / runtime_cache_root_path)


def _install_log_tee_if_needed(*, workspace_root: Path, requested_log_file_path: Optional[Path]) -> Optional[_LogTeeHandle]:
    """可选地将 stdout/stderr tee 到日志文件，并在无控制台输出流时提供兜底落盘。"""
    selected_log_file_path = requested_log_file_path

    stdout_is_missing = sys.stdout is None
    stderr_is_missing = sys.stderr is None

    if selected_log_file_path is None and (stdout_is_missing or stderr_is_missing):
        runtime_cache_root = _get_runtime_cache_root(workspace_root)
        selected_log_file_path = runtime_cache_root / "boot.log"

    if selected_log_file_path is None:
        return None

    selected_log_file_path.parent.mkdir(parents=True, exist_ok=True)
    log_file_stream = open(selected_log_file_path, "a", encoding="utf-8", errors="replace")

    original_stdout = sys.stdout
    original_stderr = sys.stderr

    if sys.stdout is None:
        sys.stdout = log_file_stream  # type: ignore[assignment]
    else:
        sys.stdout = _TeeTextIO(sys.stdout, log_file_stream)  # type: ignore[assignment]

    if sys.stderr is None:
        sys.stderr = log_file_stream  # type: ignore[assignment]
    else:
        sys.stderr = _TeeTextIO(sys.stderr, log_file_stream)  # type: ignore[assignment]

    return _LogTeeHandle(
        log_file_path=selected_log_file_path,
        log_file_stream=log_file_stream,
        original_stdout=original_stdout,
        original_stderr=original_stderr,
    )


def _preload_ocr_if_needed(*, enable_ocr_preload: bool) -> None:
    if not bool(enable_ocr_preload):
        log_warn("[BOOT] 已跳过 OCR 预热（你将自行承担 PyQt6 与 OCR DLL 冲突风险）")
        return

    # 关键：必须在 PyQt6 之前导入 RapidOCR，避免 DLL 冲突（不使用异常捕获，失败应直接抛出）
    log_debug("[BOOT] 预热 OCR 引擎（必须先于 PyQt6 导入）")
    from rapidocr_onnxruntime import RapidOCR  # noqa: E402

    preload_ocr_engine = RapidOCR()  # 强制初始化 DLL
    del preload_ocr_engine
    log_debug("[OK] OCR 引擎预加载完成")


def _install_ui_freeze_watchdog(*, qapplication, workspace_root: Path) -> None:
    """启用 UI 卡死看门狗（事件循环停止 tick 后自动 dump 全线程堆栈）。"""
    from PyQt6 import QtCore  # noqa: E402

    runtime_cache_root = _get_runtime_cache_root(workspace_root)
    freeze_dump_file_path = runtime_cache_root / "ui_freeze_traceback.log"
    freeze_dump_file_path.parent.mkdir(parents=True, exist_ok=True)

    freeze_threshold_seconds = float(getattr(settings, "UI_FREEZE_WATCHDOG_SECONDS", 10.0) or 10.0)
    freeze_dump_repeat = bool(getattr(settings, "UI_FREEZE_WATCHDOG_REPEAT", True))

    freeze_dump_stream: IO[str] = open(freeze_dump_file_path, "a", encoding="utf-8", errors="replace")
    qapplication._ui_freeze_watchdog_dump_stream = freeze_dump_stream  # type: ignore[attr-defined]

    # 额外启用 faulthandler（Crash dump 也写入同一文件）；退出时会 disable 并关闭文件句柄。
    faulthandler.enable(file=freeze_dump_stream, all_threads=True)

    def arm_freeze_watchdog() -> None:
        faulthandler.cancel_dump_traceback_later()
        faulthandler.dump_traceback_later(
            timeout=float(freeze_threshold_seconds),
            repeat=bool(freeze_dump_repeat),
            file=freeze_dump_stream,
        )

    freeze_timer = QtCore.QTimer(qapplication)
    freeze_timer.setSingleShot(False)
    freeze_timer.setInterval(1000)
    freeze_timer.timeout.connect(arm_freeze_watchdog)
    freeze_timer.start()
    qapplication._ui_freeze_watchdog_timer = freeze_timer  # type: ignore[attr-defined]

    arm_freeze_watchdog()
    log_warn(
        "[WATCHDOG] UI 卡死看门狗已启用：threshold_seconds={}, repeat={}, dump_file={}",
        float(freeze_threshold_seconds),
        bool(freeze_dump_repeat),
        str(freeze_dump_file_path),
    )

    def cleanup_watchdog() -> None:
        faulthandler.cancel_dump_traceback_later()
        faulthandler.disable()
        freeze_timer.stop()
        freeze_dump_stream.flush()
        freeze_dump_stream.close()

    qapplication.aboutToQuit.connect(cleanup_watchdog)


def _install_application_state_logger(*, qapplication) -> None:
    from PyQt6 import QtCore  # noqa: E402

    def on_application_state_changed(state: QtCore.Qt.ApplicationState) -> None:
        state_name_map = {
            QtCore.Qt.ApplicationState.ApplicationActive: "ApplicationActive",
            QtCore.Qt.ApplicationState.ApplicationInactive: "ApplicationInactive",
            QtCore.Qt.ApplicationState.ApplicationHidden: "ApplicationHidden",
            QtCore.Qt.ApplicationState.ApplicationSuspended: "ApplicationSuspended",
        }
        log_debug("[APP] applicationStateChanged: {}", state_name_map.get(state, str(state)))

    qapplication.applicationStateChanged.connect(on_application_state_changed)


def _install_global_exception_hook(*, workspace_root: Path) -> None:
    from PyQt6 import QtWidgets  # noqa: E402
    from app.ui.foundation import ui_notifier  # noqa: E402

    def exception_hook(exctype, value, traceback_obj):
        # 使用原始 stdout；若不可用则回退到当前 stdout，避免类型检查器对 Optional 的报错
        output_stream = sys.__stdout__ or sys.stdout
        if output_stream is None:
            # 兜底：不做 try/except；若连 stdout 都不可用，抛错即可。
            raise RuntimeError("sys.stdout/sys.__stdout__ 均不可用，无法输出错误信息")

        output_stream.write("=" * 60 + "\n")
        output_stream.write("程序发生错误：\n")
        output_stream.write("=" * 60 + "\n")
        import traceback as traceback_module

        traceback_module.print_exception(exctype, value, traceback_obj, file=output_stream)
        output_stream.write("=" * 60 + "\n")
        output_stream.flush()

        traceback_text = "".join(traceback_module.format_exception(exctype, value, traceback_obj))
        summary = f"{exctype.__name__}: {value}"

        runtime_cache_root = _get_runtime_cache_root(workspace_root)
        runtime_cache_root.mkdir(parents=True, exist_ok=True)
        error_log_path = runtime_cache_root / "unhandled_exception.log"

        from datetime import datetime

        with open(error_log_path, "a", encoding="utf-8", errors="replace") as log_file:
            log_file.write("=" * 60 + "\n")
            log_file.write(f"timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            log_file.write(summary + "\n")
            log_file.write(traceback_text)
            log_file.write("\n" + "=" * 60 + "\n\n")

        active_window = QtWidgets.QApplication.activeWindow()
        parent_widget = active_window if isinstance(active_window, QtWidgets.QWidget) else None
        ui_notifier.notify(
            parent_widget or object(),
            f"发生未捕获异常：{summary}（详情已写入 {error_log_path}）",
            toast_type="error",
        )

        if bool(getattr(settings, "UI_UNHANDLED_EXCEPTION_DIALOG_ENABLED", False)):
            from app.ui.foundation import dialog_utils  # noqa: E402

            dialog_utils.show_error_dialog(
                parent_widget,
                "程序发生错误",
                summary,
                details=traceback_text,
                copy_text=traceback_text,
            )

    sys.excepthook = exception_hook
    log_debug("[BOOT] 全局异常钩子已安装")


def _show_safety_notice_dialog_if_needed(*, main_window, safety_notice_text: str) -> None:
    from app.ui.foundation import dialog_utils  # noqa: E402

    if bool(settings.SAFETY_NOTICE_SUPPRESSED):
        log_debug("[BOOT] 已跳过安全声明对话框（之前选择不再提醒）")
        return

    log_debug("[BOOT] 准备弹出安全声明对话框")
    suppress = dialog_utils.ask_acknowledge_or_suppress_dialog(
        main_window,
        "安全声明",
        safety_notice_text,
        acknowledge_label="我已知晓",
        suppress_label="不再提醒",
    )
    if suppress:
        settings.SAFETY_NOTICE_SUPPRESSED = True
        settings.save()
        log_debug("[BOOT] 用户选择不再提醒安全声明，已更新设置并保存")


def run_ui_app(config: UiRunConfig) -> int:
    """启动 UI 并进入 Qt 事件循环，返回退出码。"""
    log_tee_handle = _install_log_tee_if_needed(
        workspace_root=config.workspace_root,
        requested_log_file_path=config.log_file_path,
    )
    if log_tee_handle is not None:
        log_warn("[BOOT] 已启用日志落盘：{}", str(log_tee_handle.log_file_path))

    # 关键顺序：OCR -> PyQt6
    _preload_ocr_if_needed(enable_ocr_preload=config.enable_ocr_preload)

    # 可选：加载私有扩展（不入库），并执行“启动期钩子”（OCR 已预热，尚未创建 QApplication）
    ensure_private_extensions_loaded(workspace_root=config.workspace_root)
    run_bootstrap_hooks(workspace_root=config.workspace_root)

    from PyQt6 import QtWidgets  # noqa: E402
    from app.ui.foundation.theme_manager import ThemeManager  # noqa: E402
    from app.ui.main_window import APP_TITLE, MainWindowV2  # noqa: E402

    log_warn(config.safety_notice_text)

    # 启动阶段关键步骤打点，便于排查 UI 未弹出的问题
    log_debug("[BOOT] 准备创建 QApplication 实例")
    qapplication = QtWidgets.QApplication([sys.argv[0], *list(config.qt_args)])
    log_debug("[BOOT] QApplication 创建成功")

    _install_application_state_logger(qapplication=qapplication)

    if bool(config.enable_ui_freeze_watchdog):
        _install_ui_freeze_watchdog(qapplication=qapplication, workspace_root=config.workspace_root)
    else:
        log_warn("[WATCHDOG] UI 卡死看门狗已禁用")

    log_debug("[BOOT] 应用全局主题样式...")
    ThemeManager.apply_app_style(qapplication)
    log_debug("[BOOT] 主题样式应用完成")

    _install_global_exception_hook(workspace_root=config.workspace_root)

    log_debug("[BOOT] 准备创建主窗口 MainWindowV2")
    main_window = MainWindowV2(config.workspace_root)
    log_debug("[BOOT] 主窗口创建完成")
    main_window.setWindowTitle(APP_TITLE)

    # 私有扩展可在 show() 前对主窗口进行增强（添加菜单/面板/调试入口等）
    run_main_window_hooks(main_window=main_window)
    main_window.show()
    log_debug("[BOOT] 主窗口 show() 已调用")

    if bool(config.show_safety_notice_dialog):
        _show_safety_notice_dialog_if_needed(main_window=main_window, safety_notice_text=config.safety_notice_text)
    else:
        log_warn("[BOOT] 已跳过安全声明对话框（由 CLI 参数禁用）")

    log_debug("[BOOT] 进入 Qt 事件循环 app.exec()")
    exit_code = int(qapplication.exec())

    if log_tee_handle is not None:
        log_tee_handle.close()

    return exit_code


