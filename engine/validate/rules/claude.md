## 目录用途
- 提供验证层使用的规则视图与工具函数，包括节点图代码语法/结构规则、端口类型匹配规则、复合节点嵌套规则、数据类型规则和节点挂载规则等，在校验阶段对 Graph Code 与图结构进行统一约束。
- 这里的代码通常与 `engine.configs.rules.*` 中的原始规则结构对应，通过 AST 与节点库视图将底层规则转化为面向“检查流程”的实现。

## 当前状态
- 以纯规则实现和轻量工具函数为主，专注于为 `engine.validate.*` 提供可组合的 `ValidationRule` 与辅助方法。
- 校验层读取节点图源码默认使用 `utf-8-sig`，兼容 Windows 常见的 UTF-8 BOM，避免 `ast.parse` 因 `U+FEFF` 失败。
- 与配置层规则解耦：配置层负责规则与类型体系的权威定义，本目录负责在校验过程中的使用方式与错误信息组织；组件与资源等权威定义集中在 `engine.configs.rules` 与相关注册表中，这里仅通过导入视图进行读取。
- UIKey 占位符存在性校验以 UI源码(HTML) 的 `data-ui-key` / `data-ui-state-group` 为真源；同时兼容 Workbench/写回链路生成的“长 ui_key”（形态：`<layout>__<key_or_state_group>__...`），校验时会自动提取其中的“关键标识”片段用于存在性判断。
- UI源码(HTML) 占位符扫描工具支持 `lv`（关卡）与 `ps/p1..p8`（玩家）两类作用域：规则可基于占位符推导出 UI 变量的归属实体（关卡实体/玩家实体），用于校验 Graph Code 的【获取/设置自定义变量】目标实体语义一致性。
- 规则执行会根据节点图文件路径/元数据推断 graph scope（server/client），并据此选择对应作用域的节点库视图参与校验（端口名/端口类型/必填入参等），避免 server/client 同名节点在端口定义不兼容时发生“互相覆盖”导致的误报与缓存不稳定。
- 校验规则在需要解析 GraphModel 时应使用“尽力解析”路径（strict=False，关闭严格 fail-closed）并尽量复用 `code_quality.graph_model_utils._get_or_parse_graph_model()` 的缓存结果，以便在源码不完全合规时仍能尽可能产出更多规则问题；严格 fail-closed 主要用于资源加载/导出等需要“要么正确产图、要么拒绝”的入口。
- 解析层/IR 层在“尽力解析”时会把“无法可靠建模”的问题写入 `GraphModel.metadata["ir_errors"]`；验证规则需要将其提升为 error（例如 `IrModelingErrorsRule`），避免出现“validate_file 通过但 UI 严格模式拒绝加载”的漂移。
- 图结构校验（`validate_graph_model`）的错误同样需要在验证阶段显式提升为 error（例如 `GraphStructuralErrorsRule`），以对齐 strict fail-closed 的加载行为，让作者在写完代码后即可通过 `validate_file/校验面板` 发现端口类型不匹配、流程入口未连接、数据输入缺来源等结构问题。
- 节点图代码侧的原子规则覆盖布尔条件来源、内联语法限制、变量声明、信号参数名合法性、类型名合法性以及禁止直接在 Graph Code 中写 Python 式常量赋值等约束；图结构与综合规则基于序列化图模型检查端口类型匹配、长连线、未使用结果与不可达代码等问题。节点图变量相关检查（声明合法性与类型合法性）仅消费代码级 `GRAPH_VARIABLES`。信号参数名规则会解析顶层字符串常量（含注解赋值）作为“信号名”输入来源，若值为信号 ID 会报错提醒改用信号名称，避免通过命名常量绕过校验。`if` 条件仍禁止内联 Python 比较（`==`/`!=`/`is` 等），必须使用比较类节点输出布尔值或先赋值后再分支；同时为提升 UI 可读性，新增规则禁止在 `if` 条件中直接写 `逻辑非运算(...)`（要求写成正向条件），并对 `if 是否相等(布尔值, True/False)` 给出 warning 提醒冗余比较；另提供“事件节点多流程出口”warning，帮助发现事件入口意外分叉。
- 节点图变量（GRAPH_VARIABLES）结构体类型绑定已纳入：当结构体/结构体列表图变量提供非空默认值时，校验器会要求 `struct_name` 存在且指向有效结构体定义；该规则由 `code_structure_rules` 装配，供 CLI/UI 校验入口一致复用。
- 节点图代码侧的原子规则覆盖布尔条件来源、内联语法限制、变量声明、信号参数名合法性、类型名合法性以及禁止直接在 Graph Code 中写 Python 式常量赋值等约束；图结构与综合规则基于序列化图模型检查端口类型匹配、长连线、未使用结果与不可达代码等问题。节点图变量相关检查（声明合法性与类型合法性）仅消费代码级 `GRAPH_VARIABLES`。信号参数名规则会解析顶层字符串常量（含注解赋值）作为“信号名”输入来源，若值为信号 ID 会报错提醒改用信号名称，避免通过命名常量绕过校验。`if` 条件允许使用 `not` 对布尔表达式取反；但仍禁止在 `if` 条件中直接书写 Python 比较（`==`/`!=`/`is` 等），必须使用比较类节点输出布尔值或先赋值后再分支。对于函数体内 `x: "布尔值" = ...` 这种带类型注解的变量，校验会将其视为可用于 `if` 条件的布尔来源，避免被迫写 `是否相等(x, True)` 的绕法。
- 容器字面量相关规则已收敛：列表/字典在方法体内走 rewrite 归一化，其余不支持形态由 `UnsupportedPythonSyntaxRule` 兜底；不再保留历史禁令占位规则避免重复报错。
- 语法糖归一化（rewrite）参数上限与 `enable_shared_composite_sugars` 策略由 `engine/graph/utils/graph_code_rewrite_config.py` 作为单一真源；validate 阶段在需要产出 GraphModel 时复用已改写 AST，避免同一套改写链路重复执行。
- 复合节点规则（`composite_types_nesting.py`）覆盖复合节点“引脚类型 + 禁止复合嵌套”的关键约束，并以**真实语义来源**为权威：
  - payload 格式：读取 `COMPOSITE_PAYLOAD_JSON` 中的 `virtual_pins/sub_graph` 做校验；
  - 类格式：读取方法体内 `流程入/流程出/数据入/数据出` 的 pin_marker 扫描结果做校验（而不是依赖装饰器参数）。
  - 非 payload/类格式会直接报错（`COMPOSITE_FORMAT_UNSUPPORTED`），不再兼容旧函数式复合节点格式，避免闭环分裂。
  允许的对外引脚类型为：基础类型/列表类型/字典与“流程”。**泛型仅作为“未设置”的占位**，在保存/成品校验阶段不允许出现在任何对外引脚上（包括：泛型/列表/泛型列表/泛型字典）。严禁旧别名“通用/Any”等，并禁止使用 Python 内置类型名（int/float/str/bool/list/dict），要求统一使用中文端口类型。
