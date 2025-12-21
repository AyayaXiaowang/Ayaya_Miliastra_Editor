# 目录用途
图模型、图变换与解析（不含具体节点实现）。

# 公共 API
通过 `engine` 顶层导出（本子包默认内部）。

# 当前状态
- 复合节点类格式解析：节点显示名固定取类名，忽略 docstring 中的 node_name/composite_name，避免遗漏元数据导致列表出现空标题。
- 复合节点解析同时支持“类逻辑解析（装饰器/引脚标记/IR）”与“payload 直读”：若文件顶层存在 `COMPOSITE_PAYLOAD_JSON`（多行 JSON 字符串），解析器会直接反序列化为 `CompositeNodeConfig`，用于 UI 可视化编辑落盘的闭环；该路径不再强制重跑布局，以尊重落盘的节点位置与连线结构。
- 复合节点源码格式判定统一由 `engine.graph.composite.source_format` 提供（payload / @composite_class）；**旧函数式复合节点格式不再支持**，避免“校验/解析/懒加载展示”口径分裂。
- 图模型需要就地执行布局时，统一通过 `engine.layout.LayoutService.compute_layout(..., clone_model=False)` 触发布局计算与缓存同步。
- `apply_layout_quietly(...)` 支持显式注入 `node_library/registry_context`：复合节点解析阶段会基于传入的基础节点库派生布局依赖，避免解析期反向触发 `NodeRegistry` 导致递归加载。
- 复合节点解析与虚拟引脚构建器依赖统一的 IR 管线，生成的子图可直接复用布局与校验工具；复合实例映射通过公共工具生成，解析与校验共享逻辑。类型标注解析统一通过 `validate_pin_type_annotation` 做规范化处理：其允许集合与规范中文类型名的唯一事实来源为 `engine/type_registry.py`；优先接受中文端口类型，并允许在特定场景下将 Python 内置类型名（int/float/str/bool/list/dict）转换为中文类型；在资源/复合节点等默认场景下，遇到这类内置类型名会记录告警并回退为“泛型”，避免单个复合节点写错阻断整体加载。注意：复合节点对外引脚的“允许/禁止类型”由校验规则决定；“泛型/列表/泛型列表/泛型字典”等占位类型可用于编辑期提示，但在保存/成品校验阶段必须被替换为具体类型。
- Graph API 构建器通过 `open_branch_state/close_branch_state` 驱动 `BranchState`，提供 builder 上下文管理器与数据输入统一接线方法，嵌套流程和常量注入保持稳定。
- 图解析与 IR 管线在遇到【发送信号】/【监听信号】节点时，会结合 `GraphModel.metadata["signal_bindings"]` 输出统一的信号事件名（signal_id）与参数信息，供上层（应用层/工具层）在生成可运行代码时复用。
- **运行时绑定的源码生成**（节点图可运行代码、复合节点函数/类代码）已迁移到 `app/codegen/`：`engine.graph` 仅保留 GraphModel/IR/解析与校验，不再包含任何“导入 runtime/plugins”的生成器实现。
- 变量命名、函数调用表达式与输出映射策略仍集中在 `engine.graph.common`（如 `render_call_expression/finalize_output_var_names`），供解析、校验与上层生成器共享，保持行为一致且可预测。
- 信号节点的标题与静态端口名集中定义在 `common.SIGNAL_SEND_NODE_TITLE/SIGNAL_LISTEN_NODE_TITLE` 及对应常量中，其中两类节点的“信号名”输入端口通过 `is_selection_input_port` 统一视为仅支持行内编辑的选择端口（不可连线），其值由 UI 根据已绑定的 `SignalConfig.signal_name` 写入 `node.input_constants["信号名"]`。
- GraphCodeParser 传入预解析 AST 给 `CodeToGraphParser`：IR 管线与元数据提取避免重复解析，并在 `validate_graph` 中统一检查流程/数据连线、流程入口与数据来源，同时尊重图模型中记录的 `source_lineno/source_end_lineno` 以输出贴合源码的错误提示；在解析 Graph Code 时，对 `match` 语句统一走 IR 分支构建：普通 `match 变量:` 生成【多分支】节点，而形如 `match self.<复合实例>.<入口方法>(...)` 的写法会识别为"以复合节点为控制点的多流程出口"，`case "出口名":` 将对应复合节点在节点库中标记为"流程"类型的同名输出端口连到该分支体的首个流程节点，从而在宿主图中显式表达复合节点多个流程出口的后继逻辑，即便这些端口名本身不包含"流程"等关键字；对于带字符串类型注解的常量变量（AnnAssign），解析层支持将其作为"命名常量"回填到节点的 `input_constants`，不通过数据连线表达。
- 语义元数据单一写入阶段（根除多源写入）：
  - `engine.graph.semantic.GraphSemanticPass` 是唯一允许写入 `GraphModel.metadata["signal_bindings"/"struct_bindings"]` 的实现，输出为覆盖式重建（幂等、可复现）。
  - Parser/UI/工具层只能写入“节点本体的意图/常量/端口”，供 Pass 推导：
    - 信号：`node.input_constants["信号名"]`（展示）+ `node.input_constants["__signal_id"]`（稳定 ID；Pass 会回填）
    - 结构体：`node.input_constants["结构体名"]`（展示）+ `node.input_constants["__struct_id"]`（稳定 ID；Pass 会回填）
  - 模块级命名常量通过 `collect_module_constants + set_module_constants_context` 供 `extract_constant_value` 解析，方法体内命名常量通过 `VarEnv.local_const_values` 支持 `变量名` 实参回填。
