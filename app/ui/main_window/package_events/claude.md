## 目录用途
`ui/main_window/package_events/` 用于承载“项目存档与资源索引相关事件处理”的拆分实现。
本目录只放多个小型 Mixin（按职责分组），由上层 `ui/main_window/package_events_mixin.py`
进行聚合继承，以保持对外 `PackageEventsMixin` 的导入路径稳定。

## 当前结构
- `package_load_save_mixin.py`：项目存档加载/保存、项目存档下拉框刷新、战斗预设延迟选中缓存；下拉框切换统一走“切包请求入口”，在检测到未保存修改时弹出 **保存/不保存/取消** 选择，并在取消时自动回滚下拉框与项目存档（PACKAGES）页的左侧列表选中；保存完成时会标记一次“资源库内部写盘”时间，用于抑制资源库自动刷新误触发；项目存档加载完成后会同步更新资源库 watcher 的监听作用域（共享 + 当前项目存档），并刷新 NodeRegistry/node_library 以匹配当前项目存档作用域（含复合节点），避免切包后仍沿用上一作用域节点库导致串包。
- `package_load_save_mixin.py` 在项目存档切换后会同步更新复合节点页的上下文（若复合节点页已创建），以保证复合节点左侧列表可按当前项目存档过滤显示。
- `library_selection_mixin.py`：库页选中/取消选中、右侧面板收起、模板/实体摆放/关卡实体与战斗预设选中同步
- `packages_view_mixin.py`：项目存档（PACKAGES）右侧详情展示与跳转、资源预览视图（**优先 PackageView，回退 GlobalResourceView**）、属性面板互斥收起；存档库页默认以**只读预览**方式展示资源详情，避免在未切包时编辑导致脏标记串包，并减少点击单条资源触发全局全量加载造成卡顿；当在存档库页预览“非当前存档”的节点图条目时，右侧图属性面板会进入**预览模式（仅元数据）**，不触发图资源加载与解析，避免误报“节点图不存在”。
- `management_panels_mixin.py`：管理模式右侧面板联动入口（薄壳）。保留对外稳定的 Mixin 方法名，实际编排委托给 coordinator。
- `management_panels_coordinator.py`：管理模式右侧面板选择/刷新协调器。`signals/structs/main_camera/peripheral/equipment_*` 等专用面板的刷新入口由 `ui/main_window/management_right_panel_registry.py` 提供的注册表驱动（与 `RightPanelPolicy`、`RightPanelAssemblyFeature` 共享同一份 section→tab 规则）；Coordinator 只负责编排并保证 **selection 单次解析**：在 `on_management_selection_changed` 中只解析一次 `management_widget.get_selection()` 并将解析后的 `(section_key, item_id)` 作为参数传给 selection_updater，禁止 updater 再反查库页选中，避免协议漂移导致右侧面板静默空白。
- `packages_view_mixin.py` 额外提供 `_on_packages_page_package_load_requested(package_id)`：仅在 `ViewMode.PACKAGES` 下响应 `PackageLibraryWidget.package_load_requested`，用于用户在存档库页“显式切换为当前存档”（点击按钮或双击条目）时同步切换主窗口当前项目存档上下文。
- `membership_mixin.py`：各类“所属项目存档”归属计算与写回（管理资源/信号/结构体/关卡变量等）。目录即项目存档模式下该能力已收敛为**单选归属根目录**：归属由资源物理文件所在根目录决定（共享/某项目存档），UI 切换即调用 `PackageIndexManager.move_resource_to_root(...)` 移动文件并同步当前包的内存索引快照。
- `immediate_persist_mixin.py`：库页数据变更的脏标记与去抖增量落盘请求。战斗预设将“索引引用变化”（`combat_dirty/index_dirty`）与“资源本体变化”（`combat_preset_key`）分离：仅编辑预设字段时只写回对应资源文件，不无条件写入项目存档索引；在 `global_view` 下的战斗预设库页操作不会触发项目存档保存。
- `resource_membership_mixin.py`：图/复合节点/模板/实体摆放的所属存档变更与当前包索引内存同步；归属变更统一视为“移动资源文件到目标根目录”，并在命中当前包时同步 `PackageController.current_package_index` 的内存快照与 `PackageView` 缓存失效，确保列表/属性面板联动不漂移。
- `__init__.py`：导出拆分后的 Mixin（供聚合入口引用）

## 注意事项
- Mixin 之间只通过主窗口公共属性与方法协作，避免相互导入实现细节，减少循环依赖风险。
- 本目录的 Mixin 不直接读写磁盘；落盘统一交给 `PackageController` / `PackageIndexManager`。
- 本目录内如需访问稳定依赖（例如 `PackageIndexManager/ResourceManager`），统一从 `main_window.app_state` 获取，避免依赖 `main_window.package_index_manager/resource_manager` 等旧式兼容别名（这类别名容易在重构中被移除，导致归属写回逻辑静默失效）。
- 对中央库页的刷新与上下文注入统一走 `set_context/reload/get_selection` 协议；避免再出现 `set_package/refresh/get_current_selection` 等旧入口。
- 对外入口保持在 `ui/main_window/package_events_mixin.py`，不要让外部模块直接依赖此目录的具体文件名。
- 右侧标签页的挂载/移除与切换应统一通过 `main_window.right_panel`（`ensure_visible/switch_to/apply_management_*` 等）完成，避免在各 Mixin 中直接操作 `side_tab` 或分散依赖 registry/policy 造成协议漂移。
- 当需要表达“只保留表里的 tab，其它全部收起”的互斥行为时，优先使用 `main_window.right_panel.apply_visibility_contract(...)`（合同模板集中在 `ui/main_window/right_panel_contracts.py`）。对于需要“允许并存但不强制打开”的场景，应使用 `keep_tab_ids/ensure_tab_ids` 拆分语义，避免在入口处通过 early-return 隐式实现导致行为难以追踪。
- 编排协调器（例如 `management_panels_coordinator.py`）不得依赖主窗口的 mixin 私有方法名（如 `_ensure_* / _hide_* / _update_*`）；应只调用 `right_panel_policy/right_panel_registry` 的公开接口表达“显隐意图”，并通过 registry 统一刷新右侧容器可见性。
- 管理模式下的“空选中 → 收起右侧专用编辑页签”应通过 `right_panel.apply_management_selection(..., has_selection=False)` 完成；`LibrarySelectionMixin` 只负责触发清空与可见性收敛，不再按 section_key 写死分支。
- 本目录内的“选中事件入口”（模板/实体摆放/管理/战斗 pending）会同步更新 `MainWindowViewState` 中的对应 selection 状态，供模式 presenter 与会话恢复使用；不要在这里引入新的跨模块状态机。
 - `LibrarySelectionMixin` 额外提供统一入口 `_on_library_page_selection_changed(LibrarySelection | None)`，用于接入库页的 `selection_changed` 信号并分发到既有的 `_on_template_selected/_on_instance_selected/_on_player_*_selected` 处理链路；页面侧仍负责在“无选中”时调用 `notify_selection_state(False, ...)` 触发右侧收起。


