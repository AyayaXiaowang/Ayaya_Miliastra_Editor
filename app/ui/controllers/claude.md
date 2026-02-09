# Controllers 模块

## 目录用途
控制器层，负责分离主窗口的业务逻辑，通过信号槽实现松耦合通信。每个控制器负责一个独立的功能域。

## 关键文件
- `package_controller.py`：项目存档生命周期管理（创建、加载、保存、导入、导出）。保存链条采用“脏块 + service 编排”：`PackageDirtyState` 记录图/模板/实体摆放/战斗/管理/索引等脏块，提供 `save_dirty_blocks()` 按脏块增量落盘；工具栏保存等显式入口使用 `save_now()`（flush 右侧属性面板的去抖缓冲 → 按脏块增量保存；无改动则不写盘）减少无意义 I/O；`load_package(package_id, save_before_switch=True)` 支持在切换存档前由上层决定是否保存（例如 UI 已完成“保存/不保存/取消”的确认时传 `save_before_switch=False`）；并提供 `has_unsaved_changes()` 作为上层的“未保存保护”判断入口。保存事务编排与写盘细节已下沉到 `ui/controllers/package_save/`，控制器仅委托 `PackageSaveOrchestrator` 执行“指纹基线同步 → 可选 flush → special_view / package_view 分支 → 索引写盘/指纹刷新”的顺序化流程；窗口关闭阶段遵循“flush → 按脏块保存”的策略，避免外部资源刷新后被无意义覆盖。
- `ui_html_bundle_importer.py`：UI HTML bundle 导入器：用于将（私有扩展转换得到的）UI bundle（UILayout + templates）写入运行时缓存 `app/runtime/cache/ui_artifacts/<package_id>/ui_html_bundles/`，不写入资源库；并额外生成 UI 多状态映射缓存 `app/runtime/cache/ui_artifacts/<package_id>/ui_states/<layout_id>.ui_states.json`（从 widgets 的 `__ui_state_*` 汇总 group/state→ui_key 列表），便于节点图作者实现互斥显隐切换而不必手工维护字典。
- `ui_pages_browser.py`：UI HTML 浏览入口：提供“打开 UI控件组预览（Web）”的统一入口（优先走私有扩展，缺失则回退到内置 `assets/ui_workbench` 静态服务）。批处理转换能力保留在控制器模块中；当未注册 HTML→bundle 转换器时，转换入口会提示“未启用自动转换，需在 Web 页手动导入/刷新”，而不是视为失败。
  - 兼容：转换完成后会对 `app/runtime/cache/ui_html_bundle_cli/<package_id>/*.flattened__*.flattened.html` 执行一次调试标签去重，保证同一文件内 `data-debug-label` 唯一，避免 Web 侧基于 label 的定位/点击选择因重复（例如 `text-`）失效。