- Graph Code 与 `GraphModel` 在本层只建模"使用哪些节点、如何连线以及如何布局"，不会执行节点实际业务逻辑；该层的主要用途是为 AI/脚本和开发者提供一个可验证、可排版的节点图中间表示。
- 复合节点解析支持**模块级常量引用**：在类外定义的常量（如 `关卡GUID: "GUID" = "1094713345"`）可以在节点调用参数中直接使用。解析时通过 `collect_module_constants` 收集模块顶层常量，并在 `extract_constant_value` 中通过上下文查找解析，最终回填到节点的 `input_constants`。
- 节点图 docstring 元数据解析集中在 `utils/metadata_extractor.py`，支持从“节点图变量”段落中提取变量名/类型/默认值，并识别尾部方括号标签：`[对外暴露]` 用于标记 `is_exposed`，其他标签（如 `[内部状态，说明…]`）会写入变量的 `description` 字段，不再污染默认值；事件流注释提取工具按源码行精确匹配节点并安全扩展事件流注释。
- `entity_templates.py` 以 `engine.configs.rules.entity_rules.ENTITY_TYPES` 为规则源，集中维护实体/模板与节点图变量共享的“规范中文变量类型”列表，并通过 `get_entity_type_info` 这类函数为 UI 提供实体类型的图标、默认节点图与规则说明，涵盖字符串/整数/浮点数/布尔值/三维向量/实体/GUID/配置ID/元件ID/阵营及其列表形式，以及结构体、结构体列表和字典类型。
- 图的流程/数据连线路由与默认流程出口策略集中在 `graph/ir` 层，由 `edge_router`、`flow_builder` 等模块协同实现；上层仅通过 Graph API 与 `validate_graph` 观察结果，不直接依赖具体连线推断细节。
- 常量提取增强：除模块顶层常量外，解析节点图类时也会收集 class body 顶层“类常量”（AnnAssign/Assign 且右值可静态提取），并以 key=`"self.<字段名>"` 注入常量上下文，使 `self._xxx` 这类写法在作为节点入参时可被静态回填到 `node.input_constants`（常见于定时器名称、变量名等标识性参数）。

# 依赖边界
- 允许依赖：`engine/utils`、`engine/validate`（有限度），其中图语义/算法统一通过 `engine.utils.graph` 子包获取，调试输出统一使用 `engine.utils.logging`.
- 禁止依赖：`app/*`、`plugins/*`、`assets/*`

# 注意事项
- 保持纯逻辑与确定性，禁止读写磁盘与 UI 操作。 

