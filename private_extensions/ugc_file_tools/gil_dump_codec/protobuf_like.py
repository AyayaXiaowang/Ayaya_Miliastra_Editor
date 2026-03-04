from __future__ import annotations

import base64
import hashlib
import struct
from typing import Any, Dict, Iterable, List, Optional, Tuple


JsonValue = Any


def encode_message(message_object: Dict[str, Any]) -> bytes:
    """
    将 dump-json 的“数值键 dict”编码为 protobuf-like bytes。

    约定（与当前样本一致）：
    - int -> wire_type=0 (varint)
    - float -> wire_type=5 (fixed32 float)
    - str -> wire_type=2 (utf-8 string)
    - "<binary_data> XX ..." -> wire_type=2 (bytes)
    - dict -> wire_type=2 (nested message)
    - list -> repeated field（对每个元素单独写入一次同 field_number 的 tag+value）
    """
    if not isinstance(message_object, dict):
        raise TypeError(f"encode_message expects dict[str, Any], got {type(message_object)}")

    chunks: List[bytes] = []
    for field_key in _sorted_field_keys(message_object.keys()):
        value = message_object[field_key]
        field_number = _parse_field_number(field_key)
        chunks.extend(_encode_field_value(field_number, value))
    return b"".join(chunks)


def _sorted_field_keys(keys: Iterable[str]) -> List[str]:
    numeric_keys: List[Tuple[int, str]] = []
    other_keys: List[str] = []
    for key in keys:
        if isinstance(key, str) and key.isdigit():
            numeric_keys.append((int(key), key))
        else:
            other_keys.append(str(key))
    numeric_keys.sort(key=lambda item: item[0])
    other_keys.sort()
    return [key for _num, key in numeric_keys] + other_keys


def _parse_field_number(field_key: str) -> int:
    if not isinstance(field_key, str) or not field_key.isdigit():
        raise ValueError(f"field key must be numeric string, got {field_key!r}")
    field_number = int(field_key)
    if field_number <= 0:
        raise ValueError(f"field number must be >= 1, got {field_number}")
    return field_number


def _encode_field_value(field_number: int, value: Any) -> List[bytes]:
    if isinstance(value, list):
        chunks: List[bytes] = []
        for element in value:
            chunks.extend(_encode_field_value(field_number, element))
        return chunks

    if isinstance(value, dict):
        # 兼容“decoded_field_map 风格节点”的 fixed64 表示：
        # - {"fixed64_int": <u64>} 或 {"fixed64_double": <float>}（或两者同时存在）
        # 说明：该形态不会与 nested message 冲突（nested message 的 key 只会是数字字符串）。
        if "fixed64_int" in value or "fixed64_double" in value:
            raw_u64 = value.get("fixed64_int")
            if isinstance(raw_u64, int):
                return [
                    encode_tag(field_number, 1),
                    int(raw_u64).to_bytes(8, byteorder="little", signed=False),
                ]
            raw_f64 = value.get("fixed64_double")
            if isinstance(raw_f64, (float, int)):
                return [
                    encode_tag(field_number, 1),
                    struct.pack("<d", float(raw_f64)),
                ]
            raise TypeError(
                f"unsupported fixed64 node for field {field_number}: {value!r}"
            )
        nested_bytes = encode_message(value)
        return [
            encode_tag(field_number, 2),
            encode_varint(len(nested_bytes)),
            nested_bytes,
        ]

    if isinstance(value, bool):
        # dump-json 通常不会直接输出 bool；为稳妥起见按 varint 处理
        return [
            encode_tag(field_number, 0),
            encode_varint(1 if value else 0),
        ]

    if isinstance(value, int):
        return [
            encode_tag(field_number, 0),
            encode_varint(value),
        ]

    if isinstance(value, float):
        return [
            encode_tag(field_number, 5),
            struct.pack("<f", float(value)),
        ]

    if isinstance(value, str):
        if value.startswith("<binary_data>"):
            raw_bytes = parse_binary_data_hex_text(value)
            return [
                encode_tag(field_number, 2),
                encode_varint(len(raw_bytes)),
                raw_bytes,
            ]
        encoded = value.encode("utf-8")
        return [
            encode_tag(field_number, 2),
            encode_varint(len(encoded)),
            encoded,
        ]

    raise TypeError(
        f"unsupported value type for field {field_number}: {type(value).__name__}"
    )


