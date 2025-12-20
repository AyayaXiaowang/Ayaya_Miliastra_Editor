## 目录用途
- 承载任务清单子系统的 UI 与轻量逻辑，包括左侧任务树、右侧详情面板、节点图预览、执行桥接与导航等组件。
- 通过 `TodoItem` 与相关模型与 `app.models` 协作，仅负责呈现与交互，不直接读写资源文件或驱动自动化执行器的底层实现。

## 当前状态
- 关键入口：
  - `todo_list_widget.py`：任务清单页面宿主组件，负责组装树、详情与预览面板，并与主窗口/导航控制器协作。
  - `todo_tree.py` 及辅助模块：构建与刷新任务树、三态复选框、样式与懒加载逻辑；树节点的 tooltip 会附带与图相关步骤对应的源码提示，便于从任务项直接反查生成/执行逻辑位置。
    - `todo_tree_source_tooltip.py`：图步骤的源码定位 tooltip 构建与缓存（文件路径、关联节点、行号推导）。
    - `todo_tree_node_highlight.py`：节点联动高亮/置灰（从图到步骤的反向联动），Presenter 只维护状态字段并编排调用。
- `todo_detail_model.py` / `todo_detail_renderer.py` / `todo_detail_panel.py`：基于无 Qt 依赖的 `DetailDocument` 结构构建任务详情文档，由 `TodoDetailView` 负责将文档渲染为 Widget 视图，并承载与执行相关的辅助信息（包括对图步骤的源码路径说明）。
  - `todo_detail_renderer.py` 仅保留入口 `TodoDetailBuilder.build_document()`，具体按 `detail_type` 的构建逻辑通过 registry 分发到 `detail_builders/` 插件模块中，避免长链 if/elif 集中冲突。
  - `todo_detail_panel.py` 现以结构化文档和 TodoDetailView 渲染详情，无 HTML 依赖，描述与实现保持一致；详情视图统一使用 Theme token 的字号/颜色并强制 PlainText，避免 QLabel 再次走富文本解析。
  - `todo_preview_controller.py`：节点图只读预览与高亮/聚焦控制，基于 detail_type → handler 的映射。
  - `todo_execution_service.py` 及相关适配/桥接模块：规划“整图/事件流/单步”执行序列，纯逻辑实现，不依赖 Qt。
- 所有模块按照“薄 UI + 纯逻辑服务”的方式拆分，UI 部分只做布局和信号连接，复杂流程集中在无 Qt 依赖的服务或适配层中。

## 注意事项
- 不在本目录中使用 `try/except` 吞掉异常，异常按原样抛给上层，由主窗口或测试代码决定处理方式。
- 新增功能时优先放入独立的服务或适配模块，由 Widget 通过清晰的接口调用，避免在单个 UI 文件中堆叠过多业务逻辑。
- 与节点图预览或执行相关的扩展，应通过现有控制器与服务（如 `TodoPreviewController`、执行规划服务与执行桥接模块）协同完成，而不要直接访问自动化内核或全局状态。
- 从图编辑器进入任务清单的“无缝体验”要求：跳转时应尽可能在同一帧将共享画布挂到预览页（`TodoPreviewPanel.show_shared_canvas_now()`），避免使用较大的 QTimer 延迟导致用户视觉上感知为“画布重新打开”。
- 从主窗口获取稳定依赖（workspace_path/节点库/ResourceManager 等）时，应通过 `main_window.app_state` 访问，避免依赖 `main_window.workspace_path/main_window.library/...` 这类旧式兼容别名。
- 执行监控面板的访问与显隐统一通过 `main_window.right_panel`（tab_id=`execution_monitor`）；任务清单不再依赖主窗口上额外挂的面板别名属性。
- 运行时（`python -m app.cli.run_app`）sys.path 默认不包含 `.../app`，因此 **app 内部必须统一使用 `app.ui.*` 导入路径**，不要在 app 包内部写 `ui.*` 导入。
- pytest 不应将 `<repo>/app` 加入 `sys.path`，因此 **`ui` 不是顶层包**；测试与应用代码统一使用 `app.ui.*` 导入路径，避免 `ui.*` 与 `app.ui.*` 双导入导致类对象不一致。

## 目录用途