- `package_dirty_state.py`：存档脏块模型（保存链条的 UI 侧增量落盘入口使用）。战斗预设除 `combat_dirty`（索引引用需同步）外，还提供按条目粒度的 `combat_preset_keys` 用于仅保存被编辑的预设资源本体，避免全量写盘。
- `package_save/`：存档保存链条 service（见该目录 `claude.md`）。
- `graph_editor_controller.py`：节点图编辑核心逻辑（加载、保存、验证、节点添加）
  - 控制器仅负责信号转发与依赖注入：load/save/validate/auto_layout_prepare 等跨域链路已下沉到 `ui/controllers/graph_editor_flow/` 的纯流程 service，避免 God Object 继续膨胀。
  - 节点创建的业务特例（例如“拼装字典”默认键值对端口）集中维护在 `ui/controllers/graph_editor_flow/new_node_ports_policy.py`，控制器不再按节点名硬编码分支。
  - 会话能力/只读语义/保存状态由 `GraphEditorSessionStateMachine` 统一派生（单一真源），禁止 controller/view/scene 分别维护 read_only/dirty/saving 等状态导致分叉。
  - 为复合节点页面提供专用入口 `load_graph_for_composite(composite_id, graph_data, composite_edit_context=...)`：在控制器内部完成一次 `LayoutService.compute_layout(..., clone_model=False)` 的预排版；复合节点专用的 `composite_edit_context` 通过“单次加载 options override”注入 `GraphScene`（不写入全局 `_scene_extra_options`，避免污染后续普通图加载）。
  - 复合节点预览子图在加载阶段会补齐端口“有效类型快照”（`input_types/output_types`）：先将虚拟引脚声明的具体类型按 `mapped_ports` 写入 `metadata.port_type_overrides`，再执行一次与资源层一致的有效类型推断与快照写回，避免内部节点端口长期显示为“泛型”。
  - 支持从节点图库双击打开**独立节点图**：通过 `open_independent_graph(graph_id, graph_data, graph_name)` 配合 `engine.graph.models.GraphConfig` 反序列化图配置，再调用统一的 `load_graph` 路径加载 `GraphModel`，保证独立节点图在编辑器中的数据结构与引擎侧配置模型保持一致
  - 进入编辑器时会确保会话能力回到“可交互 + 可校验”（保留 can_persist 语义），避免从 TODO 只读预览或设置页清缓存后的只读态残留导致右上角“自动排版”入口消失
  - 加载路径在反序列化与复合端口同步之后，直接使用资源层 `ResourceManager.load_resource(ResourceType.GRAPH, ...)`/`GraphResourceService.load_graph` 产出的已布局数据（含跨块复制、副本去重与基本块信息），不在 UI 层重复调用 `engine.layout.LayoutService.compute_layout`，确保编辑器视图与 `app/runtime/cache/graph_cache` 中的布局保持一致，避免“第二次布局”产生多余副本或视图与缓存不一致。
  - 默认运行于**逻辑只读模式**：屏蔽添加/删除/连线等会改变节点图结构的命令，自动保存不响应场景逻辑变更；显式保存时会从磁盘重新加载已有 `GraphConfig`，仅在允许的字段发生变化时合并并写回，不改动节点/连线/常量等逻辑：
  - 合并节点图变量 `graph_variables`（在当前 UI 策略下，变量编辑控件默认处于禁用或只读状态，避免从界面触发落盘写入）
  - 合并允许的元信息：`graph_name`、`metadata`（例如统计时间等），用于与属性面板的元信息编辑保持一致
  - 若检测到仅逻辑结构（节点/连线/常量）发生变更而变量与元信息未变，则在只读模式下拒绝保存并将状态标记为“未保存”，同时通过信号提示 UI，这类逻辑修改需要在非只读上下文中由外部工具处理。
  - 只读模式下：不在加载/保存后触发 UI 层的 `validate_current_graph()`，以避免不必要的校验提示；仍保留保存时的往返验证，用于保障外部文件变更的正确性。
