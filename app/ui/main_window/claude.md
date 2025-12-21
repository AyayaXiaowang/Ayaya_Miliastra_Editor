## 目录用途
`ui/main_window/` 目录存放主窗口的组装与事件分发逻辑，采用 Mixin 架构将职责拆分到多个子模块，然后由 `MainWindowV2` 组合成完整应用窗口。

- `main_window.py`：主窗口入口类 `MainWindowV2`，保持为“壳/装配层”：只负责窗口生命周期、Mixin 初始化顺序、依赖注入与少量事件转发。启动期的稳定依赖集合不再散落在主窗口属性初始化里，而是集中由 `MainWindowAppState` 构建；“资源库刷新”不再在主窗口内堆叠缓存失效与重建细节，而是委托给 `ResourceRefreshService` 执行失效与重建，主窗口只根据刷新结果复用 `_on_package_loaded()` 与各页面 `reload()` 完成 UI 刷新编排。
- `app_state.py`：`MainWindowAppState`（单一真源）。集中装配 workspace/settings/节点库/ResourceManager/PackageIndexManager/GraphView 等**稳定依赖**，并要求主窗口与各 Mixin **只通过 `self.app_state` 访问这些共享依赖**；不再保留 `self.workspace_path/self.resource_manager/...` 等兼容别名，避免隐式约定扩散。注意：GraphEditorController 在加载图时会重建 GraphModel/GraphScene，因此“当前 model/scene”以控制器为唯一真源，不在 AppState 内持有陈旧副本。
- `resource_refresh_service.py`：`ResourceRefreshService`（资源库刷新服务）。集中处理“资源库刷新”的缓存失效与索引重建：包含结构体/信号/关卡变量/局内存档模板等代码级 Schema 缓存失效、信号仓库 `SignalDefinitionRepository` 的二级缓存失效、结构体记录快照失效、`ResourceManager.clear_all_caches()+rebuild_index()`、进程内 graph_data 缓存清空、布局相关模型缓存失效，以及 `PackageView/GlobalResourceView` 懒加载缓存清理，并统一失效图属性/引用查询的数据提供器缓存；返回 `ResourceRefreshOutcome` 供 UI 决定如何刷新页面与恢复上下文；服务本身不直接操作 UI 组件。
  - 进程内 graph_data payload 缓存的清理由 `GraphDataService.clear_all_payload_graph_data()` 统一桥接（服务内不再直接 import `app.common.in_memory_graph_payload_cache`），降低“缓存失效入口分散”的分叉风险。
- `view_state.py`：`MainWindowViewState`（单一真源雏形）。集中维护当前 `ViewMode` 与关键选中上下文（模板/实例/管理/任务、节点图库/编辑器、战斗 pending），供 mode presenter 与会话恢复使用，逐步减少从 widget 反查状态造成的隐式依赖。
- `mode_presenters/`：模式控制器/Presenter 体系。每个 `ViewMode` 一个 presenter，专职承载“进入模式后的副作用”（刷新列表、懒加载页面、同步右侧上下文等）；`ModeSwitchMixin` 只负责公共切换流程并调用 `main_window.mode_presenter_coordinator.enter_mode(...)`。
- `mode_transition_service.py`：`ModeTransitionService`（模式切换公共流程服务）。集中封装模式切换的公共步骤与顺序约束（保存当前复合节点/图、切换中央堆栈、调整 splitter、调用 presenter、右侧标签收敛、保存会话快照）；`ModeSwitchMixin._on_mode_changed` 仅作为 UI 信号入口委托调用该服务，降低 Mixin 冲突面。
- `ui_setup_mixin.py`：UI 结构装配薄层（创建 Widget、注入依赖、布局与样式），中央模式堆栈包含元件库/实体摆放/战斗预设/管理面板/任务清单/复合节点占位/节点图库/验证/图编辑器/存档库等页面；页面/右侧面板的信号连接与标签注册已迁移到 `features/`，避免在本文件中继续堆积 `.connect(...)` 与跳转分支。
- `wiring/`：主窗口装配层的“信号绑定/导航请求转发”集中入口（page binder + right panel binder），将页面与右侧面板信号统一连接到主窗口回调或 `NavigationCoordinator.handle_request(UiNavigationRequest)`；要求所有导航请求通过 `app.models.ui_navigation.UiNavigationRequest` 工厂方法构造，减少字符串拼装与语义漂移。
- `features/`：主窗口“功能模块（Feature）”收敛层（渐进迁移用）。用于把新增功能的装配/右侧面板注册/快捷键与信号连线从 `UISetupMixin` 与多处 mixin/wiring 中逐步迁移出来，实现“新增一个功能尽量只改一个模块 + 一次注册”。目前右侧面板已大胆收敛为 `RightPanelAssemblyFeature`：集中负责执行监控面板创建、右侧面板 binder 连线、以及 tab 注册矩阵。
- `right_panel_policy.py`：右侧面板联动策略（集中处理 section/mode → tabs 显隐），避免在 mixin/presenter/handler 中散落 `_ensure_*` 分支。
- `wiring/`：主窗口装配层的集中入口：包含页面/右侧面板的 binder，以及右侧标签注册表的矩阵配置（tab_id/标题/模式约束）。主窗口装配文件只创建对象与布局，然后调用 wiring 进行统一绑定与配置。
- `controller_setup_mixin.py`：控制器初始化与回调注入，集中创建 `PackageController`、`GraphEditorController`、`NavigationCoordinator` 与 `FileWatcherManager`，并为其提供获取当前上下文（当前包、当前图容器、当前场景/视图等）的回调。
  - `NavigationCoordinator` 会被注入 `get_graph_data_service` 回调，统一通过 runtime 层 `GraphDataService` 加载/解析节点图数据，避免导航链路直接依赖多处缓存实现。
