from __future__ import annotations

import copy
import json
import random
import struct
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like import (
    encode_message,
    format_binary_data_hex_text,
    parse_binary_data_hex_text,
)
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir

from .helpers import *  # noqa: F401,F403

def add_empty_struct_definition(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    struct_name: str,
    struct_id: int | None,
) -> Dict[str, Any]:
    """
    新建一个“空结构体”：克隆 `空的结构体`(ConfigID=1077936129) 模板，仅改 struct_id/名称/内部 id，并同步注册节点定义与页签。

    用途：作为最小化写回样本，用于排除“复杂字段默认值写错”导致的导入失败。
    """
    input_path = Path(input_gil_file_path).resolve()
    output_name = Path(str(output_gil_file_path)).name
    output_path = resolve_output_file_path_in_out_dir(Path(output_name))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))
    if not str(struct_name).strip():
        raise ValueError("struct_name 不能为空")

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    payload_root = raw_dump_object.get("4")
    if not isinstance(payload_root, dict):
        raise ValueError("DLL dump-json 缺少根字段 '4'（期望为 dict）。")

    node_graph_root = _ensure_path_dict(payload_root, "10")
    struct_blob_list = _ensure_path_list_allow_scalar(node_graph_root, "6")
    if not struct_blob_list:
        raise ValueError("当前存档未包含任何结构体定义 blob（root4/10/6 为空）。")

    existing_struct_ids: List[int] = []
    template_blob_text: str | None = None
    for entry in struct_blob_list:
        blob_bytes: bytes | None = None
        if isinstance(entry, str) and entry.startswith("<binary_data>"):
            blob_bytes = parse_binary_data_hex_text(entry)
        elif isinstance(entry, Mapping):
            blob_bytes = encode_message(entry)
        else:
            continue

        struct_id_int = _try_decode_struct_id_from_blob_bytes(blob_bytes)
        if not isinstance(struct_id_int, int):
            continue
        existing_struct_ids.append(int(struct_id_int))
        if int(struct_id_int) == 1077936129:
            template_blob_text = format_binary_data_hex_text(blob_bytes)

    if template_blob_text is None:
        raise ValueError("未找到 空的结构体 (ConfigID=1077936129) 作为模板，无法创建空结构体。")

    if struct_id is None:
        reserved_ids = _collect_reserved_struct_ids_from_payload_root(payload_root)
        reserved_set = set(int(v) for v in reserved_ids if isinstance(v, int))
        existing_set = set(int(v) for v in existing_struct_ids if isinstance(v, int))
        chosen = None
        if reserved_set & existing_set:
            for candidate in reserved_ids:
                if int(candidate) not in existing_set:
                    chosen = int(candidate)
                    break
        struct_id = chosen if chosen is not None else _choose_next_struct_id(existing_struct_ids)

    existing_internal_ids = _collect_existing_struct_internal_ids(struct_blob_list)
    next_internal_id = (max(existing_internal_ids) + 2) if existing_internal_ids else 2
    new_struct_internal_id = int(next_internal_id)

    node_defs = node_graph_root.get("2")
    if not isinstance(node_defs, list):
        raise ValueError("root4/10/2 缺失或不是 list，无法同步写入结构体节点定义注册。")
    template_node_defs = _find_template_struct_node_defs(node_defs, template_struct_id=1077936129)
    existing_node_type_ids = _collect_existing_node_type_ids(node_defs)
    next_node_type_id = (max(existing_node_type_ids) + 1) if existing_node_type_ids else 1610612740

    template_bytes = parse_binary_data_hex_text(template_blob_text)
    decoded_template = decode_bytes_to_python(template_bytes)
    if not isinstance(decoded_template, dict):
        raise ValueError("template struct blob decode result is not dict")
    new_decoded = copy.deepcopy(decoded_template)

    for wrapper_key in ("field_1", "field_2"):
        struct_message = _get_struct_message_from_decoded_blob(new_decoded, wrapper_key)

        struct_id_node = struct_message.get("field_1")
        if not isinstance(struct_id_node, dict):
            raise ValueError("template missing struct_message.field_1")
        _set_int_node(struct_id_node, int(struct_id))

        struct_name_node = struct_message.get("field_501")
        if not isinstance(struct_name_node, dict):
            raise ValueError("template missing struct_message.field_501")
        _set_text_node_utf8(struct_name_node, str(struct_name).strip())

        struct_internal_id_node = struct_message.get("field_503")
        if not isinstance(struct_internal_id_node, dict):
            raise ValueError("template missing struct_message.field_503")
        _set_int_node(struct_internal_id_node, int(new_struct_internal_id))

    new_blob_dump_json = _decoded_field_map_to_dump_json_message(new_decoded)
    new_blob_bytes = encode_message(new_blob_dump_json)
    struct_blob_list.append(format_binary_data_hex_text(new_blob_bytes))

    _ensure_struct_visible_in_tabs(
        payload_root,
        struct_id_int=int(struct_id),
        template_struct_id_int=1077936129,
    )

    template_pat = _encode_varint(1077936129)
    new_pat = _encode_varint(int(struct_id))
    for name in ("拼装结构体", "拆分结构体", "修改结构体"):
        template_entry = template_node_defs[name]
        old_node_type_id = _extract_node_type_id_from_node_def(template_entry)
        if old_node_type_id is None:
            raise ValueError(f"模板节点定义缺少 node_type_id：{name}")
        new_node_type_id = int(next_node_type_id)
        next_node_type_id += 1

        cloned = copy.deepcopy(template_entry)
        _replace_binary_data_bytes_in_object(cloned, old_bytes=template_pat, new_bytes=new_pat)
        _replace_int_values_in_object(cloned, old_value=1077936129, new_value=int(struct_id))
        _replace_int_values_in_object(cloned, old_value=int(old_node_type_id), new_value=int(new_node_type_id))
        old_node_type_pat = _encode_varint(int(old_node_type_id))
        new_node_type_pat = _encode_varint(int(new_node_type_id))
        if len(old_node_type_pat) == len(new_node_type_pat):
            _replace_binary_data_bytes_in_object(cloned, old_bytes=old_node_type_pat, new_bytes=new_node_type_pat)
        node_defs.append(cloned)

    payload_bytes = encode_message(payload_root)
    container_spec = read_gil_container_spec(input_path)
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=payload_bytes, container_spec=container_spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)

    return {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "struct_id": int(struct_id),
        "struct_name": str(struct_name),
        "struct_internal_id": int(new_struct_internal_id),
        "preset": "empty-struct",
        "struct_blob_count_before": len(struct_blob_list) - 1,
        "struct_blob_count_after": len(struct_blob_list),
    }


