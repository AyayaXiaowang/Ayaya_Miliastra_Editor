## 目录用途
`engine/graph/ir/` 负责把类结构 Graph Code 的 AST 转换为 `GraphModel`：控制流建模、节点/端口构造、参数归一化、变量环境与流程/数据连线路由。

## 当前状态
- **主流程**：`flow_builder.parse_method_body` 解析语句块并产出节点/边；`node_factory.create_node_from_call` 负责把调用表达式物化为 `NodeModel`。
- **分支/循环续接点**：`parse_method_body` 返回 `(nodes, edges, final_prev_flow_node)`，用于精确表示“该语句块最终可继续接续的流程前驱”，避免仅靠“最后一个流程节点”猜测导致嵌套分支连线丢失。
- **break 语义**：`break` 会被物化为【跳出循环】节点（流程入/流程出），并由该节点连接到循环节点输入端口【跳出循环】，用于显式表达“从循环体跳出”的控制流。
- **NodeDefRef 真源**：IR 产出的 `NodeModel` 必须填充 `node_def_ref`（kind+key），后续校验/UI/导出不得再基于 `title` 做 NodeDef 查找。
- **常量与默认值**：模块常量与方法内命名常量会写入 `node.input_constants`（保留原始 Python 值类型）；当 `NodeDef.input_defaults` 存在时，未显式传入的端口会回填默认常量。
- **强类型列表入参定型**：当列表字面量被改写为【拼装列表】并连接到“明确的列表类型端口”（如 `配置ID列表/元件ID列表/阵营列表/三维向量列表`）时，会为【拼装列表】的输出端口写入 `GraphModel.metadata["port_type_overrides"]`，用于稳定 UI 预览与写回时的“有效端口类型”。
- **作用域感知**：`FactoryContext.graph_scope`（server/client）影响同名节点变体选择与局部变量建模策略，保证端口定义与校验口径一致。
- **语义元数据单点写入**：`signal_bindings/struct_bindings` 等由 `engine.graph.semantic.GraphSemanticPass` 覆盖式生成，IR 仅提供可推导输入（常量/端口/边）。

## 注意事项
- 端口与实参归一化必须通过 `arg_normalizer.normalize_call_arguments`，避免端口名分叉。
- 本目录保持纯逻辑：不做 I/O/UI；避免把语义推导/缓存逻辑塞进 `FactoryContext`。
- 优化（别名赋值/预声明常量等）必须以 `VarEnv` 的分支/循环快照语义为准，避免生成缺失写回的局部变量句柄。

