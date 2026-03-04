# engine/graph

## 目录用途

图领域纯逻辑：GraphModel/IR 建模、Graph Code 解析与校验、复合节点格式解析与语义 pass（信号/结构体绑定）等。不包含具体节点实现，也不承担运行时代码生成。

## 当前状态

- 复合节点格式支持 payload 与类格式；格式判定与提取统一在 `graph/composite/source_format.py`。
- 图结构校验以 `validate_graph_model(...)` 等公开入口为准，用于检查连线、数据来源与端口类型等一致性。
- `validate_graph_model(...)` 会校验每条边引用的 `src_port/dst_port` 必须存在于对应节点的 `outputs/inputs` 中；对“非动态端口节点传入不存在的关键字参数”这类情况 fail-fast，避免问题延迟到写回/导出阶段才以低层异常暴露。
- `validate_graph_model(...)` 解析 NodeDef 时以 `NodeModel.node_def_ref` 为真源；当 `node_def_ref.kind="event"` 但 `category/title` 可确定性映射到节点库内置 key（`<category>/<title>`）时，会解析对应 NodeDef 以复用静态端口类型（常见：信号监听事件入口），避免结构校验阶段将内置静态输出端口误判为“泛型未实例化”。
- Graph Code 解析前会执行语法糖归一化（列表/字典字面量、常见表达式语法糖等）；并支持“三维向量常量”在调用入参位置的写法：当端口期望类型为 `三维向量` 时，允许写 `(x, y, z)`（括号 tuple）作为端口常量写入 `input_constants`（不额外生成节点），保证预览与写回语义稳定。
- 需要布局时统一通过 `engine.layout` 的公开能力计算并写回缓存；反向生成 Graph Code 的实现位于 `reverse_codegen/`（工具链 round-trip 用）。
- 端口“有效类型”推断的单一真源为 `port_type_effective_resolver.EffectivePortTypeResolver`；其会优先消费 `GraphModel.metadata["port_type_overrides"]`（如局部变量建模写入的中文类型覆盖），并将 `""/泛型/字典/列表/泛型<...>` 等视为“泛型家族”（未实例化），交付边界需显式收口与 fail-fast。

## 注意事项

- 保持纯逻辑与确定性：禁止读写磁盘与 UI；禁止反向依赖 `app/*`、`plugins/*`、`assets/*`。
- “工作区根目录”统一称为 `workspace_root`；需要节点库/布局上下文时通过参数显式注入，避免隐式全局状态。
- 不使用 `try/except` 吞错；异常应直接抛出以暴露数据/脚本问题。
