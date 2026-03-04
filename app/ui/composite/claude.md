## 目录用途
`ui/composite/` 收纳复合节点领域的 UI：复合节点库浏览/预览、右侧属性面板与虚拟引脚面板等组件。

## 当前状态
- **管理器入口**：`CompositeNodeManagerWidget` 是复合节点库页面主体，包含“浏览页/预览页”两种视图。
- **数据与编排**：`composite_node_manager_service.py` 提供无 Qt 的 `CompositeNodeService`（行数据、加载/保存编排、CRUD）。
- **UI 拆分**：管理器按 mixin 拆分工具栏/搜索、目录树与列表、选中与预览加载、右键菜单与库结构操作、保存与脏改动确认等职责。
- **浏览视图**：左侧目录树 + 中间列表，显式区分“当前项目/共享”，并对共享条目做可视化标记，避免归属误判。
- **预览视图**：复用 `GraphView` 子图预览；通过 `GraphEditorController.load_graph_for_composite` 加载，并注入 `composite_edit_context`（含 `can_persist`）控制“只读预览/可落盘编辑”语义。
- **所属存档切换**：属性面板通过 `PackageMembershipSelector` + `PackageIndexManager.move_resource_to_root(...)` 在“共享/项目存档”之间移动复合节点文件。
- **磁盘刷新**：支持 `reload_library_from_disk()` 重新扫描复合节点源码，并通知上层刷新 NodeRegistry，保证列表与预览一致。
- **路径口径**：folder_path 分隔符归一化统一复用 `engine.utils.path_utils.normalize_slash`。

## 注意事项
- 仅承载复合节点领域组件；通用控件/样式应放在 `ui/foundation/`，普通节点图能力放在 `ui/graph/`。
- 需要资源与控制器时通过依赖注入获取，避免在本目录创建全局单例。
- UI 层不使用 `try/except` 吞错；确认/提示类弹窗统一走 `app.ui.foundation.dialog_utils`。
- 颜色/字体/样式优先使用 `ThemeManager` token 与 `app.ui.foundation.fonts`，避免在本目录散落硬编码十六进制色值与平台字体名。