def encode_tag(field_number: int, wire_type: int) -> bytes:
    if field_number <= 0:
        raise ValueError(f"field_number must be >= 1, got {field_number}")
    if wire_type not in (0, 1, 2, 5):
        raise ValueError(f"unsupported wire_type: {wire_type}")
    tag_value = (int(field_number) << 3) | int(wire_type)
    return encode_varint(tag_value)


def encode_varint(value: int) -> bytes:
    if not isinstance(value, int):
        raise TypeError(f"varint value must be int, got {type(value).__name__}")
    if value < 0:
        # 样本中的 NodeType::Int 会将 0xFFFFFFFF 表示为 -1。
        # `.gil` 内实际存储更像是 uint32 varint，因此这里按 32-bit two's complement 映射回无符号值。
        value = int(value) & 0xFFFFFFFF
    parts: List[int] = []
    remaining = int(value)
    while True:
        byte_value = remaining & 0x7F
        remaining >>= 7
        if remaining:
            parts.append(byte_value | 0x80)
        else:
            parts.append(byte_value)
            break
    return bytes(parts)


def decode_varint(byte_data: bytes, offset: int, end_offset: int) -> Tuple[int, int, bool]:
    """
    读取一个 protobuf-like varint。

    返回: (value, next_offset, ok)
    - ok=False 表示遇到 EOF 或超过 64-bit 限制
    """
    if offset < 0:
        raise ValueError(f"offset must be >= 0, got {offset}")
    if end_offset < 0:
        raise ValueError(f"end_offset must be >= 0, got {end_offset}")
    if end_offset > len(byte_data):
        raise ValueError(f"end_offset out of range: end_offset={end_offset}, size={len(byte_data)}")

    value = 0
    shift_bits = 0
    current_offset = offset
    while True:
        if current_offset >= end_offset:
            return 0, current_offset, False
        current_byte = byte_data[current_offset]
        current_offset += 1

        value |= (current_byte & 0x7F) << shift_bits
        if (current_byte & 0x80) == 0:
            return value, current_offset, True

        shift_bits += 7
        if shift_bits >= 64:
            return 0, current_offset, False


def decode_varint_with_raw(byte_data: bytes, offset: int, end_offset: int) -> Tuple[int, int, bytes, bool]:
    """
    读取一个 protobuf-like varint，并同时返回原始字节（用于 wire-level roundtrip）。

    返回: (value, next_offset, raw_bytes, ok)
    """
    value, next_offset, ok = decode_varint(byte_data, offset, end_offset)
    raw_bytes = bytes(byte_data[offset:next_offset])
    return int(value), int(next_offset), raw_bytes, bool(ok)


