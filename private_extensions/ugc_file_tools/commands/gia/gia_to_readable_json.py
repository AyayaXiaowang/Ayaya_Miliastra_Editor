from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gia.container import (
    read_gia_container_header,
    unwrap_gia_container,
    validate_gia_container_file,
)
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map
from ugc_file_tools.output_paths import resolve_output_dir_path_in_out_dir


def _sanitize_filename(name: str, *, max_length: int = 140) -> str:
    text = str(name or "").strip()
    if text == "":
        return "untitled"
    text = text.replace("\\", "_").replace("/", "_")
    text = text.replace(":", "_").replace("*", "_").replace("?", "_").replace('"', "_")
    text = text.replace("<", "_").replace(">", "_").replace("|", "_")
    text = " ".join(text.split())
    if len(text) > int(max_length):
        text = text[: int(max_length)].rstrip()
    return text or "untitled"


def export_gia_readable_json(
    gia_file_path: Path,
    *,
    output_dir: Path,
    check_header: bool,
    max_depth: int,
) -> Dict[str, Any]:
    gia_file_path = Path(gia_file_path).resolve()
    if not gia_file_path.is_file():
        raise FileNotFoundError(f"input gia file not found: {str(gia_file_path)!r}")

    if check_header:
        validate_gia_container_file(gia_file_path)

    header = read_gia_container_header(gia_file_path)
    proto_bytes = unwrap_gia_container(gia_file_path, check_header=False)

    fields_map, consumed = decode_message_to_field_map(
        data_bytes=proto_bytes,
        start_offset=0,
        end_offset=len(proto_bytes),
        remaining_depth=int(max_depth),
    )
    if consumed != len(proto_bytes):
        raise ValueError(
            "protobuf 解析未消费完整字节流："
            f"consumed={consumed} total={len(proto_bytes)} file={str(gia_file_path)!r}"
        )

    output_dir = resolve_output_dir_path_in_out_dir(Path(output_dir), default_dir_name="gia_readable_json")
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = _sanitize_filename(gia_file_path.stem)
    output_path = output_dir / f"gia_readable_{stem}.json"
    payload = {
        "schema_version": 1,
        "source_gia_file": str(gia_file_path),
        "header": {
            "left_size": header.left_size,
            "schema_version": header.schema_version,
            "head_tag": header.head_tag,
            "file_type": header.file_type,
            "proto_size": header.proto_size,
            "tail_tag": header.tail_tag,
        },
        "proto_bytes_len": len(proto_bytes),
        "root_message": fields_map,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "source_gia_file": str(gia_file_path),
        "output_dir": str(output_dir),
        "output_json": str(output_path),
        "proto_bytes_len": len(proto_bytes),
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description="导出 .gia（节点图/结构体等）为可读 JSON（protobuf-like lossless field map）。"
    )
    argument_parser.add_argument("--input-gia", dest="input_gia_file", required=True, help="输入 .gia 文件路径")
    argument_parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default="gia_readable_json",
        help="输出目录（默认：gia_readable_json；实际会被收口到 ugc_file_tools/out/ 下）。",
    )
    argument_parser.add_argument(
        "--check-header",
        dest="check_header",
        action="store_true",
        help="严格校验 .gia 容器头/尾（失败会直接抛错）。",
    )
    argument_parser.add_argument(
        "--max-depth",
        dest="max_depth",
        type=int,
        default=16,
        help="protobuf 递归解码深度上限（默认 16；越大越可能把 binary 当成嵌套 message 解开）。",
    )

    arguments = argument_parser.parse_args(list(argv) if argv is not None else None)

    result = export_gia_readable_json(
        Path(arguments.input_gia_file),
        output_dir=Path(arguments.output_dir),
        check_header=bool(arguments.check_header),
        max_depth=int(arguments.max_depth),
    )

    print("=" * 80)
    print("GIA 可读 JSON 导出完成：")
    print(f"- source_gia_file: {result.get('source_gia_file')}")
    print(f"- output_dir: {result.get('output_dir')}")
    print(f"- output_json: {result.get('output_json')}")
    print(f"- proto_bytes_len: {result.get('proto_bytes_len')}")
    print("=" * 80)


if __name__ == "__main__":
    from ugc_file_tools.unified_cli.entry_guard import deny_direct_execution

    deny_direct_execution(tool_name="gia_to_readable_json")