def rename_struct_definition(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    target_struct_id: int,
    new_struct_name: str,
) -> Dict[str, Any]:
    """
    仅重命名一个已存在的结构体定义（不新增/不注册/不改 node defs），用于最小化验证“写回是否可导入”。

    注意：该操作会修改 struct blob 内 field_501（显示名），其它字段保持不变。
    """
    input_path = Path(input_gil_file_path).resolve()
    output_name = Path(str(output_gil_file_path)).name
    output_path = resolve_output_file_path_in_out_dir(Path(output_name))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))
    if not str(new_struct_name).strip():
        raise ValueError("new_struct_name 不能为空")

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    payload_root = raw_dump_object.get("4")
    if not isinstance(payload_root, dict):
        raise ValueError("DLL dump-json 缺少根字段 '4'（期望为 dict）。")

    node_graph_root = _ensure_path_dict(payload_root, "10")
    struct_blob_list = _ensure_path_list_allow_scalar(node_graph_root, "6")
    if not struct_blob_list:
        raise ValueError("当前存档未包含任何结构体定义 blob（root4/10/6 为空）。")

    changed = False
    for idx, entry in enumerate(list(struct_blob_list)):
        if not isinstance(entry, str) or not entry.startswith("<binary_data>"):
            continue
        blob_bytes = parse_binary_data_hex_text(entry)
        decoded = decode_bytes_to_python(blob_bytes)
        if not isinstance(decoded, dict):
            continue

        # 检查 struct_id（以 field_1 的 struct_message 为准）
        wrapper = decoded.get("field_1")
        if not isinstance(wrapper, dict):
            continue
        struct_message = wrapper.get("message")
        if not isinstance(struct_message, dict):
            continue
        struct_id_node = struct_message.get("field_1")
        if not isinstance(struct_id_node, dict) or not isinstance(struct_id_node.get("int"), int):
            continue
        if int(struct_id_node["int"]) != int(target_struct_id):
            continue

        _sanitize_decoded_invalid_field0_message_nodes(decoded)

        # 更新 field_1 / field_2 两份 name
        for wrapper_key in ("field_1", "field_2"):
            sm = _get_struct_message_from_decoded_blob(decoded, wrapper_key)
            name_node = sm.get("field_501")
            if not isinstance(name_node, dict):
                raise ValueError("struct_message.field_501 missing")
            _set_text_node_utf8(name_node, str(new_struct_name).strip())

        new_blob_dump_json = _decoded_field_map_to_dump_json_message(decoded)
        new_blob_bytes = encode_message(new_blob_dump_json)
        struct_blob_list[idx] = format_binary_data_hex_text(new_blob_bytes)
        changed = True
        break

    if not changed:
        raise ValueError(f"未找到目标结构体定义 blob：struct_id={int(target_struct_id)}")

    payload_bytes = encode_message(payload_root)
    container_spec = read_gil_container_spec(input_path)
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=payload_bytes, container_spec=container_spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)

    return {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "target_struct_id": int(target_struct_id),
        "new_struct_name": str(new_struct_name),
        "preset": "rename-struct",
    }