- `mode_switch_mixin.py`：视图模式切换入口（UI 信号处理）。保持为**最薄事件入口**：仅负责把 UI 的 mode_changed/F5 等信号转发到 `ModeTransitionService`；不再承载右侧标签的规则封装，避免出现“mixin + policy + registry”多处并行维护。
- `right_panel_controller.py`：右侧面板对外唯一入口（`main_window.right_panel`）。对业务代码暴露 `prepare_for_mode_enter/apply_for_mode/enforce_contract/ensure_visible/apply_management_*` 等高层 API，内部组合 registry 与策略，避免双真源与协议漂移。
- `right_panel_registry.py`：右侧 `side_tab` 的注册表（内部实现细节）。集中管理 `tab_id -> widget/title/模式约束` 与 QTabWidget 挂载/移除细节。
- `ModeTransitionService` 应只依赖主窗口的显式契约（`nav_bar/central_stack/main_splitter/right_panel_registry/view_state/graph_controller` 等），避免反向调用 mixin 私有方法；主窗口对外提供稳定钩子 `refresh_save_status_label_for_mode(...)` 与 `schedule_ui_session_state_save()` 供服务层调用。
（已移除）`mode_handlers/`：历史兼容层已下线，避免出现“presenters 与 handlers 双入口”的认知负担。
- `event_handler_mixin.py`：聚合若干事件处理 Mixin，将资源加载/保存、图编辑事件、任务清单事件以及导航与窗口事件拆分到独立文件中（例如 `package_events_mixin.py`、`graph_events_mixin.py`、`todo_events_mixin.py`、`window_navigation_events_mixin.py`），主窗口通过多重继承统一组合。
- `package_events_mixin.py`：**对外稳定入口**，聚合“存档加载/保存、存档下拉框刷新、资源归属、右侧属性/管理面板联动、立即持久化”等事件处理；具体实现已拆分到 `package_events/` 子包，避免单文件过大。
- 其余 `*_events_mixin.py` 文件分别负责图加载与图库跳转、任务清单刷新与执行按钮联动，以及导航切换、窗口标题/保存状态和设置对话框/验证面板等通用行为。

