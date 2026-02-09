## 目录用途
存放“校验层/语法约束”相关测试：通过 `engine.validate.validate_files` 等入口验证节点图代码（Graph Code）的静态规则、语法糖改写与类型/命名约束，确保**不符合规范的写法在校验期直接失败**。

## 当前状态
- **语法糖改写与字面量约束**
  - `test_syntax_sugar_rewrite_rule.py`：回归常见语法糖在校验入口统一改写为等价节点调用（含列表/字典下标读写、常见内置函数、比较/逻辑/复合运算、以及 `%` 正模语义（改写为共享复合节点/回退节点链）等）。
  - `test_if_condition_inline_compare_rule.py`：回归 if 条件允许写可归一化的比较/逻辑表达式（语法糖改写后进入布尔规则），同时保持“不支持的 Compare 形态”（如链式比较）仍会在改写阶段 fail-closed。
  - `test_list_literal_rewrite_rule.py`：回归列表字面量与列表相关语法糖改写规则（含下标赋值/删除、append/pop/extend 等）与禁止用法边界。
  - `test_dict_literal_rewrite_rule.py`：回归字典字面量改写为【拼装字典】节点调用的规则与禁止用法边界（空 dict、展开写法、超长等）。
- **语句/语法禁用守卫**
  - `test_unsupported_python_syntax_rule.py`：回归 IR/语法糖无法建模的 Python 语句与“非节点函数调用”必须在校验期报错。
- **事件 / 信号 / 回调规则**
  - `test_event_name_rule.py`：回归事件名（含模块常量传入）必须可解析为内置事件或信号；未知事件名必须报错。涉及示例包信号名时需显式切换 `active_package_id=示例项目模板` 并失效信号仓库缓存，避免默认“仅共享根”导致信号仓库为空。
  - `test_on_method_name_rule.py`：回归 `def on_XXX` 的 `XXX` 必须为内置事件名或已定义信号名/ID（即使未 register）。涉及示例包信号名时同样需要切换 `active_package_id=示例项目模板`。
  - `test_event_handler_name_rule.py`：回归内置事件回调必须命名为 `on_<事件名>`（禁止追加后缀），信号事件不强制回调名。
  - `test_event_handler_signature_rule.py`：回归内置事件回调参数缺失/错名必须报错，避免运行期 kwargs 绑定失败。
  - `test_signal_code_param_names.py`：回归【发送信号】代码层参数名必须存在于信号定义中，且 Graph Code 的“信号名”参数必须使用名称而非 ID。用例依赖示例包信号定义时需切换 `active_package_id=示例项目模板`。
- **变量与求值风险**
  - `test_graph_variable_rules.py`：回归 GRAPH_VARIABLES 声明缺失/类型非法与默认值元数据提取等规则。
  - `test_graph_var_redundant_init_on_entity_created_rule.py`：回归 `on_实体创建时` 冗余把节点图变量设回默认值时应给出 warning（减少无意义初始化噪声）。
  - `test_custom_var_redundant_init_on_entity_created_rule.py`：回归 `on_实体创建时` 冗余初始化自定义变量（写入常量初始值）应给出 warning（减少无意义初始化噪声）。
  - `test_local_variable_rules.py`：回归局部变量相关校验规则（初始化、二元输出选择等）与通用“已知节点必须传 game”约束。
  - `test_alias_assignment_allowed_rule.py`：回归运行期变量之间允许别名赋值（同数据来源映射），同时保持“常量复制赋值”仍报错。
  - `test_dict_mutation_requires_graph_var_rule.py`：回归字典引用/写回语义规则（compute 多下游 warning、原地修改后继续使用 error）。
  - `test_pull_eval_reevaluation_hazard_rule.py`：回归“写入后复用同一 pull-eval 实例”的重算风险 warning，并避免安全写法误报。
- **覆盖类回归**
  - `test_enum_coverage_graphs.py`：回归“枚举覆盖图”包含节点库声明的全部枚举候选值（server/client 分作用域统计；覆盖图按目录收集 `*.py` 文件）。
- **类型一致性 / 节点调用守卫**
  - `test_port_same_type_rule.py`：回归部分比较/运算节点输入端口必须同型的规则（整数≠浮点数）。
  - `test_generic_type_annotation_forbidden_rule.py`：回归显式中文类型注解禁止使用“泛型家族”占位类型（含别名字典键/值类型为泛型的情况），避免用万能类型绕过类型收敛。
  - `test_typed_dict_alias_port_enforced.py`：回归“别名字典端口”键/值类型强校验：当端口期望 `配置ID-整数字典` 时，字典字面量/拼装字典必须满足键=配置ID、值=整数，且禁止用 `泛型/泛型字典` 绕过。
  - `test_unknown_node_call_rule.py`：回归“疑似节点调用但节点不存在/拼写错误”必须在校验期报错。
- `test_guid_ui_key_placeholder.py`：工程化回归：GUID/整数（含列表类型）的常量输入与 `GRAPH_VARIABLES.default_value` 允许 `ui_key:<key>` / `ui:<key>` 占位符；当节点图位于资源库目录结构下时，校验会要求占位符 key 必须存在于 `管理配置/UI源码/**/*.html` 的 `data-ui-key` 集合中（缺失 UI源码 或缺失 key 均应报错）。
- `test_ui_level_custom_var_target_entity_rule.py`：工程化回归：UI源码占位符引用到的 `ui_*` 自定义变量必须写到正确的目标实体；并支持通过 docstring `mount_entity_type: 关卡/玩家` 明确 `self.owner_entity` 的归属。
- **节点库解析与语义入口（校验层单一事实源）**
  - `test_node_def_resolver.py`：回归 `node_def_resolver` 的 key 解析规则（类别规范化、`#{scope}` 优先级与回退）。
  - `test_node_semantics_entrypoints.py`：回归 `node_semantics` 在图数据层优先使用 `NodeDef.semantic_id` 的语义识别入口。

## 注意事项
- 这里的测试应保持“最小 Graph Code 片段 + 明确断言错误码/消息”风格，避免引入 UI 与重型上下文。
- 不在测试里做“判空式容错”；错误应由校验器直接报出。
- GUID 类型在引擎内为数字 ID（也可用字符串包裹数字），测试用 Graph Code 的 GUID 常量应使用纯数字形式，避免 UUID 写法误导。


