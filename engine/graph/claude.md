# 目录用途
图模型、图变换与解析（不含具体节点实现）。

# 公共 API
通过 `engine` 顶层导出（本子包默认内部）。

# 当前状态
- 复合节点类格式解析：节点显示名固定取类名，忽略 docstring 中的 node_name/composite_name，避免遗漏元数据导致列表出现空标题。
- 复合节点解析同时支持“类逻辑解析（装饰器/引脚标记/IR）”与“payload 直读”：若文件顶层存在 `COMPOSITE_PAYLOAD_JSON`（多行 JSON 字符串），解析器会直接反序列化为 `CompositeNodeConfig`，用于 UI 可视化编辑落盘的闭环；该路径不再强制重跑布局，以尊重落盘的节点位置与连线结构。
- 复合节点源码格式判定统一由 `engine.graph.composite.source_format` 提供（payload / @composite_class）；**旧函数式复合节点格式不再支持**，避免“校验/解析/懒加载展示”口径分裂。
- 图模型需要就地执行布局时，统一通过 `engine.layout.LayoutService.compute_layout(..., clone_model=False)` 触发布局计算与缓存同步。
- `port_type_effective_resolver.py`：GraphModel 级“有效端口类型”推断单一真源（overrides/快照/常量/连线/声明回退），同时用于 graph_cache 写入与 UI/Todo 展示兜底推断，避免资源层与应用层各维护一套规则。
  - 节点特例补齐：`获取节点图变量/设置节点图变量` 的 `变量值` 端口类型必须从 `GraphModel.graph_variables` 反推（按 `变量名` 常量定位变量定义），避免被“变量名字符串常量”误导而显示为泛型/字符串。
  - 节点特例补齐：`列表迭代循环` 的 `迭代值` 端口类型必须跟随 `迭代列表` 的元素类型实例化（例如 `整数列表 → 整数`），避免画布长期显示“泛型”。
  - 节点特例补齐：`获取列表对应值` 的 `值` 输出端口类型必须跟随其输入 `列表` 的元素类型实例化（例如 `实体列表 → 实体`），避免后续链路残留“泛型”并触发结构校验错误。
  - 节点特例补齐：`对列表插入值` 的 `插入值` 输入端口类型在 `列表` 类型可确定时应跟随元素类型收敛，避免常量字符串化造成“插入值=字符串”的伪差异。
  - 节点特例补齐：字典查/写节点（`以键查询字典值/查询字典是否包含特定键/对字典设置或新增键值对`）的 `键/值` 端口类型会根据输入 `字典` 的别名字典类型（如 `整数_整数列表字典`）绑定为具体类型，避免键/值长期为“泛型”。
  - 节点特例补齐：`对字典按值排序/对字典按键排序` 的 `键列表/值列表` 输出端口类型会根据输入 `字典` 的别名字典类型（如 `实体-整数字典`）绑定为具体列表类型（如 `实体列表/整数列表`），避免排序结果长期为“泛型列表”导致后续迭代/连线无法实例化类型。
  - 输出端口推断：当输出端口仅能从输入常量推断为 `字符串/字符串列表`（常量在 GraphModel 中**可能**以字符串形式保存；且“纯数字字符串”会被保守视为字符串）时，若出边下游已收敛到具体非泛型类型，允许用下游类型覆盖字符串推断，避免类型长期漂移（如 `拼装列表 → 浮点数列表`）。
  - 节点特例补齐：基础算术节点（加减乘除）的端口同型约束：
    - `结果` 输出端口类型跟随其 `左值/右值` 输入类型实例化（避免数据链路残留“泛型”）。
    - 当 `左值/右值` 一侧为常量（常量在 GraphModel 中**可能**以字符串形式保存；且“纯数字字符串”会被保守视为字符串）时，输入端口会优先从兄弟输入口/输出下游约束反推具体类型，避免出现“左值整数、右值字符串”的伪差异。
  - 节点特例补齐：比较/相等节点的输入端口同型约束：
    - `是否相等`：当一侧为常量且该输入口无入边时，优先跟随兄弟输入口已收敛的具体类型，避免出现“输入1=整数、输入2=字符串”的口径漂移（UI/Todo/导出必须一致）。
    - `数值小于/小于等于/大于/大于等于`：当一侧为常量且该输入口无入边时，同样优先跟随兄弟输入口的具体类型，避免“左值整数、右值字符串”等伪差异。
