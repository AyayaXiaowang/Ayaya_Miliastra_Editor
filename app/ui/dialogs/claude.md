## 目录用途
`app/ui/dialogs/` 存放各类对话框组件与可复用的“对话框/面板内嵌编辑器”，用于设置编辑、信息查看与用户确认等交互。

## 当前状态
- **通用对话框基类**：大多数对话框继承 `BaseDialog` / `FormDialog`，统一标题/按钮区与主题样式，业务对话框只负责组装表单/表格并导出结果。
- **全局设置**：`settings_dialog.py` 负责展示并写回 `engine.configs.settings.settings` 的全局开关；确认后会同步视图缩放提示，确保 LOD/叠层按当前倍率立即生效；对影响 GraphScene/图元结构的开关（如 YDebug/basic blocks/虚拟化/fast preview）会触发一次显示层重建，使变更无需重开图即可生效；不再强制覆盖 `PRIVATE_EXTENSION_ENABLED`（私有扩展开关），避免用户无法关闭私有扩展（资源库自动刷新仍强制启用）。
- **性能与调试**：`performance_monitor_dialog.py` 展示全局性能监控报告（卡顿事件/耗时段），支持复制与清空记录。
- **类型系统编辑器**：信号/结构体等编辑对话框与内嵌 widget 提供表格/表单式编辑与只读浏览能力，复用通用表格骨架与主题 token。
- **本地测试**：`local_graph_sim_dialog.py` 提供 Local Graph Sim 对话框入口（系统浏览器预览）；server 在独立子进程中通过 `app.cli.local_graph_sim serve --ready-file` 启动，UI 仅负责参数收集/启动与生命周期管理，避免在主进程执行节点图源码。

## 注意事项
- 对话框应保持“UI 组装 + 结果导出”的薄层职责；复杂流程与写盘应下沉到 controller/service 或 `app.runtime.services`。
- 样式/颜色优先复用 `ThemeManager` token 与通用骨架，避免在对话框内散落硬编码 QSS。
- UI 层不使用 `try/except` 吞错；错误直接抛出，由上层统一处理。