## 当前状态
- 主窗口通过集中配置 `ViewMode` 与 `RIGHT_PANEL_TABS` 控制不同模式下中央视图与右侧标签的组合，右侧属性类面板统一使用 `PanelScaffold` 骨架，并通过专门的 Panel 类（如模板/实例属性面板、图属性面板、执行监控面板等）承载具体 UI。
- 节点图画布使用全局唯一的 `app_state.graph_view`：图编辑器页与任务清单预览通过 Host 容器移动复用；`ModeTransitionService` 在进入 `ViewMode.TODO` 时切换为 `EditSessionCapabilities.read_only_preview()`，离开 TODO 时恢复进入前的能力快照，保证任务清单中的画布不可编辑且切回编辑器不残留只读状态。
- 管理模式（ViewMode.MANAGEMENT）在中央使用 `ManagementLibraryWidget` 作为列表式入口，右侧根据当前 Section 按需挂载管理相关面板：通用属性/编辑面板 `ManagementPropertyPanel`、信号详情面板 `SignalManagementPanel`、结构体详情面板 `StructDefinitionManagementPanel`、主镜头编辑面板 `MainCameraManagementPanel`、外围系统编辑面板 `PeripheralSystemPanel`，以及装备数据拆分后的 `EquipmentEntry/Tag/TypeManagementPanel` 三个面板等；其中计时器、局内存档模板、单位标签等基于 ID 列表的管理类型会通过 `ManagementPropertyPanel.build_edit_form()` 在“属性”标签中直接构建可编辑表单，并在面板顶部统一集成“所属存档”多选行，由 `PackageEventsMixin` 负责根据 section key/资源 ID 计算归属集合并写回 `PackageIndex.resources.management[...]`；信号、结构体等代码级类型系统资源在管理模式下通过各自专用面板以只读方式展示定义内容，并在顶部统一复用“所属存档”多选行维护归属关系，实际定义的增删改通过 `assets/资源库` 下的 Python 资源与工具脚本完成，其它仅在全局视图下以聚合配置形式存在的管理域（例如货币与背包、关卡设置等）仍以只读摘要或专用编辑面板为主；关卡变量按源文件聚合为模板展示，右侧使用无滚动表格列出文件内全部变量并开启换行，所属存档多选对文件内所有变量批量生效，使用情况会在表单上方列出引用它们的存档名称。
- 管理模式下右侧专用编辑页签的显隐使用 `RightPanelPolicy.apply_management_selection(section_key, has_selection=...)` 统一收敛；其 section→tab 规则由 `management_right_panel_registry.py` 作为唯一真源提供：`ui_settings` 仅依赖 section_key，其余专用页签仅在有有效条目选中时出现，避免“空白页签残留”。
- 管理库选中项在“右侧专用面板刷新”链路中以库页协议 `get_selection()`（`LibrarySelection`）为唯一真源：`ManagementPanelsCoordinator.get_current_selection()` 负责解析 (section_key, item_id)；在 `on_management_selection_changed` 的专用面板分支中将 selection 作为参数传给 `management_right_panel_registry.py` 的 selection_updater，避免 updater 二次反查 `get_selection()` 造成协议漂移与右侧面板静默空白。
- 主窗口内各模块对右侧标签的操作统一通过 `RightPanelRegistry`/`RightPanelPolicy` 公共接口完成，不再依赖 `_ensure_* / _update_*` 等 mixin 私有方法名或直接操作 `side_tab.addTab/removeTab/setCurrentWidget`，降低跨模块隐式耦合与协议漂移风险。
- 库页面统一通过 `_on_library_selection_state_changed` 处理“无选中→收起右侧”的场景，`notify_selection_state` 会在资源库列表刷新或清空选中时触发，避免在各事件 Mixin 中分散调用 `_update_right_panel_visibility()`。
- 装备数据管理（词条/标签/类型）选中时仅隐藏无关编辑页签，保留对应的专用面板标签，避免在刷新右侧时被统一收起导致用户无法编辑。
- 管理模式下专用面板（信号/结构体/主镜头/外围系统/装备数据等）的刷新以 `PackageController.current_package` 为准：若当前包为空则清空面板内容并保持标签收敛，不再回退到其它上下文来源，避免出现“上下文错位但 UI 仍可编辑”的隐性问题。
- 在管理模式下无任何条目选中时，属性与专用编辑面板会被收起，并触发 `_update_right_panel_visibility()` 隐藏右侧容器，避免出现空白面板。
- 战斗预设模式（ViewMode.COMBAT）在中央使用 `CombatPresetsWidget` 统一浏览玩家模板、职业、技能、本地投射物、单位状态与道具等战斗相关资源，左侧分类与右侧列表仅负责提供“选中对象”的业务上下文，真正的详情编辑与节点图跳转由右侧的“玩家模板/职业/技能/道具”面板承担；这些面板的挂载由主窗口的 `PackageEventsMixin._on_player_template_selected/_on_player_class_selected/_on_skill_selected/_on_item_selected` 根据当前选中条目与视图模式动态控制，使战斗预设页面的列表选中与右侧详情标签之间保持一一对应关系；进入战斗预设模式时若列表尚无选中条目，会先选中首个可用条目再同步右侧详情，避免后台包切换阶段的默认选中干扰其他模式；在非战斗模式收到战斗预设选中时仅记录待处理选中，延迟到进入战斗模式后再加载对应面板，减少启动期卡顿。
- UI 会话状态保存以“窗口关闭与视图模式切换”为主：`WindowAndNavigationEventsMixin` 在关闭窗口时统一采集当前视图模式与各库页选中状态并写入 `ui_last_session.json`，在 `_on_mode_changed` 中按需触发轻量去抖的 `_schedule_ui_session_state_save()` 以覆盖异常退出场景；模板/实例等少数视图在选中变更时会请求一次会话保存，而战斗预设与管理页面的普通选中仅同步右侧详情与标签状态，不额外触发高频的会话状态写盘。
- 所有耗时操作与资源访问统一委托给控制器或资源管理器，主窗口只负责装配 UI、转发信号与维护模式/选中状态，不在此目录中直接读写磁盘文件。
- 任务清单生成在 UI 侧创建 `TodoGenerator` 时会注入主窗口单例 `PackageIndexManager`（与 `MainWindowAppState` 一致），避免模型层重复创建索引管理器导致状态分叉。
- 任务清单数据仅在进入 `ViewMode.TODO` 或已有 Todo 数据的情况下参与上下文匹配，图加载阶段不再强制刷新 Todo，避免启动时的 UI 卡顿。
- 主窗口在关闭时会通过 `WindowAndNavigationEventsMixin` 收集当前 UI 会话状态（视图模式、各库页选中项、任务清单上下文与当前编辑中的节点图 ID），并调用 `app.runtime.ui_session_state` 将其写入 `app/runtime/ui_last_session.json`；下次启动完成基础装配与初始存档加载后，会尝试从该文件读取状态，根据记录的 `ViewMode` 与各页面的轻量选中信息恢复到上一次看到的页面与业务上下文（例如重新聚焦到上一次选中的模板、实例、管理记录、战斗预设或 Todo 步骤，以及重新打开最近编辑的节点图），不在此处持久化任何大体量图数据或长期配置；关闭阶段的资源/索引落盘遵循“flush 去抖缓冲 → 按脏块增量保存”的策略：无本地改动则不写盘，以避免外部资源刷新后被无意义覆盖。
- 主窗口初始化路径在 `MainWindowV2.__init__` 中按顺序完成：保存 `workspace_path` → 二次确认并加载 `settings` → 通过集中式 `NodeRegistry` 加载节点库 → 构造 `ResourceManager` 与 `PackageIndexManager` → 创建空 `GraphModel/GraphScene/GraphView` 并绑定节点库 → 初始化控制器 → 装配 UI/菜单栏/工具栏并应用全局主题样式 → 连接控制器信号 → 加载最近存档或创建默认存档 → **将 UI 会话状态恢复排队到事件循环启动后执行**（避免在构造期同步打开上次会话的大图或大量选中恢复导致 UI 延迟显示）；该初始化路径在关键步骤使用 `engine.utils.logging.logger.log_info` 输出 `[BOOT][MainWindow] ...` 前缀的启动日志，便于在 UI 未弹出时从控制台精确判断卡在节点库加载、资源索引构建还是图场景/控制器装配阶段。

