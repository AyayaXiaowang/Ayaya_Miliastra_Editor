## 目录用途
- 提供引擎侧的通用验证能力：实体/组件/实体配置校验、节点图代码与图结构校验、项目存档级综合校验等。
- 封装验证管线、规则集与对上层暴露的统一入口（如 `validate_files`、`ComprehensiveValidator` 等），产出结构化的 `EngineIssue` / `ValidationIssue` 结果。

## 当前状态
- 校验逻辑全部为纯 Python，不依赖 UI 层或 CLI 层，通常经由 `engine.validate.*` 或应用层 CLI（如 `app.cli.graph_tools`）间接调用。
- 节点图/复合节点校验的“目标文件收集与路径归一化”提供轻量公共实现：`engine.validate.graph_validation_targets`（收敛默认扫描范围、通配符/目录展开、相对路径显示与 issue 文件路径归一化），供应用层 CLI 包装层复用，避免多处重复维护同一套收集/过滤逻辑。
- 相对路径显示与 issue 文件路径归一化统一由 `engine.validate.graph_validation_targets.relative_path_for_display/normalize_issue_path` 提供；斜杠归一化统一由 `engine.utils.path_utils.normalize_slash` 提供（`graph_validation_targets.normalize_slash` 仅作为转发以兼容旧导入），避免 Windows/Unix 分隔符差异导致 UI/CLI 漂移。
- 节点图校验的 CLI 输出（按文件分组/目录统计/文本报告/JSON 报告 payload）已收敛到 `engine.validate.graph_validation_cli_reporting`，供 `app.cli.graph_tools validate-graphs` 复用，避免多套输出逻辑漂移。
- `validate-graphs` 的 CLI 运行器已收敛到 `engine.validate.graph_validation_cli_runner.run_validate_graphs_cli`，供应用层 CLI 共用：统一 targets 收集、编排校验、文本输出与 `--json` 模式（JSON 模式仅输出 JSON，便于脚本/CI 消费）。
- `validate-graphs` 支持可选 QuickFix（默认关闭）：`engine.validate.graph_validation_quickfixes.apply_graph_validation_quickfixes` 提供“可自动补齐”的修复动作；CLI 通过 `--fix/--fix-dry-run` 触发，用于在校验前补齐常见缺失项（例如 GRAPH_VARIABLES 未声明的节点图变量）。
- 项目存档校验支持“结构体定义目录即分类”约束与 QuickFix：
  - 规则：`engine.validate.comprehensive_rules.struct_definition_rule.StructDefinitionRule` 会校验结构体定义文件所在目录（`基础结构体/`、`局内存档结构体/`）与其 `STRUCT_PAYLOAD.struct_type/struct_ype` 是否一致，避免 UI 分类漂移与“放错目录但看起来像丢失”的误解。
  - 修复：`engine.validate.struct_definition_quickfixes.apply_struct_definition_quickfixes` 提供按目录自动修正 `STRUCT_TYPE` 与 `STRUCT_PAYLOAD` 类型字段的修复动作；由 `app.cli.graph_tools validate-project --fix/--fix-dry-run` 触发（默认不写盘）。
