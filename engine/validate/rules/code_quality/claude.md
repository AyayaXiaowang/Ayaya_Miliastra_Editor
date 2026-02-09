## 目录用途
- 存放“代码质量规范”（M2/M3）相关规则实现：长连线、未使用结果、不可达代码、IR/结构错误提升，以及执行器语义风险提示等。
- 对外稳定入口为 `engine.validate.rules.code_quality`。

## 当前状态
- 已按主题拆分为多个小模块，降低单文件体积与耦合，便于按域演进与性能优化。
- 需要解析 GraphModel 的规则统一复用 `graph_model_utils._get_or_parse_graph_model()` 的缓存结果，并使用 strict=False 的“尽力解析”口径，避免 validate 与 UI 严格加载行为漂移。
- 与节点库/端口/语义等权威定义保持解耦：仅通过 `engine.nodes` 注册表与 `engine.configs.rules` 的视图读取信息。
- 模块概览：`basic.py`（长连线/事件多出口/不可达）、`graph_errors.py`（IR/结构错误提升）、`unused_query_output.py`（未使用查询输出）、`entity_destroy_event_mount.py`（销毁事件挂载冲突）、`pull_eval_reevaluation_hazard.py`（拉取式重复求值风险）、`dict_hazards.py`（字典引用语义风险）、`graph_model_utils.py`（共享解析/遍历工具）。
- `graph_errors.py` 对外导出 `IrModelingErrorsRule/GraphStructuralErrorsRule`（稳定 re-export），用于将“IR 无法可靠建模”与“图结构校验失败”提升为 error，避免 validate 与 UI 严格加载口径漂移。

## 注意事项
- 新增/调整规则时，优先放入独立模块，并在 `__init__.py` 的 `__all__` 中补齐。
- 避免跨模块形成环；共享图解析/图遍历逻辑统一收敛在 `graph_model_utils.py`。