## 注意事项
- 新增视图模式或右侧标签页时，应优先在 `view_modes.py` 中集中声明 `ViewMode/RIGHT_PANEL_TABS`；需要“进入模式副作用”时在 `mode_presenters/` 扩展对应 presenter；右侧标签的注册矩阵与联动策略优先改 `features/right_panel_assembly_feature.py` 与 `right_panel_policy.py`，避免回到 `ui_setup_mixin.py`/mixin 中继续堆 `_ensure_*` 分支；页面对外信号的连接与导航转发优先改 `features/central_pages_assembly_feature.py`（或新增 Feature），必要时才调用 `wiring/` 的 binder。
- 对“新增功能需要多点改动”的场景：优先新增 `features/` 下的 Feature 并在默认安装入口注册；Feature 内负责创建控件、注册右侧 tab、连接信号。旧 wiring/mixin 入口仍可保留以兼容，逐步迁移后再删除。
- 右侧面板的状态机/标签协议已集中在 `right_panel_protocol.md`，扩展或排查右侧未收起/未刷新的问题时先对照矩阵与约束；`ModeSwitchMixin._enforce_right_panel_contract` 在每次模式切换后会强制收敛标签集合，防止跨模式残留。
- **模式切换禁止旁路**：任何“切换到某个 ViewMode”的行为都必须走 `ModeSwitchMixin._on_mode_changed → ModeTransitionService.transition(...)`（或 `_navigate_to_mode(...)`），禁止在其它模块里直接调用 `central_stack.setCurrentIndex(...)` 来“实现切换”（唯一例外：复合节点页面的懒加载在进入 `ViewMode.COMPOSITE` 的同一模式内，用“替换占位页”为真实 widget 的结构操作）。
- **选中回调必须先校验 ViewMode**：节点图库、元件库、实体摆放等库页在切换存档/刷新资源索引时可能在后台重建列表并发出“空选中”事件；对应的主窗口回调（例如 `graph_events_mixin._on_graph_library_selected`）必须先判断当前 `ViewMode`，仅在所属模式下更新右侧面板与文件监控，避免后台刷新抢占 `GRAPH_EDITOR/TODO/MANAGEMENT` 等模式的右侧上下文。
- 新增或扩展右侧面板时，应在 `ui_setup_mixin._create_property_panels` 中集中创建实例，并通过专门的 Mixin（如 `PackageEventsMixin` 或窗口/导航相关 Mixin）连接其信号与持久化逻辑，保持主窗口初始化路径清晰。
- `ui_setup_mixin.py` 中创建页面/面板时优先从 `app_state` 读取稳定依赖（`resource_manager/package_index_manager/...`），避免继续扩散兼容别名 `self.resource_manager/...` 的隐式依赖链路。
- UI 会话状态保存/恢复（`ui_last_session.json`）使用 `main_window.app_state.workspace_path` 作为唯一路径来源；避免依赖 `self.workspace_path` 等旧式兼容别名，减少“静默 return 导致状态不保存/不恢复”的隐蔽问题。
- 事件处理 Mixin 之间应只通过主窗口公共属性与信号交互，避免在子 Mixin 里反向导入或强依赖其它 Mixin 的实现细节，减少耦合度。
- `main_window.py` 中避免继续增加“缓存失效/重建/刷新编排”细节：需要扩展资源刷新时优先改 `ResourceRefreshService`（失效与重建）或对应页面/控制器（UI 刷新），主窗口只保留委托与最小编排。
- `_create_property_panels` 中装备数据管理面板保持局部导入并放在方法体内，确保缩进正确，避免循环依赖或启动期的额外加载。
- 管理配置的“所属存档”勾选仅更新 PackageIndex（含当前包的内存索引），不触发整包保存，避免一次勾选导致全量落盘。

# ui/main_window 模块

## 目录用途
主窗口模块，使用 Mixin 架构将主窗口逻辑拆分为多个职责明确的子模块。

## 模块结构

### 核心文件
- `main_window.py` - MainWindowV2 类定义（约90行），继承所有Mixin，负责核心初始化
- `__init__.py` - 包导出，保持对外 API 稳定

### Mixin 模块（职责分离）

#### 1. controller_setup_mixin.py (~130行)
**职责**: 控制器初始化和信号连接

**主要方法**:
- `_setup_controllers()` - 初始化4个核心控制器
  - PackageController - 功能包生命周期管理（含保存前的资源库指纹脏检查）
  - GraphEditorController - 节点图编辑核心逻辑
  - NavigationCoordinator - 跳转协调
  - FileWatcherManager - 文件监控和冲突解决（监控资源库根目录及主要子目录，通过指纹判定实际变更，再由主窗口注入的回调触发资源索引重建与视图刷新）
- `_connect_controller_signals()` - 连接所有控制器信号到主窗口槽函数
- `_get_current_resource_container()` - 为 `PackageController` 提供当前编辑对象（模板/实例/关卡实体或图容器）的统一入口，用于保存存档或全局视图时将基础信息、GUID 与挂载节点图等改动正确落盘到资源库。

**关键依赖**:
- `app.ui.controllers.*` - 所有控制器类
- 需要在 UI 设置之前完成初始化（控制器回调中会引用 UI 组件）

#### 2. ui_setup_mixin.py (~280行)
**职责**: UI组件创建和布局（含基础调试快捷键），中央堆叠页面通过 `StackPageSpec` 列表集中描述，右侧属性/管理面板的可选信号连接统一使用 `_connect_optional_signal`，减少分散的 `hasattr` 判断。

**主要方法**:
- `_apply_global_theme()` - 应用全局主题样式
- `_setup_ui()` - 组装主窗口 UI 结构（委托给若干私有构建方法）
- `_setup_nav_bar()` - 左侧导航栏（NavigationBar）
- `_create_central_stack()` - 中间堆叠窗口（10个页面：模板/实体/战斗/管理/任务/复合占位/图库/验证/编辑器/功能包）
- `_create_right_panel_container()` - 右侧面板容器（属性/图属性/复合属性/虚拟引脚/界面控件设置）
- `_create_property_panels()` - 属性类子面板的装配与信号连接，并将 `TemplateInstancePanel` 暴露的“保存前刷新”回调注册到 `PackageController`，使工具栏保存按钮、自动保存以及窗口关闭时都能在持久化前主动刷新基础信息页中使用去抖写回的编辑内容（例如名称/描述/GUID），避免这些字段因用户快速保存或切换功能包而丢失。
- `_setup_menubar()` - 设置菜单栏，包含用于验证的 F5 快捷键以及用于开启/关闭 UI 悬停检查器的 F12 快捷键（开发者工具，仅在显式切换时生效；悬停检查器由 `app.ui.devtools.view_inspector.WidgetHoverInspector` 提供）
- `_setup_toolbar()` - 设置工具栏（功能包选择/新建/保存/导入导出/设置/刷新/重启/保存状态指示器）

