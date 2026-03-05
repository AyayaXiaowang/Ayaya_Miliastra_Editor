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

def clone_struct_all_supported_definition(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    struct_name: str,
    struct_id: int | None,
    profile: str,
) -> Dict[str, Any]:
    """
    克隆 `struct_all_supported`(ConfigID=1077936130) 为一个新的结构体（通常写入到预注册槽位 1077936132）。

    profile:
    - base: 仅改 struct_id/名称（以及必要的注册：node10/2 + tab），不改任何默认值/引用ID/内部ID
    - scalars: 在 base 基础上，仅修改“纯标量字段”的默认值（int/bool/float/string/vector3）
    - int/bool/float/string/vector3: 在 base 基础上，仅修改对应单一字段（用于更细粒度二分定位）

    用途：对游戏导入失败做二分定位，判断是否是某类默认值编码/长度触发校验。
    """
    profile_value = str(profile or "").strip()
    if profile_value not in {"base", "scalars", "int", "bool", "float", "string", "vector3"}:
        raise ValueError(f"unsupported profile: {profile_value!r}")

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
        if int(struct_id_int) == 1077936130:
            template_blob_text = format_binary_data_hex_text(blob_bytes)

    if template_blob_text is None:
        raise ValueError("未找到 struct_all_supported (ConfigID=1077936130) 作为模板，无法克隆。")

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

    node_defs = node_graph_root.get("2")
    if not isinstance(node_defs, list):
        raise ValueError("root4/10/2 缺失或不是 list，无法同步写入结构体节点定义注册。")
    template_node_defs = _find_template_struct_node_defs(node_defs, template_struct_id=1077936130)
    existing_node_type_ids = _collect_existing_node_type_ids(node_defs)
    next_node_type_id = (max(existing_node_type_ids) + 1) if existing_node_type_ids else 1610612740

    template_bytes = parse_binary_data_hex_text(template_blob_text)
    decoded_template = decode_bytes_to_python(template_bytes)
    if not isinstance(decoded_template, dict):
        raise ValueError("template struct blob decode result is not dict")
    new_decoded = copy.deepcopy(decoded_template)

    mod_int = profile_value in {"scalars", "int"}
    mod_bool = profile_value in {"scalars", "bool"}
    mod_float = profile_value in {"scalars", "float"}
    mod_string = profile_value in {"scalars", "string"}
    mod_vector3 = profile_value in {"scalars", "vector3"}

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

        # 仅为保证可重编码：把 decode_gil 误解码出的 field_0(bytes=00 00) 归一为 raw_hex=0000
        _sanitize_decoded_invalid_field0_message_nodes(struct_message)

        if mod_int:
            # int
            int_entry, int_entry_kind, int_field = _find_field_message(struct_message, "整数字段")
            _, int_container, _ = _get_type_value_container(int_field)
            _set_default_int_in_message_container(int_container, 12345)
            _commit_field_entry(int_entry, int_entry_kind, int_field)

        if mod_bool:
            # bool
            bool_entry, bool_entry_kind, bool_field = _find_field_message(struct_message, "布尔值字段")
            _, bool_container, _ = _get_type_value_container(bool_field)
            _set_default_bool_node(bool_container, True)
            _commit_field_entry(bool_entry, bool_entry_kind, bool_field)

        if mod_float:
            # float
            float_entry, float_entry_kind, float_field = _find_field_message(struct_message, "浮点数字段")
            _, float_container, _ = _get_type_value_container(float_field)
            _set_default_float_in_message_container(float_container, 9.87)
            _commit_field_entry(float_entry, float_entry_kind, float_field)

        if mod_string:
            # string
            str_entry, str_entry_kind, str_field = _find_field_message(struct_message, "字符串字段")
            _, str_container, _ = _get_type_value_container(str_field)
            _set_default_string_node(str_container, "写回_标量_字符串_测试")
            _commit_field_entry(str_entry, str_entry_kind, str_field)

        if mod_vector3:
            # vector3
            vec_entry, vec_entry_kind, vec_field = _find_field_message(struct_message, "三维向量字段")
            _, vec_container, _ = _get_type_value_container(vec_field)
            _set_default_vector3_in_message_container(vec_container, 1.1, 2.2, 3.3)
            _commit_field_entry(vec_entry, vec_entry_kind, vec_field)

    new_blob_dump_json = _decoded_field_map_to_dump_json_message(new_decoded)
    new_blob_bytes = encode_message(new_blob_dump_json)
    struct_blob_list.append(format_binary_data_hex_text(new_blob_bytes))

    _ensure_struct_visible_in_tabs(
        payload_root,
        struct_id_int=int(struct_id),
        template_struct_id_int=1077936130,
    )

    template_pat = _encode_varint(1077936130)
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
        _replace_int_values_in_object(cloned, old_value=1077936130, new_value=int(struct_id))
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
        "preset": f"clone-all-supported-{profile_value}",
        "struct_blob_count_before": len(struct_blob_list) - 1,
        "struct_blob_count_after": len(struct_blob_list),
    }


