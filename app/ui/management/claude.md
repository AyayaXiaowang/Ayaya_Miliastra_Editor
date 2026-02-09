## 目录用途
管理模式下与“管理配置”相关的通用基类与注册表，供管理库页面、右侧编辑 Panel 以及各类工具脚本复用。

## 当前状态
- 管理配置数据统一依赖 `engine.resources` 提供的 `PackageView/GlobalResourceView` 与 `ResourceManager` 访问资源库的管理配置目录（共享根 + 当前项目存档根：`assets/资源库/共享/管理配置/**` + `assets/资源库/项目存档/<package_id>/管理配置/**`）；项目存档仅通过 `PackageIndex.resources.management[...]` 中的 ID 列表引用这些资源 ID，作为“索引/标签”，实际编辑的总是 `*.management.*` 这一层的视图模型。
- 管理模式下的 UI 入口与列表行为由 `app.ui.graph.library_pages.management_library_widget.ManagementLibraryWidget` 与各 `management_section_*.py` Section 实现负责，本目录中的 `BaseConfigPage/StandardTablePage/FormTablePage/DualPaneConfigPage` 属于旧版页面骨架，目前仅保留给少量遗留管理对话框、工具页或代码示例参考，新增管理页面应直接使用管理库 Section 与推荐对话框基类。

## 当前结构
- `section_registry.py`：集中声明每个管理 section 的 key/title/group/group_title 以及资源 key 与聚合模式：
  - `ManagementSectionSpec`：描述管理类型的元数据（如 `"timer"`、`"variable"`、`"main_cameras"`），`MANAGEMENT_SECTIONS` 作为唯一来源供管理库页面与存档库等视图复用。
  - `ManagementResourceSpec`：描述 **PackageIndex.resources.management 的资源桶（binding_key）** 的元数据（标题/ResourceType/聚合模式），并通过 `MANAGEMENT_RESOURCES` 提供 **稳定且不冲突** 的：
    - `MANAGEMENT_RESOURCE_ORDER`（资源桶顺序）
    - `MANAGEMENT_RESOURCE_TITLES`（资源桶标题）
    - `MANAGEMENT_RESOURCE_BINDINGS`（资源桶 → ResourceType）
    - `MANAGEMENT_RESOURCE_AGGREGATION_MODES`（资源桶 → 聚合计数规则）
  - `MANAGEMENT_RESOURCE_DEFAULT_SECTION_KEYS`：资源桶 key → 管理页面默认 section_key 的映射，用于“项目存档页”双击跳转（解决 `timers → timer` 等不一致）。
  - `MANAGEMENT_RESOURCE_TITLES`：将资源 key（如 `background_music` / `level_settings` / `peripheral_systems`）映射为人类可读的管理标题，确保不同视图中展示一致的中文名称。
  - `MANAGEMENT_RESOURCE_AGGREGATION_MODES`：为每个管理资源声明在聚合视图中的展示/计数模式（按资源 ID 逐条列出、基于信号条目展开、按非空配置体汇总或按外围系统条目汇总），供存档库等页面按统一约定构建“管理配置”树。
  - UI 工作流不再以“管理配置资源”方式维护：HTML 为真源，派生物进入运行时缓存；因此管理库不再提供 `UI页面/UI布局/UI控件模板` 等入口。
- 旧版配置页面基类（`BaseConfigPage` / `StandardTablePage` / `FormTablePage` / `DualPaneConfigPage` 等）已下线：
  - 管理模式的主入口统一迁移到 `app.ui.graph.library_pages.management_library_widget.ManagementLibraryWidget` 与各 `BaseManagementSection`；
  - 右侧属性与专用编辑面板由 `app.ui.panels` 中的 Panel 组件承担；
  - 表单类编辑弹窗统一使用 `app.ui.foundation.base_widgets.FormDialog` 与 `app.ui.forms.schema_dialog.FormDialogBuilder` 等辅助工具按需组装字段，不再通过本目录提供页面骨架。

## 与主窗口的协作
- 管理模式下主窗口使用 `ManagementLibraryWidget` 作为列表式入口页面：左侧选择管理类型（如计时器、变量、预设点、主镜头等），右侧展示当前类型下的条目列表。
- 主窗口通过 `PackageEventsMixin._on_management_selection_changed` 监听列表选中变化，根据当前 section key 决定右侧展示通用属性面板还是专用编辑 Panel（信号、结构体、主镜头等）。
- 各 `management_section_*.py` 负责实现 `iter_rows/create_item/edit_item/delete_item` 等操作，完成具体的增删改逻辑；操作完成后通过 `data_changed` 信号驱动持久化与其它视图刷新。

## 注意事项
- 新增管理类型时：
  - 在 `section_registry.MANAGEMENT_SECTIONS` 中添加一项，声明标题、分组、资源绑定与聚合模式。装备数据已拆分为三个 Section（`equipment_entries` / `equipment_tags` / `equipment_types`），共享底层 `equipment_data` 资源。
  - 在 `app.ui.graph.library_pages.management_sections.py` 中实现对应的 Section（继承 `BaseManagementSection`），实现 `iter_rows/create_item/edit_item/delete_item` 等接口。
  - 如需右侧专用编辑面板，则在 `app.ui.panels` 下新增 Panel，并在主窗口的 `PackageEventsMixin` / `ModeSwitchMixin` 中按 `section_key` 接入更新逻辑与标签页显隐控制。
  - 若该类型会出现在“项目存档页 → 管理配置”中，务必同时补齐：
    - `section_registry.MANAGEMENT_RESOURCES`：保证资源桶标题/顺序稳定；
    - `section_registry.MANAGEMENT_RESOURCE_DEFAULT_SECTION_KEYS`：保证双击跳转能从资源桶正确映射到管理页面 section（尤其是 `timers/level_variables/...` 这类桶 key 与 section_key 不同的类型）。
- 使用本目录中的表格/表单基类时（主要面向遗留/特殊场景），应优先复用 `ThemeManager` 提供的样式与 `FormDialogBuilder` 的表单布局，避免分散的硬编码 QSS。
- 所有配置编辑错误应通过统一的对话框提示用户，不在此处吞掉异常；遵循项目“不使用 try/except 静默忽略错误”的约定。