**UI 组件层次**:
```
QMainWindow
└── main_widget (QWidget)
    └── main_layout (QHBoxLayout)
        ├── nav_bar (NavigationBar) - 左侧导航
        └── main_splitter (QSplitter)
            ├── central_stack (QStackedWidget) - 中间堆叠窗口
            │   ├── 0: template_widget
            │   ├── 1: placement_widget
            │   ├── 2: combat_widget
            │   ├── 3: management_widget
            │   ├── 4: todo_widget
            │   ├── 5: composite_widget (懒加载)
            │   ├── 6: graph_library_widget
            │   ├── 7: validation_panel
            │   ├── 8: graph_editor_canvas_host（节点图编辑器 Host，承载全局 `app_state.graph_view` 以支持跨页面复用画布）
            │   └── 9: package_library_widget
            └── right_panel_container (QWidget) - 右侧面板（默认情况下初始宽度约为中央区的 2/3，以便属性/变量等表格类页面有足够展示空间；在任务清单模式下会适度收窄右侧宽度，为中间详情与图预览留出更多空间；容器宽度约束：min=350，max=1200）
                └── side_tab (QTabWidget)
                    ├── property_panel (基础，始终存在，用于模板/实例/关卡实体)
                    ├── player_editor_panel (按模式，ViewMode.COMBAT 下展示玩家模板详情)
                    ├── graph_property_panel (按模式)
                    ├── composite_property_panel (按模式，来自 `ui/composite`)
                    ├── composite_pin_panel (按模式，来自 `ui/composite`)
                    ├── ui_control_settings_panel (按模式)
                    └── execution_monitor（ExecutionMonitorPanel，按模式）
```

#### 3. mode_switch_mixin.py (~340行)
**职责**: 视图模式切换和右侧面板管理

**主要方法**:
- `_on_mode_changed(mode)` - 模式切换主入口：保存当前编辑状态（复合节点/节点图）→ 切换中央堆叠索引与分割器比例 → 调用 `mode_handlers.enter_mode(...)` 执行模式副作用 → 通过 `right_panel_registry` 应用右侧标签配置与收敛 → 输出调试状态（nav/central/side）
- `_apply_right_tabs_for_mode(view_mode)` - 委托 `RightPanelRegistry.apply_for_mode(view_mode)` 按 `RIGHT_PANEL_TABS` 挂载/移除静态标签，并回收越权动态标签
- `_enforce_right_panel_contract(view_mode)` - 委托 `RightPanelRegistry.enforce_contract(view_mode)`，防止跨模式残留
- `_update_right_panel_visibility()` / `_switch_to_first_visible_tab()` - 委托注册表的 UI 收敛方法
- `_ensure_property_tab_visible(should_show)` - 按需显示/隐藏模板/实例属性标签
- `_ensure_player_editor_tab_visible(should_show)` - 按需显示/隐藏“玩家模板”标签，仅在战斗预设模式下使用
- `_ensure_ui_settings_tab()` / `_remove_ui_settings_tab()` / `_update_ui_settings_tab_for_management(section_key?)` - 管理界面控件设置标签，仅在管理模式且当前 section 为“界面控件组`(key=\"ui_control_groups\")` 时显示
- `_switch_to_validation_and_validate()` - F5快捷键处理

**模式切换逻辑**（按 ViewMode 枚举）：
- TEMPLATE / PLACEMENT - 显示属性面板；进入 PLACEMENT 时通过 `EntityPlacementWidget._rebuild_instances()` 重建实例列表
- COMBAT - 战斗预设模式下右侧“玩家模板 / 职业 / 技能”详情标签全部采用按选中对象动态插入的策略：`CombatPresetsWidget` 通过 `player_template_selected` / `player_class_selected` / `skill_selected` 信号，将当前选中条目交给主窗口的 `_on_player_template_selected/_on_player_class_selected/_on_skill_selected`，由后者分别调用 `_ensure_player_editor_tab_visible/_ensure_player_class_editor_tab_visible/_ensure_skill_editor_tab_visible` 在有有效上下文时插入对应标签，并在收到空 ID 时清空上下文并移除标签；这样当只选中玩家模板时只展示“玩家模板详情”标签，不会残留空的“职业/技能”页签，整体体验与元件库/实体摆放中“无有效选中对象→收起属性面板”的行为保持一致
- COMBAT（模式切回时的同步） - 当从其它模式切回战斗预设时，`ModeSwitchMixin._on_mode_changed` 会通过 `CombatPresetsWidget.get_current_selection()` 读取当前列表选中状态并显式调用上述三个选中处理方法，使进入或返回战斗预设模式时右侧战斗详情面板自动与左侧列表保持同步，而不依赖用户重新点击列表项。
- MANAGEMENT - 默认不显示属性；当左侧管理库选中“🖼️ 界面控件组” section 时，在右侧插入“界面控件设置”标签，并绑定管理库内部暴露的 `ui_control_group_manager`
- TODO - 默认不挂载任何额外标签；进入任务清单模式后，由 `TodoListWidget` 和 `TodoEventsMixin.on_todo_selection_changed` 在选中**节点图相关步骤**时按需插入“执行监控”标签，在选中模板/实例类步骤时按需插入只读“属性”标签
- COMPOSITE - 显示复合节点属性+虚拟引脚（懒加载复合节点管理器）
- GRAPH_LIBRARY - 显示图属性；切换到图库模式时会清空当前编辑上下文，并在刷新节点图库后根据当前选中节点图（若无选中则自动聚焦首个）刷新右侧图属性面板，保证左侧高亮与右侧属性始终同步
- VALIDATION - 进入时**不再默认触发验证**：页面用于查看已存在的校验结果；验证由用户显式触发（面板按钮或 F5 快捷键），右侧仅挂载“验证详情”标签用于展示选中问题的详细信息
- GRAPH_EDITOR - 显示图属性（当前图）
- PACKAGES - 无特殊右侧面板