def decode_message_to_wire_chunks(
    *,
    data_bytes: bytes,
    start_offset: int,
    end_offset: int,
) -> Tuple[List[Tuple[bytes, bytes]], int]:
    """
    wire-level 解码：按“tag_raw + value_raw”拆分 message，不做任何语义解析与 sanitize。

    用途：
    - roundtrip 自检：确保“读取->写回”在字节层面完全一致（包括非规范 varint 编码）。
    """
    if start_offset < 0:
        raise ValueError(f"start_offset must be >= 0, got {start_offset}")
    if end_offset < 0:
        raise ValueError(f"end_offset must be >= 0, got {end_offset}")
    if end_offset > len(data_bytes):
        raise ValueError(f"end_offset out of range: end_offset={end_offset}, size={len(data_bytes)}")

    chunks: List[Tuple[bytes, bytes]] = []
    current_offset = int(start_offset)

    while current_offset < end_offset:
        tag_value, current_offset2, tag_raw, ok = decode_varint_with_raw(data_bytes, current_offset, end_offset)
        if not ok:
            raise ValueError("wire decode failed: invalid tag varint")
        if tag_value == 0:
            break

        wire_type = int(tag_value) & 0x07
        current_offset = int(current_offset2)

        if wire_type == 0:
            _value, next_offset, raw, ok2 = decode_varint_with_raw(data_bytes, current_offset, end_offset)
            if not ok2:
                raise ValueError("wire decode failed: invalid varint value")
            chunks.append((tag_raw, raw))
            current_offset = int(next_offset)
            continue

        if wire_type == 1:
            if current_offset + 8 > end_offset:
                raise ValueError("wire decode failed: fixed64 out of range")
            raw = bytes(data_bytes[current_offset : current_offset + 8])
            chunks.append((tag_raw, raw))
            current_offset += 8
            continue

        if wire_type == 5:
            if current_offset + 4 > end_offset:
                raise ValueError("wire decode failed: fixed32 out of range")
            raw = bytes(data_bytes[current_offset : current_offset + 4])
            chunks.append((tag_raw, raw))
            current_offset += 4
            continue

        if wire_type == 2:
            length_value, next_offset, length_raw, ok2 = decode_varint_with_raw(data_bytes, current_offset, end_offset)
            if not ok2:
                raise ValueError("wire decode failed: invalid length varint")
            length_int = int(length_value)
            if length_int < 0 or next_offset + length_int > end_offset:
                raise ValueError("wire decode failed: length out of range")
            payload = bytes(data_bytes[next_offset : next_offset + length_int])
            chunks.append((tag_raw, length_raw + payload))
            current_offset = int(next_offset + length_int)
            continue

        raise ValueError(f"unsupported wire_type: {wire_type}")

    return chunks, int(current_offset)


def encode_wire_chunks(chunks: List[Tuple[bytes, bytes]]) -> bytes:
    out: List[bytes] = []
    for tag_raw, value_raw in chunks:
        if not isinstance(tag_raw, (bytes, bytearray)):
            raise TypeError("tag_raw must be bytes")
        if not isinstance(value_raw, (bytes, bytearray)):
            raise TypeError("value_raw must be bytes")
        out.append(bytes(tag_raw))
        out.append(bytes(value_raw))
    return b"".join(out)


def _is_probably_printable_text(text: str) -> bool:
    if not text:
        return False
    printable_count = 0
    for character in text:
        if character.isprintable() or character in "\n\r\t":
            printable_count += 1
    return printable_count / max(len(text), 1) >= 0.92


def _sanitize_utf8_text_for_decode_gil(text: str) -> tuple[str, bool]:
    """
    对齐 decode_gil：保留可见字符 + \\t\\r\\n，剔除其他控制字符，再 strip()。

    返回：
    - cleaned_text: 清理后的文本
    - removed_nonprintable_controls: 是否剔除了“非 printable 且不在 \\t\\r\\n 内”的控制字符

    说明：
    - 当 length-delimited bytes 中夹带控制字符时（例如嵌套 message 的 tag/len bytes），
      若把其当作 utf8 文本再 strip，会导致回写时 payload bytes 漂移。
    - 因此上层可据此选择：仅在未剔除控制字符时才暴露 utf8 字段；否则仅保留 raw_hex，按 bytes 处理。
    """
    cleaned: List[str] = []
    removed_nonprintable_controls = False
    for ch in text:
        if ch.isprintable() or ch in "\t\r\n":
            cleaned.append(ch)
        else:
            removed_nonprintable_controls = True

    # 关键：decode_gil 会对 utf8 文本做 strip()；但对 `.gil` 的 protobuf-like 结构来说，
    # length-delimited bytes 可能“碰巧可解码为 utf8”，且其开头/结尾包含 tag/len 这类控制字节
    # （常见 0x0A + 0x09/0x0B/0x0C/0x0D ...），strip() 会把它们当作空白删掉，导致写回时
    # bytes 漂移并生成不可被官方侧识别的存档。
    #
    # 因此：若 strip() 会改变文本，则将其视为“更像 bytes/blob”，不暴露 utf8 字段（仅保留 raw_hex）。
    cleaned_text = "".join(cleaned)
    stripped_text = cleaned_text.strip()
    removed_by_strip = cleaned_text != stripped_text
    removed_controls = bool(removed_nonprintable_controls or removed_by_strip)
    return str(stripped_text), bool(removed_controls)