`app/ui/todo/` 目录承载**任务清单页面的所有子组件**，负责在 UI 层展示/操作由 `app.models.todo_generator` 生成的 Todo 列表，并与执行子系统、图预览以及主窗口进行桥接。

- `todo_list_widget.py`：任务清单主组件（左侧树 + 右侧详情/预览），负责 UI 布局、对外接口与信号桥接，提示逻辑统一通过 `ui_notifier.notify` 进行 Toast 输出。
- `todo_list_orchestrator.py`：任务清单编排层（`TodoListOrchestrator`），集中负责子组件创建、信号连线、执行入口分发以及识别回填联动，宿主只持有轻量状态并将领域逻辑委托给该类。
- `todo_tree.py`：树数据与样式管理，包括懒加载节点图步骤、三态复选框、运行态状态着色和 BasicBlock 分组头节点；图相关类型/根判断统一依赖 `StepTypeRules`，不再直接硬编码 `detail_info["type"]` 字符串。
  - `todo_tree_source_tooltip.py`：图步骤源码定位 tooltip（含缓存与行号推导）。
  - `todo_tree_node_highlight.py`：节点联动高亮/置灰（供预览面板点击节点时复用），`TodoTreeManager` 仅保留对外 API 与状态字段维护。
-- `todo_detail_panel.py`：右侧详情页，基于 `TodoDetailAdapter` 与 `TodoDetailBuilder` 构建 `DetailDocument` 并通过 `TodoDetailView` 渲染结构化详情和统计信息，所有明细内容统一放在单一滚动区域中，内部表格按内容高度展开且关闭自身滚动条，由详情页整体负责滚动；面板顶部提供标题/描述与执行按钮区域，文档分节标题仅在需要补充层级语义时展示，表格复用 `ThemeManager.table_style()`、交替行配色与统一行高。
-- `todo_preview_panel.py`：预览面板的“图相关步骤”使用 **全局唯一 `app_state.graph_view`** 作为画布，通过 Host 容器在 `ViewMode.TODO` 的预览页与 `ViewMode.GRAPH_EDITOR` 之间移动，实现“跳转前后是同一张画布”的体验；高亮/聚焦仍由 `TodoPreviewController` 驱动，但共享画布场景下不再单独重建 `GraphScene`；进入预览会强制 `EditSessionCapabilities.read_only_preview()` 以保证任务清单中的画布不可编辑（含禁用行内常量编辑控件与隐藏自动排版入口），切回编辑器时由主窗口恢复编辑器右上角按钮与交互能力；“复合节点步骤”仍使用独立只读画布预览其子图，避免将非 Graph 资源的子图加载到编辑器会话里造成落盘语义混淆。
- `todo_executor_bridge.py`：执行桥接层，将 UI 执行入口（图根/事件流根/复合节点/叶子步骤）统一映射到 `ExecutionRunner + EditorExecutor`，并回填运行态状态与树勾选；具体“当前根/锚点步骤/执行序列”的规划逻辑下沉到 `todo_execution_service.py`，本模块负责图数据解析与执行监控面板 wiring，同时在启动执行时将所用的 `EditorExecutor` 注入到监控面板，使执行线程与“检查/定位镜头/拖拽测试”等功能共享同一份执行器实例与视口状态。执行桥接层仅依赖主窗口的 `right_panel.ensure_visible("execution_monitor", ...)` 与 `ExecutionMonitorPanel.set_context/set_shared_executor` 等公开 API，不再通过 `getattr/hasattr` 反射探测协作。连续执行（整图/剩余步骤）结束后会恢复到本轮起始上下文，单步执行结束后则保留当前选中步骤不做额外跳转。运行过程中任务树的“当前步骤选中”以 `step_will_start` 事件驱动，不在 `step_completed` 时按 UI 展示顺序强行跳转，避免与重试/跳过等运行时策略错位。
- `todo_runtime_state.py`：叶子步骤运行态（failed/skipped）的集中状态机，供 `TodoTreeManager` 决定文本样式与 Tooltip。
- `current_todo_resolver.py`：**统一的"当前 Todo"解析器**，将解析规则收敛到单一模块，避免编排层和桥接层各自实现一套优先级策略；解析结果被 `TodoListOrchestrator` 与 `TodoExecutorBridge` 通过 `CurrentTodoContext` 统一消费。
- `todo_execution_service.py`：Todo 执行规划领域服务（纯逻辑，不依赖 Qt），负责在给定 `CurrentTodoContext/todo_map` 与若干查找回调的前提下，解析模板图根/事件流根，构建“从此步起执行剩余步骤”的连续执行序列，以及“严格仅执行当前一步”的单步执行计划，并在类型不支持自动执行时返回结构化错误信息供 UI 提示使用。
- `todo_widgets.py`：任务清单页面内复用的小部件与控件工厂，目前提供统一的执行按钮创建函数，默认文案为“执行当前步骤”，由上层根据 `StepExecutionProfile` 在“叶子图步骤/模板图根/事件流根/复合节点步骤”等不同语义之间切换更贴切的中文文案，同时集中管理最小高度等视觉约定。
- 其它辅助模块（如 `todo_context_menu.py`、`todo_rich_item_delegate.py` 等）负责右键菜单、基于 tokens 的行内着色与局部样式，不直接依赖执行器实现。

