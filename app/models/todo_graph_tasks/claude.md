## 目录用途
`todo_graph_tasks/` 目录负责“节点图任务”的细粒度拆分逻辑，用于在已有 `GraphModel` 上生成事件流级别的 Todo 步骤（创建节点、连线、动态端口、参数与类型设置等），不依赖任何 UI 组件或自动化执行器。

## 当前结构
- `dynamic_port_steps.py`：根据节点定义与 `NodeTypeHelper` 规划动态端口新增、端口类型设置及参数配置步骤；生成的“设置类型/配置参数/创建节点”等图步骤会在 detail_info 中附带 `node_category`，供 UI 在不加载 GraphModel 的情况下也能按节点类别着色；在规划参数时会结合图中的数据连线，只为缺少上游数据的输入常量生成“配置参数”步骤，并仅将文本常量 `"None"` 视为“端口留空”的占位值（不为其生成参数配置步骤），避免任务清单引导在编辑器中输入字面量 `None`；布尔常量（无论 True/False 或等价写法）一律保留为配置参数，让任务清单明确呈现所有布尔开关；对信号发送/监听节点的“信号名”端口以及结构体相关节点的“结构体名”端口则交由独立的绑定步骤处理（分别对应 `graph_bind_signal` 与 `graph_bind_struct`），通用参数步骤中不再重复生成“配置信号名/结构体名”；同时会过滤语义推导使用的隐藏稳定 ID 键（`__signal_id/__struct_id`，以及兼容旧数据的 `_signal_id/_struct_id`），避免在任务清单中暴露内部 ID；在类型步骤中会枚举该节点所有声明为“泛型”的输出端口名，并在输入侧仅围绕 Todo 中显式给出的泛型输入端口名补齐类型设置入口，对于以“字典”命名的泛型输入端口若未在 Todo 参数中出现，则不会为其自动生成类型设置明细，避免对上游已确定类型的字典端口重复发出基础类型设置指引。
- `edge_lookup.py`：从 `GraphModel` 构建统一的边索引视图，区分流程边与数据边，并提供入度/邻接结构，供事件流遍历与块内重排复用。
- `event_flow.py`：事件流任务的高层 orchestrator，基于 BasicBlock 与 `GraphEdgeLookup` 组织人类模式与两种 AI 模式（AI-先配置后连线 / AI-逐个节点模式）下的事件流步骤构建；AI 模式下会对传入 `GraphModel` 调用 `LayoutService.compute_layout(..., clone_model=False)` 以获得稳定坐标（该调用会原地插入副本/relay 并重写连线，因此需重建 `GraphEdgeLookup`）；事件起点节点集合在收集后会按“首次出现顺序去重”并结合节点坐标做稳定排序，保证事件流根步骤生成顺序在多次运行之间保持一致，并在事件起点为“监听信号”节点时，通过 `EventFlowEmitters` 额外生成一条“绑定信号”子步骤。
- `event_flow_emitters.py`：集中封装 TodoItem 的写入逻辑（创建节点、连接节点、数据节点副本、剩余边处理等），并在合适时机调用 `DynamicPortStepPlanner` 追加动态端口、类型与参数步骤；对信号节点统一生成 `graph_bind_signal` 类型的步骤（覆盖“发送信号”和“监听信号”），对结构体相关节点统一生成 `graph_bind_struct` 类型的步骤，引导在图编辑器中通过“配置结构体…”对话框选择结构体与字段。
- `event_flow_traversal.py`：事件流遍历策略实现：人类模式使用 BFS 的“连线并创建”顺序；AI 模式提供按块批处理（AI-先配置后连线）与逐个节点立即配置（AI-逐个节点模式）两种策略；两种 AI 模式均在最后统一生成连线步骤。支持可选 `progress_advance(stage, completed_delta, total_delta)`，用于在生成事件流时按“节点数 + 连线数”的粒度推进进度，供上层汇总为 0–100% 百分比进度条（纯模型回调，不引入 PyQt）。
- `node_predicates.py`：对节点角色的判定工具（如事件节点、流程节点等），用于在遍历与任务生成过程中做分支。

