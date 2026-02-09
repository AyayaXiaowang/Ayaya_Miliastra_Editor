## 目录用途
- 存放“信号系统”综合校验规则的拆分实现，服务于包级一致性验证：信号存在性、参数端口覆盖、常量类型与连线类型兼容性等。
- `engine.validate.comprehensive_rules.signal_rule` 保持为稳定入口；本目录仅承载实现细节，便于维护与复用。

## 当前状态
- 按功能域拆分：定义边界检查、单图扫描与节点级校验、端口覆盖、常量类型解析、连线类型兼容、边索引与 NodeDef 解析等。
- 共享逻辑以纯函数形式暴露，便于后续引入更细粒度的缓存（例如按 graph_id 的快照缓存、按 signal_id 的参数视图缓存）。
- NodeDef 解析统一复用 `engine.validate.node_def_resolver.resolve_node_def_from_library`（带 scope 优先级），避免在信号规则内重复拼 `candidate_key/#scope` 逻辑导致漂移。
- 发送/监听信号节点的识别与 alias/#scope 兼容统一复用 `engine.validate.node_semantics`；静态端口集合复用 `engine.graph.common` 的 `SIGNAL_SEND_STATIC_INPUTS` / `SIGNAL_LISTEN_STATIC_OUTPUTS` 常量，避免散落硬编码。
- 信号使用规则对“挂载节点图”的扫描范围包含：模板/实体摆放/关卡实体挂载的节点图，以及玩家模板（战斗预设/玩家模板）中 `metadata.player_editor.*.graphs` 挂载的节点图，避免漏扫导致的“信号定义存在但用法未被校验”。

## 注意事项
- 本目录规则只能依赖 `engine.*`，禁止依赖 `app/*` / `plugins/*` 或任何内部开发工具链。
- 信号节点的 `node.input_constants` 可能包含语义提示用的隐藏键（如 `__signal_id`）；这些键不对应真实端口，不应参与“参数端口覆盖”等一致性校验的端口集合计算。
- 新增信号相关综合规则时，优先在本目录新增模块并在 `usage.py` 中装配，避免把逻辑堆回单文件。


