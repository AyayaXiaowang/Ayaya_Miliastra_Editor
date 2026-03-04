from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Sequence

import ugc_file_tools.struct_def_writeback as struct_writer
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message, parse_binary_data_hex_text


def _has_struct_node_defs(node_defs: Sequence[Any], struct_id: int) -> bool:
    wanted_names = {"拼装结构体", "拆分结构体", "修改结构体"}
    pat = struct_writer._encode_varint(int(struct_id))
    hits: Dict[str, int] = {name: 0 for name in wanted_names}

    for entry in node_defs:
        if not isinstance(entry, dict):
            continue
        inner = entry.get("1")
        if not isinstance(inner, dict):
            continue
        name_raw = inner.get("200")
        name = str(name_raw) if isinstance(name_raw, str) else struct_writer._get_utf8_from_text_node(name_raw)
        if name not in wanted_names:
            continue

        def count_int_occurrences(x: object, wanted: int) -> int:
            if isinstance(x, dict):
                total = 0
                for v in x.values():
                    total += count_int_occurrences(v, wanted)
                return total
            if isinstance(x, list):
                total = 0
                for v in x:
                    total += count_int_occurrences(v, wanted)
                return total
            if isinstance(x, int) and int(x) == int(wanted):
                return 1
            return 0

        binary_texts = struct_writer._collect_all_binary_data_texts(inner)
        count = 0
        for text in binary_texts:
            raw = parse_binary_data_hex_text(text)
            count += raw.count(pat)
        count += count_int_occurrences(inner, int(struct_id))
        if count > 0:
            hits[str(name)] = int(count)

    return all(hits.get(name, 0) > 0 for name in wanted_names)


def _choose_template_struct_id_for_node_defs(
    *,
    node_defs: Sequence[Any],
    existing_struct_ids: Sequence[int] | None,
) -> int:
    # 优先使用 struct_all_supported，其次使用空结构体（历史基底常见）
    for sid in (1077936130, 1077936129):
        if _has_struct_node_defs(node_defs, sid):
            return int(sid)

    # 否则：从当前存档已存在的结构体定义里挑一个“确实有三类结构体节点定义”的 struct_id 作为模板。
    # 说明：部分存档不会包含 6129/6130，但会包含其它 struct_id 的结构体节点定义模板（可用于克隆替换）。
    candidates: List[int] = []
    if existing_struct_ids is not None:
        for sid in existing_struct_ids:
            if isinstance(sid, int):
                candidates.append(int(sid))

    for sid in sorted(set(candidates)):
        if _has_struct_node_defs(node_defs, int(sid)):
            return int(sid)

    raise ValueError(
        "当前存档缺少可用的结构体节点定义模板（未找到可用于克隆的 拼装/拆分/修改结构体 节点定义）。"
    )


def choose_template_struct_id_for_node_defs(
    *,
    node_defs: Sequence[Any],
    existing_struct_ids: Sequence[int] | None,
) -> int:
    """Public API (no leading underscores)."""
    return _choose_template_struct_id_for_node_defs(node_defs=node_defs, existing_struct_ids=existing_struct_ids)


def _ensure_struct_node_defs(
    *,
    node_defs: List[Any],
    struct_id: int,
    template_struct_id: int,
    next_node_type_id: int,
) -> int:
    if _has_struct_node_defs(node_defs, int(struct_id)):
        return int(next_node_type_id)

    template_node_defs = struct_writer._find_template_struct_node_defs(node_defs, template_struct_id=int(template_struct_id))
    template_pat = struct_writer._encode_varint(int(template_struct_id))
    new_pat = struct_writer._encode_varint(int(struct_id))

    for name in ("拼装结构体", "拆分结构体", "修改结构体"):
        template_entry = template_node_defs[name]
        old_node_type_id = struct_writer._extract_node_type_id_from_node_def(template_entry)
        if old_node_type_id is None:
            raise ValueError(f"模板节点定义缺少 node_type_id：{name}")
        new_node_type_id = int(next_node_type_id)
        next_node_type_id += 1

        cloned = json.loads(json.dumps(template_entry, ensure_ascii=False))
        struct_writer._replace_binary_data_bytes_in_object(cloned, old_bytes=template_pat, new_bytes=new_pat)
        struct_writer._replace_int_values_in_object(cloned, old_value=int(template_struct_id), new_value=int(struct_id))
        struct_writer._replace_int_values_in_object(cloned, old_value=int(old_node_type_id), new_value=int(new_node_type_id))
        old_node_type_pat = struct_writer._encode_varint(int(old_node_type_id))
        new_node_type_pat = struct_writer._encode_varint(int(new_node_type_id))
        if len(old_node_type_pat) == len(new_node_type_pat):
            struct_writer._replace_binary_data_bytes_in_object(cloned, old_bytes=old_node_type_pat, new_bytes=new_node_type_pat)
        node_defs.append(cloned)

    return int(next_node_type_id)


def ensure_struct_node_defs(
    *,
    node_defs: List[Any],
    struct_id: int,
    template_struct_id: int,
    next_node_type_id: int,
) -> int:
    """Public API (no leading underscores)."""
    return _ensure_struct_node_defs(
        node_defs=node_defs,
        struct_id=struct_id,
        template_struct_id=template_struct_id,
        next_node_type_id=next_node_type_id,
    )