- 任务清单执行按钮文案策略：详情面板与预览面板共用一套基于 `StepExecutionProfile` 的文案计算规则，事件流根场景下主按钮显示“执行整个事件流”，辅按钮显示“执行剩余事件流”，叶子图步骤场景下则分别显示“执行当前步骤”和“执行剩余步骤”。
- 事件流相关连续执行：执行桥接层在事件流根上下文下除了支持单个事件流执行外，还支持从当前事件流起串行执行同一节点图下的剩余事件流序列，具体步骤列表由 `ExecutionPlanner.plan_steps` 在每个事件流根上规划后串联得到，根解析逻辑仍统一依赖 `todo_execution_service` 与 `current_todo_resolver`。

## 当前状态

- 任务清单已按职责拆分为"树管理（TodoTreeManager）+ 详情面板 + 预览面板 + 执行桥接 + 运行态状态机"的组合，`TodoListWidget` 作为薄宿主，通过 `TodoListOrchestrator` 完成子组件创建与信号 wiring。
- **"当前 Todo"解析逻辑已统一收敛到 `current_todo_resolver.py`**，编排层（`TodoListOrchestrator`）和桥接层（`TodoExecutorBridge`）都通过该模块解析当前要执行的 Todo，不再各自实现解析规则。统一优先级：
  1. 树选中项（与用户视觉上的"当前任务"一致）
  2. `current_todo_id`（由详情面板/外部跳转维护）
  3. `detail_info` 全量匹配（用于外部联动/旧上下文恢复）
  4. `graph_id` 兜底（用于任务清单刷新后 ID 发生变化的情况，仅叶子步骤执行）
- 图数据加载与预览复用 `app.runtime.services.graph_data_service.GraphDataService`、`TodoPreviewController` 与 `TodoTreeGraphSupport`：GraphDataService 统一负责图资源加载（GraphConfig/graph_data）、GraphModel 缓存签名失效，并桥接 `graph_data_key` 的进程内临时 payload 缓存；TreeSupport 负责从模板图根 Todo 解析并按需加载图数据；节点库与布局模型来源统一依赖 `engine.resources` 和 `engine.graph`，避免在 UI 层重复解析资源。
  执行场景下的图数据解析统一收敛到 `graph_data_resolver.py`，该模块会先根据当前执行上下文解析期望的 `graph_id`，仅在预览面板当前图的 `graph_id` 与之匹配时复用 `current_graph_data`，否则按“预览控制器 → TreeManager 图根加载 → graph_data 缓存”这一顺序解析 graph_data，确保执行始终基于与任务清单一致的图数据。
  - 本目录中的预览/执行数据解析不再直接 import `app.common.in_memory_graph_payload_cache`，所有对 `graph_data_key` 的解析统一通过 `GraphDataService.resolve_payload_graph_data()` 桥接，避免 UI 侧产生新的“缓存失效入口”。