- `apply_layout_quietly(...)` 支持显式注入 `node_library/registry_context`：复合节点解析阶段会基于传入的基础节点库派生布局依赖，避免解析期反向触发 `NodeRegistry` 导致递归加载。
- GraphCodeParser 的解析链路在触发布局时会显式传入 `workspace_path`（来自解析器初始化参数），避免外部未初始化 `settings.set_config_path(...)` 时布局层无法推导工作区而抛错。
- `validate_graph_model(...)` 是 GraphModel 结构校验的标准入口；在未显式传入 `workspace_path` 且需要加载节点库时，会优先使用 `settings.set_config_path(...)` 注入的 workspace_root（单一真源）；若未注入则回退到 `engine.utils.workspace` 的统一推断，避免不同入口间的“根目录猜测”规则漂移。
- `validate_graph_model(...)` 除流程/数据连线与缺线检查外，也会结合节点库与 `GraphModel.metadata.port_type_overrides` 判定端口“有效类型”，对“枚举”端口做候选集合约束（常量值必须为字符串且落在候选集合内；`semantic_id="enum.equals"` 的枚举比较节点支持按连线来源动态绑定候选集合）；用于对齐 UI 自动排版的【获取局部变量】relay 等增强结构，避免 strict 校验口径漂移。
  - 结构校验额外禁止“任何数据端口的有效类型仍为泛型家族”：只要端口存在于图中，就必须被实例化为明确类型，否则在校验阶段直接报错，避免画布出现“泛型”这种类型集合占位。此处“泛型家族”仅指 `泛型/泛型列表/泛型字典/空类型占位`，不包含 `结构体/结构体列表`（结构体绑定信息由 `struct_bindings` 单独承载）。
  - NodeDef 解析统一以 `NodeModel.node_def_ref` 为唯一真源（builtin→canonical key；composite→composite_id），运行时不再允许基于 `title` 的 fallback；缺失 ref 视为不兼容数据，应触发缓存重建而不是继续运行。
- 复合节点解析与虚拟引脚构建器依赖统一的 IR 管线，生成的子图可直接复用布局与校验工具；复合实例映射通过公共工具生成，解析与校验共享逻辑。类型标注解析统一通过 `validate_pin_type_annotation` 做规范化处理：其允许集合与规范中文类型名的唯一事实来源为 `engine/type_registry.py`；优先接受中文端口类型，并允许在特定场景下将 Python 内置类型名（int/float/str/bool/list/dict）转换为中文类型；在资源/复合节点等默认场景下，遇到这类内置类型名会记录告警并回退为“泛型”，避免单个复合节点写错阻断整体加载。注意：复合节点对外引脚的“允许/禁止类型”由校验规则决定；“泛型/列表/泛型列表/泛型字典”等占位类型可用于编辑期提示，但在保存/成品校验阶段必须被替换为具体类型。
- Graph API 构建器通过 `open_branch_state/close_branch_state` 驱动 `BranchState`，提供 builder 上下文管理器与数据输入统一接线方法，嵌套流程和常量注入保持稳定。
- GraphCodeParser / Graph API 构建器会尊重节点定义 `NodeDef.input_defaults`：对声明了默认值的输入端口，在未提供连线/常量/参数时自动补齐默认常量，确保结构校验与运行时语义闭环（缺省不再表现为“缺少数据来源”）。
- 存档与变量模型收敛：关卡变量以 `LevelVariableDefinition` 作为代码级定义单一真源；实例/关卡实体对变量值的覆写统一使用 `LevelVariableOverride`（按 `variable_id + value`），模板侧变量通过 `metadata.custom_variable_file` 关联关卡变量文件。
- 图解析与 IR 管线在遇到【发送信号】/【监听信号】节点时，会结合 `GraphModel.metadata["signal_bindings"]` 输出统一的信号事件名（signal_id）与参数信息，供上层（应用层/工具层）在生成可运行代码时复用。
- **运行时绑定的源码生成**（节点图可运行代码、复合节点函数/类代码）已迁移到 `app/codegen/`：`engine.graph` 仅保留 GraphModel/IR/解析与校验，不再包含任何“导入 runtime/plugins”的生成器实现。
- 反向生成 Graph Code（工具链用）：`graph_code_reverse_generator.py` 提供 `GraphModel -> 类结构 Python Graph Code` 的生成与 round-trip 校验能力：
  - 生成侧支持线性事件流 + 结构化控制流（`if/else`、`match/case`、`for`、`break`），输出为“解析器可稳定识别的规范子集”，用于 JSON→代码→正向解析的闭环验证。
  - 为避免嵌套控制流下“外层分支出口仅取分支体最后一个流程节点”的 IR 约束导致接续漂移，反向生成会在 `match/case` 输出时按 join 可达性调整 case 顺序，使“可接续分支”在源码中尽量靠后，从而与原图的流程连线语义一致。
  - 事件节点的输出（事件参数）在反向生成中视为“天然已绑定的数据源”，不会被当作需要提前发出的源节点，避免错误触发“提前生成流程节点”的 fail-closed 路径。
  - 支持同一事件方法内存在多个“流程入口序列”：当图里存在**无流程入但有流程出**的入口节点（常见于 client 校准/布局图），会在主入口序列生成后继续补发这些入口序列，保证 round-trip 不丢节点。
  - 对 **无分支连线** 的【双分支/多分支】节点（仅用于占位/布局）会退化为普通节点调用（如 `双分支(self.game, 条件=True)`），避免用 `if/match` 生成而导致解析器无法抽取条件/控制表达式。
  - 对 **动态输出端口** 的节点（`NodeDef.output_types` 为空，如 `拆分结构体`），反向生成会强制使用“输出端口名”作为赋值目标变量名，避免解析器把变量名当作端口名生成动态端口而导致 round-trip 端口集合漂移。
  - 对 client 过滤器图（GraphModel 内含 `graph_end_*` / `节点图结束（布尔型/整数）` 节点）会生成 `return <expr>`（而不是裸 `return`），使解析侧可重建过滤器输出锚点并保持语义一致。
  - 语义签名比较会忽略 node/edge id 与布局坐标，同时会忽略“已连线输入端口上的冗余 `input_constants`”（连线优先级覆盖常量），以贴合解析/执行时的数据来源优先级，避免因为解析器的双写行为导致误报差异。
  - 复合节点已支持普通调用与多流程出口的 `match self.<实例>.<方法>(...)`；对“多流程出口 + 数据输出被下游引用”等无法同时表达的形态仍 fail-closed。
