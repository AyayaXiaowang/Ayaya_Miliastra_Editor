# ugc_file_tools/tools 目录说明

## 目录用途
- 存放 **工具索引与风险说明**（文档），用于回答“我该跑哪个工具 / 是否会写盘改存档”。
- 本目录不再承载同名 CLI wrapper（避免“双入口 / 同名多处实现”）。

## 当前状态
- `工具索引.md`：按读写风险分类的工具清单（优先参考；由注册表生成）。
  - 已包含 `.gia` 相关的辅助导出/写回工具（例如 `gia_to_readable_json`、`gia_graph_ir_to_gia`、`gia_build_entity_decorations_wire`）。
  - 也包含通用分析辅助工具（例如 `inspect_json` 用于 JSON 深层路径探测）。
  - 已包含信号专项诊断工具（例如 `inspect_gil_signals` 用于“同一信号多点发送/监听”排查与格式反推）。
- `generate_tool_index_md.py`：从 `ugc_file_tools/tool_registry.py` 生成/校验 `工具索引.md`。
  - 写入：`python -X utf8 -m ugc_file_tools.tools.generate_tool_index_md --write`
  - 校验：`python -X utf8 -m ugc_file_tools.tools.generate_tool_index_md --check`
- 统一运行方式：`python -X utf8 -m ugc_file_tools tool <name> --help`
- 不提供 `encode_gil` 工具入口：JSON→GIL 回写能力仍为预留/未实现，避免占位功能误导用户。
  - `.gia` 最终导出目录说明以 `ugc_file_tools.beyond_local_export.get_beyond_local_export_dir()`（基于 `Path.home()`）为准。

## 注意事项
- 本目录不放业务/写回核心逻辑；核心实现应沉淀在 `gil_package_exporter/`、`package_parser/`、`graph_codegen/`、`gil_dump_codec/`、`node_graph_writeback/` 等模块目录。
- 入口脚本不使用 `try/except`；错误直接抛出即可。
- 工具名/风险/一句话说明的单一真源为 `ugc_file_tools/tool_registry.py`；`工具索引.md` 不手改。