- 切换到编辑页面后：默认不自动 `fit_all()`（避免超大图进入“压缩状态”且触发全量边界计算带来的卡顿），加载完成后仅将镜头轻量居中到场景内容中心（默认不改变缩放；若当前缩放极小会先恢复为默认缩放以避免“打开即压缩”）。若用户在设置中显式开启 `settings.GRAPH_AUTO_FIT_ALL_ENABLED`（自动适配全图/压缩视图），则进入编辑器与自动排版完成后会恢复旧行为自动执行 `GraphView.fit_all()`；手动总览默认快捷键为 Ctrl+0。
  - 提供 `refresh_persistent_cache_after_layout()`：在自动排版完成后由视图层回调触发，通过 `ResourceManager.update_persistent_graph_cache_from_model(graph_id, model, layout_changed=True)` 刷新持久化缓存（覆盖旧缓存，result_data 结构由资源层统一组装并补齐 node_defs_fp/layout_settings 等），随后通过 `graph_runtime_cache_updated(graph_id)` 信号通知主窗口统一失效上层缓存（GraphDataService 的 GraphModel/payload 缓存、图属性面板数据提供器等），避免 UI 中分散维护“需要清一串缓存”的链条；排版完成后不强制改变镜头，保持用户当前视图与缩放，下一次加载直接使用最新布局位置（不修改源 .py）。
  - 提供一次性排版前准备：`schedule_reparse_on_next_auto_layout()` + `prepare_for_auto_layout()`，用于在“数据节点跨块复制”从 True→False 后的首次自动排版前清缓存并从 `.py` 重解析；当触发了“重解析+重载”时，`prepare_for_auto_layout()` 会返回 True 并记录 pending 标记，使自动排版延后到图加载完成后自动触发（避免 AutoLayout 在旧模型上运行）。
  - 提供 `rebuild_scene_for_settings_change(preserve_view=True)`：在不影响会话 baseline/dirty 的前提下，基于当前模型重建 `GraphScene` 与图元，用于设置页切换 fast_preview/行内常量控件虚拟化等画布性能开关后“点确定立即生效”。
  - 通过 `app.ui.graph.scene_builder.populate_scene_from_model()` 批量装配场景，编辑器与只读预览共用同一装配逻辑，避免多处维护 `for node in model.nodes` 循环以及 `is_bulk_adding_items` 标记。
  - 提供 `close_editor_session()`：保存当前图后重置模型/场景/视图并清空 `current_graph_id`，用于设置页“清除缓存”等场景将用户送回节点图列表，确保内存与文件监控彻底脱钩。
  - 在场景批量装配完成后，会基于 `GraphModel.metadata["signal_bindings"]` 与当前包视图的 `signals` 字段，统一触发信号节点端口同步入口，为“发送信号/监听信号”节点追加缺失的参数端口并刷新端口类型，使节点图编辑器在重新打开已有图时也能立即反映最新的信号定义。
  - 对于早期写入的 `graph_cache`（仅记录 `signal_schema_hash` 但尚未补全参数端口），加载阶段会在哈希匹配但检测到发送/监听信号节点缺少定义中参数端口时强制重跑一次信号端口同步，从而修复节点图库/编辑器中动态参数端口缺失的问题，并为后续持久化缓存刷新提供已补全的模型结构。
  - 大图非阻塞加载：当节点/连线规模超过阈值时，控制器改用“后台准备 + 主线程增量装配”——后台线程 `GraphPrepareThread` 执行 GraphModel 反序列化/语义 pass 等 CPU 密集步骤；主线程通过 `scene_builder.IncrementalScenePopulateJob` 以 time-budget 分帧创建图元并刷新进度；进度条会额外纳入批量装配收尾阶段的“延迟端口重排”（整理端口布局），避免节点/连线计数到 100% 后仍在忙导致的卡顿错觉；全程通过 `GraphView.loading_overlay` 展示状态并阻断交互，且使用 generation/取消机制避免旧任务覆盖新加载结果。
    - 图规模估算 `_estimate_graph_size_from_data` 兼容 `GraphModel.serialize` 的 nodes/edges 列表格式（以及旧的 dict 形式），保证超大图能稳定命中非阻塞加载策略。
  - 运行期画布缓存：控制器维护 GraphScene LRU 缓存（`settings.GRAPH_SCENE_LRU_CACHE_SIZE`，默认2，0禁用）用于同进程 A→B→A 秒切回，避免反复装配/重建 `QGraphicsItem`；缓存项严格绑定 graph 文件 mtime、node_defs_fp、layout_settings 与影响图元结构的画布开关（fast_preview/批量边/常量虚拟化等）以及 `EditSessionCapabilities`，任一不兼容则回退到正常加载；设置变更与 `close_editor_session()` 会清空缓存释放内存。