- 变量命名、函数调用表达式与输出映射策略仍集中在 `engine.graph.common`（如 `render_call_expression/finalize_output_var_names`），供解析、校验与上层生成器共享，保持行为一致且可预测。
- 节点名称索引 `node_name_index_from_library(...)` 额外兼容“/ ↔ 或”变体：当节点显示名包含 `/` 时，同时收录 `去掉/` 与 `把/替换为或` 的同义索引，用于对齐部分导出/生成链路的命名差异（如 `实体移除或销毁时`）。
- 信号节点的标题与静态端口名集中定义在 `common.SIGNAL_SEND_NODE_TITLE/SIGNAL_LISTEN_NODE_TITLE` 及对应常量中，其中两类节点的“信号名”输入端口通过 `is_selection_input_port` 统一视为仅支持行内编辑的选择端口（不可连线），其值由 UI 根据已绑定的 `SignalConfig.signal_name` 写入 `node.input_constants["信号名"]`。
- 常用端口名（如 `TARGET_ENTITY_PORT_NAME`、`VARIABLE_NAME_PORT_NAME`）同样集中在 `engine.graph.common`，供校验、解析与工具层复用，避免散落硬编码。
- GraphCodeParser 传入预解析 AST 给 `CodeToGraphParser`：IR 管线与元数据提取避免重复解析，并在 `validate_graph_model` 中统一检查流程/数据连线、流程入口与数据来源，同时尊重图模型中记录的 `source_lineno/source_end_lineno` 以输出贴合源码的错误提示；在解析 Graph Code 时，对 `match` 语句统一走 IR 分支构建：普通 `match 变量:` 生成【多分支】节点，而形如 `match self.<复合实例>.<入口方法>(...)` 的写法会识别为"以复合节点为控制点的多流程出口"，`case "出口名":` 将对应复合节点在节点库中标记为"流程"类型的同名输出端口连到该分支体的首个流程节点，从而在宿主图中显式表达复合节点多个流程出口的后继逻辑，即便这些端口名本身不包含"流程"等关键字；对于带字符串类型注解的常量变量（AnnAssign），解析层支持将其作为"命名常量"回填到节点的 `input_constants`，不通过数据连线表达。
- 解析支持**严格模式（fail-closed）**：当启用 strict 时，语法糖改写 issue、IR 解析错误（无法可靠建模）或图结构校验失败都会直接抛错并拒绝产图，避免“静默生成错误节点图”；validate 阶段可显式关闭 strict 以便尽力解析并输出尽可能多的规则问题。
  - 严格模式在执行 `validate_graph_model` 前会先把 `graph_type/folder_path/graph_variables` 同步到 `GraphModel`：避免因 scope 与变量表缺失导致端口类型推断退化为“泛型”，从而在批量导出/资源加载链路中误报并中断。
  - 严格模式抛出的 `GraphParseError` 会在错误文本中包含节点图源码的绝对路径（`文件: <abs_path>`），便于 UI 弹窗/日志在不额外拼接的情况下定位到具体 `.py`。
