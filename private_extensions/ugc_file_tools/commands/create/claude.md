# ugc_file_tools/commands/create 目录说明

## 目录用途

- 存放“生成/创建最小输入样本”的工具入口脚本（多数用于构造合成 GraphModel / `.gia` / `.gil` 的最小可复现用例）。
- 该目录只做参数解析与样本组装；复杂语义/编码规则应复用 `ugc_file_tools/node_graph_semantics/`、`ugc_file_tools/contracts/` 等单一真源模块。

## 当前状态

- 包含若干用于构造信号/节点图最小样本的脚本（例如生成最小发送信号变体的 GraphModel/`.gia`），供回归测试与人工诊断复用。

## 注意事项

- fail-fast：不使用 `try/except` 吞错；输入结构不符直接抛异常。
- 避免在本目录复制端口类型推断/Concrete 规则；应调用语义层公开 API。