- 当前图验证：通过 `engine.validate.ComprehensiveValidator` 执行，`GraphEditorController.validate_current_graph()` 使用 `ComprehensiveValidator.validate_graph_for_ui(...)` 将结构规则与挂载/作用域/结构告警/端口一致性统一成 UI 可用的问题列表（含节点级 detail 用于高亮）。
- `navigation_coordinator.py`：跳转协调（任务清单、验证面板、预览窗口、实体间跳转），以 `app.models.ui_navigation.UiNavigationRequest` 作为统一的“导航意图”数据模型，将来自任务清单 detail_info、验证问题 detail、图属性引用、图库/项目存档页点击以及管理面板等来源的原始上下文封装为 `UiNavigationRequest` 后，通过单一入口 `handle_request()` 解析出目标 `ViewMode`、需要选中的资源（模板/实体摆放/关卡实体/管理 Section）以及是否需要打开节点图并定位到节点或连线；detail_info 关键字段（如 `type/graph_id/node_id`）统一通过 `app.models.todo_detail_info_accessors` 读取，避免散落 dict 直读；节点图数据解析与加载统一通过 `app.runtime.services.graph_data_service.GraphDataService`（内部桥接 `graph_data_key` 进程内缓存），其中 **UI 线程只读取 payload 缓存**，需要磁盘加载时由后台线程完成，数据就绪后再发出 `open_graph`，避免超大图读盘/解析阻塞 UI。
- `validation_graph_code_service.py`：验证页面的“节点图源码校验”服务，校验编排统一复用 `engine.validate.graph_validation_orchestrator.collect_validate_graphs_engine_issues(...)`（与 CLI 同口径），并负责 EngineIssue→ValidationIssue 的 UI 适配（file/line_span/错误码与跳转 detail）；其中 **scope=package（当前存档）仅纳入当前存档节点图源码中实际引用到的“复合节点库 .py 文件”**，避免无关复合节点问题污染验证面板；scope=all 的默认 targets 收集与路径归一化/相对路径显示复用 `engine.validate.graph_validation_targets`（与 CLI 同一真源），全量覆盖资源库多根目录下的节点图源码与复合节点库。
- `file_watcher_manager.py`：文件系统监控与冲突解决的主窗口侧门面（facade），统一使用 `QFileSystemWatcher` 监听当前节点图 `.py` 文件与资源库目录树：整体链路坚持“目录事件→后台算指纹→对比基线→触发主窗口统一刷新入口”的单向确认，避免目录事件误触发刷新；**watcher 侧不提前推进指纹基线**，基线仅由主窗口 `refresh_resource_library()`→`ResourceRefreshService`→`ResourceManager.rebuild_index()` 在“失效 + 重建成功”后更新。具体实现按职责拆分到 `ui/controllers/file_watcher/`：`GraphFileWatchCoordinator` 负责图文件变更去抖、watcher 恢复、冲突检测与重载后视图状态恢复/撤销栈清理；`ResourceWatchRegistry` 负责资源库目录递归扫描（事件循环启动后后台扫描）与主线程分批 `addPath`，并在 `directoryChanged` 后增量补齐新目录 watcher；`ResourceAutoRefreshBridge` 负责将 `resource_library_auto_refresh_state_machine.py` 的纯逻辑动作桥接到 Qt 计时器/线程与主窗口刷新回调，并在 watcher 无法覆盖全部目录时启用“周期性指纹复核”兜底以降低漏刷新概率。执行线程运行期间可通过 `begin_execution_suppression()/end_execution_suppression()` 临时抑制 watcher 事件与自动刷新，避免本地文件更新打断执行。
  - 目录事件聚合：`directoryChanged` 会先进入队列并按固定最小延迟合并一轮（对同目录去重），再统一交给 `ResourceWatchRegistry` 与 `ResourceAutoRefreshBridge` 处理；避免目录事件风暴在 UI 线程中频繁触发“去抖调度/日志刷屏/线程启动”，导致卡顿或卡死。
  - 目录过滤策略：由 `ui/controllers/file_watcher/resource_watch_policy.py` 提供 `ResourceWatchPolicy`（单一真源），供 directoryChanged 过滤 / watcher 注册 / 扫描剪枝共同复用，避免多处实现分叉。
  - 退出稳定性：`QFileSystemWatcher` 必须归属到 `FileWatcherManager`（Qt parent 关系），避免退出阶段 Python GC/Qt 析构顺序不确定导致 `access violation`；后台扫描/指纹计算使用 QThread 子类并支持 `requestInterruption()`，在 `cleanup()` 中等待退出。
  - 诊断：对资源库 `directoryChanged` 事件做低频聚合输出（计数 + 最近目录 + ignored 计数），用于排查“目录事件风暴导致刷新风暴/卡死”的场景；其中对非资源目录子树的事件会被过滤（不触发自动刷新/增量扫描），避免解析产物/工具输出目录导致无意义的指纹扫描。
  - 日志分层：watcher 的“开始/停止监控、单次 fileChanged、目录监控建立/清理”等高频细节默认输出到 `log_debug`（由 `settings.DEBUG_LOG_VERBOSE` 控制），避免启动与正常使用时刷屏；面向用户的行为仍通过 toast 与上层刷新摘要呈现。
  - 刷新后台化协作：资源库刷新改为后台任务后，`FileWatcherManager` 通过 `notify_resource_refresh_started()/notify_resource_refresh_completed()` 将“实际刷新任务开始/结束”回传给自动刷新状态机，保持刷新互斥与 pending 合并语义正确（避免回调快速返回导致状态机误判“刷新已完成”）。
  - watcher 作用域：共享目录始终监听；项目存档目录只监听当前 `package_id`（存档切换时会重建 watcher），避免其它项目的文件更新触发自动刷新与卡顿/崩溃风险。