- GraphCodeParser 读取源码默认使用 `utf-8-sig`，兼容 Windows 常见的 UTF-8 BOM，避免 `ast.parse` 因 `U+FEFF` 失败。
- 解析入口对常见 Python 语法糖做归一化：在类方法体内遇到 `列表[序号]`、`len(列表)`、`字典[键]` 读写与 `del`、`in/==/>=` 等比较、`and/or` 逻辑组合、`+=` 等增量赋值与 `append(...)` 等写法时，解析器会将其改写为等价的节点调用（并按 graph scope 处理 server/client 的节点名与端口名差异）。普通节点图在 server 作用域还允许启用“共享复合节点语法糖”（整数列表切片、`sum/any/all`、三元表达式），解析时会改写为共享复合节点实例方法调用并自动注入 `__init__` 的实例声明。该归一化仅用于解析/建模，不写回源码；非法写法由验证层报错，解析层仅尽力生成图模型以便定位。
  - 有效类型推断在声明为“泛型家族”的端口上不会盲信 `NodeModel.input_types/output_types` 的展示快照：会继续结合 overrides/常量/连线推断得到具体类型，避免“常量字符串化”把端口误显示为字符串。
  - `apply_effective_port_type_snapshots(...)` 在写回 `input_types/output_types` 时会执行“纠错升级”：当 resolver 能算出具体类型时会覆盖旧快照；仅在 resolver 退化为泛型时才保留旧的具体快照，避免旧缓存中的错误快照长期滞留或影响 UI/工具链展示。
- 节点名索引按 scope 构建：`CodeToGraphParser.parse_code(..., scope=...)` 会将 Graph Code 中的 `名称(...)` 自动映射到节点库的 `名称#client/#server` 变体（当 server/client 端口不兼容时由 nodes pipeline 生成），避免 client 图误用 server 版本节点导致端口名不一致与 UI 连线缺失；同时会将 scope 写入 IR 的 `FactoryContext.graph_scope`，供局部变量建模等子模块在端口不兼容节点上做作用域分支。
- **client 过滤器图 return 建模**：对 `folder_path` 属于布尔/整数过滤器的 client 图，IR 会将 `return <值>` 物化为对应的【节点图结束（布尔型/整数）】纯数据节点，并将返回值绑定到其输入端 `结果`，从而让“过滤器图输出”在 GraphModel 中可见且可被 UI/自动化执行。
- **client 模板锚点坐标对齐**：当 client 图包含“新建时模板默认存在”的锚点节点（如技能图的【节点图开始】、过滤器图的【节点图结束】），解析器会以该锚点为基准平移整张图，使锚点落在 (0,0) 的模板坐标，避免 UI 自动化在跳过创建锚点节点时校准漂移。
- 为支持“长生命周期解析器实例”（例如资源加载器缓存 GraphCodeParser）与编辑器的实时重解析：`CodeToGraphParser` 在每次 parse 开始与每个事件方法（`on_...`）解析前都会重置 `VarEnv/Validators` 的方法级状态（命名常量、局部变量句柄、赋值分析缓存等），避免跨文件/跨事件/跨次解析串用旧状态导致局部变量建模漂移或常量回填错误。
- 解析入口对列表相关语法糖做归一化：在类方法体内遇到非空列表字面量 `[...]` 与常见列表原地修改写法时，解析器会将其改写为等价的节点调用（如【拼装列表】/【对列表修改值】等）。注意：**for 的迭代器位置禁止直接使用列表字面量**（必须先显式声明带中文类型注解的列表变量再迭代），否则会在验证阶段报错。该归一化仅用于解析/建模，不写回源码；空列表与超长列表等非法写法由验证层报错。
- 解析入口对字典字面量 `{k: v}` 做语法糖归一化：在类方法体内遇到非空字典字面量时，解析器会将其改写为等价的【拼装字典】节点调用。注意：空字典 `{}`、超长（>50）、`{**d}` 展开以及 `for x in {...}` 形态均会在验证阶段报错；解析层仅尽力建模以便定位，不写回源码。
- 语法糖改写的“参数上限（列表/字典元素数等）+ 共享复合节点语法糖开关策略”集中由 `engine/graph/utils/graph_code_rewrite_config.py` 维护；validate 流程在需要产出 GraphModel 时可复用已改写 AST，避免重复执行改写链路。
- 语义元数据单一写入阶段（根除多源写入）：
  - `engine.graph.semantic.GraphSemanticPass` 是唯一允许写入 `GraphModel.metadata["signal_bindings"/"struct_bindings"]` 的实现，输出为覆盖式重建（幂等、可复现）。
  - Parser/UI/工具层只能写入“节点本体的意图/常量/端口”，供 Pass 推导：
    - 信号：`node.input_constants["信号名"]`（展示）+ `node.input_constants["__signal_id"]`（稳定 ID；Pass 会回填）
    - 结构体：`node.input_constants["__struct_id"]`（稳定 ID；Pass 会回填）+ `node.input_constants["结构体名"]`（展示/兼容；**不再是端口**）
  - 关卡变量（自定义变量节点）：节点的 `变量名` 端口应直接填写 `variable_name`（给人看的名字，如中文或 `1_chip_*`）。综合校验会禁止填写 `variable_id`（`var_*`）与旧展示文本格式。
  - 模块级命名常量通过 `collect_module_constants + set_module_constants_context` 供 `extract_constant_value` 解析，方法体内命名常量通过 `VarEnv.local_const_values` 支持 `变量名` 实参回填。
  - 解析层不再保留旧式“解析阶段直接写 metadata”的兼容入口，避免误用导致多源写入与覆盖口径分叉。