- 右侧"执行监控"面板与任务清单通过 `TodoExecutorBridge` 以及主窗口的 `right_panel`（tab_id=`execution_monitor`）解耦：执行桥接层负责注入执行上下文并优先复用监控面板内部维护的共享 `EditorExecutor`（工作区一致时），保证执行线程与“检查/定位镜头/拖拽测试”在同一工作区下共用一套坐标映射与识别缓存；识别回填信号统一通过 `TodoPreviewPanel.wire_recognition_from_monitor_panel()` 幂等绑定并透传到 `TodoPreviewPanel.recognition_focus_succeeded`，外层只需监听一次，避免重复回调。
- 任务清单右侧图预览在只读模式下支持“从图到步骤”的反向联动：单击预览中的某个节点，会自动在左侧树中定位到该节点的创建步骤，并高亮所有与该节点相关的配置和连线步骤，同时将与该节点无直接关联的其它步骤统一置灰，强化视觉聚焦；单击预览空白处会清除这类联动高亮与置灰效果，不影响当前树选中项。
  - 置灰与高亮均采用 **role 驱动的差量更新**（`DIMMED_ROLE` + 局部背景/前缀 token），避免每次点击触发整树样式刷新与全量 repaint；富文本委托在 tokens 缺失时同样可按 `DIMMED_ROLE` 绘制置灰，因此不需要通过 `setForeground()` 破坏基础样式。
  - 预览图侧的灰显（opacity）同样以场景缓存做差量更新，避免连续点击时反复全量遍历所有节点/连线。
  当节点图在编辑器中自动排版或外部刷新后，任务清单预览会优先复用当前 `GraphEditorController` 已加载的场景；当用户在任务清单中切换到不同 `graph_id` 时，通过 `graph_controller.load_graph(...)` 重建场景以反映最新布局与元数据。
- 识别联动（执行监控“定位镜头”回调）统一由 `TodoListOrchestrator.on_recognition_focus_succeeded` 处理：根据可见节点 ID 与当前预览图定位事件流根与最新可见创建步骤，并仅对图相关叶子步骤执行“自动勾选已完成”；自动勾选通过 `TodoTreeManager.set_leaf_checked_silent()` 更新 todo_states 与样式但不发出 `todo_checked`，避免触发“每次勾选都立即落盘”的路径；父级/分组节点三态由 `TodoTreeManager` 根据叶子状态反推。
- 事件流根（`event_flow_root`）的子步骤展示按 BasicBlock 分组：由 `todo_event_flow_blocks` 基于 GraphModel.basic_blocks 解析每个子步骤所属块索引并生成逻辑分组，`TodoTreeManager` 依据这些分组在树中创建块头节点并挂载子步骤；仅当至少有一个步骤具备块信息时才启用分组视图，block_index 为 `None` 的分组保持直接挂在事件流根下，其余分组通过逻辑块头节点承载，并支持块级高亮与预览聚焦；逻辑块分组头在任务树中使用对应 BasicBlock 的颜色作为文字配色，并在选中时叠加统一选中背景，使其与图画布中的逻辑块矩形与编号标签在颜色感知上保持一致，整树重建时会自动清理块级高亮状态，避免保留指向已被删除树项的 UI 引用。
- 模板图根懒加载采用“上下文解析 → 生成 Todo → 补树”三段式流程：`TodoTreeManager` 通过宿主注入的依赖（约定为 `(package, resource_manager[, package_index_manager])`）与 Todo.detail_info 解析 `GraphConfig`，调用 `TodoGenerator.expand_graph_tasks` 扩展出图内步骤，并在树中按最新父子关系补充节点，确保 `todo_map/todos/树节点` 三者结构一致；当注入了 `package_index_manager` 时应优先透传，以复用索引缓存避免状态分叉。
  图步骤的 GraphModel 加载与缓存通过 `app.runtime.services.graph_model_cache` 进行简单封装：缓存以 graph_id 为主键，但会基于 graph_data 的稳定签名（包含节点位置）自动失效，避免“自动排版/刷新后仍复用旧 GraphModel”的幽灵问题；树支持类只维护本地缓存字典。