def _decode_length_delimited_to_decoded_node(field_bytes: bytes, remaining_depth: int) -> Any:
    """
    decode_gil 风格（lossless 优先）的 length-delimited 解码：
    - 优先尝试 UTF-8 可读文本（返回 {raw_hex, utf8}）
    - 否则尝试嵌套 message（返回 {message: {...}}）
    - 否则返回 {raw_hex}

    注意：该输出结构会被 node_graph_writeback 用作“可修改并可回写”的中间表示，因此：
    - packed 不会展开为 list（避免回写时语义漂移）；必要信息通过 raw_hex 保留。
    """
    if len(field_bytes) == 0:
        return {"raw_hex": ""}

    raw_hex = field_bytes.hex()

    # 文本判定：统一采用严格 UTF-8（errors=replace 且不允许出现 U+FFFD）+ printable 比例阈值
    decoded_text = field_bytes.decode("utf-8", errors="replace")
    if "\ufffd" not in decoded_text and _is_probably_printable_text(decoded_text):
        cleaned_text, removed_controls = _sanitize_utf8_text_for_decode_gil(decoded_text)
        value_object: Dict[str, Any] = {"raw_hex": raw_hex}
        # 关键：若清理过程中剔除了非 printable 控制字符，则视为“更像 bytes/blob”，不要写入 utf8 字段。
        # 否则在 dump-json → numeric_message → encode_message 的链路中会把 bytes 误写成字符串并造成 payload 漂移。
        if cleaned_text != "" and (not bool(removed_controls)):
            value_object["utf8"] = cleaned_text
        return value_object

    # packed varint stream 探测（保持 raw_hex，不误判为嵌套 message）：
    # - 典型场景：UI record 的 children GUID 列表（varint stream）在少数情况下会“碰巧可被当作 message 解码”，
    #   从而导致 writeback/export 时把原始 bytes 误写成 nested message（游戏侧可能拒绝解析）。
    # - 这里不展开为 list（仍然保持 raw_hex 以便 lossless roundtrip），仅用于阻止错误的 message 识别。
    packed_varints = _parse_packed_varints(field_bytes, max_items=256)
    if packed_varints is not None:
        # 经验：GUID 大多落在 0x40000000 段（约 1.07e9），用范围过滤避免误判普通嵌套 message。
        guid_like = 0
        for v in packed_varints:
            if 1073000000 <= int(v) <= 1075000000:
                guid_like += 1
        if guid_like / max(len(packed_varints), 1) >= 0.8:
            return {"raw_hex": raw_hex}

    # 非文本：尝试嵌套 message（深度允许时）
    if remaining_depth > 1:
        nested_message, nested_consumed_offset = decode_message_to_field_map(
            data_bytes=field_bytes,
            start_offset=0,
            end_offset=len(field_bytes),
            remaining_depth=remaining_depth - 1,
        )
        if len(nested_message) > 0 and nested_consumed_offset == len(field_bytes):
            return {"message": nested_message}

    return {"raw_hex": raw_hex}


