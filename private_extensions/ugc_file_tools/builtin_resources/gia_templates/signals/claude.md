## 目录用途
- 存放 `ugc_file_tools` 信号相关的内置 `.gia` 模板资源（GraphUnit 结构模板），供信号导出/创建示例等命令直接引用。

## 当前状态
- `signal_node_defs_full.gia`：信号导出默认模板（覆盖更全的信号 node_def 形态）。
- `signal_node_defs_minimal.gia`：单信号最小模板（用于演示参数类型差异、生成示例节点图等）。

## 注意事项
- 模板应保持可公开、仅结构夹具，不应包含未授权业务内容。
- 缺失应 fail-fast 抛错，不做静默降级。

