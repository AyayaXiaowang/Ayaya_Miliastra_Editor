# 目录用途
启动装配（bootstrap）管线：承载 UI 启动阶段的“顺序约束 + 基础设施装配 + 资源生命周期管理”，让 `app/cli` 的入口脚本保持薄而稳定。

# 公共 API
- `app.bootstrap.ui_bootstrap.run_ui_app(...)`：UI 启动装配与事件循环入口（供 `app.cli.run_app` 调用）。

# 依赖边界
- 允许依赖：`engine/*`、`app.ui/*`
- 禁止依赖：任何内部开发工具链；禁止在模块顶层导入 `PyQt6`/OCR 等重型依赖（必须延迟导入以满足顺序约束）

# 当前状态
- `ui_bootstrap.py`：封装“日志 tee（可选）→ OCR 预热（必须先于 PyQt6）→（可选）私有扩展加载/启动钩子 → QApplication → 主题 → 异常钩子 → UI 卡死看门狗（可选）→ 主窗口（show 前私有主窗口钩子）→ 安全声明弹窗（可选）→ app.exec()”，并在退出时做资源清理（定时器/文件句柄/faulthandler）。
  - 启动期日志默认以摘要为主：高频状态变化（如 applicationStateChanged、QApp/主题/窗口装配阶段细节）降为 `log_debug`，避免每次启动刷屏；仅在需要排查启动卡点或焦点切换问题时开启 `settings.DEBUG_LOG_VERBOSE` 查看细节。

# 注意事项
- **顺序约束**：`rapidocr_onnxruntime` 必须在 `PyQt6` 之前导入，否则可能触发 DLL 冲突。
- **错误策略**：不使用 try/except 吞错；未捕获异常由 `sys.excepthook` 统一记录到控制台与运行时缓存（`unhandled_exception.log`），默认不弹阻塞错误对话框；如需恢复弹窗，可通过 `settings.UI_UNHANDLED_EXCEPTION_DIALOG_ENABLED` 启用。
- **保持入口薄**：CLI 参数解析留在 `app/cli`，启动装配细节留在本目录，避免 `run_app.py` 膨胀为巨函数。