- Graph Code 与 `GraphModel` 在本层只建模"使用哪些节点、如何连线以及如何布局"，不会执行节点实际业务逻辑；该层的主要用途是为 AI/脚本和开发者提供一个可验证、可排版的节点图中间表示。
- 复合节点解析支持**模块级常量引用**：在类外定义的常量（如 `关卡GUID: "GUID" = "1094713345"`）可以在节点调用参数中直接使用。解析时通过 `collect_module_constants` 收集模块顶层常量，并在 `extract_constant_value` 中通过上下文查找解析，最终回填到节点的 `input_constants`。
- 节点图 docstring 元数据解析集中在 `utils/metadata_extractor.py`：仅解析 `graph_id/graph_name/description/dynamic_ports` 等基础字段。节点图变量的唯一事实来源为模块顶层 `GRAPH_VARIABLES: list[GraphVariableConfig]`（可包含 `default_value/description/is_exposed/struct_name/dict_key_type/dict_value_type`），避免多源漂移。
- `entity_templates.py` 以 `engine.configs.rules.entity_rules.ENTITY_TYPES` 为规则源，集中维护实体/模板与节点图变量共享的“规范中文变量类型”列表，并通过 `get_entity_type_info` 这类函数为 UI 提供实体类型的图标、默认节点图与规则说明，涵盖字符串/整数/浮点数/布尔值/三维向量/实体/GUID/配置ID/元件ID/阵营及其列表形式，以及结构体、结构体列表和字典类型。
- 图的流程/数据连线路由与默认流程出口策略集中在 `graph/ir` 层，由 `edge_router`、`flow_builder` 等模块协同实现；上层仅通过 Graph API 与 `validate_graph_model` 观察结果，不直接依赖具体连线推断细节。
- 常量提取增强：除模块顶层常量外，解析节点图类时也会收集 class body 顶层“类常量”（AnnAssign/Assign 且右值可静态提取），并以 key=`"self.<字段名>"` 注入常量上下文，使 `self._xxx` 这类写法在作为节点入参时可被静态回填到 `node.input_constants`（常见于定时器名称、变量名等标识性参数）。

# 依赖边界
- 允许依赖：`engine/utils`、`engine/validate`（有限度），其中图语义/算法统一通过 `engine.utils.graph` 子包获取，调试输出统一使用 `engine.utils.logging`.
- 禁止依赖：`app/*`、`plugins/*`、`assets/*`

# 注意事项
- 保持纯逻辑与确定性，禁止读写磁盘与 UI 操作。 
- 文档字符串与注释中的“工作区根目录”统一称为 `workspace_root`（不绑定具体仓库目录名）。