def decode_message_to_field_map(
    *,
    data_bytes: bytes,
    start_offset: int,
    end_offset: int,
    remaining_depth: int,
) -> Tuple[Dict[str, Any], int]:
    """
    decode_gil 风格（兼容既有输出结构）的 message 解码。

    返回: (fields_map, next_offset)
    - fields_map: {"field_<n>": value_or_list}
    - value 节点形态（兼容 node_graph_writeback 的回写中间表示）：
      - varint: {"int": int, "int32_high16": int, "int32_low16": int} 或 {"int": int}
      - fixed32: {"fixed32_int": int, "fixed32_float": float}
      - fixed64: {"fixed64_int": int, "fixed64_double": float}
      - length-delimited: {"raw_hex": str, "utf8"?: str} 或 {"message": {...}}

    重要：本实现会将 tag=0 / field_number<=0 视为非法并停止解析，避免产出 field_0 导致回写 encoder 抛错。
    """
    if remaining_depth <= 0:
        return {}, start_offset

    if start_offset < 0:
        raise ValueError(f"start_offset must be >= 0, got {start_offset}")
    if end_offset < 0:
        raise ValueError(f"end_offset must be >= 0, got {end_offset}")
    if end_offset > len(data_bytes):
        raise ValueError(f"end_offset out of range: end_offset={end_offset}, size={len(data_bytes)}")

    fields_map: Dict[str, Any] = {}
    current_offset = start_offset

    def _append(field_number: int, value_object: Any) -> None:
        field_key = "field_" + str(field_number)
        existing_value = fields_map.get(field_key)
        if existing_value is None:
            fields_map[field_key] = value_object
            return
        if isinstance(existing_value, list):
            existing_value.append(value_object)
            return
        fields_map[field_key] = [existing_value, value_object]

    while current_offset < end_offset:
        tag_value, current_offset, ok = decode_varint(data_bytes, current_offset, end_offset)
        if not ok:
            break
        if tag_value == 0:
            break

        field_number = tag_value >> 3
        wire_type = tag_value & 0x07
        if field_number <= 0:
            break

        if wire_type == 0:
            value, current_offset, ok = decode_varint(data_bytes, current_offset, end_offset)
            if not ok:
                break
            if 0 <= value <= 0xFFFFFFFF:
                lower32 = value & 0xFFFFFFFF
                high16 = lower32 >> 16
                low16 = lower32 & 0xFFFF
                value_object = {
                    "int": int(value),
                    "int32_high16": int(high16),
                    "int32_low16": int(low16),
                }
            else:
                value_object = {
                    "int": int(value),
                }
            _append(int(field_number), value_object)
            continue

        if wire_type == 1:
            if current_offset + 8 > end_offset:
                break
            raw_bytes = data_bytes[current_offset : current_offset + 8]
            current_offset += 8
            integer_value = int.from_bytes(raw_bytes, byteorder="little", signed=False)
            float_value = struct.unpack("<d", raw_bytes)[0]
            _append(
                int(field_number),
                {
                    "fixed64_int": int(integer_value),
                    "fixed64_double": float(float_value),
                },
            )
            continue

        if wire_type == 5:
            if current_offset + 4 > end_offset:
                break
            raw_bytes = data_bytes[current_offset : current_offset + 4]
            current_offset += 4
            integer_value = int.from_bytes(raw_bytes, byteorder="little", signed=False)
            float_value = struct.unpack("<f", raw_bytes)[0]
            _append(
                int(field_number),
                {
                    "fixed32_int": int(integer_value),
                    "fixed32_float": float(float_value),
                },
            )
            continue

        if wire_type == 2:
            length_value, current_offset, ok = decode_varint(data_bytes, current_offset, end_offset)
            if not ok:
                break
            length_int = int(length_value)
            if length_int < 0:
                break
            if current_offset + length_int > end_offset:
                break
            field_bytes = data_bytes[current_offset : current_offset + length_int]
            current_offset += length_int
            value_object = _decode_length_delimited_to_decoded_node(field_bytes, remaining_depth)
            _append(int(field_number), value_object)
            continue

        # 其他 wire_type（3/4 group 等）暂不支持
        break

    return fields_map, current_offset


def _bytes_to_sha1_hex(byte_data: bytes) -> str:
    sha1_hasher = hashlib.sha1()
    sha1_hasher.update(byte_data)
    return sha1_hasher.hexdigest()


def _bytes_preview_hex(byte_data: bytes, preview_length: int) -> str:
    if preview_length <= 0:
        return ""
    return byte_data[:preview_length].hex()


def _parse_packed_varints(byte_data: bytes, max_items: int) -> Optional[List[int]]:
    values: List[int] = []
    current_offset = 0
    end_offset = len(byte_data)
    while current_offset < end_offset:
        if len(values) >= max_items:
            return None
        value, current_offset, ok = decode_varint(byte_data, current_offset, end_offset)
        if not ok:
            return None
        values.append(int(value))
    if len(values) <= 1:
        return None
    return values