- 任务清单发起的各类执行入口在运行时会记录一次树形任务列表的父节点展开状态，并在执行结束后恢复，保证单步或连续执行不会意外改变用户当前浏览到的任务结构与选中位置。
- 端口类型推断适配器 `port_type_inference_adapter` 在图模型可用时，会为类型设置相关步骤提供基于节点定义、连线结构与结构体字段定义的类型解析：例如当通过“以键查询字典值”节点从结构体字段字典中读取某个字段时，可在任务明细中展示结构体中声明的规范类型（如 `GUID列表`），而不是简单地回落为字符串，便于在 Todo 树中直观看到更精确的数据类型；适配器通过 `NodeTypeHelper` 复用节点库，并实现与端口类型推断工具兼容的最小 executor 接口子集（如 `get_node_def_for_model` 与 `log`），在 UI 环境下无需引入 `EditorExecutor` 即可使用通用端口类型推断逻辑。

### 布局与尺寸

- `TodoListWidget` 使用水平 `QSplitter` 将页面拆分为**左侧步骤树**和**右侧详情/预览堆栈**：
  - 左侧步骤树默认宽度基于 `ThemeSizes.LEFT_PANEL_WIDTH` 略作放大，相比早期配置适度收窄，避免占用过多空间；相关数值集中在 `LayoutConstants.SPLITTER_LEFT_WIDTH`。
  - 右侧详情/预览区域的初始宽度与伸缩权重由 `LayoutConstants.SPLITTER_RIGHT_WIDTH/SPLITTER_RIGHT_STRETCH` 控制，在窗口整体变宽时优先获得更多宽度，保证详情文本和图预览的可读性。
  - 左右宽度仅作为初始值，用户仍可通过分割条自由拖拽调整。
  - 执行精简模式：`TodoListWidget.set_execution_compact_mode(True)` 会隐藏右侧详情/预览堆栈（含节点图预览）并压缩头部信息，用于执行场景。
    - 右侧堆栈会被强制压到宽度=0（min/max=0），避免在 `QSplitter` 中仅隐藏控件导致仍保留占位宽度，从而出现“步骤树两侧空白”。
    - 左侧步骤树在精简模式下不再被 maxWidth 限死：允许吃满当前可用宽度，避免因最大宽度限制+右侧占位导致中间出现空白区；同时仍通过 `splitter.setSizes([...])` 给出期望的初始窄宽度与更小的层级缩进。

## 核心 API 与约定

- **UI 上下文单一入口**：统一通过 `TodoUiContext` 获取主窗口依赖（`app_state/right_panel/package_controller`）、执行监控面板、`GraphDataService` 与 `CurrentTodoContext`；`TodoListOrchestrator`、`TodoExecutorBridge`、`TodoPreviewPanel` 只依赖该对象，不在各处散落 `getattr/hasattr` 与多入口兜底解析。
- **当前 Todo / 当前根解析**：统一使用 `current_todo_resolver` 提供的 `CurrentTodoContext`、`resolve_current_todo_for_leaf` 与 `resolve_current_todo_for_root`。本目录中不要手写一套“树选中 / current_todo_id / detail_info / graph_id”优先级逻辑。
- **执行步骤规划**：统一通过 `todo_execution_service` 的 `plan_template_root_execution`、`plan_event_flow_root_execution`、`plan_remaining_event_flows_execution`、`plan_execute_from_this_step`、`plan_single_step_execution` 构建执行序列：根/剩余步骤由规划器基于 todo_map 生成完整串联，单步执行则只返回当前叶子步骤本身，不在 UI 层直接基于 `children[start_index:]` 等方式裁剪步骤列表。
- **步骤类型语义判断**：所有 detail_type 相关判断（是否图根/事件流根/叶子图步骤/复合步骤、是否支持预览/执行剩余/自动勾选/右键执行）统一依赖 `todo_config.StepTypeRules`，不要在组件内维护自己的字符串集合。
- **图相关但不触发预览的步骤类型**：仅在详情中展示、不切换右侧图预览的图相关步骤类型集合集中维护在 `todo_config.TodoStyles.GRAPH_DETAIL_TYPES_WITHOUT_PREVIEW`，供预览控制器和详情渲染逻辑统一判断。
- **图数据解析**：执行或预览场景下获取 graph_data 时，统一通过 `graph_data_resolver.resolve_graph_data_for_execution(..., graph_data_service, current_package)`；`graph_data_service/current_package` 由 `TodoUiContext.get_graph_data_service()` / `TodoUiContext.try_get_current_package()` 提供，避免在 UI 层直接按 graph_id 访问 `resource_manager` 或操作 `graph_data_key`。
- **预览上下文解析**：从 Todo 推导 `(graph_data, graph_id, container)` 的规则统一收敛到 `preview_graph_context_resolver.resolve_graph_preview_context(..., graph_data_service, current_package)`（预览与执行共用）；不要在 `TodoPreviewController` 或各入口内手写一套“向上找 graph_id/graph_data/容器”的优先级逻辑。
- **识别回填创建节点解析**：跨模块若需要“从 `Todo.detail_info` 提取创建节点 ID”，统一调用 `recognition_backfill_planner.get_created_node_id_from_detail(...)`；不要导入下划线开头的私有函数（如 `_get_created_node_id_from_detail`），避免形成真实耦合点。
- **BasicBlock 块聚焦**：编排层如需基于“逻辑块分组头”计算块内节点集合，统一调用 `TodoTreeManager.collect_block_node_ids_for_header_item()`，不要访问 `TodoTreeManager._graph_support` 之类私有字段。
- **事件流根预览聚焦**：事件流根需要“节点集合”时，优先通过调用参数传递给预览控制器（`TodoPreviewController.focus_and_highlight_task(..., event_flow_node_ids=...)`），避免在 `todo.detail_info` 中写入临时字段。
- **运行态状态来源**：叶子步骤的 failed/skipped 等运行态统一由 `TodoRuntimeState` 维护，树样式与详情/预览面板只读取该状态，不各自保存一份运行态副本。
- **UI 层职责**：本目录下的 UI 组件应尽量只负责布局、信号连线和调用上述核心 API，将“选哪个 Todo、执行哪一串步骤、如何判断类型语义”等决策下沉到对应的纯逻辑模块中。