- 复合节点引脚方向规则（`composite_pin_direction.py`）补齐“方向一致性”约束：payload 的虚拟引脚方向/流程标记必须与 `mapped_ports` 一致；类格式入口方法内同名引脚禁止同时声明为 `数据入` 与 `数据出`（数据入不能设置为出引脚）；并禁止“数据出变量通过纯别名链透传自数据入/入口形参”（例如 `描述回声 = 说明文本`），避免把数据入当作数据出而导致输出缺少内部映射。
- 复合节点流程结构规则（`composite_flow_nodes_required.py`）：类格式 `@flow_entry` 入口若声明了流程引脚（流程入/流程出），方法体内必须产生至少一个可建模的流程节点（控制流或带流程端口的节点调用），否则报错，避免出现“有流程口但内部无流程链路”。
- 复合节点名称规范规则（`composite_node_name_length.py`）：从文件头 docstring 的 `node_name` 读取，仅要求名称字数不超过 12 个字（不统计 `_` 与空白），避免资源库与节点标题区显示过长。
- 代码结构规则额外覆盖“节点调用必填入参”：基于节点库静态输入端口清单，禁止漏传必填端口（流程端口与变参占位端口除外），并对结构体类节点的“结构体名”取值做存在性校验，避免静默错误。

## 注意事项
- 不在文档字符串或注释中暴露外部知识库或文档系统的具体路径，引用外部资料时保持在“内部规则文档”等抽象描述层级。
- 保持与配置层规则结构和命名的一致性，避免在此层重新硬编码规则常量或重复实现同类数据结构。
- 类型体系（规范中文类型名、结构体/变量允许集合、别名字典解析等）的唯一事实来源为 `engine/type_registry.py`；验证层不得维护平行类型清单，历史导入路径仅保留兼容转发。
- 新增或调整规则时，优先通过现有的 AST 工具、节点库视图与 Schema 视图获取信息，避免在规则内部直接依赖上层 UI、工具或资源加载逻辑。
- GUID 类型在引擎内就是数字 ID（可用字符串包裹数字）形式的标识，纯数字是正常形态；如遇编辑器对数字 GUID 报格式警告，可在使用侧按需忽略该静态检查。
- 节点图代码中的 `GUID/配置ID/元件ID` 数字约束：当值可静态解析为常量（命名常量声明、节点调用入参常量、以及 `GRAPH_VARIABLES` 的 `default_value`）时，必须为 **1~10 位纯数字**（支持整数或数字字符串）；否则会报错 `CODE_ID_LITERAL_DIGITS_1_TO_10_REQUIRED`。

