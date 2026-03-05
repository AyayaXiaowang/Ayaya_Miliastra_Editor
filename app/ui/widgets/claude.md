## 目录用途
`app/ui/widgets/`：应用层通用/半通用控件集合，主要服务于节点图画布与管理面板：画布行内常量编辑器、图变量/信号等表格控件，以及命令面板/快捷键相关对话框。

## 当前状态
- **常量编辑器门面**：`constant_editors.py` 作为稳定导入入口，内部拆分 text/bool/vector3 与 factory/display/helpers；与 `GraphPalette` / `graph_component_styles` 协作，支持行内控件虚拟化（按需创建/释放）。
- **表格类控件**：提供 CRUD 表格骨架、两行结构字段表格（click-to-edit、列表/字典子表格）、图变量表格与引用列表等；样式统一复用 `ThemeManager.table_style()`。
- **全局命令/快捷键**：提供 `CommandPaletteDialog`、快捷键帮助与快捷键设置等基础组件；用户配置落盘到 runtime cache 并即时生效。

## 注意事项
- 需要显式字体时统一用 `app.ui.foundation.fonts`；主题与颜色走 `ThemeManager`/token，避免散落硬编码。
- 控件不直接写盘：持久化/缓存通过控制器或 `app.runtime.services.*`（例如 `JsonCacheService`）。
- 避免循环导入与 Qt 生命周期坑：类型标注用 `TYPE_CHECKING`，与 `GraphScene/NodeGraphicsItem` 的交互尽量走公开接口；不使用 try/except 吞错。
