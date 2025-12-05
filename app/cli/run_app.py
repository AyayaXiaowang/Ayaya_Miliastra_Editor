
from __future__ import annotations

import sys
from pathlib import Path

# 确保从项目根导入
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
# 使顶层包名 `ui` 可用（UI 模块位于 `app/ui`，内部使用绝对导入 `ui.*`）
APP_DIR = WORKSPACE_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from engine.utils.logging.console_sanitizer import install_ascii_safe_print

# 安装全局 ASCII 安全打印（避免 Windows 控制台编码问题）
install_ascii_safe_print()

# 关键：必须在 PyQt6 之前导入 RapidOCR，避免 DLL 冲突（不使用异常捕获，失败应直接抛出）
from rapidocr_onnxruntime import RapidOCR
_preload_ocr = RapidOCR()  # 强制初始化 DLL
del _preload_ocr

from PyQt6 import QtWidgets  # noqa: E402  # 在 OCR 预热之后导入
from ui.main_window import MainWindowV2, APP_TITLE  # noqa: E402
from ui.foundation.theme_manager import ThemeManager  # noqa: E402
from ui.foundation import dialog_utils  # noqa: E402
from engine.configs.settings import settings  # noqa: E402
from engine.utils.logging.logger import log_info  # noqa: E402

SAFETY_NOTICE = (
    "【安全声明】小王千星工坊（Ayaya_Miliastra_Editor）仅用于离线教学、代码模拟与节点图研究。"
    "不得将任何脚本、自动化流程或鼠标指令连接至官方《原神》客户端或服务器，"
    "否则可能触发账号封禁、奖励回收等处罚。"
)


def main() -> None:
    workspace = WORKSPACE_ROOT
    # 在应用创建前尽早加载用户设置，确保主题模式等开关在启动阶段生效
    settings.set_config_path(workspace)
    settings.load()
    # GUI/CLI 入口统一在启动阶段打开信息级日志，确保控制台可见关键进度
    settings.NODE_IMPL_LOG_VERBOSE = True

    # 显示 OCR 引擎预加载结果（已在文件顶部完成）
    log_info("[OK] OCR 引擎预加载完成")
    log_info(SAFETY_NOTICE)

    # 启动阶段关键步骤打点，便于排查 UI 未弹出的问题
    log_info("[BOOT] 准备创建 QApplication 实例")
    app = QtWidgets.QApplication(sys.argv)
    log_info("[BOOT] QApplication 创建成功")

    log_info("[BOOT] 应用全局主题样式...")
    ThemeManager.apply_app_style(app)
    log_info("[BOOT] 主题样式应用完成")

    def exception_hook(exctype, value, traceback_obj):
        # 使用原始 stdout；若不可用则回退到当前 stdout，避免类型检查器对 Optional 的报错
        output_stream = sys.__stdout__ or sys.stdout
        output_stream.write("=" * 60 + "\n")
        output_stream.write("程序发生错误：\n")
        output_stream.write("=" * 60 + "\n")
        import traceback as _traceback
        _traceback.print_exception(exctype, value, traceback_obj, file=output_stream)
        output_stream.write("=" * 60 + "\n")
        output_stream.flush()

    sys.excepthook = exception_hook
    log_info("[BOOT] 全局异常钩子已安装")

    log_info("[BOOT] 准备创建主窗口 MainWindowV2")
    win = MainWindowV2(workspace)
    log_info("[BOOT] 主窗口创建完成")
    win.setWindowTitle(APP_TITLE)
    win.show()
    log_info("[BOOT] 主窗口 show() 已调用")

    if not settings.SAFETY_NOTICE_SUPPRESSED:
        log_info("[BOOT] 准备弹出安全声明对话框")
        suppress = dialog_utils.ask_acknowledge_or_suppress_dialog(
            win,
            "安全声明",
            SAFETY_NOTICE,
            acknowledge_label="我已知晓",
            suppress_label="不再提醒",
        )
        if suppress:
            settings.SAFETY_NOTICE_SUPPRESSED = True
            settings.save()
            log_info("[BOOT] 用户选择不再提醒安全声明，已更新设置并保存")
    else:
        log_info("[BOOT] 已跳过安全声明对话框（之前选择不再提醒）")

    log_info("[BOOT] 进入 Qt 事件循环 app.exec()")
    sys.exit(app.exec())


if __name__ == '__main__':
    main()


