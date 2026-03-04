from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Sequence, Tuple

from .protobuf_like import decode_message_to_wire_chunks, decode_varint, encode_tag, encode_varint, encode_wire_chunks


WireChunk = Tuple[bytes, bytes]


@dataclass(frozen=True, slots=True)
class ParsedTag:
    field_number: int
    wire_type: int


def parse_tag_raw(tag_raw: bytes) -> ParsedTag:
    """
    从 wire-level 的 tag_raw(varint bytes) 解析 field_number 与 wire_type。
    """
    if not isinstance(tag_raw, (bytes, bytearray)):
        raise TypeError("tag_raw must be bytes")
    raw = bytes(tag_raw)
    tag_value, next_offset, ok = decode_varint(raw, 0, len(raw))
    if not ok or next_offset != len(raw):
        raise ValueError("invalid tag_raw varint")
    if int(tag_value) == 0:
        raise ValueError("tag_raw decoded to 0")
    field_number = int(tag_value) >> 3
    wire_type = int(tag_value) & 0x07
    if field_number <= 0:
        raise ValueError(f"invalid field_number decoded from tag_raw: {field_number}")
    return ParsedTag(field_number=int(field_number), wire_type=int(wire_type))


def split_length_delimited_value_raw(value_raw: bytes) -> Tuple[bytes, bytes]:
    """
    wire_type=2 的 value_raw 形态为：length_raw(varint bytes) + payload_bytes。
    返回：(length_raw, payload_bytes)。
    """
    if not isinstance(value_raw, (bytes, bytearray)):
        raise TypeError("value_raw must be bytes")
    raw = bytes(value_raw)
    length_value, next_offset, ok = decode_varint(raw, 0, len(raw))
    if not ok:
        raise ValueError("invalid length varint in length-delimited value_raw")
    length_int = int(length_value)
    if length_int < 0:
        raise ValueError("length-delimited length must be >= 0")
    payload = raw[next_offset:]
    if len(payload) != length_int:
        raise ValueError(
            "length-delimited length mismatch: "
            f"declared={length_int}, actual={len(payload)}"
        )
    return raw[:next_offset], payload


def build_length_delimited_value_raw(payload_bytes: bytes) -> bytes:
    if not isinstance(payload_bytes, (bytes, bytearray)):
        raise TypeError("payload_bytes must be bytes")
    payload = bytes(payload_bytes)
    return encode_varint(len(payload)) + payload


def replace_varint_value_raw(value_raw: bytes, new_value: int) -> bytes:
    """
    wire_type=0 的 value_raw 为 varint bytes；返回新的 varint bytes。
    """
    if not isinstance(new_value, int):
        raise TypeError("new_value must be int")
    return encode_varint(int(new_value))


def upsert_varint_field(
    chunks: Sequence[WireChunk],
    *,
    field_number: int,
    new_value: int,
) -> List[WireChunk]:
    """
    在 message 的 wire chunks 中“更新或追加”一个 varint 字段：
    - 若存在第一个匹配 (field_number, wire_type=0)，替换其 value_raw
    - 否则在末尾追加一个新字段（tag/value 使用最短编码）
    """
    out: List[WireChunk] = []
    replaced = False
    for tag_raw, value_raw in list(chunks):
        parsed = parse_tag_raw(tag_raw)
        if (not replaced) and parsed.field_number == int(field_number) and parsed.wire_type == 0:
            out.append((bytes(tag_raw), replace_varint_value_raw(value_raw, int(new_value))))
            replaced = True
            continue
        out.append((bytes(tag_raw), bytes(value_raw)))
    if not replaced:
        out.append((encode_tag(int(field_number), 0), encode_varint(int(new_value))))
    return out


def replace_length_delimited_fields_payload_bytes_in_message_bytes(
    *,
    message_bytes: bytes,
    payload_bytes_by_field_number: Mapping[int, bytes],
) -> bytes:
    """
    wire-level patch：在一个 message 的 raw bytes 中，按 field_number 替换/插入若干 length-delimited 字段的 payload bytes。

    关键保证：
    - 只修改被指定的字段（field_number 的 wire_type=2 value_raw），其它 tag/value 原始字节**完全不变**；
    - 这比“解码成 dict → encode_message 全量重编码”更保真，可用于避免官方侧依赖的 wire-level 不变量被破坏。

    参数：
    - message_bytes：protobuf-like message 的原始 bytes
    - payload_bytes_by_field_number：{field_number: new_payload_bytes}

    约束（保守）：
    - 若发现目标 field_number 在 message 中出现多次（repeated），直接抛错（避免误伤）。
    - 若目标 field_number 不存在，则按 field_number 升序在合适的位置插入（尽量保持“近似有序”）。
    """
    if not isinstance(message_bytes, (bytes, bytearray)):
        raise TypeError(f"message_bytes must be bytes, got {type(message_bytes).__name__}")
    raw = bytes(message_bytes)

    chunks, consumed = decode_message_to_wire_chunks(
        data_bytes=raw,
        start_offset=0,
        end_offset=len(raw),
    )
    if int(consumed) != len(raw):
        raise ValueError(
            "message_bytes did not decode to a single complete message: "
            f"consumed={int(consumed)}, total={len(raw)}"
        )

    replacements: Dict[int, bytes] = {}
    for k, v in dict(payload_bytes_by_field_number or {}).items():
        if not isinstance(k, int):
            raise TypeError(f"payload_bytes_by_field_number key must be int, got {type(k).__name__}")
        if int(k) <= 0:
            raise ValueError(f"invalid field_number: {int(k)} (must be > 0)")
        if not isinstance(v, (bytes, bytearray)):
            raise TypeError(
                f"payload_bytes_by_field_number[{int(k)}] must be bytes, got {type(v).__name__}"
            )
        replacements[int(k)] = bytes(v)

    if not replacements:
        return raw

    parsed_tags = [parse_tag_raw(tag_raw) for tag_raw, _ in list(chunks)]

    for field_number in sorted(replacements.keys()):
        new_payload = replacements[int(field_number)]
        new_value_raw = build_length_delimited_value_raw(new_payload)

        indices: List[int] = []
        for i, tag in enumerate(list(parsed_tags)):
            if int(tag.field_number) != int(field_number):
                continue
            if int(tag.wire_type) != 2:
                raise ValueError(
                    f"cannot patch field={int(field_number)}: expected wire_type=2(length-delimited), got {int(tag.wire_type)}"
                )
            indices.append(int(i))

        if len(indices) > 1:
            raise ValueError(
                f"cannot patch field={int(field_number)}: found multiple occurrences: indices={indices}"
            )

        if len(indices) == 1:
            idx = int(indices[0])
            tag_raw, _old_value_raw = chunks[idx]
            chunks[idx] = (bytes(tag_raw), bytes(new_value_raw))
            continue

        # missing → insert before first field_number greater than target (keep near-sorted)
        insert_at = len(chunks)
        for i, tag in enumerate(list(parsed_tags)):
            if int(tag.field_number) > int(field_number):
                insert_at = int(i)
                break

        tag_raw = encode_tag(int(field_number), 2)
        chunks.insert(int(insert_at), (bytes(tag_raw), bytes(new_value_raw)))
        parsed_tags.insert(int(insert_at), parse_tag_raw(bytes(tag_raw)))

    return encode_wire_chunks(list(chunks))

