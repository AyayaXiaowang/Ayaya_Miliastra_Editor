## 目录用途
`engine/graph/ir/` 负责把类结构 Graph Code 的 AST 转换为 `GraphModel`：控制流建模、节点/端口构造、参数归一化、变量环境与流程/数据连线路由。

## 当前状态
- **入口**：`flow_builder.parse_method_body` + `flow_utils.materialize_call_node` 负责“语句 → 节点/边”的主流程；节点创建在 `node_factory.create_node_from_call`。
- **常量体系（已下沉）**：
  - 模块级命名常量通过 `ast_utils.collect_module_constants` 设置为上下文，供 `extract_constant_value` 解析 `ast.Name`。
  - 方法体内命名常量预扫描写入 `VarEnv.local_const_values`，节点创建时可将 `变量名` 实参回填为 `node.input_constants`。
- **语义元数据（单点写入）**：
  - IR 层不再写入 `GraphModel.metadata["signal_bindings"/"struct_bindings"]`；这些字段统一由 `engine.graph.semantic.GraphSemanticPass` 覆盖式生成（幂等、可复现）。
  - IR 层只负责把“选择端口常量/动态字段端口”建模到 NodeModel（`input_constants` + `ports`），作为 Pass 的推导输入。
- 复合节点虚拟引脚构建以**类格式**为前提（pin_marker + 方法签名推断），不再支持旧函数式复合节点“按顶层函数签名提取引脚”的路径，避免解析口径分裂。
- 事件处理方法参数名推导会对事件节点输出端口名做 `make_valid_identifier` 规范化并保证唯一，避免端口名包含 `：`/括号等导致生成代码出现非法标识符。

## 注意事项
- 端口/参数归一化必须通过 `arg_normalizer.normalize_call_arguments`，避免端口名分叉。
- 本目录保持纯逻辑（不做 UI）；`FactoryContext` 仅承载节点库与名称索引（`node_library/node_name_index`），不再承担语义元数据推导所需的索引注入。
- “纯别名赋值”（`目标 = 某变量`）默认可通过 `handle_alias_assignment` 走快速路径，但当目标变量处于“多分支合流/已有局部变量句柄”模式时必须禁用该优化，避免出现“生成获取局部变量但缺少设置局部变量”的异常图。
- 本文件不记录修改历史，只描述“目录用途、当前状态、注意事项”的实时概况。