## 注意事项

- Todo 相关 UI 模块**不使用 try/except**；前置条件缺失（无图数据/无监控面板/无法定位叶子步骤）应通过执行监控日志或 Toast 明确暴露，而不是静默失败。
- 解析"当前要执行的步骤"时，**必须使用 `current_todo_resolver` 模块**，不要在各模块内重复实现解析逻辑。如需调整优先级规则，只需修改该模块；按图根加载 `graph_data` 时，应优先通过 `TodoTreeManager.load_graph_data_for_root` 或 `TodoTreeGraphSupport.load_graph_data_for_root`，不要在 UI 层直接操作 `resource_manager` 与 `graph_data_key`。
- 懒加载节点图步骤（`template_graph_root` 的子步骤展开）必须通过 `TodoTreeManager.expand_graph_on_demand` 触发，确保：
  - 新生成的 `TodoItem` 被写入 `todo_map` 与 `todos`；
  - 树节点与 Todo ID 一一对应；当检测到树中存在 todo_id 已不在最新 `todo_map` 中的树项时，`TodoTreeManager` 会强制整树重建，以避免懒加载残留导致的“幽灵步骤”或重复项；
  - 与包和资源访问相关的依赖统一在编排层通过 `TodoUiContext` 解析后注入到树/详情/预览/执行桥，避免在各模块中各自反查主窗口结构。
