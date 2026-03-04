from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from ugc_file_tools.gia.container import unwrap_gia_container, validate_gia_container_file, wrap_gia_container
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_tag, encode_varint
from ugc_file_tools.wire.codec import decode_message_to_wire_chunks, encode_wire_chunks
from ugc_file_tools.wire.patch import parse_tag_raw


@dataclass(frozen=True, slots=True)
class WireChunk:
    field_number: int
    wire_type: int
    tag_raw: bytes
    value_raw: bytes


def _parse_chunks(chunks: List[Tuple[bytes, bytes]]) -> List[WireChunk]:
    parsed: List[WireChunk] = []
    for tag_raw, value_raw in chunks:
        tag = parse_tag_raw(tag_raw)
        parsed.append(
            WireChunk(
                field_number=int(tag.field_number),
                wire_type=int(tag.wire_type),
                tag_raw=bytes(tag_raw),
                value_raw=bytes(value_raw),
            )
        )
    return parsed


def _replace_root_file_path(proto_bytes: bytes, *, new_file_path: str) -> bytes:
    """
    仅在 wire-level 替换 Root.filePath（field_number=3, wire_type=2）。
    - 其它所有字段保持原始 tag_raw/value_raw 不变（保真）。
    - 若原文件没有 field_3，则追加一个 field_3（放在末尾）。
    """
    chunks_raw, consumed = decode_message_to_wire_chunks(
        data_bytes=proto_bytes,
        start_offset=0,
        end_offset=len(proto_bytes),
    )
    if consumed != len(proto_bytes):
        raise ValueError(f"wire decode not fully consumed: consumed={consumed} total={len(proto_bytes)}")

    parsed = _parse_chunks(chunks_raw)
    new_bytes = str(new_file_path).encode("utf-8")
    new_value_raw = encode_varint(len(new_bytes)) + new_bytes

    replaced = False
    out_chunks: List[Tuple[bytes, bytes]] = []
    for c in parsed:
        if c.field_number == 3 and c.wire_type == 2 and not replaced:
            out_chunks.append((c.tag_raw, new_value_raw))
            replaced = True
        else:
            out_chunks.append((c.tag_raw, c.value_raw))

    if not replaced:
        out_chunks.append((encode_tag(3, 2), new_value_raw))

    return encode_wire_chunks(out_chunks)


def patch_gia_file_path_wire(
    *,
    base_gia_path: Path,
    output_gia_path: Path,
    new_file_path: str,
    check_header: bool,
) -> dict:
    """
    对 `.gia` 做“保真 wire-level”补丁：只改 Root.filePath（field_3）。
    这是用于验证“我们生成的文件看不到是否因为重编码破坏了 raw blob”的最小对照。
    """
    base_gia_path = Path(base_gia_path).resolve()
    if check_header:
        validate_gia_container_file(base_gia_path)

    proto_bytes = unwrap_gia_container(base_gia_path, check_header=False)
    patched_proto = _replace_root_file_path(proto_bytes, new_file_path=str(new_file_path))
    out_bytes = wrap_gia_container(patched_proto)

    output_gia_path = Path(output_gia_path)
    output_gia_path = Path(output_gia_path).resolve()
    output_gia_path.parent.mkdir(parents=True, exist_ok=True)
    output_gia_path.write_bytes(out_bytes)

    return {
        "base_gia_file": str(base_gia_path),
        "output_gia_file": str(output_gia_path),
        "new_file_path": str(new_file_path),
        "proto_size": len(patched_proto),
    }


