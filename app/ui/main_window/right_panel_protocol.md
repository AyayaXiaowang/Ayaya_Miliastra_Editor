# 右侧面板状态机与协议

## 目标
- 给出集中、可查的右侧面板管理规则，避免规则分散在各类回调里导致“切页但标签未收起或未刷新”的隐性问题。
- 明确每种视图模式下允许出现的标签、驱动这些标签的信号来源，以及离开模式时的回收策略，便于扩展和排查。

## 职责分工
- `ModeTransitionService`：封装模式切换公共步骤（保存/切堆栈/左右比例调整/会话快照），并将“进入某模式后的副作用”委托给 `ui/main_window/mode_presenters/`；右侧标签的挂载/移除统一委托给 `RightPanelRegistry`（`ui/main_window/right_panel_registry.py`），最后执行 `_enforce_right_panel_contract` / `_switch_to_first_visible_tab` / `_update_right_panel_visibility` 做收敛。`ModeSwitchMixin._on_mode_changed` 仅作为 UI 信号入口调用该服务。
- `PackageEventsMixin`：处理模板/实例/关卡、战斗预设、存档库与管理配置的选中事件。所有选中回调都会先判断当前 `ViewMode`，在空 ID 或模式不匹配时清空面板并移除对应标签；在存档库模式下使用 `_hide_packages_basic_property_panel` / `_hide_packages_management_property_panel` 防止两套属性页同时存在。
- `TodoEventsMixin`：在 `ViewMode.TODO` 下根据任务类型切换右侧行为：模板/实例类步骤以只读方式挂载 `property` 标签；节点图相关步骤通过 `_update_execution_monitor_tab_for_todo` 按需插入/移除 `execution_monitor`。
- `RightPanelAssemblyFeature`：负责右侧面板的“创建/信号连线/注册矩阵”装配，并在主窗口挂载 `right_panel_policy` 用于集中处理“section/mode → tabs 显隐”。
- `WindowAndNavigationEventsMixin`：`_on_management_section_changed` 只负责把 section_key 记录到 `view_state` 并委托 `right_panel_policy.apply_management_section(...)`；`_navigate_to_mode` 触发统一的模式切换入口；会话恢复时复用相同入口保证右侧状态与导航一致。

## 模式与标签矩阵（允许的右侧标签与上下文来源）
- `TEMPLATE`：仅 `property`（可编辑）。来源 `_on_template_selected`；空选中清空并移除标签。
- `PLACEMENT`：仅 `property`（实例/关卡）。来源 `_on_instance_selected` / `_on_level_entity_selected`；空选中清空并移除标签。
- `COMBAT`：默认无基础属性。`player_editor` / `player_class_editor` / `skill_editor` / `item_editor` 由 `_on_player_template_selected` 等在有有效上下文时通过 `right_panel_policy.set_combat_detail_tabs_visible(...)` 挂载，空选中时通过 `right_panel_policy.reset_combat_detail_tabs()` 清空并移除。
- `MANAGEMENT`：默认不显示基础属性。`management_property` 由列表选中驱动；`ui_settings`/`signal_editor`/`struct_editor`/`main_camera_editor`/`peripheral_system_editor`/`equipment_*` 等专用面板由 `right_panel_policy.apply_management_section(section_key)` 根据 section key 决定，离开模式由 `RightPanelRegistry.enforce_contract` 统一回收。
- `GRAPH_LIBRARY`：只保留 `graph_property`，进入模式时同步当前选中图或默认选中首个；其它标签移除。
- `GRAPH_EDITOR`：`graph_property` 绑定当前图；复合相关标签移除；Todo 执行按钮可见性由 `_update_graph_editor_todo_button_visibility` 控制。
- `COMPOSITE`：`composite_property` + `composite_pins`；图/基础属性移除，进入时载入当前复合节点。
- `TODO`：默认无额外标签；模板/实例任务以只读方式挂载 `property`；节点图任务按需挂载 `execution_monitor`。
- `VALIDATION`：右侧标签全部移除，随后触发 `_trigger_validation`。
- `PACKAGES`：切入时收起所有标签。点击资源后按类型挂载：模板/实例/关卡 → `property`（可编辑）；节点图 → `graph_property`（只读属性+归属）；管理配置 → `management_property`（只读摘要+归属多选）；战斗预设条目 → 对应战斗面板。切换资源类别前先调用 `_hide_packages_basic_property_panel` 或 `_hide_packages_management_property_panel` 防止混用。

## 触发顺序与约束
- 模式切换顺序：保存当前复合节点/图 → 切换中央堆栈 → `mode_presenter_coordinator.enter_mode(...)` 执行模式副作用（刷新/懒加载/同步上下文）→ `RightPanelRegistry.apply_for_mode(view_mode)` 按 `RIGHT_PANEL_TABS` 挂载/移除静态标签并回收越权动态标签 →（可选）切换到处理器返回的首选右侧标签 → `_enforce_right_panel_contract` → `_switch_to_first_visible_tab` → `_update_right_panel_visibility` → 刷新保存状态与会话快照。
- 选中回调必须先校验当前 `ViewMode`，空 ID 或模式不匹配时清空面板并 `_ensure_*_tab_visible(False)`；只在所属模式下才刷新数据，避免后台刷新抢占右侧上下文。
- 新增标签时优先新增/扩展 `RightPanelAssemblyFeature`（注册矩阵）与 `RightPanelPolicy`（联动策略）；静态标签仍需更新 `RIGHT_PANEL_TABS`。避免回到“mixin 里散落 _ensure_* 分支”的旧模式。
- 调试建议：观察 `[MODE-STATE]` 日志与 `side_tab.tabText(*)`，对照矩阵核验当前模式允许的标签；确认选中信号发出时的 `ViewMode`；在存档库/管理/战斗间切换时留意是否调用了对应的收起函数与 `_update_right_panel_visibility()`。

