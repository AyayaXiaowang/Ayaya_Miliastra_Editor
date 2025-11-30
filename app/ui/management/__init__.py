"""管理模式相关通用工具与注册表入口。

当前主要职责：
- 提供管理 Section 元数据注册表（见 `section_registry`），供管理配置库与其他视图复用。

配置页面基类（`BaseConfigPage` / `StandardTablePage` / `FormTablePage` / `DualPaneConfigPage`
等）已被管理库 Section 与表单对话框工具取代，管理模式入口统一使用
`ui.graph.library_pages.management_library_widget` + `BaseManagementSection` 体系，表单类
对话框统一复用 `FormDialog` 与 `ui.forms.schema_dialog.FormDialogBuilder` 等辅助工具。
"""

__all__: list[str] = []

