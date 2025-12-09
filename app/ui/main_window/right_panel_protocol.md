# 右侧面板状态机与协议

## 目标
- 给出集中、可查的右侧面板管理规则，避免规则分散在各类回调里导致“切页但标签未收起或未刷新”的隐性问题。
- 明确每种视图模式下允许出现的标签、驱动这些标签的信号来源，以及离开模式时的回收策略，便于扩展和排查。

## 职责分工
- `ModeSwitchMixin`：`_on_mode_changed` 负责模式切换、左右布局比例调整，并调用 `_apply_right_tabs_for_mode` 依据 `RIGHT_PANEL_TABS` 统一挂载/移除静态标签；通过 `_is_dynamic_tab_allowed_in_mode` 回收不属于当前模式的动态标签；管理 `ui_control_settings` 在管理模式下的挂载；最后调用 `_switch_to_first_visible_tab` 与 `_update_right_panel_visibility`。
- `PackageEventsMixin`：处理模板/实例/关卡、战斗预设、存档库与管理配置的选中事件。所有选中回调都会先判断当前 `ViewMode`，在空 ID 或模式不匹配时清空面板并移除对应标签；在存档库模式下使用 `_hide_packages_basic_property_panel` / `_hide_packages_management_property_panel` 防止两套属性页同时存在。
- `TodoEventsMixin`：在 `ViewMode.TODO` 下根据任务类型切换右侧行为：模板/实例类步骤以只读方式挂载 `property` 标签；节点图相关步骤通过 `_update_execution_monitor_tab_for_todo` 按需插入/移除 `execution_monitor`。
- `WindowAndNavigationEventsMixin`：`_on_management_section_changed` 根据 section 切换管理专用标签；`_navigate_to_mode` 触发统一的模式切换入口；会话恢复时复用相同入口保证右侧状态与导航一致。

## 模式与标签矩阵（允许的右侧标签与上下文来源）
- `TEMPLATE`：仅 `property`（可编辑）。来源 `_on_template_selected`；空选中清空并移除标签。
- `PLACEMENT`：仅 `property`（实例/关卡）。来源 `_on_instance_selected` / `_on_level_entity_selected`；空选中清空并移除标签。
- `COMBAT`：默认无基础属性。`player_editor` / `player_class_editor` / `skill_editor` / `item_editor` 由 `_on_player_template_selected` 等在有有效上下文时挂载，空 ID 时清空并移除；切回模式时通过 `CombatPresetsWidget.get_current_selection()` 重新同步。
- `MANAGEMENT`：默认不显示基础属性。`management_property` 由列表选中驱动；`ui_control_settings` 仅在 section `ui_control_groups` 时挂载；`signal`/`struct`/`main_camera`/`peripheral_system`/`equipment_*` 等专用面板由 `_ensure_*_editor_tab_for_management` 依据 section key 决定，离开模式统一收起。
- `GRAPH_LIBRARY`：只保留 `graph_property`，进入模式时同步当前选中图或默认选中首个；其它标签移除。
- `GRAPH_EDITOR`：`graph_property` 绑定当前图；复合相关标签移除；Todo 执行按钮可见性由 `_update_graph_editor_todo_button_visibility` 控制。
- `COMPOSITE`：`composite_property` + `composite_pins`；图/基础属性移除，进入时载入当前复合节点。
- `TODO`：默认无额外标签；模板/实例任务以只读方式挂载 `property`；节点图任务按需挂载 `execution_monitor`。
- `VALIDATION`：右侧标签全部移除，随后触发 `_trigger_validation`。
- `PACKAGES`：切入时收起所有标签。点击资源后按类型挂载：模板/实例/关卡 → `property`（可编辑）；节点图 → `graph_property`（只读属性+归属）；管理配置 → `management_property`（只读摘要+归属多选）；战斗预设条目 → 对应战斗面板。切换资源类别前先调用 `_hide_packages_basic_property_panel` 或 `_hide_packages_management_property_panel` 防止混用。

## 触发顺序与约束
- 模式切换顺序：保存当前复合节点/图 → 切换中央堆栈 → 按模式块清理/刷新 → `_apply_right_tabs_for_mode` 挂载静态标签并回收非法动态标签 → 如需根据左侧列表同步右侧详情（战斗预设、管理）则立即调用对应选中处理 → `_switch_to_first_visible_tab` → `_update_right_panel_visibility` → 刷新保存状态与会话快照。
- 选中回调必须先校验当前 `ViewMode`，空 ID 或模式不匹配时清空面板并 `_ensure_*_tab_visible(False)`；只在所属模式下才刷新数据，避免后台刷新抢占右侧上下文。
- 新增标签时务必同时更新：`RIGHT_PANEL_TABS`、`_is_dynamic_tab_allowed_in_mode`、所属回调的 `_ensure_*_tab_visible` 逻辑，以及必要的模式切换同步（如战斗预设的 `get_current_selection` 段）。
- 调试建议：观察 `[MODE-STATE]` 日志与 `side_tab.tabText(*)`，对照矩阵核验当前模式允许的标签；确认选中信号发出时的 `ViewMode`；在存档库/管理/战斗间切换时留意是否调用了对应的收起函数与 `_update_right_panel_visibility()`。