## 补充约定
- 类型占位（`engine.configs.rules.datatypes_typing`）仅用于静态检查；`engine.validate.rules.datatypes_typing` 仅作为兼容旧导入路径的 re-export；节点图“类/文件校验入口”统一由 `engine.validate.node_graph_validator` 提供（runtime 侧仅做 re-export）。
- 数据类型规则（`engine.validate.rules.datatype_rules`）仅作为兼容旧导入路径的 re-export，权威来源为 `engine.type_registry`（避免多处清单漂移与多跳转发）。
- 节点挂载规则以 `engine.configs.rules.node_mount_rules` 为唯一事实来源；`engine.validate.rules.node_mount_rules` 仅作为兼容旧导入路径的 re-export（避免在 validate 层重复维护一份规则数据）。

## 子模块概览
- 原子代码规则（M2 层）：`code_syntax_rules.py` / `code_structure_rules.py` / `code_quality` 聚焦"容器字面量语法糖归一化""布尔条件来源必须为布尔节点""禁止内联 if/算术""长连线/未使用结果/不可达代码""发送信号参数名必须来源于信号定义"等约束。`code_structure_rules.py` 与 `code_quality` 为稳定入口，具体实现分别拆分到 `code_structure/` 与 `code_quality/` 子包中；列表/字典语法糖改写由 `ListLiteralRewriteRule/DictLiteralRewriteRule/SyntaxSugarRewriteRule` 提供，避免解析器静默跳过导致“缺线/缺数据来源”。
  - 语法糖扩展：允许 `a + b / a - b / a * b / a / b`（二元算术）与 `for 序号, 元素 in enumerate(列表变量):`（会改写为 `len + range + 下标读取`；要求列表变量具备 `"X列表"` 注解以推断元素类型）。
