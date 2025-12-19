## 目录用途
- 承载与“真实编辑器窗口”强相关的运行时执行器实现与适配逻辑。
- 典型职责包括：对接截图/识别/输入能力，按协议执行节点图步骤。

## 当前状态
- 主要模块：
  - `real_executor.py`：真实执行器实现，面向自动化场景下的节点图执行；启动时会自动选择 OCR 模板 profile（如 `4K-100-CN` / `4K-125-CN`），并暴露 `ocr_template_profile` 供需要固定模板的能力复用（例如字典键/值标签）。
- `RealExecutor.connect` 在计算连线端口中心时复用同一帧截图，并通过 `app.automation.editor.connection_drag.mean_abs_diff_in_region` 仅对局部区域做像素差分，减少重复的整图数组转换；端口挑选逻辑委托 `ports.port_picker`，拖拽/验证步骤统一复用 `app.automation.editor.connection_drag.perform_connection_drag`，与编辑器执行器保持一致的节奏。
- 画布平移相关逻辑复用 `app.automation.editor.view_mapping.perform_drag_with_motion_estimation()`，与 EditorExecutor 使用同一套“拖拽+相位相关”流程，减少重复实现；`ensure_visible_node` 通过 `app.automation.editor.view_alignment.run_pan_loop` 与核心执行器共享同一视口循环骨架，仅注入运行时特有的拖拽实现。
- `_drag_with_phase_correction()` 聚合画布拖拽后的相位相关与视口偏移更新，确保 `ensure_visible_node`、`pan_by_vector_pixels` 等路径共享同一执行细节与日志格式。

## 注意事项
- 这里的实现依赖 `app.automation.editor`、`app.automation.capture`、`app.automation.input`、`app.automation.vision` 等子包提供的能力。
- 新增运行时实现时，应尽量通过协议与注入回调完成扩展，而不是直接耦合到 UI 或 CLI 层。