- `resource_library_auto_refresh_state_machine.py`：资源库自动刷新纯逻辑状态机（事件→状态→动作），并将“刷新互斥 / 指纹复核 / 内部写盘抑制”做成可测试组件；目录文本规范化统一复用 `engine.utils.path_utils.normalize_slash`；内部写盘抑制支持“按目录粒度”缩小忽略范围（节点图保存仅抑制其所在目录，整包保存可沿用全局抑制），降低误吞其它目录外部新增资源事件的概率；对应最小回归在 `tests/ui/test_resource_library_auto_refresh_state_machine.py`。
  - 节点图文件变更处理采用可取消的单次计时器做去抖（合并 200ms 内的多次 fileChanged），避免重复触发重载；并在延迟回调中尝试恢复对图文件路径的 watcher，以兼容部分编辑器的“原子写入/重命名覆盖”保存方式导致的 watcher 丢失。
  - `cleanup()` 设计为幂等：支持被安全调用多次；信号断开使用“按槽函数精确 disconnect + 连接状态标记”，避免重复 disconnect 抛错；不再依赖 `__del__` 触发清理，资源释放统一由窗口关闭流程负责调用。
- `graph_error_tracker.py`：节点图错误状态跟踪（单例模式，记录保存失败的节点图）

## 注意事项补充
- 节点添加等图编辑命令统一通过 `app.ui.graph.graph_undo` 中的 UI 级命令类封装，并交由场景的 `UndoRedoManager` 管理，控制器层不直接依赖引擎内部的模型级命令实现。
- 用户提示与确认对话框统一走 UI 层封装：控制器自身不直接实例化 `QMessageBox`，而是通过 UI 控件的 `ConfirmDialogMixin` 或 `app.ui.foundation.dialog_utils` 暴露的函数触发弹窗，确保消息样式和行为与整体主题一致；涉及简单文本或类型选择时，同样应优先复用 `app.ui.foundation.input_dialogs` 提供的标准输入对话框，而不是直接使用 `QInputDialog`。

## 设计原则
- **单一职责**：每个控制器只负责一个功能域
- **信号通信**：控制器之间和控制器与UI之间通过PyQt6信号槽通信，避免直接依赖
- **依赖注入**：控制器通过构造函数接收必要的依赖（资源管理器、模型等）
- **回调函数**：对于需要访问主窗口状态的场景，使用lambda回调函数代替直接引用
- **异常处理约定**：不使用 `try/except` 掩盖错误；遇到错误直接抛出，由上层统一处理或中止流程，避免隐性回退或降级逻辑

