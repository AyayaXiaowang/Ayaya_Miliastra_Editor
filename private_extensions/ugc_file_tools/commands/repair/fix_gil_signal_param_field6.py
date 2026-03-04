from __future__ import annotations

"""
修复 `.gil` 信号参数定义中缺失 `field_6(send_to_server_port_index)` 的问题。

背景：
- 部分损坏样本会出现 signal_entry.param_definition 仅有 field_4/field_5（send/listen），缺失 field_6（server）；
- 导致导出/解析链路在读取该参数定义时直接报错：
  `expected field_6 to be dict, got: NoneType`。

策略：
- 使用 wire-level patch（tag/value 原始字节）做最小改动，不走整包 decode→re-encode；
- 仅在 param_definition 缺失 field_6 且存在 field_5 时补齐：
  `field_6 = field_5 + 1`（与当前信号端口分配规律保持一致）。
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_varint, encode_tag, encode_varint
from ugc_file_tools.gil_package_exporter.gil_reader import read_gil_header
from ugc_file_tools.wire.codec import decode_message_to_wire_chunks, encode_wire_chunks
from ugc_file_tools.wire.patch import build_length_delimited_value_raw, parse_tag_raw, split_length_delimited_value_raw


@dataclass(frozen=True, slots=True)
class _ParamPatchRecord:
    entry_index: int
    signal_name: str
    param_index: int
    inferred_field6_value: int


def _decode_chunks(payload_bytes: bytes) -> list[tuple[bytes, bytes]]:
    chunks, consumed = decode_message_to_wire_chunks(
        data_bytes=payload_bytes,
        start_offset=0,
        end_offset=len(payload_bytes),
    )
    if consumed != len(payload_bytes):
        raise ValueError(f"wire decode consumed mismatch: consumed={consumed}, total={len(payload_bytes)}")
    return list(chunks)


def _decode_varint_value(value_raw: bytes) -> int:
    value, offset, ok = decode_varint(value_raw, 0, len(value_raw))
    if not ok or offset != len(value_raw):
        raise ValueError("invalid varint value_raw")
    return int(value)


def _read_first_string_field(payload_bytes: bytes, field_number: int) -> str:
    for tag_raw, value_raw in _decode_chunks(payload_bytes):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number != int(field_number) or parsed.wire_type != 2:
            continue
        _, text_payload = split_length_delimited_value_raw(value_raw)
        return text_payload.decode("utf-8")
    return ""


def _patch_param_definition_payload(param_payload_bytes: bytes) -> tuple[bytes, bool, int]:
    chunks = _decode_chunks(param_payload_bytes)
    has_field6 = False
    field5_value: Optional[int] = None
    for tag_raw, value_raw in chunks:
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number == 6 and parsed.wire_type == 0:
            has_field6 = True
        if parsed.field_number == 5 and parsed.wire_type == 0:
            field5_value = _decode_varint_value(value_raw)

    if has_field6:
        return param_payload_bytes, False, -1
    if not isinstance(field5_value, int):
        raise ValueError("signal param definition missing field_5; cannot infer field_6")

    inferred_field6 = int(field5_value) + 1
    chunks.append((encode_tag(6, 0), encode_varint(inferred_field6)))
    return encode_wire_chunks(chunks), True, inferred_field6


def _repair_missing_field6(*, input_gil_file_path: Path, output_gil_file_path: Path) -> dict:
    input_path = Path(input_gil_file_path).resolve()
    output_path = Path(output_gil_file_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))
    if output_path == input_path:
        raise ValueError("output path cannot be the same as input path")
    if output_path.suffix.lower() != ".gil":
        raise ValueError(f"output file must be .gil: {str(output_path)}")

    file_bytes = input_path.read_bytes()
    header = read_gil_header(file_bytes)
    payload_bytes = file_bytes[20 : 20 + int(header.body_size)]
    if len(payload_bytes) != int(header.body_size):
        raise ValueError(
            f"gil payload size mismatch: expected={int(header.body_size)} got={len(payload_bytes)} path={str(input_path)!r}"
        )

    root_chunks = _decode_chunks(payload_bytes)

    section10_index = -1
    section10_payload_bytes = b""
    for idx, (tag_raw, value_raw) in enumerate(root_chunks):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number == 10 and parsed.wire_type == 2:
            _, section10_payload_bytes = split_length_delimited_value_raw(value_raw)
            section10_index = idx
            break
    if section10_index < 0:
        raise ValueError("payload root missing section 10")

    section10_chunks = _decode_chunks(section10_payload_bytes)

    section5_index = -1
    section5_payload_bytes = b""
    for idx, (tag_raw, value_raw) in enumerate(section10_chunks):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number == 5 and parsed.wire_type == 2:
            _, section5_payload_bytes = split_length_delimited_value_raw(value_raw)
            section5_index = idx
            break
    if section5_index < 0:
        raise ValueError("payload section 10 missing section 5 (signal registry)")

    section5_chunks = _decode_chunks(section5_payload_bytes)

    patched_records: list[_ParamPatchRecord] = []
    scanned_param_count = 0
    scanned_signal_entry_count = 0
    patched_section5_chunks: list[tuple[bytes, bytes]] = []

    signal_entry_seen_index = -1
    for section5_tag_raw, section5_value_raw in section5_chunks:
        parsed5 = parse_tag_raw(section5_tag_raw)
        if parsed5.field_number != 3 or parsed5.wire_type != 2:
            patched_section5_chunks.append((section5_tag_raw, section5_value_raw))
            continue

        signal_entry_seen_index += 1
        scanned_signal_entry_count += 1
        _, signal_entry_payload = split_length_delimited_value_raw(section5_value_raw)
        signal_entry_chunks = _decode_chunks(signal_entry_payload)
        signal_name = _read_first_string_field(signal_entry_payload, 3)

        patched_entry_chunks: list[tuple[bytes, bytes]] = []
        entry_changed = False
        param_seen_index = -1
        for entry_tag_raw, entry_value_raw in signal_entry_chunks:
            entry_parsed = parse_tag_raw(entry_tag_raw)
            if entry_parsed.field_number != 4 or entry_parsed.wire_type != 2:
                patched_entry_chunks.append((entry_tag_raw, entry_value_raw))
                continue

            param_seen_index += 1
            scanned_param_count += 1
            _, param_payload = split_length_delimited_value_raw(entry_value_raw)
            patched_param_payload, changed, inferred_field6 = _patch_param_definition_payload(param_payload)
            if changed:
                patched_records.append(
                    _ParamPatchRecord(
                        entry_index=int(signal_entry_seen_index),
                        signal_name=str(signal_name),
                        param_index=int(param_seen_index),
                        inferred_field6_value=int(inferred_field6),
                    )
                )
                entry_changed = True
                patched_entry_chunks.append((entry_tag_raw, build_length_delimited_value_raw(patched_param_payload)))
                continue

            patched_entry_chunks.append((entry_tag_raw, entry_value_raw))

        if entry_changed:
            patched_signal_entry_payload = encode_wire_chunks(patched_entry_chunks)
            patched_section5_chunks.append((section5_tag_raw, build_length_delimited_value_raw(patched_signal_entry_payload)))
            continue

        patched_section5_chunks.append((section5_tag_raw, section5_value_raw))

    patched_section5_payload = encode_wire_chunks(patched_section5_chunks)
    section5_tag_raw, _section5_value_raw = section10_chunks[section5_index]
    section10_chunks[section5_index] = (section5_tag_raw, build_length_delimited_value_raw(patched_section5_payload))

    patched_section10_payload = encode_wire_chunks(section10_chunks)
    section10_tag_raw, _section10_value_raw = root_chunks[section10_index]
    root_chunks[section10_index] = (section10_tag_raw, build_length_delimited_value_raw(patched_section10_payload))

    output_payload_bytes = encode_wire_chunks(root_chunks)
    container_spec = read_gil_container_spec(input_path)
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=output_payload_bytes, container_spec=container_spec)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)

    return {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "scanned_signal_entries": int(scanned_signal_entry_count),
        "scanned_signal_params": int(scanned_param_count),
        "patched_param_count": int(len(patched_records)),
        "patched_params": [
            {
                "entry_index": int(r.entry_index),
                "signal_name": str(r.signal_name),
                "param_index": int(r.param_index),
                "inferred_field6_value": int(r.inferred_field6_value),
            }
            for r in patched_records
        ],
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="修复 .gil 信号参数定义缺失 field_6(send_to_server_port_index) 的问题（wire-level 最小补丁）。"
    )
    parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    parser.add_argument("output_gil_file", help="输出 .gil 文件路径（不能与输入相同）")
    parser.add_argument(
        "--report",
        dest="report_json_file",
        default="",
        help="可选：输出修复报告 JSON 文件路径",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    report = _repair_missing_field6(
        input_gil_file_path=Path(str(args.input_gil_file)),
        output_gil_file_path=Path(str(args.output_gil_file)),
    )

    report_path_text = str(args.report_json_file or "").strip()
    if report_path_text:
        report_path = Path(report_path_text).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()