def _parse_packed_fixed32(byte_data: bytes, max_items: int) -> Optional[Dict[str, JsonValue]]:
    if len(byte_data) % 4 != 0:
        return None
    item_count = len(byte_data) // 4
    if item_count <= 1 or item_count > max_items:
        return None
    values_u32: List[int] = []
    values_f32: List[float] = []
    for index in range(item_count):
        start_offset = index * 4
        chunk = byte_data[start_offset : start_offset + 4]
        values_u32.append(struct.unpack("<I", chunk)[0])
        values_f32.append(struct.unpack("<f", chunk)[0])
    return {"u32": values_u32, "f32": values_f32}


def _parse_packed_fixed64(byte_data: bytes, max_items: int) -> Optional[Dict[str, JsonValue]]:
    if len(byte_data) % 8 != 0:
        return None
    item_count = len(byte_data) // 8
    if item_count <= 1 or item_count > max_items:
        return None
    values_u64: List[int] = []
    values_f64: List[float] = []
    for index in range(item_count):
        start_offset = index * 8
        chunk = byte_data[start_offset : start_offset + 8]
        values_u64.append(struct.unpack("<Q", chunk)[0])
        values_f64.append(struct.unpack("<d", chunk)[0])
    return {"u64": values_u64, "f64": values_f64}


class ProtobufLikeParseOptions:
    def __init__(
        self,
        max_depth: int,
        bytes_preview_length: int,
        max_length_delimited_string_bytes: int,
        max_packed_items: int,
        max_message_bytes_for_probe: int,
    ) -> None:
        self.max_depth = max_depth
        self.bytes_preview_length = bytes_preview_length
        self.max_length_delimited_string_bytes = max_length_delimited_string_bytes
        self.max_packed_items = max_packed_items
        self.max_message_bytes_for_probe = max_message_bytes_for_probe