- `UnsupportedPythonSyntaxRule` 作为“硬禁止”规则：当 Graph Code/复合节点方法体出现 IR/语法糖无法建模的 Python 语句（如 while/try/with/continue/for-else/推导式/async/yield/方法体 import 等）或出现非节点函数调用时，直接产出 error；同时补齐“IR 会静默跳过”的形态（assert/del/global/nonlocal/海象/三目/残留 AugAssign/纯数据节点裸调用/非 docstring 的非调用表达式语句），保证**非允许即禁止**。
  - 复合节点方法体允许 `流程入/流程出/数据入/数据出` 等“引脚声明辅助函数”调用（pure no-op），它们用于静态声明虚拟引脚，不属于节点函数调用。
  - range 参数额外约束：for iter 的 `range(...)` 仅允许 1~2 个位置参数且参数必须是“变量名或数值常量”（禁止调用/下标/属性/算术表达式），避免 IR 静默把复杂表达式当作 0。
  - 已知节点必须传 game：只要函数名在节点库中，就必须显式传入 `self.game/game`（支持位置参数或 `game=self.game` 关键字形式），避免漏传 game 绕过部分静态规则并在运行期报错。
  - 【获取局部变量】调用结果必须二元拆分赋值或显式下标选择输出端口（句柄/值），避免“把二元返回当作单值”潜伏到运行期。
  - 事件相关：除 `EventNameRule` 校验事件名合法性外，`EventHandlerNameRule` 进一步要求“内置事件”的回调命名必须为 `on_<事件名>`（严格一致），避免 `on_定时器触发时_XXX` 这类看似新事件但实际复用同一内置事件的写法绕过规范；信号事件不强制回调名。
  - 内置事件回调签名：当 `register_event_handler` 注册内置事件且回调为标准命名 `on_<事件名>` 时，校验对应方法的参数名集合必须与事件节点输出端口一致（剔除流程端口），缺参或错名会报错，避免运行期 kwargs 绑定失败。
  - 内置事件“泛型输出端口”类型绑定：当事件节点输出端口类型为 `泛型` 时，即便回调方法体内未使用该参数，也必须在代码中显式绑定为具体中文类型（形参注解或占位注解赋值），否则端口类型无法确定。
  - `OnMethodNameRule` 对所有类结构节点图生效：只要方法名以 `on_` 开头，后缀就必须为内置事件名或已定义信号名/ID（即使未注册也会报错），防止伪事件入口潜伏。
  - 额外包含“未知节点函数名”约束：当代码出现 `某函数(self.game, ...)` 形态但该函数名不在节点库中，会直接报错，避免拼写错误或不存在节点名被静默跳过。
  - 图变量冗余初始化提示（warning）：当 `on_实体创建时` 内【设置节点图变量】把变量设回 `GRAPH_VARIABLES.default_value` 时，报告 `CODE_GRAPH_VAR_REDUNDANT_INIT_DEFAULT`，用于减少无意义的默认值重置噪声。
  - 自定义变量冗余初始化提示（warning）：当 `on_实体创建时` 内【设置自定义变量】写入“可静态识别的常量初始值”（含列表 clear 后写回空列表）时，报告 `CODE_CUSTOM_VAR_REDUNDANT_INIT_ON_ENTITY_CREATED`，用于提醒删除无意义的初始化写入并将初始值收敛到实体/模板的变量定义。
- `code_quality` 额外包含拉取式执行器风险提示 `PullEvalReevaluationHazardRule`（warning）：当【设置自定义变量】写入后，后续流程节点仍依赖同一个【获取自定义变量】节点实例时，报告 `CODE_PULL_EVAL_REEVAL_AFTER_WRITE`，用于提前暴露“重复求值导致条件/数值偏移”的易踩坑；规则会将跨块数据节点副本规约到 `original_node_id`，避免在 for/match 等多块结构中漏报。
- `code_quality` 额外包含“实体销毁时挂载语义提醒与同图冲突检测”（warning+error）：当节点图包含事件【实体销毁时】时先提醒其仅在关卡实体可触发；若同图存在任何“已知挂载限制且无法挂载关卡”的节点/事件则报错，避免把关卡广播事件与玩家/角色等实体专属事件混在同一张节点图中。若作者已在节点图 docstring 中显式声明 `mount_entity_type: 关卡`（或 `owner_entity_type/mount_entity`），将不再重复输出该提醒 warning，但冲突检测仍会执行。
- `code_quality` 额外包含字典“重复求值/引用语义”风险提示 `DictComputeMultiUseHazardRule`（warning）：当字典来源于“计算节点明确声明的字典输出端口”且被多个下游节点消费时，报告 `CODE_DICT_COMPUTE_MULTI_USE`，提示在无缓存的拉取式执行器中可能重复求值而导致“不是同一 dict 引用”，若需要写回语义应改为【节点图变量】承载（局部变量禁止字典类型）。
- `code_quality` 额外包含字典“写回/可变引用”语义约束 `DictMutationRequiresGraphVarRule`（error）：当【对字典设置或新增键值对/以键对字典移除键值对/清空字典】对字典原地修改后，后续流程仍继续依赖同一字典来源，且该字典来源于“计算节点明确声明的字典输出端口”时，报告 `CODE_DICT_MUTATION_REQUIRES_GRAPH_VAR`，要求将字典落到【节点图变量】承载（局部变量禁止字典类型，无法用于缓存/写回）。
- 组合规则（M3 层）：`code_port_types_match.py`、`composite_types_nesting.py` 等模块在端口类型匹配、复合节点嵌套与泛型类型使用等方面补充更高层次的检查，其中端口类型匹配规则会结合节点库中声明的端口类型与枚举候选值，对 Graph Code 中的常量与变量类型进行约束校验。
  - 端口类型匹配会额外对基础算术节点（如加减乘除）的“左值/右值”执行语义级限制：禁止把“布尔值”当作数值参与算术运算，即便节点端口写成了“泛型”也会报错，避免类型语义被隐式滥用。
  - 端口类型匹配会对【数据类型转换】补充“输入类型 → 输出类型”的联动校验：当输入类型与目标类型均可静态推断时，要求该转换对必须存在于 `engine.type_registry.TYPE_CONVERSIONS`，避免出现“浮点数转布尔值”等不支持的组合。
  - 端口类型匹配会对“别名字典”类型端口（`键类型-值类型字典` / `键类型_值类型字典`）执行键/值类型强校验：禁止用 `泛型/泛型字典` 绕过；对可静态识别的字典构造表达式（字典字面量→【拼装字典】、【建立字典】）会检查键/值类型是否匹配；并对 `_`/`-` 两种分隔写法做规范化以避免同义类型误报。
  - 端口跨端口约束补充“同型输入”规则：对 `是否相等/枚举是否相等/数值比较/取较大值/范围限制/加减乘除/拼装列表` 等节点，要求指定输入端口的类型必须完全一致（**整数≠浮点数**），避免在“泛型端口”下混用类型绕过校验；错误码为 `PORT_SAME_TYPE_REQUIRED`。
