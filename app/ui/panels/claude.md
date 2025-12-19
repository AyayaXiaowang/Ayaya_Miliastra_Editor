## 目录用途
- 存放主窗口右侧各类属性编辑面板（模板/实例、战斗预设、管理配置、UI 控件组与 Widget 配置等），统一复用 `PanelScaffold` 与主题 token，只负责 UI 装配与资源字段读写。

## 当前状态
- 面板按领域拆分：模板/实例面板、战斗预设面板（玩家模板/职业/技能/道具）、管理配置面板（Signal/Struct/Equipment/MainCamera/PeripheralSystem 等）、UI 控件组与 `widget_configs/` 子包等；子包 `template_instance/` 与 `widget_configs/` 已分模块维护。
- 外围系统管理面板已按 Tab 拆分到 `peripheral_system/` 子包：主面板负责上下文/所属存档行与信号编排，三个 Tab 组件负责表单装配与字段读写。
- 资源的单一真相源由 `ResourceManager` 维护，面板通过视图模型和控制器写回索引/资源文件；全局视图、存档视图与未分类视图共享同一底层对象。
- 图数据加载与缓存已收敛到无 Qt 依赖的 `app.runtime.services.graph_data_service.GraphDataService`：面板与异步加载器应直接依赖 runtime service，避免各自维护图数据与 GraphModel 缓存。
- `validation_panel.py` 已支持“双来源校验结果”展示：存档综合校验 + 节点图源码校验（含复合节点结构校验开关），并通过 `issue.detail` 与 `NavigationCoordinator` 支持双击跳转到图/节点/连线/复合节点/管理配置来源。
- 公共骨架与注入逻辑集中在 `PanelScaffold`、`panel_search_support`、`package_membership_selector` 等模块，现有面板均已拆分 Tab/Mixin 降低单文件复杂度。
- 战斗预设面板（职业/技能/道具）已将“编辑表单 UI + 写回逻辑”拆分到独立 widget（例如 `combat_skill_edit_widget.py`、`combat_item_edit_widget.py`、`combat_class_edit_widgets.py`），面板类仅负责上下文注入、状态徽章与信号转发；重复的 editor 分组结构抽到 `combat_preset_editor_structs.py`。
- `combat_player_panel_sections.py` 已按职责拆分为多个小模块（`combat_player_panel_sections_app.ui.py` / `*_graphs.py` / `*_ingame_save.py` / `*_custom_variables.py` / `*_player_fields.py` / `*_role_fields.py` / `*_types.py`），入口文件仅负责对外导出与类型提示，便于维护与定位。
  - 其中“复苏”分组已开始采用 `ui/forms/schema_bound_form.SchemaBoundForm` 进行 schema 驱动的字段绑定：UI 构建侧不再手写各字段控件创建/信号写回，字段加载侧通过 `load_from_model()` 统一刷新，便于后续继续按分组迁移并降低维护成本。
- `panel_scaffold` 提供 `build_scrollable_column` 统一构建顶对齐的滚动列容器，避免右侧表单内容在可用高度内居中分散。
- 通用的 dict/list 段落初始化辅助收敛到 `panel_dict_utils.py`（如 `ensure_dict_field` / `ensure_list_field`），用于减少面板内反复出现的 metadata 纠偏样板代码。
- 推荐优先使用 `panel_dict_utils.ensure_nested_dict/ensure_nested_list` 处理多级嵌套段落初始化，避免在面板内手写“逐级判断类型并写回默认 dict/list”的样板逻辑。
- 装备词条面板的“选择属性”使用不可编辑下拉框：预置常用属性项（生命值/攻击力/防御力修正与调整率、各元素抗性与增伤调整率、暴击相关、恢复效果等），默认有“请选择属性”占位，若加载到列表外的旧值会临时加入下拉供选择与保存。
- 战斗预设玩家模板面板通过 `app.runtime.services.json_cache_service.JsonCacheService` 在 `app/runtime/cache/player_ingame_save_selection.json` 记忆最近的局内存档模板选择（按玩家模板 ID 作为 KV key 存储），优先读取模板 metadata，确保下次打开"自定义变量_局内存档变量"时沿用上次选择；右侧局内存档变量表格基于局内存档管理模板 `entries` 中的 `struct_id` 与 `max_length` 为每个 `1_chip_*` 槽位展示结构体名称与最大条目数，模板概要区域仅保留“当前模板 + 映射数量”等整体说明，具体的“最大条目数”信息以列表形式直接在表格列中呈现，便于按行对照。
- 玩家模板自定义变量匹配逻辑（`_get_external_player_level_variable_payloads`）：优先按 `variable_file_id`（即变量文件的 `VARIABLE_FILE_ID` 常量）匹配，兼容按完整路径或文件名（`source_stem`）匹配。
- 玩家模板自定义变量表格中的只读结构体字段会显示"查看"按钮，点击后通过 `_on_struct_view_requested` 弹出 `StructViewerDialog` 以只读模式展示结构体定义详情。
- 界面控件组相关面板（布局、模板库等）中的新增/编辑对话框统一复用 `BaseDialog`/`FormDialog` 及主题样式，通过表单布局收集输入字段。

## 注意事项
- 编辑流程通过控制器或 helper 协调，涉及包索引/所属存档的操作统一委托 `PackageController`/`PackageIndexManager`，不要在面板内手写业务流或直接操作文件。
- 遵循 UI 目录约定：不使用 `try/except` 吞错，异常直接抛出；主题/尺寸统一使用 `ThemeManager` 与 token，避免散落的硬编码 QSS 或颜色。
- 字体：避免硬编码字体族名（如 `Microsoft YaHei UI`），需要显式设置字体时统一使用 `app.ui.foundation.fonts`；多数场景直接依赖应用级默认字体即可。
- 面板如需写入运行期缓存或 UI 记忆类状态，统一通过 `app.runtime.services.*`（例如 `JsonCacheService`）完成；不要在面板内自行拼 `app/runtime/cache` 路径或手写 JSON 读写逻辑。
- 面板需要文本/枚举/整数输入弹窗时，统一从 `app.ui.foundation` 顶层导入 `prompt_text/prompt_item/prompt_int`（实现位于 `ui/foundation/input_dialogs.py`）；`dialog_utils.py` 仅用于消息框类提示。
- 组件仅操作传入的资源实例，不复制或缓存独立副本，确保多视图下编辑同一资源时状态一致。
- 布局保持向上对齐：滚动容器内的表单/编辑器在内部布局添加补充伸缩或 alignment，避免内容在可用高度内居中分散。
- 布局面板中的“添加界面控件”对话框继承 `BaseDialog`，复用统一的主题样式与按钮。
- 左侧搜索输入（`panel_search_support.SidebarSearchController`）统一套用 ThemeManager 的输入样式，保证在未显式套用 Panel 样式的父容器中也维持主题一致的输入外观。