- 懒加载实现细节已收敛到 `todo_tree_graph_expander.py`，`TodoTreeManager` 仅保留薄封装入口，避免在树管理类中堆叠图扩展的资源解析与回填细节。
- 执行相关的 UI 入口（详情按钮、预览按钮、右键菜单）应尽量复用 `TodoExecutorBridge` 提供的高层方法，而不是直接构造或操作 `ExecutionRunner/EditorExecutor`，保持执行行为和监控联动的一致性。
- 修改任务清单相关逻辑时，优先在本目录内复用已有工具（如 `TodoTreeGraphSupport`、`TodoNavigationController`、`current_todo_resolver`），避免在主窗口或其它页面重新实现遍历、图数据解析或导航逻辑。
- 预览 handlers（`todo_preview_handlers.py`）只允许依赖 `TodoPreviewController` 的**公开 API**（无下划线方法）。严禁使用 `controller._xxx()` 私有方法名作为跨模块协议；如需新增预览能力，应先在 `TodoPreviewController` 上提供稳定公开方法，再由 handlers 调用。
- 任务清单整体样式集中在 `todo_config.TodoStyles` 中管理，`TodoStyles.widget_stylesheet()` 负责 `TodoListWidget` 的 QSS；新增或调整样式时应保持与 Qt 样式表语法兼容（如在 `color` 等属性上仅使用纯色值），避免应用启动时出现样式解析错误；父级步骤（如模板图根、事件流根以及模板/实例/战斗/管理类别等）在任务树中统一通过 `TodoTreeManager` 的父级样式应用逻辑使用类型配色：图根/事件流根使用 `StepTypeColors` 中的专用颜色，其它父级步骤使用 `TaskTypeMetadata` 中的任务类型颜色，叶子步骤仍按步骤类型与节点类别着色，保证在白底下父/子层级之间有清晰的颜色区分。
- 修改任务类型、颜色或图标时，请优先调整 `todo_config.py` 中的配置常量，不要在各组件内硬编码。
- 任务清单的运行态状态以 `TodoRuntimeState` 为权威来源，树控件与详情/预览面板应通过它同步状态。
- 预览节点图时依赖 `GraphView/GraphScene` 与执行监控面板，请确保在绑定监控上下文时正确传入工作区路径与当前图模型；叶子步骤与事件流根在解析预览上下文时会沿父链查找到对应的模板图根，以其 `graph_id` 与缓存 key 为准加载图数据。
- 预览聚焦动画具备节流：当连续聚焦请求间隔小于 `TodoStyles.PREVIEW_FOCUS_MIN_INTERVAL_MS` 时自动改为瞬时跳转，确保镜头移动不会拖慢下一步。
- UI 层不应吞掉异常，错误交由上层统一处理或直接抛出，保持调试信息可见。
 - 本目录代码不保留 `TODO/FIXME/HACK/workaround/临时/待改` 这类“待办标记”；若需要表达未来演进点，应通过 `StepTypeRules`/执行规划服务的公开 API + 测试用例固化规则，而不是在实现文件中散落注释标记。
- 步骤勾选交互遵循"**只认复选框**"原则：仅点击复选框本体会切换叶子步骤的勾选状态；点击行文本或空白区域只改变树项选中与右侧详情/预览，不会改变完成度。父节点（包含模板图根/事件流根以及 BasicBlock 分组头）本身不参与勾选逻辑，其三态与文本完全由叶子步骤的完成状态推导。
- 图相关步骤类型（图根/事件流根/叶子图步骤/复合步骤，以及“可预览/可自动勾选/支持富文本 token/支持右键执行”等能力标签）统一通过 `app.ui.todo.todo_config.StepTypeRules` 进行语义判断；新增或调整 detail_type 时，应优先在该类中补充语义，并优先通过 `StepTypeRules.build_execution_profile` 等集中方法获取执行相关标记，再在预览控制器、树支持或执行桥等处复用这些判断，避免在各组件内各自维护字符串集合。
- 图节点参数配置、端口类型设置以及多分支分支输出配置的只读“明细子项”挂载规则统一通过 `StepTypeRules` 和 `TodoTreeGraphSupport` 维护；参数配置步骤的虚拟子项以“配置「参数名」为「值」（类型）”的形式展示端口声明类型（例如（枚举）），端口类型设置步骤的明细子项则会基于图模型解析端口侧（左/右）与端口序号，并按“左侧优先、端口序号升序”的顺序输出文案（形如“设置左侧的端口1【某端口名】为【字符串】”）；多分支分支输出步骤的虚拟子项以“配置【端口N】为【值】”的形式按顺序展开各分支匹配值（N 从 1 开始，对应非默认输出端口的顺序），便于在树中快速总览配置内容；新增或调整相关 detail_type 时，应优先修改 `StepTypeRules` 中的语义判断，再在树/预览等处复用这些接口，避免在组件内各自维护独立集合。与信号/结构体相关的绑定步骤（`graph_bind_signal`、`graph_bind_struct`）在任务树中作为独立叶子步骤展示，由详情/预览与导航控制器负责高亮目标节点与展示当前绑定信息，实际绑定操作仍在节点图编辑器中完成。
- 模板级“添加组件”类 Todo 的详情渲染统一通过 `engine.configs.components.component_registry` 提供的通用组件注册表获取组件说明，保证与实体属性面板中的通用组件描述保持一致。


