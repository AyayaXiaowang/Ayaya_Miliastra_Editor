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

def add_all_types_test_struct_definition(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    struct_name: str,
    struct_id: int | None,
    seed: int | None,
) -> Dict[str, Any]:
    """
    新建一个“全类型测试结构体”：克隆 `struct_all_supported` 模板，并写入一组可辨识的默认值。

    约束：
    - 不尝试从零构建“复杂字段结构”，仅在已知模板的 shape 上做定点修改；
    - 若输入存档缺少模板结构体（ConfigID=1077936130），则直接抛错。
    """
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))
    if not str(struct_name).strip():
        raise ValueError("struct_name 不能为空")
    rng = random.Random(int(seed)) if seed is not None else None

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    payload_root = raw_dump_object.get("4")
    if not isinstance(payload_root, dict):
        raise ValueError("DLL dump-json 缺少根字段 '4'（期望为 dict）。")

    node_graph_root = _ensure_path_dict(payload_root, "10")
    struct_blob_list = _ensure_path_list_allow_scalar(node_graph_root, "6")
    if not struct_blob_list:
        raise ValueError("当前存档未包含任何结构体定义 blob（root4/10/6 为空）。")

    existing_ref_ids = _collect_existing_struct_ref_ids(struct_blob_list)
    next_ref_id = (max(existing_ref_ids) + 1) if existing_ref_ids else 1073741825
    new_struct_field_ref_id = int(next_ref_id)
    next_ref_id += 1
    # 模板里结构体列表字段通常包含 2 个 item；这里按模板 item 数动态分配
    new_struct_list_item_ref_ids: List[int] = []

    existing_struct_ids: List[int] = []
    template_blob_text: str | None = None
    for entry in struct_blob_list:
        if not isinstance(entry, str) or not entry.startswith("<binary_data>"):
            continue
        blob_bytes = parse_binary_data_hex_text(entry)
        struct_id_int = _try_decode_struct_id_from_blob_bytes(blob_bytes)
        if not isinstance(struct_id_int, int):
            continue
        existing_struct_ids.append(int(struct_id_int))
        if int(struct_id_int) == 1077936130:
            template_blob_text = entry

    if template_blob_text is None:
        raise ValueError("未找到 struct_all_supported (ConfigID=1077936130) 作为模板，无法创建全类型测试结构体。")

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

    # struct_message.field_503 看起来是一个“内部结构体类型 id”，需避免与现有结构体重复
    existing_internal_ids = _collect_existing_struct_internal_ids(struct_blob_list)
    next_internal_id = (max(existing_internal_ids) + 2) if existing_internal_ids else 2
    new_struct_internal_id = int(next_internal_id)

    # 结构体系统：每个结构体通常需要对应的“拼装/拆分/修改结构体”节点定义（root4/10/2）
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

    # 先计算“结构体列表字段”模板 item 数，以便分配 ref_id（避免与模板重复）
    template_struct_message = _get_struct_message_from_decoded_blob(new_decoded, "field_1")
    struct_list_entry, _struct_list_kind, struct_list_field_msg = _find_field_message(
        template_struct_message, "结构体列表字段"
    )
    _type_key, struct_list_container, _inner = _get_type_value_container(struct_list_field_msg)
    struct_list_container_msg = struct_list_container.get("message")
    if not isinstance(struct_list_container_msg, dict):
        raise ValueError("结构体列表字段缺少 message")
    template_items = struct_list_container_msg.get("field_1")
    if not isinstance(template_items, list):
        raise ValueError("结构体列表字段 message.field_1 不是 list")
    for _ in template_items:
        new_struct_list_item_ref_ids.append(int(next_ref_id))
        next_ref_id += 1

    # 对 field_1 / field_2 两份结构体描述同时改名/改 ID，并定点修改默认值
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

        # ---- 修复：克隆时必须为结构体引用生成新的 ugc_ref_id_int，避免与模板重复（游戏侧可能校验唯一性）
        struct_ref_entry, struct_ref_kind, struct_ref_field = _find_field_message(struct_message, "结构体字段")
        _type_key, struct_ref_container, _inner = _get_type_value_container(struct_ref_field)
        struct_ref_msg = struct_ref_container.get("message")
        if not isinstance(struct_ref_msg, dict):
            raise ValueError("结构体字段缺少 message")
        field_502 = struct_ref_msg.get("field_502")
        if not isinstance(field_502, dict):
            raise ValueError("结构体字段缺少 field_502")
        field_502_msg = field_502.get("message")
        if not isinstance(field_502_msg, dict):
            raise ValueError("结构体字段缺少 field_502.message")
        field_4 = field_502_msg.get("field_4")
        if not isinstance(field_4, dict):
            raise ValueError("结构体字段缺少 field_4")
        _set_int_node(field_4, int(new_struct_field_ref_id))
        _commit_field_entry(struct_ref_entry, struct_ref_kind, struct_ref_field)

        struct_list_entry, struct_list_kind, struct_list_field = _find_field_message(struct_message, "结构体列表字段")
        _type_key, struct_list_container, _inner = _get_type_value_container(struct_list_field)
        struct_list_container_msg = struct_list_container.get("message")
        if not isinstance(struct_list_container_msg, dict):
            raise ValueError("结构体列表字段缺少 message")
        items = struct_list_container_msg.get("field_1")
        if not isinstance(items, list):
            raise ValueError("结构体列表字段 message.field_1 不是 list")
        if len(items) != len(new_struct_list_item_ref_ids):
            raise ValueError("结构体列表字段模板条目数与 ref_id 分配数不一致")
        for item, ref_id in zip(items, new_struct_list_item_ref_ids):
            if not isinstance(item, dict):
                raise ValueError("结构体列表字段条目不是 dict")
            item_msg = item.get("message")
            if not isinstance(item_msg, dict):
                raise ValueError("结构体列表字段条目缺少 message")
            field_35 = item_msg.get("field_35")
            if not isinstance(field_35, dict):
                raise ValueError("结构体列表字段条目缺少 field_35")
            field_35_msg = field_35.get("message")
            if not isinstance(field_35_msg, dict):
                raise ValueError("结构体列表字段条目缺少 field_35.message")
            field_502 = field_35_msg.get("field_502")
            if not isinstance(field_502, dict):
                raise ValueError("结构体列表字段条目缺少 field_35.message.field_502")
            field_502_msg = field_502.get("message")
            if not isinstance(field_502_msg, dict):
                raise ValueError("结构体列表字段条目缺少 field_502.message")
            field_4 = field_502_msg.get("field_4")
            if not isinstance(field_4, dict):
                raise ValueError("结构体列表字段条目缺少 field_4")
            _set_int_node(field_4, int(ref_id))
        _commit_field_entry(struct_list_entry, struct_list_kind, struct_list_field)

        # ---- 写入一组跨类型的可辨识默认值（覆盖标量/列表/字典/向量等）
        # int（可随机）
        int_entry, int_entry_kind, int_field = _find_field_message(struct_message, "整数字段")
        _, int_container, _ = _get_type_value_container(int_field)
        int_value = int(rng.randint(0, 2000000000)) if rng is not None else 12345
        _set_default_int_in_message_container(int_container, int_value)
        _commit_field_entry(int_entry, int_entry_kind, int_field)

        # bool（可随机；True 用 message.field_1=int(1)）
        bool_entry, bool_entry_kind, bool_field = _find_field_message(struct_message, "布尔值字段")
        _, bool_container, _ = _get_type_value_container(bool_field)
        bool_value = bool(rng.getrandbits(1)) if rng is not None else True
        _set_default_bool_node(bool_container, bool_value)
        _commit_field_entry(bool_entry, bool_entry_kind, bool_field)

        # float（可随机）
        float_entry, float_entry_kind, float_field = _find_field_message(struct_message, "浮点数字段")
        _, float_container, _ = _get_type_value_container(float_field)
        float_value = float(round(rng.random() * 1000.0, 3)) if rng is not None else 9.87
        _set_default_float_in_message_container(float_container, float_value)
        _commit_field_entry(float_entry, float_entry_kind, float_field)

        # string（可随机；不改配置ID等敏感字段）
        str_entry, str_entry_kind, str_field = _find_field_message(struct_message, "字符串字段")
        _, str_container, _ = _get_type_value_container(str_field)
        text_value = f"写回_随机_{int(seed) if seed is not None else 'fixed'}_{int(rng.randint(1000, 9999)) if rng is not None else 0}" if rng is not None else "写回_字符串_测试"
        _set_default_string_node(str_container, text_value)
        _commit_field_entry(str_entry, str_entry_kind, str_field)

        # vector3（可随机）
        vec_entry, vec_entry_kind, vec_field = _find_field_message(struct_message, "三维向量字段")
        _, vec_container, _ = _get_type_value_container(vec_field)
        if rng is None:
            _set_default_vector3_in_message_container(vec_container, 1.1, 2.2, 3.3)
        else:
            _set_default_vector3_in_message_container(
                vec_container,
                round(rng.uniform(-50.0, 50.0), 3),
                round(rng.uniform(-50.0, 50.0), 3),
                round(rng.uniform(-50.0, 50.0), 3),
            )
        _commit_field_entry(vec_entry, vec_entry_kind, vec_field)

        # entity list
        # 模板里会出现 field_0=0 的“非法 message”占位（等价于原始 bytes `00 00`）；若不处理，encoder 会因 field_number=0 抛错。
        # 这里不改语义，只做等价归一化：把该形态转为 raw_hex=0000。
        _sanitize_decoded_invalid_field0_message_nodes(struct_message)

        # dict<string,bool>（key/value 可随机；模板只有 2 条目，保持 2）
        dict_entry, dict_entry_kind, dict_field = _find_field_message(struct_message, "字典字段")
        _, dict_container, _ = _get_type_value_container(dict_field)
        if rng is None:
            dict_keys = ["写回KeyA", "写回KeyB"]
            dict_values = [True, False]
        else:
            dict_keys = [f"Key_{rng.randint(1000, 9999)}", f"Key_{rng.randint(1000, 9999)}"]
            dict_values = [bool(rng.getrandbits(1)), bool(rng.getrandbits(1))]
        _set_default_dict_string_bool(dict_container, dict_keys, dict_values)
        _commit_field_entry(dict_entry, dict_entry_kind, dict_field)

        # 下面这些字段在模板里是“引用/枚举/资源ID”类，游戏侧很可能会做严格校验（存在性/合法性）。
        # 为了提高导入成功率，默认保持模板原值不变，只验证我们在纯数据字段上的写回能力。
        # - GUID字段 / GUID列表字段
        # - 阵营字段 / 阵营列表字段
        # - 配置ID列表字段 / 元件ID列表字段
        # 若需要测试这些字段，请提供已确认存在的有效 ID（或从模板值集合中挑选）。

        # packed int list（可随机）
        int_list_entry, int_list_entry_kind, int_list_field = _find_field_message(struct_message, "整数列表字段")
        _, int_list_container, _ = _get_type_value_container(int_list_field)
        int_list_values = [7, 8, 9, 10] if rng is None else [int(rng.randint(0, 99999)) for _ in range(6)]
        _set_default_packed_varint_list(int_list_container, int_list_values)
        _commit_field_entry(int_list_entry, int_list_entry_kind, int_list_field)

        # packed bool list（可随机）
        bool_list_entry, bool_list_entry_kind, bool_list_field = _find_field_message(struct_message, "布尔值列表字段")
        _, bool_list_container, _ = _get_type_value_container(bool_list_field)
        bool_list_values = [1, 0, 1] if rng is None else [int(bool(rng.getrandbits(1))) for _ in range(7)]
        _set_default_packed_varint_list(bool_list_container, bool_list_values)
        _commit_field_entry(bool_list_entry, bool_list_entry_kind, bool_list_field)

        # float list（可随机，写回 stride8）
        float_list_entry, float_list_entry_kind, float_list_field = _find_field_message(struct_message, "浮点数列表字段")
        _, float_list_container, _ = _get_type_value_container(float_list_field)
        float_list_values = [0.12, 3.14, 2.72] if rng is None else [round(rng.uniform(-100.0, 100.0), 3) for _ in range(5)]
        _set_default_float_list(float_list_container, float_list_values)
        _commit_field_entry(float_list_entry, float_list_entry_kind, float_list_field)

        # string list（可随机；raw_hex 内部是一个 message：field_1 repeated string）
        str_list_entry, str_list_entry_kind, str_list_field = _find_field_message(struct_message, "字符串列表字段")
        _, str_list_container, _ = _get_type_value_container(str_list_field)
        str_list_values = ["写回A", "写回B", "写回C"] if rng is None else [f"S_{rng.randint(100,999)}" for _ in range(5)]
        _set_default_string_list_raw(str_list_container, str_list_values)
        _commit_field_entry(str_list_entry, str_list_entry_kind, str_list_field)

        # GUID/阵营/配置ID/元件ID 相关字段保持模板值，不做修改

    # 将新的结构体定义 blob 写回 root4/10/6（列表）
    new_blob_dump_json = _decoded_field_map_to_dump_json_message(new_decoded)
    new_blob_bytes = encode_message(new_blob_dump_json)
    struct_blob_list.append(format_binary_data_hex_text(new_blob_bytes))

    _ensure_struct_visible_in_tabs(
        payload_root,
        struct_id_int=int(struct_id),
        template_struct_id_int=1077936130,
    )

    # 同步追加 3 个结构体节点定义（拼装/拆分/修改结构体），并把模板 struct_id=1077936130 替换为新 struct_id
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
        # node_type_id 必须全局唯一：否则导入时可能出现节点定义冲突
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
        "preset": "all-types-test",
        "struct_ref_id_int": int(new_struct_field_ref_id),
        "struct_list_ref_id_ints": [int(v) for v in new_struct_list_item_ref_ids],
        "struct_blob_count_before": len(struct_blob_list) - 1,
        "struct_blob_count_after": len(struct_blob_list),
    }