## 信号设计规范

### PackageController 信号
- `package_loaded(str)` - 项目存档加载完成，传递package_id
- `package_saved()` - 项目存档保存完成
- `package_list_changed()` - 项目存档列表发生变化
- `title_update_requested(str)` - 请求更新窗口标题
- `request_save_current_graph()` - 请求保存当前编辑的节点图

### GraphEditorController 信号
- `graph_loaded(str)` - 节点图加载完成，传递graph_id
- `graph_saved(str)` - 节点图保存完成，传递graph_id
- `graph_validated(list)` - 节点图验证完成，传递问题列表
- `validation_triggered()` - 触发验证
- `switch_to_editor_requested()` - 请求切换到编辑页面
- `title_update_requested(str)` - 请求更新窗口标题
- `save_status_changed(str)` - 保存状态变化（"saved" | "unsaved" | "saving" | "readonly"）

### GraphErrorTracker 信号
- `error_status_changed(str, bool)` - 错误状态变化（graph_id, has_error）

### NavigationCoordinator 信号
- `navigate_to_mode(str)` - 导航到指定模式
- `select_template(str)` - 选中模板
- `select_instance(str)` - 选中实体摆放
- `select_level_entity()` - 选中关卡实体
- `open_graph(str, dict, object)` - 打开节点图
- `focus_node(str)` - 聚焦到节点
- `focus_edge(str, str, str)` - 聚焦到连线
- `load_package(str)` - 加载项目存档
- `switch_to_editor()` - 切换到编辑器
- `open_player_editor()` - 打开玩家编辑器
- `select_player_template(str)` - 选中战斗预设玩家模板
- `select_player_class(str)` - 选中战斗预设职业
- `select_skill(str)` - 选中战斗预设技能
- `select_composite_name(str)` - 选择复合节点（按名称）
- `focus_management_section_and_item(str, str)` - 管理配置定位（section_key, item_id；item_id 允许为空表示仅切换 section）

### FileWatcherManager 信号
- `reload_graph_requested()` - 请求重新加载节点图
- `show_toast(str, str)` - 显示Toast通知（消息, 类型）
- `conflict_detected()` - 检测到冲突
- `graph_reloaded(str, dict)` - 节点图已重新加载（graph_id, graph_data）
- `force_save_requested()` - 强制保存本地版本

## 面向开发者的要点
- **避免循环信号**：确保信号连接不会造成循环触发，必要时使用`blockSignals()`
- **状态同步**：控制器间的状态通过信号同步，避免直接访问其他控制器的属性
- **空指针检查**：所有控制器方法都应检查必要的依赖是否已初始化
- **错误传播**：控制器内的错误通过信号传递给主窗口处理，或直接抛出
- **回调函数设置**：某些控制器需要访问主窗口状态，通过`get_xxx`回调函数实现（在主窗口的`_setup_controllers`中设置）

## 数据流示例

### 项目存档加载流程
1. 用户在下拉框选择项目存档 → 主窗口的“切包请求入口”（负责未保存保护与取消回滚下拉框）
2. → `PackageController.load_package(package_id, save_before_switch=...)`
3. → `PackageController.package_loaded` 信号
4. → `MainWindow._on_package_loaded` 更新UI组件

补充：切换存档时 `PackageController.load_package` 会在重建 `ResourceManager` 当前作用域索引后，显式失效该存档的 `PackageIndex` 派生缓存（`PackageIndexManager.invalidate_package_index_cache`），避免“在共享视图作用域下派生出的空资源列表”被复用，导致节点图库等页面只显示共享资源。

### 节点图编辑流程
1. 用户在属性面板双击节点图 → `TemplateInstancePanel.graph_selected` 信号
2. → `MainWindow._on_graph_selected`
3. → `GraphEditorController.open_graph_for_editing`
4. → `GraphEditorController.switch_to_editor_requested` 信号
5. → `MainWindow` 切换到编辑页面
6. → `GraphEditorController.load_graph` 加载图数据