此外，管理模式下的信号/结构体/主镜头/外围系统编辑面板以及战斗预设模式下的“玩家模板/职业/技能/道具”详情面板等**上下文驱动的右侧标签**，在模式切换时会由 `RightPanelRegistry` 按 `ViewMode` 约束统一回收：一旦离开各自所属模式，这些动态面板即使未显式调用对应的 `_ensure_*_visible(False)` 也会被自动从 `side_tab` 中移除，避免残留越权页签。

**调试输出**:
每次模式切换输出 `[MODE-STATE]` 行，包含：
- nav: 左侧导航当前模式
- central: {index, mode, is_graph_view}
- side: {count, current, tabs}

#### 4. graph_events_mixin.py
**职责**: 图编辑相关事件处理与跳转

**主要内容**:
- `_on_graph_loaded` / `_on_graph_saved` / `_on_graph_reloaded` - 节点图加载与保存链路；在外部节点图文件发生变更时，通过文件监控触发从资源管理器重新加载当前图，并在加载前使图属性面板使用的图数据缓存失效，确保右侧“节点图变量”等只读视图始终反映最新的图结构与变量声明；节点图写盘位于 `assets/资源库/节点图/...`，保存完成会同步标记“资源库内部写盘”时间，并尽量按“当前图文件所在目录”做抑制范围，避免保存当前图时误吞其它目录的外部新增资源事件。
- `_on_graph_runtime_cache_updated` - 节点图运行期缓存更新的统一入口（例如自动排版覆盖 `graph_cache`、强制重解析）：由 `GraphEditorController.graph_runtime_cache_updated` 信号触发，集中失效 `GraphDataService` 的图模型与 payload 缓存，并同步失效/刷新右侧图属性面板的数据提供器，避免“某入口刷新后又回退/显示不一致”。
- `_on_open_graph_request` / `_on_graph_selected` / `_on_player_editor_graph_selected` / `_on_graph_updated_from_property` - 图属性与编辑器之间的联动，其中 `_on_player_editor_graph_selected` 负责响应战斗预设玩家模板、职业与技能详情面板中“节点图”子标签发出的图打开请求，以独立方式在节点图编辑器中打开挂接在玩家/角色/技能上的节点图。
- `_focus_node` / `_focus_edge` / `_on_jump_to_graph_element` - 节点与连线的聚焦跳转

#### 5. package_events_mixin.py / package_events/
**职责**: 存档与资源索引相关事件处理（`package_events_mixin.py` 仅聚合继承；实现拆分在 `package_events/`）

**主要内容**:
- `_on_package_loaded` / `_on_package_saved` / `_on_package_combo_changed` - 功能包加载、保存与下拉框联动；保存完成后会触发验证并刷新“存档库”页面，使其中展示的 GUID 与挂载节点图等汇总信息始终反映当前落盘状态。
- `_on_template_selected` / `_on_instance_selected` / `_on_level_entity_selected` - 将左侧元件库/实体摆放的选中结果同步到右侧 `TemplateInstancePanel`，并**仅在对应视图模式下**响应这些选中信号：元件库模式中才根据模板选中更新“元件属性”，实体摆放模式中才根据实例或关卡实体选中更新对应属性；当元件库或实体列表刷新后当前分类/存档中已不再包含原先选中的对象且发出“空 ID”选中信号时，仅在各自所属模式下清空右侧属性面板并移除“属性”标签，避免在管理面板、任务清单等模式中因后台刷新触发的选中变化导致右侧属性面板意外弹出或上下文被抢占。
- `_on_package_resource_activated` - 响应存档库页面中右侧详情树对资源条目的点击：当点击元件、实例或关卡实体行时，通过 `GlobalResourceView` 在右侧 `TemplateInstancePanel` 中展示对应对象的基础信息、变量与组件，并按需插入“属性”标签；当点击节点图行时，在右侧 `GraphPropertyPanel` 中加载该图的属性与引用信息；当点击战斗预设相关条目时，复用战斗预设详情面板在右侧展示只读或可编辑摘要。存档视图下这些属性页签与管理配置详情互斥：在“模板/实例/关卡实体/节点图/战斗预设”等资源与“信号/计时器/局内存档模板”等管理配置之间切换时，会自动收起上一类资源对应的属性标签，右侧始终只展示当前选中条目的详情，避免残留旧的属性面板造成混淆。
- `_on_data_updated` - 右侧属性面板数据更新后，根据当前视图模式与属性上下文区分刷新策略：在以模板为主的视图中刷新元件库列表，在“实体摆放”模式下仅在编辑实例时刷新实例列表，并避免在编辑实体实例时触发元件库刷新引发的模板重选中，保证“实体修改 GUID 等基础信息不会导致右侧属性上下文从实体意外切回元件”；同时通过 `_on_immediate_persist_requested` 将变更对应的资源 ID/域标记为脏并交给 `PackageController.save_dirty_blocks()` 去抖增量落盘，避免为局部字段改动触发整包写盘。
- 结构体与信号等代码级管理资源的右侧专用面板当前仅作为只读视图：`PackageEventsMixin._on_struct_property_panel_struct_changed` 仍会在用户尝试修改结构体时给出明确提示，引导在对应的 Python 模块中完成定义变更；信号面板的变更回调 `PackageEventsMixin._on_signal_property_panel_changed` 现为静默空实现，只负责占位与文档语义，不再弹出任何提示或执行写回操作，避免在用户误触编辑控件时频繁打断浏览；列表行中仅依赖名称、字段数量等聚合信息的 Section 仍通过集中快照机制避免纯 UI 操作（如展开/折叠列表或字典字段详情）反复重建面板和重置滚动位置，从而保持管理模式下的浏览体验稳定、流畅，存档归属仍由各面板顶部的“所属存档”多选行即时写回 `PackageIndex`。
- `_on_graph_package_membership_changed` / `_on_composite_package_membership_changed` / `_on_template_package_membership_changed` - 统一写入 `PackageIndex` 中的资源归属关系。
- `_on_management_selection_changed` - 接收管理配置库页面当前选中记录的信息，在管理模式下根据 section key 决定右侧管理区域的表现：信号管理与结构体定义（包括基础结构体与局内存档结构体）以及主镜头等依旧使用各自的专用编辑面板，其余大部分管理类型（计时器、变量、关卡设置、货币与背包、技能资源、背景音乐、装备数据、路径、多语言文本、光源、聊天频道、单位标签、护盾、扫描标签、商店模板、局内存档与实体布设组等）通过 `app.ui.graph.library_pages.management_sections.get_management_section_by_key()` 查找到对应 `BaseManagementSection` 实例，并优先调用其可选的 `build_inline_edit_form(parent, package, item_id, on_changed)` 接口在通用 `ManagementPropertyPanel` 中构建就地编辑表单；若某个 Section 未实现内联表单，则退化为只读摘要表单展示；“界面控件组”仍由 `UIControlSettingsPanel` 作为专用编辑页嵌入右侧堆栈，避免与通用属性面板混用；所有这些编辑入口在数据变更后通过 `_on_management_edit_page_data_updated`、通用的 `on_changed` 回调或专用回调触发管理库列表刷新与即时持久化。