- `validate-graphs` 的“编排层”（`validate_files` + 复合节点结构补齐）收敛到 `engine.validate.graph_validation_orchestrator.collect_validate_graphs_engine_issues(...)`：会按文件所属资源根目录分组切换运行期 `active_package_id`，并刷新 NodeRegistry 与代码级 Schema 作用域后再执行校验，避免跨项目存档混扫时复合节点/结构体/变量等定义串包导致误报或漏报。
- 节点图代码校验的“文件/类便捷入口”统一由 `engine.validate.node_graph_validator` 提供；其内部会按被校验文件所属的资源根目录推断并切换运行期 `active_package_id`，同步刷新 NodeRegistry 与代码级 Schema 作用域后再执行 `validate_files`，避免单文件/多文件校验时复合节点/结构体/信号等定义串包导致误报；runtime 层仅做 re-export（保持旧导入路径可用）。
- 节点图代码校验的作用域推断规则：若被校验文件位于资源库目录结构下，则按其所属资源根目录推断并切换运行期 `active_package_id`；若文件不在资源库目录结构下（例如临时目录/生成文件），则保持调用方当前 `active_package_id` 不变，避免意外降级为共享根导致复合节点作用域缺失。
- `engine.validate.node_graph_validator.validate_node_graph`（装饰器或显式调用）会对节点图类所属文件执行一次性文件级校验（进程内去重）；若存在 error 且处于 strict 模式，将直接抛出 `NodeGraphValidationError`，用于确保“运行/导入节点图脚本”时立刻暴露不支持语法与节点调用问题。
- 节点图代码校验会将 IR 解析阶段收集到的 `GraphModel.metadata["ir_errors"]` 显式提升为 error（即便 validate 采用“尽力解析”而关闭 strict fail-closed），确保“validate_file 通过”与“UI 严格模式可加载”行为一致。
- 节点图代码校验同样会在 validate 阶段执行一次 `validate_graph_model` 图结构校验，并将其错误提升为 error（仅在无 IR 建模错误时执行，行为与 strict fail-closed 对齐），确保“validate_file/校验面板”与“严格加载”在端口类型/缺线等结构问题上保持一致。
- 复合节点/普通节点图的规则集选择统一由 `engine.nodes.composite_file_policy.is_composite_definition_file` 判定：位于资源库任意“资源根目录”（`共享/`、`项目存档/<package_id>/`）下的 `复合节点库/`（含子目录）中的 `.py` 文件即按“复合节点”规则集校验；复合节点文件名不再要求 `composite_` 前缀，避免命名约束导致的入口漂移。
- 复合节点校验除“引脚类型/禁止嵌套”等约束外，还要求虚拟引脚方向与映射端口方向保持一致：payload 复合节点中 `virtual_pins[].is_input/is_flow` 必须与 `mapped_ports[]` 的标记一致；类格式入口方法内禁止同名引脚同时声明为 `数据入` 与 `数据出`，避免数据入被错误视为出引脚。
- 复合节点类格式新增流程约束：`@flow_entry` 若声明了流程引脚（流程入/流程出），方法体内必须产生至少一个可建模的流程节点（控制流或带流程端口的节点调用），否则视为结构性错误并报错。
- 复合节点额外包含名称规范校验：从文件头 docstring 的 `node_name` 读取，要求名称使用 `_` 分段时最多两段且每段不超过 12 个字，避免资源库与节点标题区显示过长。
- 复合节点规则集除复合节点专属约束外，也包含信号/结构体静态端口校验：对【发送信号】的 `信号名`、结构体相关节点的 `结构体名` 等端口，强制要求字面量或模块顶层字符串常量，禁止通过 `数据入`/连线把运行期变量喂给静态端口。
- `engine.validate.node_graph_validator.validate_file` 支持“直接运行单个节点图文件”的自检用法：会自动推断并注入 `workspace_root`（推断规则统一委托 `engine.utils.workspace`，支持源码仓库与便携版目录，后者以 `assets/资源库` 作为标记），避免布局阶段因 `Settings._workspace_root` 未设置而崩溃。
- `engine.validate.node_graph_validator.strict_parse_file` 提供“严格模式（fail-closed）解析”入口：在切换作用域（active_package_id）并刷新 NodeRegistry/Schema 后，对不同文件类型走不同严格解析链路：
  - 节点图（类结构 Graph Code）：使用 `GraphCodeParser(strict=True)` 解析单文件；
  - 复合节点（`复合节点库/**/*.py`）：使用 `CompositeCodeParser` 解析并额外执行“引脚类型不得为泛型家族”的阻断式校验；
  用于对齐资源加载/批量导出链路并提前发现 strict 下会拒绝解析的问题。
