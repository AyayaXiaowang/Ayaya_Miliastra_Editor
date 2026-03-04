## 目录用途
GraphModel → “类结构 Python Graph Code” 的反向生成与 round-trip 语义签名比较（纯逻辑）。

## 当前状态
- 入口生成与模块骨架输出：`generator.py`。
- 事件体发射器：`emitter.py`（结构化输出 `if/match/for/break` 等控制流）。
- 反向生成选项：`_common.py::ReverseGraphCodeOptions` 支持 `prefer_arithmetic_operators`，可将基础算术节点（加减乘除）在输出时还原为带括号的运算符表达式（仅在端口有效类型为整数/浮点数时启用；否则 fail-closed）。
- break 还原策略：当图中存在【跳出循环】节点且其流程后继连接到循环节点输入【跳出循环】时，反向生成会将其输出为语句级 `break`（而非节点调用）。
- 语义签名：`signature.py`（忽略 node/edge id 与布局坐标的差分）。
- 遇到无法稳定表达的结构会 fail-closed 抛 `ReverseGraphCodeError`。

## 注意事项
- 保持纯逻辑与确定性；禁止读写磁盘与 UI 操作；不使用 `try/except` 吞错。
- 对外使用稳定入口（如 `engine.graph.graph_code_reverse_generator` 及包级 re-export），本目录内部模块路径不作为稳定依赖。