#### 6. todo_events_mixin.py
**职责**: 任务清单相关事件处理

**主要内容**:
- `_refresh_todo_list` - 基于当前包或视图模型重新生成 Todo 列表，并在刷新前后通过上下文快照尽量恢复任务清单中的当前选中项与右侧详情/预览上下文；在资源库被外部工具修改或当前包重新加载时，由主窗口统一调用以保持 Todo 与真实数据的一致性。
- `_on_todo_checked` - 接收任务清单页面发出的勾选变更事件，仅将结果写入当前包的 `todo_states` 并更新右上角保存状态指示，不在此处直接触发存档保存；Todo 勾选的持久化统一依赖工具栏“保存”按钮或窗口关闭流程。
- `on_todo_selection_changed` - 在任务清单模式下接收当前选中 `TodoItem`：模板/实例的“属性类步骤”会以只读方式加载到右侧 `TemplateInstancePanel` 并显示“属性”标签；节点图/复合节点相关步骤则按需显示并**优先切到**右侧“执行监控”标签，避免图步骤在选中或自动执行时被误判为“模板/实例任务”而抢占到“属性”页造成上下文错位。

#### 7. window_navigation_events_mixin.py
**职责**: 窗口级导航事件与模式切换入口

**主要内容**:
- `_navigate_to_mode` / `_open_player_editor` - 作为 `NavigationCoordinator` 与主窗口之间的桥接
- `closeEvent` - 统一处理窗口关闭时的保存与清理逻辑

### 向后兼容
`app.ui.main_window` 包的 `__init__.py` 直接导出 `MainWindowV2` 与 `APP_TITLE`，外部代码使用
```python
from app.ui.main_window import MainWindowV2
```
即可，不再依赖同名的顶层模块文件。

## 当前状态

### 已完成
- ✅ Mixin 架构拆分（4个模块）
- ✅ 向后兼容的导出
- ✅ 职责清晰分离（控制器/UI/模式切换/事件处理）
- ✅ 保持所有原有功能和信号连接
- ✅ 图编辑器右上角集成“前往执行”按钮：在图编辑器模式下**始终显示**，点击后跳转到任务清单并尽量定位当前图对应步骤（必要时自动生成 Todo）
- ✅ “前往执行”跳转到任务清单时复用全局画布：进入 TODO 后会立刻把 `app_state.graph_view` 挂到任务清单的预览页并显示，避免因延迟 attach 导致用户感知为“画布关闭后再打开”
- ✅ 即使从节点图库或属性面板直接打开图，也会通过 `TodoListWidget.find_first_todo_for_graph()` 自动匹配关联步骤；若未匹配到也会至少跳到任务清单页面
- ✅ 首次打开节点图时若任务清单尚未加载，会在后台自动刷新一次，确保上一条能力在冷启动场景同样生效

### 优势
1. **可维护性**: 每个 Mixin 职责单一，约200-340行，易于理解和修改
2. **可测试性**: 各模块可独立测试（注入依赖即可）
3. **可扩展性**: 新增功能只需添加新 Mixin 或扩展现有 Mixin
4. **向后兼容**: 外部代码无需修改
5. **调试友好**: 模式切换输出清晰的状态快照

## 注意事项

### Mixin 依赖顺序
继承顺序很重要，需确保：
1. `ControllerSetupMixin` 在最前（其他 Mixin 依赖控制器）
2. `UISetupMixin` 次之（其他 Mixin 依赖 UI 组件）
3. `ModeSwitchMixin` 和 `EventHandlerMixin` 互相依赖较少，顺序灵活
4. `QtWidgets.QMainWindow` 在最后

### 属性共享（约束）
所有 Mixin 仍共享主窗口上的 UI/控制器引用（例如 `package_controller/graph_controller/nav_coordinator` 与各页面/面板实例），但**共享依赖与状态必须显式收敛**：
- 稳定依赖（workspace/节点库/ResourceManager/PackageIndexManager/GraphView）统一从 `self.app_state` 读取；
- 视图/选中上下文统一从 `self.view_state` 读取与写入；
- 当前 GraphModel/GraphScene 统一从 `self.graph_controller.get_current_model()/get_current_scene()` 获取（控制器是唯一真源）。

