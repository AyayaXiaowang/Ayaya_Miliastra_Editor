from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GiaContainerHeader:
    """
    `.gia` 容器头（20 bytes）：
    - 0x00: left_size     = file_size - 4
    - 0x04: schema_version = 1
    - 0x08: head_tag       = 0x0326
    - 0x0C: file_type      = 3 (GIA)
    - 0x10: proto_size     = file_size - 24

    文件末尾 4 bytes 为 tail_tag = 0x0679。
    """

    left_size: int
    schema_version: int
    head_tag: int
    file_type: int
    proto_size: int
    tail_tag: int


def _read_u32_be(data: bytes, offset: int) -> int:
    chunk = data[offset : offset + 4]
    if len(chunk) != 4:
        raise ValueError(f"expected 4 bytes at offset {offset}, got {len(chunk)}")
    return int.from_bytes(chunk, byteorder="big", signed=False)


def read_gia_container_header(gia_file_path: Path) -> GiaContainerHeader:
    gia_file_path = Path(gia_file_path).resolve()
    raw = gia_file_path.read_bytes()
    if len(raw) < 24:
        raise ValueError(f"invalid gia file: too small ({len(raw)} bytes): {str(gia_file_path)!r}")

    head = raw[:20]
    tail_tag = _read_u32_be(raw[-4:], 0)
    return GiaContainerHeader(
        left_size=_read_u32_be(head, 0),
        schema_version=_read_u32_be(head, 4),
        head_tag=_read_u32_be(head, 8),
        file_type=_read_u32_be(head, 12),
        proto_size=_read_u32_be(head, 16),
        tail_tag=tail_tag,
    )


def validate_gia_container_file(gia_file_path: Path) -> GiaContainerHeader:
    gia_file_path = Path(gia_file_path).resolve()
    raw = gia_file_path.read_bytes()
    header = read_gia_container_header(gia_file_path)

    file_size = len(raw)
    expected_left_size = file_size - 4
    expected_proto_size = file_size - 24

    if header.left_size != expected_left_size:
        raise ValueError(f"invalid gia header.left_size: {header.left_size} != {expected_left_size}")
    if header.schema_version != 1:
        raise ValueError(f"invalid gia header.schema_version: {header.schema_version} != 1")
    if header.head_tag != 0x0326:
        raise ValueError(f"invalid gia header.head_tag: 0x{header.head_tag:04x} != 0x0326")
    if header.file_type != 3:
        raise ValueError(f"invalid gia header.file_type: {header.file_type} != 3")
    if header.proto_size != expected_proto_size:
        raise ValueError(f"invalid gia header.proto_size: {header.proto_size} != {expected_proto_size}")
    if header.tail_tag != 0x0679:
        raise ValueError(f"invalid gia tail_tag: 0x{header.tail_tag:04x} != 0x0679")

    return header


def unwrap_gia_container(gia_file_path: Path, *, check_header: bool = True) -> bytes:
    gia_file_path = Path(gia_file_path).resolve()
    raw = gia_file_path.read_bytes()
    if check_header:
        validate_gia_container_file(gia_file_path)
    return raw[20:-4]


def wrap_gia_container(proto_bytes: bytes) -> bytes:
    message = bytes(proto_bytes or b"")
    file_size = 20 + len(message) + 4
    header = (
        int(file_size - 4).to_bytes(4, byteorder="big", signed=False)
        + int(1).to_bytes(4, byteorder="big", signed=False)
        + int(0x0326).to_bytes(4, byteorder="big", signed=False)
        + int(3).to_bytes(4, byteorder="big", signed=False)
        + int(len(message)).to_bytes(4, byteorder="big", signed=False)
    )
    tail = int(0x0679).to_bytes(4, byteorder="big", signed=False)
    return header + message + tail


