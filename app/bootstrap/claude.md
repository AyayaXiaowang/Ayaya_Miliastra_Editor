## 目录用途
UI 启动装配（bootstrap）管线：集中管理启动阶段的顺序约束、基础设施装配与退出清理，使 `app/cli` 入口保持薄而稳定。

## 当前状态
- `app.bootstrap.ui_bootstrap.run_ui_app(...)` 作为 UI 启动主入口：负责 OCR 预热顺序、`QApplication`/主题、全局异常钩子、可选卡死看门狗、主窗口展示与安全声明提示等。
- 主窗口置前：启动时优先使用 Qt 的 `raise_/activateWindow` 与 Windows 原生 `SetForegroundWindow`；仅在失败时用 `SetWindowPos` 做一次性“置顶→恢复”，避免通过 `setWindowFlag + show()` 触发窗口重建导致的闪烁。

## 注意事项
- 若启用 OCR 且环境存在 `rapidocr_onnxruntime`，必须在导入 `PyQt6` 前完成预加载，避免 DLL 冲突。
- 本目录避免在模块顶层导入 PyQt6/OCR 等重依赖，保持惰性导入与可复用性。
- 不使用 try/except 吞错：启动/装配错误应直接抛出，由统一异常钩子记录与提示。