### 跳转流程（集中使用 UiNavigationRequest）
1. 用户在任务清单选中任务 → `TodoListWidget.jump_to_task` 信号（自动触发，携带 detail_info）
2. → `MainWindow.UISetupMixin._create_todo_page` 将 detail_info 包装为 `UiNavigationRequest(resource_kind="graph_task", origin="todo", payload=detail_info)` 并调用 `NavigationCoordinator.handle_request()`
3. → `NavigationCoordinator._handle_graph_request/_handle_graph_todo_detail`：根据 `detail_info.type` 与 `graph_id/template_id/instance_id` 决定切换到元件库/实体摆放/图编辑器/复合节点管理等模式，并通过 `open_graph` 与后续的 `_locate_graph_element` 在编辑器内完成节点/连线定位
4. → 验证面板、图属性面板、节点图库与项目存档页等其它导航源同样通过各自的 UISetupMixin 回调将业务上下文转成 `UiNavigationRequest`，统一交给 `NavigationCoordinator.handle_request()` 决定 `ViewMode` 切换与右侧属性/图属性面板的资源选中；`NavigationCoordinator` 不直接依赖任意具体 Widget 结构，只通过信号与主窗口及控制器协作完成跳转

## 注意事项与边界条件
- 控制器不直接操作UI组件，所有UI操作通过信号委托给主窗口。
- 控制器可以访问数据模型和资源管理器。
- 主窗口作为信号连接的中枢，在 `_connect_controller_signals` 中集中管理所有连接。
- 控制器之间的通信必须通过主窗口中转，不允许控制器直接引用其他控制器。
- `PackageController.save_package()` 保存存档时，需要确保任何仅存在于 `PackageView` 视图模型中的包级配置（例如信号配置、管理配置）都已序列化回写到对应的 `PackageIndex` 字段与管理配置资源文件，避免编辑器关闭后这些配置只停留在内存缓存中而未写入索引/资源库。
- **文件监控与场景刷新**：当复合节点库更新触发场景刷新时（`_refresh_current_graph_display()`），必须清除 undo_manager 历史，避免文件监控误判为有本地修改。
- **最近打开的选择**：支持记录并恢复 `<共享资源>`（`global_view`）模式，重启后会回到该模式。
- **加载性能建议**：加载大图时，先将 `GraphView.setUpdatesEnabled(False)`、`scene.undo_manager.on_change_callback=None`、`scene.on_data_changed=None`，并把 `QGraphicsScene.ItemIndexMethod` 设为 `NoIndex`；批量添加节点与连线完成后，由控制器统一调用场景的重建入口（重算场景矩形与小地图缓存），再恢复为 `BspTreeIndex`、恢复回调并启用视图更新，最后 `viewport().update()` 一次性刷新，避免在批量添加阶段对每个节点执行全图边界统计。
- **自动保存防抖**：非只读模式下，自动保存受到 `engine.configs.settings.Settings.AUTO_SAVE_INTERVAL` 控制（单位秒；0 表示每次修改立即保存），使用单次计时器合并短时间内的频繁修改。
- **小地图位置更新**：加载完成后使用 `ViewAssembly.update_mini_map_position(self.view)` 更新小地图位置。
- 资源访问：统一使用 `engine.resources.*`（`PackageView/GlobalResourceView`）。

## 当前状态
- 控制器层已稳定承担“主窗口业务逻辑分离”的角色，主窗口聚焦于视图装配与信号连接。
- 节点图加载、保存、验证、导航等关键交互均通过专门控制器协作完成，便于后续扩展与测试。
- 与 UI 术语对齐：用户可见文案统一使用“项目存档”指代 package（新建/切换/导入/导出/验证等入口）。

---
注意：本文件不记录任何修改历史。请始终保持对"目录用途、当前状态、注意事项"的实时描述。