- `engine.validate.node_graph_validator.format_validate_file_report` 提供 `validate_file` 的文本报告格式化（CLI/runtime 共用），避免输出口径漂移。
- 节点图代码侧的静态规则集中在 `rules/code_*.py`，覆盖语法/结构/布尔条件/变量声明/端口类型/类型名，以及“发送信号调用所用参数名必须与信号定义一致”“Graph Code 中【信号名】参数必须使用信号名称而非 ID”“信号名/结构体名等静态端口必须是字面量或模块常量”等约束，并依赖节点库索引、信号/结构体 Schema 视图与 AST 工具进行分析。
- 节点图校验规则装配（`engine.validate.api`）直接从 `engine.validate.rules.code_quality` 导入代码质量规则。
- 节点图代码侧包含数字 ID 约束：当节点图/复合节点中出现可静态解析的 `GUID/配置ID/元件ID` 常量（命名常量声明、节点调用入参常量、以及 `GRAPH_VARIABLES.default_value`）时，必须为 **1~10 位纯数字**（支持整数或数字字符串）；否则报错 `CODE_ID_LITERAL_DIGITS_1_TO_10_REQUIRED`。
- 节点图变量（GRAPH_VARIABLES）结构体类型已纳入校验：当结构体/结构体列表图变量提供**非空默认值**时，必须同时提供 `struct_name` 且指向有效结构体定义；用于保证后续写回存档/编辑器解析能对齐既有结构体类型。
- 节点图代码侧 M3 层规则在端口类型匹配之外，补充“同型输入”约束：对 `是否相等/数值比较/加减乘除/拼装列表` 等节点要求关键输入端口类型完全一致（整数≠浮点数），避免在“泛型端口”下混用类型潜伏到运行期。
- 节点图代码侧新增“内置事件回调命名”校验：当 `register_event_handler` 注册的是内置事件时，回调必须为 `on_<事件名>`（严格一致）；信号事件不强制回调名。
- 节点图代码侧新增“内置事件回调签名”校验：当 `register_event_handler` 注册内置事件且回调为标准命名 `on_<事件名>` 时，回调函数参数必须与该事件节点的输出端口一致（剔除流程端口）；缺参或参数名不匹配会报错，避免运行期 kwargs 绑定失败。
- 节点图代码侧新增 `on_XXX` 方法名严格校验：只要方法名以 `on_` 开头，`XXX` 必须是内置事件名或已定义信号名/ID（即使未注册也会报错），防止伪事件入口潜伏。
- 节点图代码侧额外提供“节点调用必填入参”校验：基于节点库静态输入端口清单，禁止 Graph Code 漏传必填端口（流程端口与变参占位端口除外），减少运行期静默失败。
- 节点图代码侧新增【获取局部变量】用法校验：必须二元拆分赋值或显式下标选择输出（`[0]=句柄`、`[1]=值`），避免误用二元返回值。
- 节点图代码侧新增“已知节点必须传 game”校验：只要函数名在节点库中，就必须显式传入 `self.game/game`（支持位置参数或 `game=self.game` 关键字形式），避免漏传 game 绕过部分静态规则并在运行期报错。
- 节点图代码侧新增“实体销毁时挂载语义提醒与同图冲突检测”：发现事件【实体销毁时】时先提醒其仅在关卡实体可触发；若同图存在“无法挂载关卡”的节点/事件则直接报错，避免把关卡广播事件与其他实体专属事件混在同一张节点图中。
- 代码可读性相关的规则除 error 级硬约束外，也提供若干 warning：例如事件节点多流程出口提示、`if 是否相等(布尔值, True/False)` 的冗余比较提示，以及 `on_实体创建时` 冗余把节点图变量设回默认值的提示（`CODE_GRAPH_VAR_REDUNDANT_INIT_DEFAULT`）与 `on_实体创建时` 冗余初始化自定义变量的提示（`CODE_CUSTOM_VAR_REDUNDANT_INIT_ON_ENTITY_CREATED`），用于帮助开发者在不阻断流程的前提下发现 UI 可读性风险点。
- 针对离线/简化“拉取式执行器”新增风险提示规则：当【设置自定义变量】写入后，后续流程节点仍依赖同一个【获取自定义变量】节点实例时，报告 `CODE_PULL_EVAL_REEVAL_AFTER_WRITE` warning，提醒可能因重复求值导致条件/数值偏移；推荐在执行器层实现“同一 node_id 单次事件流只求值一次”的输出缓存语义。
- 新增字典“重复求值/引用语义”风险提示规则：当字典来源于“计算节点明确声明的字典输出端口”且被多个下游节点消费时，报告 `CODE_DICT_COMPUTE_MULTI_USE` warning，提示在无缓存的拉取式执行器中可能重复求值导致“不是同一 dict 引用”，若需要写回语义应改为【节点图变量】承载（局部变量禁止字典类型）。
- 新增字典“写回/可变引用”语义约束规则：当【对字典设置或新增键值对/以键对字典移除键值对/清空字典】对字典原地修改后，后续流程仍继续依赖同一字典来源，且字典来源于“计算节点明确声明的字典输出端口”时，报告 `CODE_DICT_MUTATION_REQUIRES_GRAPH_VAR` error，要求将字典落到【节点图变量】承载（局部变量禁止字典类型，无法用于缓存/写回）。
- 图结构与综合规则通过 `comprehensive_graph_checks.py`（入口 `validate_graph_cache_data`）与 `comprehensive_rules/*` 完成统一标准化与多维检查，复用缓存的节点库与图模型构建；结构校验直接基于节点图序列化数据（含布局阶段生成的数据节点副本）构造 `GraphModel` 并调用引擎层的 `validate_graph_model`，保证 CLI 校验、运行期校验与 UI 校验在连线完整性（如流程入口是否连接、数据输入是否有来源）上的行为一致，并保留节点的 `source_lineno/source_end_lineno` 等源码行信息以便输出贴近代码的错误范围提示。对于运行时代码会注入默认值的特定输入端口（例如自定义变量节点的“目标实体”），结构校验在“缺少数据来源”规则上做了对应豁免，避免与代码生成语义产生冲突。
- 节点定义解析入口开始收敛：`engine.validate.node_def_resolver` 提供统一的 NodeDef 解析；运行时主链路以 `NodeModel.node_def_ref` 为唯一真源（builtin→canonical key；composite→composite_id；event→事件名且不参与 NodeDef 解析），禁止在校验链路中使用 title/category/#scope fallback；旧数据缺失 ref 视为不兼容并应触发缓存重建。端口定义一致性校验会跳过 `kind=event` 的事件节点（事件节点不走节点库对齐）。
- 语义节点定位入口收敛：`engine.validate.node_semantics` 以语义 ID（如 `signal.*` / `graph_var.*` / `struct.*` / `custom_var.*`）集中提供关键语义节点的定位能力；完全依赖节点库 `NodeDef.semantic_id`（由实现侧 `@node_spec(semantic_id=...)` 透传），并统一处理 alias key 与 `#scope` 变体，避免规则散落硬编码节点标题字符串或固定 key 映射。
- 节点端口定义一致性校验支持“范围占位端口”（如 `0~99`、`键0~49`）与展开端口（如 `0`、`1`、`键0`…）互相兼容，用于覆盖变参/批量端口节点的图数据表示差异，避免误报缺失端口。
- 结构校验与挂载/作用域校验产出的 `ValidationIssue` 会保留稳定错误码 `code`（例如 `CONNECTION_*`、`NODE_MOUNT_FORBIDDEN`），便于 UI/工具侧做跳转、统计与豁免。
- 复合节点的“结构一致性校验”（缺少数据来源/未连接/端口类型不匹配等）提供统一入口 `collect_composite_structural_issues(...)`，用于 UI/CLI 共用，避免重复实现与规则漂移。
- 存档级关卡实体规则 `package.level_entity` 仅在实际配置了关卡实体时检查其类型与组件是否符合约定；如果当前存档未配置关卡实体，则跳过该规则而不产出任何错误或警告，避免在示例包/临时测试包中产生噪声。
- 验证入口采用 `ValidationPipeline`+`ValidationContext` 组合组织规则执行，可根据配置选择启用的规则集、严格模式与豁免策略；`validation_cache.py` 会在规则签名与文件状态均稳定且当前无错误时，为单个文件复用上一次的验证结果。
- 验证缓存的规则签名包含工作区节点库指纹，节点定义或复合节点变更会自动使缓存失效。
- 列表相关语法糖在类方法体内允许使用：`ListLiteralRewriteRule` 会在校验入口将其自动改写为等价的节点调用（如【拼装列表】/【对列表修改值】等）；同时强制禁止空列表 `[]` 与元素数超过上限的列表，避免无法静态建模或端口超界。注意：**for 的迭代器位置禁止直接使用列表字面量**（必须先声明带中文类型注解的列表变量再迭代），避免类型推断变弱导致端口类型校验漏报。
- 字典字面量 `{k: v}` 在类方法体内仅允许以“**带别名字典中文类型注解的变量声明**”形式出现（例如 `映射: "键类型-值类型字典" = {k: v}` / `映射: "键类型_值类型字典" = {k: v}`）；禁止直接在节点调用入参或其它表达式里内联 `{...}`（会报错 `CODE_DICT_LITERAL_TYPED_ANNOTATION_REQUIRED`）。`DictLiteralRewriteRule` 仍会在校验入口将合法字面量改写为等价的【拼装字典】节点调用；同时强制禁止空字典 `{}`、键值对数量超过上限（默认 50）以及 `{**d}` 展开语法。**for 的迭代器位置禁止直接使用字典字面量**，字典遍历需先转为键/值列表再迭代；键/值类型需满足【拼装字典】的泛型约束（键仅允许实体/GUID/整数/字符串/阵营/配置ID/元件ID 等）。
- 常见 Python 语法糖（解析器/IR 不直接支持的语法）在校验入口统一归一化：`SyntaxSugarRewriteRule` 会将列表/字典下标读取与写入、`len(...)`、`in/==/>=` 等比较、`and/or` 逻辑组合、`+=` 等增量赋值以及 `append(...)` 等写法改写为等价节点调用，并按 scope（server/client）处理节点名与端口名差异，以减少“缺线/缺数据来源”类问题。
- 对“共享复合节点语法糖”提供可控改写（仅普通节点图启用）：对 `any/all/sum`、`整数列表[start:end]`、以及“整数/浮点数三元表达式（X if 条件 else Y）”等高频但不支持的写法，在校验入口自动改写为共享复合节点的实例方法调用，并注入 `__init__` 中的实例声明以保证解析器识别；复合节点文件默认关闭该能力以避免“复合内嵌套复合”违规。
- 容器字面量相关约束已收敛：不再保留“历史禁令占位规则”；列表/字典在方法体内走 rewrite 归一化，其余不支持形态统一由 `UnsupportedPythonSyntaxRule` 报错。
- `MatchCaseLiteralPatternRule` 对所有节点图（包括复合节点）生效，限制 `match/case` 的 `case` 模式只能使用字面量（或字面量 `|` 组合）与 `_` 通配，避免出现 `case self.xxx`/`case 变量名` 等解析器无法静态处理的写法。
- Graph Code 的可读性规则持续演进：除“if 条件必须为布尔来源、禁止内联 Python 比较”等基础约束外，新增规则禁止在 `if` 条件中直接调用 `逻辑非运算(...)`，要求使用正向条件（例如 `if 条件: pass else: return`）让主流程从“是”分支接续。
- 节点图代码侧新增“未知节点函数名”校验：当代码出现 `某函数(self.game, ...)` 形态但该函数名不在节点库中，会直接报错，避免拼写错误/不存在节点名在校验阶段被静默放过。

