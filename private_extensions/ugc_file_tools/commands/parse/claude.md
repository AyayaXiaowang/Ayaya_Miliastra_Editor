# ugc_file_tools/commands/parse 目录说明

## 目录用途
- 存放“解析/只读导出”类工具入口（CLI 薄封装），用于将 `.gil/.gia` 转为可读产物（JSON/Graph IR/Markdown）或抽取包结构信息。

## 当前状态
- `.gil`：
  - `parse_gil_payload_to_graph_ir.py`：直接解析 `.gil` payload 的 NodeGraph blob（section10 groups）并导出 Graph IR（JSON + 可选 Markdown；容器切片统一复用 `gil_dump_codec/gil_container.py`）。
  - `gil_to_readable_json.py`：`.gil` payload 转可读 JSON（含字符串索引等辅助；容器头/尾解析复用 `gil_dump_codec/gil_container.py` 的单一真源）。
  - `extract_graph_entry_demo_gil.py`：从 `.gil` 抽取/裁剪单张节点图；支持 `--drop-other-graphs` 真正裁剪节点图段，仅保留目标 GraphEntry（其余段保持不变）。
- `.gia`：
  - `parse_gia_to_graph_ir.py`：解析 `.gia` 内嵌 NodeGraph → Graph IR（实现复用 `graph/node_graph/gia_graph_ir.py`，本脚本保持“参数解析 + 编排 + 写盘”）。
- 解析实现（语义层）已逐步下沉到 `ugc_file_tools/graph/node_graph/*`：
  - `.gil payload → Graph IR` 的 shared 实现位于 `ugc_file_tools.graph.node_graph.gil_payload_graph_ir`。
  - 本目录脚本尽量保持“参数解析 + 编排 + 写盘”。

## 注意事项
- 本目录仅做入口与编排；不要在这里复制/散落跨域语义规则，公共解析应落到 `ugc_file_tools/graph/*` 或 `ugc_file_tools/contracts/*`。
- 不使用 `try/except`；解析失败直接抛错（fail-fast），便于定位真源口径差异。
- 本目录入口脚本不再作为独立 CLI 入口：直接执行会提示改用统一入口。
- **在 Cursor/IDE 的“工具调用输出回传”环境中，不要依赖 stdout 回显判断脚本是否完成**：少数情况下终端回显会丢失/延迟，表现为“似乎永远没有结果”。
  - 解析/导出类工具的**真结果**以落盘文件为准：统一检查 `private_extensions/ugc_file_tools/out/<output_dir>/index.json` 与 `graphs/*.json` 是否生成。
  - 推荐用法：先跑命令生成产物，再用 PowerShell `Get-Content`/`ConvertFrom-Json` 读取 `index.json` 做后续对比与诊断（避免卡在回显上）。