### 方法命名约定
- 公共方法（外部调用）: 无前缀
- 私有方法（内部使用）: 单下划线前缀 `_`
- UI 设置方法: `_setup_*`
- 事件响应方法: `_on_*`
- 辅助方法: `_ensure_*`, `_remove_*`, `_refresh_*`, `_trigger_*`

### 信号连接
- 控制器信号在 `_connect_controller_signals()` 中统一连接
- UI 组件信号在 `_setup_ui()` 中创建组件时立即连接
- 跨组件信号通过控制器协调，不要直接连接

### 颜色与样式
- 主窗口工具栏的保存状态标签与图编辑器右上角的“前往执行”按钮均基于全局主题 token（`Colors`/`ThemeManager`）着色，保持与整体 UI 主题一致；节点图库（`ViewMode.GRAPH_LIBRARY`）固定为只读提示；复合节点（`ViewMode.COMPOSITE`）则根据页面能力（`CompositeNodeManagerWidget.can_persist_composite`）显示“预览（不落盘）/允许保存”，避免在启用复合节点落盘能力时仍显示误导性的只读提示；从只读页面切换回其它模式（如图编辑器、任务清单、管理面板等）时，会根据最近一次保存状态（已保存/未保存/保存中）恢复对应的状态标签与文案，保证只读提示不会在非只读页面残留。
- 新增按钮或状态徽标时，优先复用主题提供的颜色和 QSS 片段，避免在本模块中分散硬编码颜色值。

### 懒加载组件
- `composite_widget` - 首次进入复合节点模式时创建
- `execution_monitor`（tab_id=`execution_monitor`）- 右侧执行监控面板实例，按模式与当前上下文动态显示；标签页的挂载/移除统一通过 `RightPanelController.ensure_visible("execution_monitor", ...)` 管理，任务清单等页面只调用该公开方法，不直接操作 `side_tab` 结构，也不依赖主窗口上的面板别名属性。

### 模式切换流程
1. 保存当前编辑状态（复合节点/节点图）——**仅在有未保存修改时才触发保存**，避免无谓的 I/O 操作
2. 切换中央堆叠窗口索引
3. 根据模式动态调整右侧标签页
4. 刷新对应页面数据
5. 应用集中配置的右侧标签
6. 切换到第一个可见标签
7. 更新右侧面板可见性
8. 输出调试状态

### 工具栏布局与分组

- `_setup_toolbar()` 负责主窗口顶部工具栏的装配：
  - 左侧为“当前功能包选择”下拉框（含文本标签）。
  - 中部为与存档相关的操作按钮：**新建存档 / 保存**（保存走 `PackageController.save_now()`：先 flush 去抖缓冲，再按脏块增量落盘；无改动则不写盘）。
  - 右侧为“⚙️ 设置 / 刷新 / 重启”按钮组，以及“保存状态”标签（已保存 / 未保存 / 保存中）；其中“刷新”按钮会调用主窗口统一的 `refresh_resource_library()` 入口，在关闭资源库自动刷新时可作为手动刷新入口。
  - 最右侧使用伸缩控件将“保存状态”标签靠右对齐。

#### 分组与分隔线规则

- 顶部工具栏通过 **单一分隔线** 区分若干功能组：
  - 功能包选择区域
  - 存档操作组（新建存档 / 保存）
  - 设置与系统控制按钮组（⚙️ 设置 / 重启）
- 约定：相邻功能组之间只允许存在 **一条分隔线**，禁止连续调用 `toolbar.addSeparator()` 形成“双竖线”效果。
- 若临时移除某个按钮组（例如运行按钮组），应同时删除与该组相关的分隔线调用，避免出现“分隔线之间没有按钮”或视觉上的重复边界。

## 边界信息和细节

### 为什么选择 Mixin 而不是组合模式？
- **优势**: 保持原有的继承结构，无需修改外部代码
- **优势**: 所有 Mixin 共享主窗口状态，不需要复杂的依赖注入
- **权衡**: Mixin 之间可能有隐式依赖，需要注意方法调用顺序

### 如何添加新的模式？
1. 在 `app.models.view_modes.ViewMode` 中添加新枚举值
2. 在 `UISetupMixin._create_central_stack()` 中添加对应页面的创建方法
3. 在 `ModeSwitchMixin._on_mode_changed()` 中添加新模式的处理逻辑
4. 如需右侧面板，在 `RIGHT_PANEL_TABS` 中配置

### 如何调试模式切换问题？
1. 查看 `[模式切换]` 开头的日志输出
2. 查看 `[MODE-STATE]` 行的状态快照
3. 确认左侧导航/中央区域/右侧面板的状态一致性
4. 检查 `ViewMode.from_index()` 和 `ViewMode.from_string()` 的映射
5. 在管理模式下，留意与 section key 相关的辅助方法（例如 `_update_ui_settings_tab_for_management` 以及若干 `_ensure_*_editor_tab_for_management` / `_ensure_*_editor_tab_visible`），确认它们是否根据当前模式与 section key 正确增删右侧标签，避免在错误模式或错误 section 下残留管理面板。

### 性能考虑
- 复合节点管理器懒加载，避免启动时扫描所有复合节点
- 模式切换时仅刷新必要的页面数据
- 右侧标签页按需添加/移除，不保留隐藏标签

### 未来改进方向
1. **单元测试**: 为每个 Mixin 编写独立测试
2. **类型提示**: 添加完整的类型注解
3. **文档字符串**: 为每个方法添加详细的 docstring
4. **配置驱动**: 将模式切换逻辑改为配置驱动，减少硬编码
5. **事件总线**: 考虑引入事件总线替代直接信号连接