## 注意事项
- 允许依赖：`engine/nodes`、`engine/graph`、`engine/utils`、`engine/configs`；禁止引入 `plugins/*`、`app/*`、`assets/*`、`core/*` 等上层模块。
- 规则和管线实现避免使用 try/except 捕捉业务异常，发现问题直接抛给调用方或以 Issue 形式返回，由上层决定处理策略。
- **禁止为通过校验而补节点**：校验报 `CODE_UNKNOWN_NODE_CALL` / “节点不在当前作用域节点库中”，说明该 scope 下不能用这个节点；应修改节点图/替换为已有节点/调整写法，不能通过新增 `plugins/nodes/**` 节点实现来绕过。
- 数字 ID（1~10 位纯数字）的判定逻辑统一复用 `engine.utils.id_digits.is_digits_1_to_10`，避免在不同规则/子系统中维护多份正则与边界口径。
- 涉及节点库或资源图定义时，务必通过 `workspace_path` 获取对应的注册表或资源管理器，并优先复用已有缓存工具函数。
- 综合规则应通过 `ComprehensiveValidator` 的辅助方法访问图校验入口，避免跨越封装直接调用内部实现细节。
- 针对节点图或生成代码的修改，需要通过配套的验证脚本或工具执行一次完整校验，确保在引擎级验证下无报错后再集成到上层流程；对于存在错误的文件，每次验证都会重新执行规则而不会使用缓存。
- `RoundtripValidator`（GraphModel ↔ Graph Code 往返）不再在引擎内构造“源码生成器”，而是通过依赖注入接收 `code_generator.generate_code(...)`，避免验证层绑定运行时/插件导入策略。