-  - 工程化扩展：当端口期望类型为 `GUID` / `整数`（及其列表类型）时，允许传入字符串占位符 `ui_key:<key>` / `ui:<key>` 作为常量输入；校验会在节点图位于资源库目录结构下时读取 `管理配置/UI控件GUID映射/ui_guid_registry.json` 并校验该 key 必须真实存在，否则报错；写回 `.gil` 时由 `ugc_file_tools` 将占位符替换为真实整数 ID（常用于 UI 控件索引等 1073741xxx 数字的去硬编码）。
- 规则入口由 `engine.validate.api.validate_files()` 统一装配：`_build_rules()` 会按配置开关与“是否复合节点文件”选择规则集，并通过 `ValidationPipeline` 顺序执行；是否启用严格实体入参校验由配置键 `STRICT_ENTITY_INPUTS_WIRE_ONLY` 控制（由 `validate_files(..., strict_entity_wire_only=...)` 参数注入）。
- `node_index.py` 提供节点库速查与缓存清理工具（`clear_node_index_caches()`），并以“节点库 key 的名称部分（`类别/名称` → `名称`）”作为 Graph Code 的可调用名来源，从而兼容管线注入的别名（如 `make_valid_identifier(name)`）；同时提供“内置事件 → 回调参数名/参数类型”映射，供事件相关规则复用。`ast_utils.py` 负责 AST 解析、源码缓存与统一生成 `EngineIssue` 的辅助函数；涉及节点图代码特有语义时，可以依赖 `engine.graph.utils` 提供的纯函数工具（如复合节点实例提取），避免在规则内部重复实现解析逻辑。
- 语义节点定位统一通过 `engine.validate.node_semantics`：规则不直接硬编码关键语义节点的标题字符串，而是用语义 ID 表达意图（如 signal/graph_var/struct/custom_var），并借助 `node_index` 派生的“可调用名 → 节点 key”映射做 alias/#scope 规约。
- 类型名相关规则负责检查节点图代码中的中文类型注解以及代码级 `GRAPH_VARIABLES` 声明中的图变量类型是否落在引擎支持的数据类型集合内（含基础类型、列表类型、结构体、枚举、泛型等），避免出现诸如“任意”这类未注册的自由类型名，并统一约定仅使用“泛型”这一宽泛类型标识；docstring 中的“节点图变量”段落仅作说明，校验与声明完全忽略。