def parse_message(
    *,
    byte_data: bytes,
    start_offset: int,
    end_offset: int,
    depth: int,
    options: ProtobufLikeParseOptions,
) -> Tuple[Dict[str, JsonValue], int, bool, Optional[Dict[str, JsonValue]]]:
    """
    解析一段 protobuf-like message（readable JSON 风格）。

    返回: (message_json, next_offset, ok, error)
    - ok=False 时 message_json 依然包含已解析的部分与 _meta.error。
    """
    if start_offset < 0:
        raise ValueError(f"start_offset must be >= 0, got {start_offset}")
    if end_offset < 0:
        raise ValueError(f"end_offset must be >= 0, got {end_offset}")
    if end_offset > len(byte_data):
        raise ValueError(f"end_offset out of range: end_offset={end_offset}, size={len(byte_data)}")

    current_offset = start_offset
    message_fields: Dict[str, List[JsonValue]] = {}
    total_entries = 0

    def append_field_value(field_number: int, value: JsonValue) -> None:
        nonlocal total_entries
        field_key = str(field_number)
        if field_key not in message_fields:
            message_fields[field_key] = []
        message_fields[field_key].append(value)
        total_entries += 1

    while current_offset < end_offset:
        tag_value, current_offset, ok = decode_varint(byte_data, current_offset, end_offset)
        if not ok:
            error = {"offset": current_offset, "reason": "invalid_varint_tag"}
            message_json: Dict[str, JsonValue] = {"_meta": {"byte_length": end_offset - start_offset, "entry_count": total_entries, "error": error}}
            message_json.update(message_fields)
            return message_json, current_offset, False, error

        if tag_value == 0:
            error = {"offset": current_offset, "reason": "tag_is_zero"}
            message_json = {"_meta": {"byte_length": end_offset - start_offset, "entry_count": total_entries, "error": error}}
            message_json.update(message_fields)
            return message_json, current_offset, False, error

        field_number = tag_value >> 3
        wire_type = tag_value & 0x07

        if field_number <= 0:
            error = {"offset": current_offset, "reason": "field_number_invalid", "tag": int(tag_value)}
            message_json = {"_meta": {"byte_length": end_offset - start_offset, "entry_count": total_entries, "error": error}}
            message_json.update(message_fields)
            return message_json, current_offset, False, error

        if wire_type == 0:
            varint_value, current_offset, ok = decode_varint(byte_data, current_offset, end_offset)
            if not ok:
                error = {"offset": current_offset, "reason": "invalid_varint_value", "field": int(field_number)}
                message_json = {"_meta": {"byte_length": end_offset - start_offset, "entry_count": total_entries, "error": error}}
                message_json.update(message_fields)
                return message_json, current_offset, False, error
            append_field_value(
                int(field_number),
                {
                    "wire_type": 0,
                    "varint": int(varint_value),
                    "as_bool": (int(varint_value) == 1) if int(varint_value) in (0, 1) else None,
                },
            )
            continue

        if wire_type == 1:
            if current_offset + 8 > end_offset:
                error = {"offset": current_offset, "reason": "fixed64_out_of_range", "field": int(field_number)}
                message_json = {"_meta": {"byte_length": end_offset - start_offset, "entry_count": total_entries, "error": error}}
                message_json.update(message_fields)
                return message_json, current_offset, False, error
            raw_bytes = byte_data[current_offset : current_offset + 8]
            current_offset += 8
            raw_u64 = struct.unpack("<Q", raw_bytes)[0]
            raw_f64 = struct.unpack("<d", raw_bytes)[0]
            append_field_value(
                int(field_number),
                {
                    "wire_type": 1,
                    "u64": int(raw_u64),
                    "f64": float(raw_f64),
                },
            )
            continue

        if wire_type == 5:
            if current_offset + 4 > end_offset:
                error = {"offset": current_offset, "reason": "fixed32_out_of_range", "field": int(field_number)}
                message_json = {"_meta": {"byte_length": end_offset - start_offset, "entry_count": total_entries, "error": error}}
                message_json.update(message_fields)
                return message_json, current_offset, False, error
            raw_bytes = byte_data[current_offset : current_offset + 4]
            current_offset += 4
            raw_u32 = struct.unpack("<I", raw_bytes)[0]
            raw_f32 = struct.unpack("<f", raw_bytes)[0]
            append_field_value(
                int(field_number),
                {
                    "wire_type": 5,
                    "u32": int(raw_u32),
                    "f32": float(raw_f32),
                },
            )
            continue

        if wire_type == 2:
            length_value, current_offset, ok = decode_varint(byte_data, current_offset, end_offset)
            if not ok:
                error = {"offset": current_offset, "reason": "invalid_length_delimited_length", "field": int(field_number)}
                message_json = {"_meta": {"byte_length": end_offset - start_offset, "entry_count": total_entries, "error": error}}
                message_json.update(message_fields)
                return message_json, current_offset, False, error

            length_int = int(length_value)
            if length_int < 0:
                error = {"offset": current_offset, "reason": "negative_length_delimited_length", "field": int(field_number), "length": int(length_int)}
                message_json = {"_meta": {"byte_length": end_offset - start_offset, "entry_count": total_entries, "error": error}}
                message_json.update(message_fields)
                return message_json, current_offset, False, error
            if current_offset + length_int > end_offset:
                error = {"offset": current_offset, "reason": "length_delimited_out_of_range", "field": int(field_number), "length": int(length_int)}
                message_json = {"_meta": {"byte_length": end_offset - start_offset, "entry_count": total_entries, "error": error}}
                message_json.update(message_fields)
                return message_json, current_offset, False, error

            value_bytes = byte_data[current_offset : current_offset + length_int]
            current_offset += length_int

            interpretation = interpret_length_delimited(value_bytes, depth=depth, options=options)
            append_field_value(
                int(field_number),
                {
                    "wire_type": 2,
                    "length": int(length_int),
                    "value": interpretation,
                },
            )
            continue

        error = {"offset": current_offset, "reason": "unsupported_wire_type", "field": int(field_number), "wire_type": int(wire_type)}
        message_json = {"_meta": {"byte_length": end_offset - start_offset, "entry_count": total_entries, "error": error}}
        message_json.update(message_fields)
        return message_json, current_offset, False, error

    message_json = {"_meta": {"byte_length": end_offset - start_offset, "entry_count": total_entries}}
    message_json.update(message_fields)
    return message_json, current_offset, True, None


