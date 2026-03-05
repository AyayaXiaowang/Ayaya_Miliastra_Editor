## 目录用途
`ui/panels/template_instance/` 收纳元件模板/实体摆放/关卡实体的属性面板子标签页（tabs）。每个 tab 独立维护 UI 与数据交互逻辑，`TemplateInstancePanel` 负责装配、上下文注入与信号协调。

## 当前状态
- **通用属性**：`basic_info_tab.py` 作为 Common Inspector，展示/编辑基础字段与 `metadata.common_inspector` 下的通用模块；支持装饰物列表编辑，并提供“打散为元件”快捷动作（将 `decorations` 拆分为多个独立元件模板写入 `元件库/`）；折叠状态通过 `JsonCacheService` 记忆。
- **图与变量覆写**：`graphs_tab.py` 管理挂载节点图与“暴露变量覆盖”；资源读写委托 `TemplateInstanceService`，图数据加载复用 `GraphDataService/GraphAsyncLoader`，并通过 `GraphSelectionDialog` 选图。
- **变量标签页**：`variables_tab.py` 只做“关卡变量定义预览 + 实例覆写值编辑”；外部引用解析集中在 `variables_external_loader.py`，复杂值编辑复用 `struct_list_editor_widget.py` / `variables_table_widget.py`。
- **组件标签页**：`components_tab.py` 提供 Inspector 风格组件卡片列表与 `ComponentPickerDialog`；允许组件集合由 `engine.configs.rules.get_entity_allowed_components()` 推导；表单实现由 `component_form_factory.py` 路由并通过 `on_settings_changed` 上抛保存请求。
- **战斗标签页**：`combat_tab.py` 管理战斗相关字段（写入 `entity_config["battle"]`）。
- **通用基类/控件**：`tab_base.py` 提供 `TemplateInstanceTabBase`（上下文注入、工具栏、集合聚合、只读切换）；`vector3_editor.py` 提供可复用三维向量编辑控件。

## 注意事项
- 所有 tab 必须通过 `set_context()` 接收 `current_object/object_type/package`，不要直接依赖面板内部字段或全局单例。
- 需要写盘/校验/确认提示时，统一走服务层与 `app.ui.foundation.dialog_utils` / `prompt_*`；主题色与提示文案统一使用 `ThemeManager` token。
- 变量“定义”不在此处编辑：定义在 `管理配置/关卡变量` 的 Python 文件中维护；本目录只处理预览与覆写值。

