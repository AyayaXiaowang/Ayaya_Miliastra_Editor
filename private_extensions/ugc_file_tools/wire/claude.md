## 目录用途
- wire-level 工具命名空间：统一收口“protobuf-like 的 tag/value 原始字节”相关能力，避免在各功能域里出现多套相似的 wire patch / wire chunk 实现。
- 本目录只提供**稳定导出路径**（`ugc_file_tools.wire.*`），底层实现仍保持单一真源，主要在 `ugc_file_tools/gil_dump_codec/`。

## 当前状态
- `codec.py`
  - 提供 `decode_message_to_wire_chunks` / `encode_wire_chunks` 的统一导出，用于“tag/value 原始字节级 roundtrip/补丁”能力。
- `patch.py`
  - 提供 `parse_tag_raw` / `split_length_delimited_value_raw` / `upsert_varint_field` 等 wire-level 小工具的统一导出。
  - 额外提供 message-bytes 级 patch：`replace_length_delimited_fields_payload_bytes_in_message_bytes(...)`（只替换指定 field 的 length-delimited payload bytes，其它 bytes 原样保留）。
- `__init__.py`
  - 聚合导出：便于 `from ugc_file_tools.wire import ...` 使用。

## 注意事项
- 本目录不实现任何 `.gil/.gia` 语义层逻辑；语义提取应放在对应域（例如 `.gia` 的 VarBase 语义提取）。
- 不使用 try/except；失败直接抛错，保证定位清晰。