## 注意事项
- 只依赖 `engine.graph` 提供的模型与工具，不得反向依赖 `app/ui` 或自动化执行模块，保持任务生成层的纯模型属性。
- 所有任务生成函数以 `GraphModel` 与 `GraphEdgeLookup` 为输入，禁止在这里自行读取/缓存资源文件；图数据由上层 orchestrator 负责传入。
- 参数与类型步骤的规划应与信号系统与节点规范文档保持一致：类型步骤仅考虑含“泛型”端口的节点；参数步骤以 `input_constants` 为基础，但需要避开已经有数据连线的端口，避免引导用户重复配置，同时按照既定约定忽略“默认恒为真”等无需人工干预的常量配置。

# Todo Graph Tasks

## 目录用途
拆分 `TodoGraphTaskGenerator` 的巨量逻辑，提供图任务生成相关的独立模块（边索引、复合节点任务、事件流任务）。该目录只包含纯模型/算法代码，不依赖 UI。

## 当前状态
- `edge_lookup.py`：集中构建 GraphEdgeLookup，一次性缓存流程邻接、端口映射等信息，供其它模块重复使用。
- `composite.py`：封装复合节点相关 Todo 生成（根步骤、引脚配置、子图展开等）；复用上一阶段收集的 `composite_id -> 节点列表` 映射推导输入/输出，引脚扫描不会反复遍历整张图。
- `event_flow.py`：负责事件流 orchestrator，收集事件起点、调用布局，并把执行委托给动态端口规划器/遍历器/发射器；在事件流子步骤全部生成后，会基于 BasicBlock 块索引对 `graph_connect`/`graph_connect_merged` 连线步骤做块内的轻量重排，使同一节点在同一块中的“数据出口连线”步骤优先于“数据入口连线”步骤。
- `dynamic_port_steps.py`：节点级动态端口、类型与参数步骤规划，统一 `DynamicPortTodoPlan` 的落地逻辑；对子步骤追加采用去重策略，复用既有 Todo。类型步骤会基于 `NodeTypeHelper` 收集所有泛型输入/输出端口名称，并合并节点上的常量参数，生成 `graph_set_port_types_merged` 任务明细。
- `event_flow_emitters.py`：集中所有 TodoItem 写操作（流根、节点创建、数据节点、连接步骤），可与遍历解耦演进，内部已处理 children 去重，避免懒加载多次生成重复步骤；生成步骤会继承上层 graph 的 `task_type` 并在合并连线时参考 `settings.TODO_MERGE_CONNECTION_STEPS`；合并连线子边列表会按端口序号“从下往上”做稳定排序，减少连线遮挡与点击难度。
- `event_flow_traversal.py`：实现人类/AI 模式的遍历状态机，只通过 emitters 输出结果，内部沿用 deque/BFS 与块内批处理策略；支持可选 `progress_advance(stage, completed_delta, total_delta)`，用于 UI 超大图懒加载时驱动百分比进度条。
- `node_predicates.py`：封装事件节点等判定逻辑，避免在遍历/布局中散落硬编码字符串。
 - 与信号节点相关的 Todo 步骤会按引擎层约定处理“信号名”端口：信号名通过 `graph_bind_signal` 绑定步骤引导用户选择/确认；参数配置步骤会跳过隐藏稳定 ID（`__signal_id`）及其旧键名（`_signal_id`），避免在任务描述与 UI 指引中混用显示名称与内部 ID。
- `__init__.py`：暴露模块入口，方便 `todo_graph_task_generator.py` 调用。
- AI-先配置后连线：块内按“创建→（动态端口）→类型→（如需）分支输出→参数”阶段生成；AI-逐个节点模式：每个节点按同样阶段“创建→配置”立即追加；两种 AI 模式的连线步骤都在最后统一生成。

## 注意事项
- 保持无 PyQt 依赖，专注数据与结构。
- 若 `GraphModel` 在生成阶段被修改，需重新构建 `GraphEdgeLookup`。
- 所有事件流子步骤依赖传入的 `task_type`，新增 emitters 或 traversal 时务必继续向下游 builder 透传，确保 UI 过滤正确。
- `EventFlowEmitters` 中部分步骤（如 `create_data_node_step`）在需要生成结构体绑定等依赖图上下文的子步骤时需要 `GraphModel`；遍历层调用 emitters 时必须透传 `model`，以保证绑定步骤能获得完整图信息。
- 人类模式遍历在处理每个当前节点时，会沿数据边反向扩展其数据依赖链，逐层生成“反向拖线创建数据节点”步骤；该扩展按“下游先创建、上游后创建”的顺序入队，确保步骤与编辑器操作一致。
- 本目录描述仅反映最新结构，不记录历史。

