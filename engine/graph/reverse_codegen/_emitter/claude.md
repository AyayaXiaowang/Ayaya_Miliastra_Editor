## 目录用途
`reverse_codegen/_emitter` 是 `engine.graph.reverse_codegen.emitter` 的内部实现子包，用于承载事件体结构化发射、节点调用参数渲染与命名等纯逻辑实现细节。

## 当前状态
- 入口类：`structured_event_emitter.py::_StructuredEventEmitter`（由 `reverse_codegen/emitter.py` 兼容 re-export）。
- 模块拆分：`constants.py`（常量）、`call_args.py`（调用参数）、`naming.py`（命名）、`core.py`（边索引/可达性）、`data_emitter.py`（数据节点/表达式）、`flow_emitter.py`（结构化控制流发射）、`flow_handlers.py`（控制流节点处理器）。

## 注意事项
- 保持纯逻辑与确定性；禁止 I/O 与 UI；不使用 `try/except` 吞错；无法稳定表达时应抛 `ReverseGraphCodeError`。
- 本目录为内部实现细节，外部应通过 `engine.graph.reverse_codegen.emitter` 或更高层稳定入口使用。

