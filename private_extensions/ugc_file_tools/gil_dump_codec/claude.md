## 目录用途
- 提供“dump-json ↔ `.gil` 二进制 payload”的最小闭环能力：
  - 将 dump-json（数值键 JSON）重新编码为 protobuf-like bytes
  - 将 payload bytes 按 `.gil` 容器头尾封装为可写入的 `.gil` 文件
- 该目录聚焦“通用编码/封装”，不包含具体 UI 业务逻辑；UI 改动逻辑放在 `ui_patchers/`。

## 当前状态
- `protobuf_like.py`：统一的 protobuf-like codec（**唯一真源**）：
  - encoder：将 dump-json 的“数值键 JSON(dict)”编码为 protobuf-like bytes（支持 varint/fixed32/fixed64/length-delimited/nested/repeated；fixed64 仅在值为 `{"fixed64_int": ...}` / `{"fixed64_double": ...}` 形态时启用）。
  - decoder：提供 `decode_gil` 风格的 lossless 解码（field_map 中间表示）与 `gil_to_readable_json` 的 readable 解析（含 string/message/packed/bytes 判定）。
  - utf8 判定护栏：当 length-delimited bytes 的 UTF-8 文本包含“非 printable 且不在 `\\t\\r\\n` 内”的控制字符时，不写入 `utf8` 字段（仅保留 `raw_hex`），避免写回链路把嵌套 message bytes 误当作文本导致 payload 漂移/存档拒识。
  - wire roundtrip：提供 `decode_message_to_wire_chunks/encode_wire_chunks`，用于“tag/value 原始字节级重组”自检与排障（不做 sanitize、不做语义解析）。
  - 底层口径（varint/fixed32/64/length-delimited、文本判定、packed 判定）集中维护，避免工具间互相打脸。
- `protobuf_like_bridge.py`：表示层桥接（集中维护，供 `.gil/.gia` 共享）：
  - `decoded_field_map ↔ numeric_message ↔ binary_data_text(<binary_data> ...)`
  - 不实现 wire 规则，仅调用 `protobuf_like.py` 做编解码/判定；用于消除工具脚本里的重复互转实现。
  - 支持写回/roundtrip 的 **lossless 模式**：当 length-delimited 节点同时包含 `raw_hex/utf8` 时，可选择优先使用 `raw_hex`，避免 sanitize/strip 导致 payload 字节变化。
- `gil_container.py`：基于输入 `.gil` 的 header/footer 参数封装输出 `.gil`（不依赖 JSON→GIL 的 DLL 实现）。
  - `read_gil_payload_bytes(...)`：从 `.gil` 读取 payload bytes（不含头尾封装），用于纯 Python dump/分析/写回链路复用。
  - `read_gil_payload_bytes_and_container_meta(...)`：读取 payload bytes + 容器 meta（header fields），用于消除多处手搓容器解析导致的口径漂移。
- `dump_gil_to_json.py`：纯 Python `.gil → dump-json`：
  - 直接解码 `.gil` payload 为“数值键 JSON”，并输出顶层 `{"4": <payload_root>}` 结构，供 UI/写回工具作为统一中间表示。
- `dump_json_tree.py`：dump-json 数值键树工具（写回侧复用）：
  - 提供 `ensure_dict/ensure_list/ensure_list_allow_scalar` 等“树编辑”小工具，避免在不同写回域重复实现导致漂移。
  - 提供统一入口 `load_gil_payload_as_dump_json_object/load_gil_payload_as_numeric_message`（纯 Python in-memory 解码，不落临时文件），并支持 `prefer_raw_hex_for_utf8` 的 lossless 模式。
- `wire_patch.py`：wire-level 小工具（供写回侧复用）：
  - 解析 `tag_raw` 得到 `(field_number, wire_type)`，并提供 length-delimited 的 `value_raw` 拆分/重建工具。
  - 提供 varint 字段的 upsert（优先替换第一个匹配项，不存在则追加），用于在不全量重编码 payload 的前提下更新少量字段（例如修改时间）。
  - 提供 “只替换指定 length-delimited 字段 payload bytes” 的 message-bytes 级 patch：`replace_length_delimited_fields_payload_bytes_in_message_bytes(...)`，用于避免复杂 base `.gil` 在 decode→encode 全量重编码时发生 payload drift。

## 注意事项
- 不使用 try/except；编码/封装遇到不支持的结构直接抛错，避免生成不可控的损坏存档。
- 该编码器假设 dump-json 输出的 float 对应 wire_type=5（fixed32），与当前样本一致。
- dump-json 中可能出现 `-1`（常见于 Transform 的占位字段），编码时会按 32-bit two's complement 映射为 `uint32` 再写入 varint。
- decoder 会将 `tag=0` / `field_number<=0` 视为非法并停止解析，避免产出 `field_0` 导致回写 encoder 抛错。
- length-delimited 的 bytes 在尝试“嵌套 message”识别前，会先做 packed-varint(GUID stream) 探测：当 bytes 看起来像 GUID 列表（例如 UI record children varint stream）时，强制保持为 `raw_hex`，避免误判为嵌套 message 导致回写时字节语义漂移。