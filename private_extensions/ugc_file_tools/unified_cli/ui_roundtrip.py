from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from ugc_file_tools.gil_dump_codec.gil_container import (
    build_gil_file_bytes_from_payload,
    read_gil_container_spec,
    read_gil_payload_bytes,
)
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map, encode_message
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_wire_chunks, encode_wire_chunks
from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import decoded_field_map_to_numeric_message
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


def _sha1_hex(data: bytes) -> str:
    h = hashlib.sha1()
    h.update(data)
    return h.hexdigest()


def _first_mismatch(a: bytes, b: bytes) -> int | None:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    if len(a) != len(b):
        return n
    return None


def _hex_window(data: bytes, *, center: int, radius: int = 24) -> str:
    start = max(int(center) - int(radius), 0)
    end = min(int(center) + int(radius), len(data))
    return data[start:end].hex()


def _command_ui_roundtrip_gil(arguments: argparse.Namespace) -> None:
    input_gil_path = Path(arguments.input_gil_file).resolve()
    if not input_gil_path.is_file():
        raise FileNotFoundError(str(input_gil_path))

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)

    container_spec = read_gil_container_spec(input_gil_path)
    payload_bytes = read_gil_payload_bytes(input_gil_path)

    decoded_field_map, consumed_offset = decode_message_to_field_map(
        data_bytes=payload_bytes,
        start_offset=0,
        end_offset=len(payload_bytes),
        remaining_depth=32,
    )
    if consumed_offset != len(payload_bytes):
        raise ValueError(
            "gil payload 未能完整解码为单个 message（存在 trailing bytes）："
            f"consumed={consumed_offset}, total={len(payload_bytes)}"
        )

    payload_message = decoded_field_map_to_numeric_message(decoded_field_map, prefer_raw_hex_for_utf8=True)
    if not isinstance(payload_message, dict):
        raise TypeError("decoded payload root must be dict")

    rebuilt_payload_bytes = encode_message(payload_message)
    output_gil_bytes = build_gil_file_bytes_from_payload(payload_bytes=rebuilt_payload_bytes, container_spec=container_spec)
    output_gil_path.write_bytes(output_gil_bytes)

    mismatch = _first_mismatch(payload_bytes, rebuilt_payload_bytes)

    print("=" * 80)
    print("UI roundtrip 完成（不改任何字段：payload decode->encode->wrap）：")
    print(f"- input:  {str(input_gil_path)}")
    print(f"- output: {str(output_gil_path)}")
    print(f"- payload_bytes:  in={len(payload_bytes)}, out={len(rebuilt_payload_bytes)}")
    print(f"- payload_sha1:   in={_sha1_hex(payload_bytes)}, out={_sha1_hex(rebuilt_payload_bytes)}")
    print(f"- payload_mismatch_offset: {mismatch}")
    if mismatch is not None:
        print(f"- in_window_hex:  {_hex_window(payload_bytes, center=mismatch)}")
        print(f"- out_window_hex: {_hex_window(rebuilt_payload_bytes, center=mismatch)}")
    print("=" * 80)


def _command_ui_roundtrip_gil_wire(arguments: argparse.Namespace) -> None:
    input_gil_path = Path(arguments.input_gil_file).resolve()
    if not input_gil_path.is_file():
        raise FileNotFoundError(str(input_gil_path))

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)

    container_spec = read_gil_container_spec(input_gil_path)
    payload_bytes = read_gil_payload_bytes(input_gil_path)

    chunks, consumed_offset = decode_message_to_wire_chunks(
        data_bytes=payload_bytes,
        start_offset=0,
        end_offset=len(payload_bytes),
    )
    if consumed_offset != len(payload_bytes):
        raise ValueError(
            "wire decode 未能完整消费 payload："
            f"consumed={consumed_offset}, total={len(payload_bytes)}"
        )

    rebuilt_payload_bytes = encode_wire_chunks(chunks)
    output_gil_bytes = build_gil_file_bytes_from_payload(payload_bytes=rebuilt_payload_bytes, container_spec=container_spec)
    output_gil_path.write_bytes(output_gil_bytes)

    mismatch = _first_mismatch(payload_bytes, rebuilt_payload_bytes)

    print("=" * 80)
    print("UI roundtrip(wire) 完成（tag/value 原始字节级重组）：")
    print(f"- input:  {str(input_gil_path)}")
    print(f"- output: {str(output_gil_path)}")
    print(f"- payload_bytes:  in={len(payload_bytes)}, out={len(rebuilt_payload_bytes)}")
    print(f"- payload_sha1:   in={_sha1_hex(payload_bytes)}, out={_sha1_hex(rebuilt_payload_bytes)}")
    print(f"- payload_mismatch_offset: {mismatch}")
    if mismatch is not None:
        print(f"- in_window_hex:  {_hex_window(payload_bytes, center=mismatch)}")
        print(f"- out_window_hex: {_hex_window(rebuilt_payload_bytes, center=mismatch)}")
    print("=" * 80)


def register_ui_roundtrip_subcommands(ui_subparsers: argparse._SubParsersAction) -> None:
    parser = ui_subparsers.add_parser(
        "roundtrip-gil",
        help="打开并直接保存 .gil（不改任何字段），用于验证 Python 读取/写回链路是否正确",
    )
    parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    parser.add_argument("output_gil_file", help="输出 .gil 文件路径（强制落盘到 ugc_file_tools/out/ 下）")
    parser.set_defaults(entrypoint=_command_ui_roundtrip_gil)

    parser_wire = ui_subparsers.add_parser(
        "roundtrip-gil-wire",
        help="打开并直接保存 .gil（wire-level 字节重组，不做语义解析），用于验证 payload 读取/写回能否做到字节级一致",
    )
    parser_wire.add_argument("input_gil_file", help="输入 .gil 文件路径")
    parser_wire.add_argument("output_gil_file", help="输出 .gil 文件路径（强制落盘到 ugc_file_tools/out/ 下）")
    parser_wire.set_defaults(entrypoint=_command_ui_roundtrip_gil_wire)