def add_one_string_struct_definition(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    struct_name: str,
    field_name: str,
    field_default: str,
    struct_id: int | None,
) -> Dict[str, Any]:
    input_path = Path(input_gil_file_path).resolve()
    output_name = Path(str(output_gil_file_path)).name
    output_path = resolve_output_file_path_in_out_dir(Path(output_name))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))
    if not str(struct_name).strip():
        raise ValueError("struct_name 不能为空")
    if not str(field_name).strip():
        raise ValueError("field_name 不能为空")

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    payload_root = raw_dump_object.get("4")
    if not isinstance(payload_root, dict):
        raise ValueError("DLL dump-json 缺少根字段 '4'（期望为 dict）。")

    node_graph_root = _ensure_path_dict(payload_root, "10")
    struct_blob_list = _ensure_path_list_allow_scalar(node_graph_root, "6")

    existing_struct_ids: List[int] = []
    for entry in struct_blob_list:
        if not isinstance(entry, str) or not entry.startswith("<binary_data>"):
            continue
        blob_bytes = parse_binary_data_hex_text(entry)
        struct_id_int = _try_decode_struct_id_from_blob_bytes(blob_bytes)
        if isinstance(struct_id_int, int):
            existing_struct_ids.append(int(struct_id_int))

    if struct_id is None:
        reserved_ids = _collect_reserved_struct_ids_from_payload_root(payload_root)
        chosen = None
        for candidate in reserved_ids:
            if int(candidate) not in set(existing_struct_ids):
                chosen = int(candidate)
                break
        struct_id = chosen if chosen is not None else _choose_next_struct_id(existing_struct_ids)

    existing_internal_ids = _collect_existing_struct_internal_ids(struct_blob_list)
    next_internal_id = (max(existing_internal_ids) + 2) if existing_internal_ids else 2
    new_struct_internal_id = int(next_internal_id)

    if not struct_blob_list:
        raise ValueError("当前存档未包含任何结构体定义 blob（root4/10/6 为空），本脚本暂不支持从零构建模板。")

    # 选择一个“标准结构体 blob”作为模板（跳过混入的非标准条目）
    template_text = None
    for entry in struct_blob_list:
        if not isinstance(entry, str) or not entry.startswith("<binary_data>"):
            continue
        struct_id_int = _try_decode_struct_id_from_blob_bytes(parse_binary_data_hex_text(entry))
        if isinstance(struct_id_int, int):
            template_text = entry
            break
    if not isinstance(template_text, str):
        raise ValueError("未找到可用的结构体 blob 模板（root4/10/6 中可能不存在标准结构体定义条目）")
    template_bytes = parse_binary_data_hex_text(template_text)
    decoded_template = decode_bytes_to_python(template_bytes)
    if not isinstance(decoded_template, dict):
        raise ValueError("template struct blob decode result is not dict")

    new_decoded = copy.deepcopy(decoded_template)
    for wrapper_key in ("field_1", "field_2"):
        wrapper = new_decoded.get(wrapper_key)
        if not isinstance(wrapper, dict):
            raise ValueError(f"template missing {wrapper_key} wrapper")
        struct_message = wrapper.get("message")
        if not isinstance(struct_message, dict):
            raise ValueError(f"template missing {wrapper_key}.message")

        struct_id_node = struct_message.get("field_1")
        if not isinstance(struct_id_node, dict):
            raise ValueError("template missing struct_message.field_1")
        _set_int_node(struct_id_node, int(struct_id))

        struct_name_node = struct_message.get("field_501")
        if not isinstance(struct_name_node, dict):
            raise ValueError("template missing struct_message.field_501")
        _set_text_node_utf8(struct_name_node, str(struct_name).strip())

        struct_internal_id_node = struct_message.get("field_503")
        if not isinstance(struct_internal_id_node, dict):
            raise ValueError("template missing struct_message.field_503")
        _set_int_node(struct_internal_id_node, int(new_struct_internal_id))

        # 模板为单字段结构体：field_3.message 即字段定义
        field_3_wrapper = struct_message.get("field_3")
        if not isinstance(field_3_wrapper, dict):
            raise ValueError("template missing struct_message.field_3 wrapper")
        field_message = field_3_wrapper.get("message")
        if not isinstance(field_message, dict):
            raise ValueError("template missing struct_message.field_3.message")

        field_name_node_1 = field_message.get("field_5")
        field_name_node_2 = field_message.get("field_501")
        if not isinstance(field_name_node_1, dict) or not isinstance(field_name_node_2, dict):
            raise ValueError("template missing field name nodes (field_5/field_501)")
        _set_text_node_utf8(field_name_node_1, str(field_name).strip())
        _set_text_node_utf8(field_name_node_2, str(field_name).strip())

        # 默认值：字段内 field_3.message.field_16
        value_wrapper = field_message.get("field_3")
        if not isinstance(value_wrapper, dict):
            raise ValueError("template missing field_message.field_3 wrapper")
        value_message = value_wrapper.get("message")
        if not isinstance(value_message, dict):
            raise ValueError("template missing field_message.field_3.message")
        default_node = value_message.get("field_16")
        if not isinstance(default_node, dict):
            raise ValueError("template missing value_message.field_16")
        _set_default_string_node(default_node, str(field_default))

    new_blob_dump_json = _decoded_field_map_to_dump_json_message(new_decoded)
    new_blob_bytes = encode_message(new_blob_dump_json)
    struct_blob_list.append(format_binary_data_hex_text(new_blob_bytes))

    payload_bytes = encode_message(payload_root)
    container_spec = read_gil_container_spec(input_path)
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=payload_bytes, container_spec=container_spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)

    return {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "struct_id": int(struct_id),
        "struct_name": str(struct_name),
        "struct_internal_id": int(new_struct_internal_id),
        "field_name": str(field_name),
        "field_default": str(field_default),
        "struct_blob_count_before": len(struct_blob_list) - 1,
        "struct_blob_count_after": len(struct_blob_list),
    }


