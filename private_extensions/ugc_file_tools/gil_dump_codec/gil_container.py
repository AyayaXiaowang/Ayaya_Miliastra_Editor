from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ugc_file_tools.gil_package_exporter.gil_reader import read_gil_header


@dataclass(frozen=True, slots=True)
class GilContainerSpec:
    header_value_one: int
    header_value_two: int
    type_id_value: int
    footer_value: int


def read_gil_container_spec(input_gil_file_path: Path) -> GilContainerSpec:
    gil_bytes = Path(input_gil_file_path).read_bytes()
    header = read_gil_header(gil_bytes)
    return GilContainerSpec(
        header_value_one=int(header.header_value_one),
        header_value_two=int(header.header_value_two),
        type_id_value=int(header.type_id_value),
        footer_value=int(header.footer_value),
    )


def read_gil_payload_bytes(input_gil_file_path: Path) -> bytes:
    """
    读取 `.gil` 文件的 payload bytes（不包含头尾封装）。

    `.gil` 文件结构（基于现有 `_read_gil_header` 口径）：
    - [0..19] 5 个 u32(big-endian)：(total_size_field, header1, header2, type_id, body_size)
    - [20..20+body_size) payload（protobuf-like bytes）
    - [20+body_size..20+body_size+4) footer u32(big-endian)
    """
    gil_bytes = Path(input_gil_file_path).read_bytes()
    header = read_gil_header(gil_bytes)
    start = 0x14
    end = int(start + int(header.body_size))
    if end > len(gil_bytes):
        raise ValueError("gil payload range out of file size")
    return bytes(gil_bytes[start:end])


def read_gil_payload_bytes_and_container_meta(*, gil_file_path: Path) -> tuple[bytes, dict[str, Any]]:
    """
    读取 `.gil` 文件 payload bytes，并返回容器头尾元信息（header fields）。

    说明：
    - 该函数仅负责“容器层”（header/payload/footer）的切片与元信息提取；
    - payload 内容的 protobuf-like 解码由上层决定（例如 `protobuf_like.parse_message` 或 NodeGraph blob 扫描）。
    """
    path = Path(gil_file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"input gil file not found: {str(path)!r}")

    file_bytes = path.read_bytes()
    header = read_gil_header(file_bytes)
    body_size = int(header.body_size)
    if body_size <= 0:
        raise ValueError(f"invalid gil body_size={body_size}: {str(path)!r}")

    payload = file_bytes[20 : 20 + body_size]
    if len(payload) != body_size:
        raise ValueError(f"payload size mismatch: expected={body_size} got={len(payload)} path={str(path)!r}")

    meta = {
        "total_size_field": int(header.total_size_field),
        "header_value_one": int(header.header_value_one),
        "header_value_two": int(header.header_value_two),
        "type_id_value": int(header.type_id_value),
        "body_size": int(header.body_size),
        "footer_value": int(header.footer_value),
    }
    return bytes(payload), meta


def build_gil_file_bytes_from_payload(*, payload_bytes: bytes, container_spec: GilContainerSpec) -> bytes:
    """
    将 payload bytes 封装为 `.gil` 文件：
    [0-19] 5 个 u32(big-endian)：(file_size-4, header1, header2, type_id, payload_size)
    [20..] payload
    [end-4..end-1] footer u32(big-endian)
    """
    if not isinstance(payload_bytes, (bytes, bytearray)):
        raise TypeError(f"payload_bytes must be bytes, got {type(payload_bytes).__name__}")
    payload = bytes(payload_bytes)

    payload_size = int(len(payload))
    file_size = payload_size + 24

    total_size_field = file_size - 4
    body_size_field = file_size - 24

    header_bytes = (
        int(total_size_field).to_bytes(4, "big", signed=False)
        + int(container_spec.header_value_one).to_bytes(4, "big", signed=False)
        + int(container_spec.header_value_two).to_bytes(4, "big", signed=False)
        + int(container_spec.type_id_value).to_bytes(4, "big", signed=False)
        + int(body_size_field).to_bytes(4, "big", signed=False)
    )

    footer_bytes = int(container_spec.footer_value).to_bytes(4, "big", signed=False)
    return header_bytes + payload + footer_bytes


