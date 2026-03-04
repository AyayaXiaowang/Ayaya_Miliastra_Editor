"""
将 .gil 存档尽可能解析为“可读 JSON”。

设计目标：
- 不依赖仓库内现有的二进制导向解析脚本（自研实现）。
- 输出以可读性优先：字段尽量展开；二进制提供 sha1+hex 预览；字符串尽量还原。
- 以“protobuf-like”通用规则解析 payload（varint / fixed32 / fixed64 / length-delimited），并对 length-delimited
  尝试判定为：UTF-8 字符串 / 嵌套 message / packed 数组 / 原始 bytes。

使用示例（在仓库根目录）：
  python ugc_file_tools/gil_to_readable_json.py --input ugc_file_tools/builtin_resources/seeds/template_instance_exemplars.gil --package-name test2
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from typing import Any, Dict, Iterable, List, Optional

from ugc_file_tools.gil_dump_codec.gil_container import read_gil_payload_bytes_and_container_meta
from ugc_file_tools.gil_dump_codec.protobuf_like import ProtobufLikeParseOptions, parse_message
from ugc_file_tools.output_paths import resolve_output_dir_path_in_out_dir


JsonValue = Any


def walk_strings(message_json: Dict[str, JsonValue]) -> List[Dict[str, JsonValue]]:
    results: List[Dict[str, JsonValue]] = []

    def visit_message(current_message: Dict[str, JsonValue], path_prefix: str) -> None:
        for field_key, field_values in current_message.items():
            if field_key.startswith("_"):
                continue
            if not isinstance(field_values, list):
                continue
            for value_index, value in enumerate(field_values):
                current_path = f"{path_prefix}.f{field_key}[{value_index}]"

                if not isinstance(value, dict):
                    continue

                wire_type = value.get("wire_type")
                if wire_type != 2:
                    continue

                value_object = value.get("value")
                if not isinstance(value_object, dict):
                    continue

                kind = value_object.get("kind")
                if kind == "string":
                    text_value = value_object.get("text")
                    if isinstance(text_value, str):
                        results.append({"path": current_path, "text": text_value, "length": len(text_value)})
                    continue

                if kind == "message":
                    nested = value_object.get("message")
                    if isinstance(nested, dict):
                        visit_message(nested, current_path)

    visit_message(message_json, "root")
    return results


def summarize_parsed_value(value: JsonValue) -> Dict[str, JsonValue]:
    if not isinstance(value, dict):
        return {"kind": "unknown", "python_type": type(value).__name__}

    wire_type = value.get("wire_type")
    if wire_type == 0:
        return {"wire_type": 0, "varint": value.get("varint"), "as_bool": value.get("as_bool")}
    if wire_type == 1:
        return {"wire_type": 1, "u64": value.get("u64"), "f64": value.get("f64")}
    if wire_type == 5:
        return {"wire_type": 5, "u32": value.get("u32"), "f32": value.get("f32")}

    if wire_type != 2:
        return {"wire_type": wire_type, "kind": "unknown"}

    length_value = value.get("length")
    value_object = value.get("value")
    if not isinstance(value_object, dict):
        return {"wire_type": 2, "length": length_value, "kind": "unknown"}

    kind = value_object.get("kind")
    if kind == "string":
        text_value = value_object.get("text")
        if isinstance(text_value, str):
            preview_text = text_value[:200]
        else:
            preview_text = None
        return {"wire_type": 2, "length": length_value, "kind": "string", "text_length": len(text_value) if isinstance(text_value, str) else None, "preview": preview_text}

    if kind == "bytes":
        return {
            "wire_type": 2,
            "length": value_object.get("length", length_value),
            "kind": "bytes",
            "sha1": value_object.get("sha1"),
            "preview_hex": value_object.get("preview_hex"),
            "has_base64": value_object.get("base64") is not None,
        }

    if kind == "message":
        bytes_meta = value_object.get("bytes")
        nested_message = value_object.get("message")
        nested_meta = nested_message.get("_meta", {}) if isinstance(nested_message, dict) else {}
        return {
            "wire_type": 2,
            "length": length_value,
            "kind": "message",
            "bytes": bytes_meta,
            "nested_entry_count": nested_meta.get("entry_count"),
        }

    if kind == "packed_varint":
        packed_values = value_object.get("values")
        if isinstance(packed_values, list):
            return {"wire_type": 2, "length": length_value, "kind": "packed_varint", "count": len(packed_values)}
        return {"wire_type": 2, "length": length_value, "kind": "packed_varint", "count": None}

    if kind in ("packed_fixed32", "packed_fixed64"):
        packed_values = value_object.get("values")
        if isinstance(packed_values, dict):
            first_key = "f32" if kind == "packed_fixed32" else "f64"
            array_value = packed_values.get(first_key)
            if isinstance(array_value, list):
                return {"wire_type": 2, "length": length_value, "kind": kind, "count": len(array_value)}
        return {"wire_type": 2, "length": length_value, "kind": kind, "count": None}

    return {"wire_type": 2, "length": length_value, "kind": kind}


def build_root_fields_summary(message_json: Dict[str, JsonValue]) -> List[Dict[str, JsonValue]]:
    field_summaries: List[Dict[str, JsonValue]] = []

    field_keys = [key for key in message_json.keys() if not key.startswith("_")]
    field_keys_sorted = sorted(field_keys, key=lambda key: int(key) if str(key).isdigit() else key)

    for field_key in field_keys_sorted:
        field_values = message_json.get(field_key)
        if not isinstance(field_values, list):
            continue
        field_summaries.append(
            {
                "field": int(field_key) if str(field_key).isdigit() else field_key,
                "count": len(field_values),
                "values": [summarize_parsed_value(value) for value in field_values],
            }
        )

    return field_summaries


def walk_length_delimited_index(message_json: Dict[str, JsonValue]) -> List[Dict[str, JsonValue]]:
    results: List[Dict[str, JsonValue]] = []

    def visit_message(current_message: Dict[str, JsonValue], path_prefix: str) -> None:
        for field_key, field_values in current_message.items():
            if field_key.startswith("_"):
                continue
            if not isinstance(field_values, list):
                continue
            for value_index, value in enumerate(field_values):
                current_path = f"{path_prefix}.f{field_key}[{value_index}]"

                if not isinstance(value, dict):
                    continue

                if value.get("wire_type") != 2:
                    continue

                length_value = value.get("length")
                value_object = value.get("value")
                if not isinstance(value_object, dict):
                    continue

                kind = value_object.get("kind")
                if kind == "string":
                    continue

                record: Dict[str, JsonValue] = {"path": current_path, "kind": kind, "length": length_value}

                if kind == "bytes":
                    record.update(
                        {
                            "sha1": value_object.get("sha1"),
                            "preview_hex": value_object.get("preview_hex"),
                            "has_base64": value_object.get("base64") is not None,
                        }
                    )
                    results.append(record)
                    continue

                if kind == "message":
                    bytes_meta = value_object.get("bytes")
                    nested_message = value_object.get("message")
                    nested_meta = nested_message.get("_meta", {}) if isinstance(nested_message, dict) else {}
                    record.update({"bytes": bytes_meta, "nested_entry_count": nested_meta.get("entry_count")})
                    results.append(record)
                    if isinstance(nested_message, dict):
                        visit_message(nested_message, current_path)
                    continue

                if kind == "packed_varint":
                    packed_values = value_object.get("values")
                    record.update({"count": len(packed_values) if isinstance(packed_values, list) else None})
                    results.append(record)
                    continue

                if kind in ("packed_fixed32", "packed_fixed64"):
                    packed_values = value_object.get("values")
                    if isinstance(packed_values, dict):
                        array_key = "f32" if kind == "packed_fixed32" else "f64"
                        array_value = packed_values.get(array_key)
                        record.update({"count": len(array_value) if isinstance(array_value, list) else None})
                    results.append(record)
                    continue

                results.append(record)

    visit_message(message_json, "root")
    return results


def group_strings_by_category(strings_index: List[Dict[str, JsonValue]]) -> Dict[str, List[Dict[str, JsonValue]]]:
    categories: Dict[str, List[Dict[str, JsonValue]]] = {
        "entity": [],
        "graph": [],
        "variable": [],
        "ui": [],
        "other": [],
    }

    keyword_map = {
        "entity": ["entity", "Entity", "实体", "prefab", "Prefab", "unit", "Unit", "怪物", "角色"],
        "graph": ["graph", "Graph", "node", "Node", "节点", "连线", "端口", "pin", "Pin"],
        "variable": ["var", "Var", "变量", "global", "local", "field", "Field", "关卡", "存档"],
        "ui": ["UI", "ui", "RectTransform", "TextBox", "Button", "Canvas", "GUID", "Guid"],
    }

    for record in strings_index:
        text_value = record.get("text")
        if not isinstance(text_value, str):
            continue

        matched_category: Optional[str] = None
        for category, keywords in keyword_map.items():
            if any(keyword in text_value for keyword in keywords):
                matched_category = category
                break

        if matched_category is None:
            matched_category = "other"

        categories[matched_category].append(record)

    return categories


def extract_suspected_variable_names(strings_index: List[Dict[str, JsonValue]]) -> List[Dict[str, JsonValue]]:
    results: List[Dict[str, JsonValue]] = []

    identifier_pattern = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{2,63}$")
    contains_separator_pattern = re.compile(r"[/_:：]")

    for record in strings_index:
        text_value = record.get("text")
        if not isinstance(text_value, str):
            continue

        if identifier_pattern.match(text_value) is not None:
            results.append(record)
            continue

        if contains_separator_pattern.search(text_value) is not None and 2 <= len(text_value) <= 64:
            results.append(record)
            continue

        if "变量" in text_value and len(text_value) <= 64:
            results.append(record)
            continue

    return results


def write_json_file(output_path: pathlib.Path, data: JsonValue) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False), encoding="utf-8")


def locate_repo_root(script_path: pathlib.Path) -> pathlib.Path:
    # 本脚本位于 ugc_file_tools/ 下，因此仓库根目录是其父目录
    return script_path.resolve().parent.parent


def main() -> None:
    argument_parser = argparse.ArgumentParser(description="将 .gil 尽可能解析为可读 JSON，并导出到 项目存档/<package>/ 下。")
    argument_parser.add_argument(
        "--input",
        required=True,
        help="输入 .gil 文件路径，例如 ugc_file_tools/builtin_resources/seeds/template_instance_exemplars.gil",
    )
    argument_parser.add_argument("--package-name", required=True, help="输出项目存档名称（package_id），例如 test2")
    argument_parser.add_argument(
        "--package-root",
        default=None,
        help="项目存档根目录（默认推断为 Graph_Generater/assets/资源库/项目存档）",
    )
    argument_parser.add_argument("--max-depth", type=int, default=8, help="嵌套 message 最大递归深度（默认 8）")
    argument_parser.add_argument("--bytes-preview", type=int, default=64, help="bytes 预览 hex 长度（默认 64）")
    arguments = argument_parser.parse_args()

    input_path = pathlib.Path(arguments.input)
    if not input_path.exists():
        raise FileNotFoundError(str(input_path))

    if arguments.package_root is None:
        package_root = resolve_output_dir_path_in_out_dir(pathlib.Path("gil_readable_packages"))
    else:
        package_root = resolve_output_dir_path_in_out_dir(pathlib.Path(arguments.package_root))

    package_directory = package_root / arguments.package_name
    output_directory = package_directory / "原始解析" / "自研解析"

    payload_bytes, container_meta = read_gil_payload_bytes_and_container_meta(gil_file_path=input_path)
    container_meta = dict(container_meta)
    file_size = int(input_path.stat().st_size)

    payload_start = 20
    payload_length = int(container_meta.get("body_size") or 0)
    payload_end = payload_start + payload_length
    footer_offset = int(container_meta.get("total_size_field") or 0)
    if payload_end != footer_offset:
        raise ValueError(
            "unexpected layout: payload_end != footer_offset "
            f"(payload_end={payload_end}, footer_offset={footer_offset})"
        )
    if footer_offset + 4 != file_size:
        raise ValueError(
            "unexpected layout: footer_offset + trailer(4) != file_size "
            f"(footer_offset={footer_offset}, file_size={file_size})"
        )

    trailer_u32_be = int(container_meta.get("footer_value") or 0)
    trailer_raw_hex = int(trailer_u32_be).to_bytes(4, byteorder="big", signed=False).hex()

    container_json = {
        "schema_version": 2,
        "input_file": str(input_path.as_posix()),
        "file_size": file_size,
        # `.gil` 文件结构（big-endian u32）：
        # - u32[0]=total_size_field
        # - u32[1]=header_value_one
        # - u32[2]=header_value_two
        # - u32[3]=type_id_value
        # - u32[4]=body_size（payload_length）
        "container_u32_be_fields": {
            "total_size_field": int(container_meta.get("total_size_field") or 0),
            "header_value_one": int(container_meta.get("header_value_one") or 0),
            "header_value_two": int(container_meta.get("header_value_two") or 0),
            "type_id_value": int(container_meta.get("type_id_value") or 0),
            "body_size": int(container_meta.get("body_size") or 0),
        },
        "container_meta": container_meta,
        "layout": {
            "payload_start": payload_start,
            "payload_end": payload_end,
            "footer_offset": footer_offset,
        },
        # 兼容旧输出口径（deprecated）：早期脚本手搓 header 并使用含糊命名（header_version/header_value_*）。
        # 新代码请使用 `container_u32_be_fields` / `container_meta` / `layout`。
        "legacy_header": {
            "total_length_after_first_u32": int(container_meta.get("total_size_field") or 0),
            "header_version": int(container_meta.get("header_value_one") or 0),
            "header_value_1": int(container_meta.get("header_value_two") or 0),
            "header_value_2": int(container_meta.get("type_id_value") or 0),
            "payload_length": payload_length,
            "payload_start": payload_start,
            "payload_end": payload_end,
        },
        "trailer": {
            "raw_hex": trailer_raw_hex,
            "u32_be": trailer_u32_be,
        },
    }

    parse_options = ProtobufLikeParseOptions(
        max_depth=int(arguments.max_depth),
        bytes_preview_length=int(arguments.bytes_preview),
        max_length_delimited_string_bytes=200_000,
        max_packed_items=10_000,
        max_message_bytes_for_probe=2_000_000,
    )

    payload_message, _next_offset, ok, error = parse_message(
        byte_data=payload_bytes,
        start_offset=0,
        end_offset=len(payload_bytes),
        depth=0,
        options=parse_options,
    )

    payload_summary = {
        "payload_length": len(payload_bytes),
        "parse_ok": ok,
        "parse_error": error,
        "root_entry_count": payload_message.get("_meta", {}).get("entry_count"),
    }

    strings_index = walk_strings(payload_message)
    categorized_strings = group_strings_by_category(strings_index)
    suspected_variable_names = extract_suspected_variable_names(strings_index)
    root_fields_summary = build_root_fields_summary(payload_message)
    length_delimited_index = walk_length_delimited_index(payload_message)

    length_delimited_with_size = []
    for record in length_delimited_index:
        if record.get("kind") == "bytes":
            size_value = record.get("length")
        elif record.get("kind") == "message":
            bytes_meta = record.get("bytes")
            size_value = bytes_meta.get("length") if isinstance(bytes_meta, dict) else record.get("length")
        else:
            size_value = record.get("length")
        length_delimited_with_size.append((int(size_value) if isinstance(size_value, int) else 0, record))
    largest_length_delimited_items = [record for _size, record in sorted(length_delimited_with_size, key=lambda item: item[0], reverse=True)[:200]]

    write_json_file(output_directory / "gil_container.json", container_json)
    write_json_file(output_directory / "payload_summary.json", payload_summary)
    write_json_file(output_directory / "payload_parsed.json", payload_message)
    write_json_file(output_directory / "root_fields_summary.json", root_fields_summary)
    write_json_file(output_directory / "strings_all.json", strings_index)
    write_json_file(output_directory / "strings_by_category.json", categorized_strings)
    write_json_file(output_directory / "strings_suspected_variable_names.json", suspected_variable_names)
    write_json_file(output_directory / "length_delimited_index.json", length_delimited_index)
    write_json_file(output_directory / "largest_length_delimited_items.json", largest_length_delimited_items)

    # 额外按资源目录投放便于检索的索引文件（不覆盖既有解析产物）
    write_json_file(package_directory / "管理配置" / "关卡变量" / "自研_疑似自定义变量名.json", suspected_variable_names)
    write_json_file(package_directory / "节点图" / "原始解析" / "自研_节点图相关字符串路径索引.json", categorized_strings["graph"])
    write_json_file(package_directory / "实体摆放" / "自研_实体相关字符串路径索引.json", categorized_strings["entity"])


if __name__ == "__main__":
    from ugc_file_tools.unified_cli.entry_guard import deny_direct_execution

    deny_direct_execution(tool_name="gil_to_readable_json")