def probe_message(byte_data: bytes, depth: int, options: ProtobufLikeParseOptions) -> Optional[Dict[str, JsonValue]]:
    if len(byte_data) == 0:
        return None
    if len(byte_data) > options.max_message_bytes_for_probe:
        return None
    if depth >= options.max_depth:
        return None

    message_json, next_offset, ok, _error = parse_message(
        byte_data=byte_data,
        start_offset=0,
        end_offset=len(byte_data),
        depth=depth + 1,
        options=options,
    )
    if not ok:
        return None
    if next_offset != len(byte_data):
        return None

    entry_count = int(message_json.get("_meta", {}).get("entry_count", 0))
    if entry_count <= 0:
        return None

    return message_json


def interpret_length_delimited(byte_data: bytes, depth: int, options: ProtobufLikeParseOptions) -> Dict[str, JsonValue]:
    """
    length-delimited 的统一判定口径：
    - string（严格 UTF-8 且可打印）
    - nested message（probe 成功且对齐）
    - packed（varint/fixed32/fixed64）
    - bytes（sha1 + hex 预览，可选 base64）

    说明：先 probe message 再判 packed，用于降低“嵌套 message 被误判为 packed”的概率。
    """
    byte_length = len(byte_data)
    sha1_hex = _bytes_to_sha1_hex(byte_data)
    preview_hex = _bytes_preview_hex(byte_data, options.bytes_preview_length)

    if byte_length == 0:
        return {"kind": "bytes", "length": 0, "sha1": sha1_hex, "preview_hex": ""}

    if byte_length <= options.max_length_delimited_string_bytes:
        decoded_text = byte_data.decode("utf-8", errors="replace")
        if "\ufffd" not in decoded_text and _is_probably_printable_text(decoded_text):
            return {"kind": "string", "text": decoded_text}

    nested_message = probe_message(byte_data, depth=depth, options=options)
    if nested_message is not None:
        return {
            "kind": "message",
            "bytes": {"length": int(byte_length), "sha1": sha1_hex, "preview_hex": preview_hex},
            "message": nested_message,
        }

    packed_varints = _parse_packed_varints(byte_data, max_items=options.max_packed_items)
    if packed_varints is not None:
        return {"kind": "packed_varint", "values": packed_varints}

    packed_fixed32 = _parse_packed_fixed32(byte_data, max_items=options.max_packed_items)
    if packed_fixed32 is not None:
        return {"kind": "packed_fixed32", "values": packed_fixed32}

    packed_fixed64 = _parse_packed_fixed64(byte_data, max_items=options.max_packed_items)
    if packed_fixed64 is not None:
        return {"kind": "packed_fixed64", "values": packed_fixed64}

    base64_value: Optional[str] = None
    if byte_length <= 256:
        base64_value = base64.b64encode(byte_data).decode("ascii")

    return {
        "kind": "bytes",
        "length": int(byte_length),
        "sha1": sha1_hex,
        "preview_hex": preview_hex,
        "base64": base64_value,
    }


def parse_binary_data_hex_text(text: str) -> bytes:
    if not isinstance(text, str) or not text.startswith("<binary_data>"):
        raise ValueError("expected '<binary_data>' hex string")
    hex_text = text.replace("<binary_data>", "").strip()
    compact = hex_text.replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", "")
    if compact == "":
        return b""
    if len(compact) % 2 != 0:
        raise ValueError("binary_data hex length must be even")
    hexdigits = "0123456789abcdefABCDEF"
    if any(ch not in hexdigits for ch in compact):
        raise ValueError("binary_data hex contains non-hex digits")
    return bytes.fromhex(compact)


def format_binary_data_hex_text(data: bytes) -> str:
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError(f"data must be bytes, got {type(data).__name__}")
    data_bytes = bytes(data)
    if not data_bytes:
        return "<binary_data> "
    return "<binary_data> " + " ".join(f"{b:02X}" for b in data_bytes)


