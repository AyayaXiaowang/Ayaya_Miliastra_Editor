from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

from engine.resources.custom_variable_file_refs import normalize_custom_variable_file_refs
from ugc_file_tools.gia_export.templates import build_component_template_root_id_int
from ugc_file_tools.project_archive_importer.custom_variable_writeback import (
    load_level_variable_payloads_by_file_id,
    upsert_custom_variables_from_level_variable_payloads,
)
from ugc_file_tools.project_archive_importer.template_decorations_scanner import (
    TemplateDecorationRecord,
    apply_template_decorations_writeback_to_payload_root,
    collect_parent_instance_ids_by_template_id_from_payload_root,
    extract_template_decoration_records_from_template_obj,
)
from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import binary_data_text_to_numeric_message
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message
from ugc_file_tools.node_graph_writeback.gil_dump import dump_gil_to_raw_json_object, get_payload_root
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


@dataclass(frozen=True, slots=True)
class TemplatesImportOptions:
    mode: str = "overwrite"  # "merge" | "overwrite"
    skip_placeholders: bool = True
    include_template_json_files: List[Path] | None = None  # 仅写回指定模板文件（绝对路径，指向项目存档内 元件库/*.json）
    # 同名冲突策略（导出中心 selection-json 透传；按 template_json_file 精确匹配）。
    # item schema（dict）：
    # - template_json_file: str（绝对路径）
    # - action: "overwrite" | "add" | "skip"
    # - new_template_name: str（仅 action="add" 时需要）
    template_conflict_resolutions: List[Dict[str, str]] | None = None


_SEED_TEMPLATE_EXEMPLARS_CACHE: Tuple[Dict[str, Any], Dict[int, Dict[str, Any]]] | None = None
_SEED_ROOT8_INSTANCE_EXEMPLARS_CACHE: Tuple[Dict[str, Any], Dict[int, Dict[str, Any]]] | None = None


def _load_seed_template_exemplars() -> Tuple[Dict[str, Any], Dict[int, Dict[str, Any]]]:
    """
    为“极空 base .gil / 空模板段”提供可克隆样本：
    - 当目标 `.gil` 的 root4/4/1 为空时，新增模板无法从目标存档内找到可克隆 entry；
    - 此时使用 ugc_file_tools/builtin_resources 内的 seed `.gil` 提供最小样本 entry 形态（仅作为 clone 原型，不会把 seed 模板本体写入目标）。
    """
    global _SEED_TEMPLATE_EXEMPLARS_CACHE
    if _SEED_TEMPLATE_EXEMPLARS_CACHE is not None:
        return _SEED_TEMPLATE_EXEMPLARS_CACHE

    from ugc_file_tools.repo_paths import ugc_file_tools_builtin_resources_root

    ugc_root = ugc_file_tools_builtin_resources_root()
    # 重要：这里的 seed 用于“元件库模板(root4/4/1)”克隆原型。
    # 经验：空存档通常只带 UI 模板(type_code=1000000/1000001 等)，不带“物件/元件模板”；
    # 若直接拿 UI 模板当原型，再强行改 type_code，会导致模板结构不匹配（常见表现：transform/装饰物等字段缺失或退化）。
    # 因此这里优先使用包含“空模型元件(type_code=10005018)”的 seed（`save/test2.gil`），作为通用物件模板原型来源。
    seed_gil_path = (ugc_root / "seeds" / "template_instance_exemplars.gil").resolve()
    if not seed_gil_path.is_file():
        raise FileNotFoundError(str(seed_gil_path))

    seed_dump = dump_gil_to_raw_json_object(seed_gil_path)
    seed_root = get_payload_root(seed_dump)
    seed_template_section = seed_root.get("4")
    if not isinstance(seed_template_section, dict):
        raise ValueError("seed gil 缺少模板段 root4/4（期望为 dict）。")

    seed_entries = seed_template_section.get("1")
    if isinstance(seed_entries, dict):
        seed_entries = [seed_entries]
    if seed_entries is None:
        seed_entries = []
    if not isinstance(seed_entries, list):
        raise ValueError("seed gil 字段 root4/4/1 结构异常（期望为 list/dict/None）。")

    any_exemplar: Optional[Dict[str, Any]] = None
    preferred_any_exemplar: Optional[Dict[str, Any]] = None
    exemplar_by_type_code: Dict[int, Dict[str, Any]] = {}
    for entry in seed_entries:
        if not isinstance(entry, dict):
            continue
        template_id_int = _extract_first_int_from_repeated_field(entry, "1")
        if not isinstance(template_id_int, int):
            continue
        if any_exemplar is None:
            any_exemplar = entry
        type_code_int = _extract_first_int_from_repeated_field(entry, "2")
        if isinstance(type_code_int, int) and int(type_code_int) not in exemplar_by_type_code:
            exemplar_by_type_code[int(type_code_int)] = entry
        # 优先选“空模型元件”(10005018)作为通用物件模板原型：其字段形态更贴近元件/物件模板，而不是 UI 控件模板。
        if preferred_any_exemplar is None and isinstance(type_code_int, int) and int(type_code_int) == 10005018:
            preferred_any_exemplar = entry

    if any_exemplar is None:
        raise RuntimeError("seed gil 的 root4/4/1 未找到任何可克隆的模板 entry（内部错误）。")
    if preferred_any_exemplar is not None:
        any_exemplar = preferred_any_exemplar

    _SEED_TEMPLATE_EXEMPLARS_CACHE = (any_exemplar, dict(exemplar_by_type_code))
    return _SEED_TEMPLATE_EXEMPLARS_CACHE


def _load_seed_root8_instance_exemplars() -> Tuple[Dict[str, Any], Dict[int, Dict[str, Any]]]:
    """
    为“模板装饰物(root27) 写回需要父实例(root8)”提供可克隆样本：
    - 观测：模板 decorations 的挂载（root27.2）父实例可能存在于 root8.1（record['2']['1']=template_id）。
    - 空/极简 base 常见 root8 为空；此时需要自举生成 root8 父实例，否则 decorations 在编辑器内不可见。
    """
    global _SEED_ROOT8_INSTANCE_EXEMPLARS_CACHE
    if _SEED_ROOT8_INSTANCE_EXEMPLARS_CACHE is not None:
        return _SEED_ROOT8_INSTANCE_EXEMPLARS_CACHE

    from ugc_file_tools.repo_paths import ugc_file_tools_builtin_resources_root

    ugc_root = ugc_file_tools_builtin_resources_root()
    seed_gil_path = (ugc_root / "seeds" / "template_instance_exemplars.gil").resolve()
    if not seed_gil_path.is_file():
        raise FileNotFoundError(str(seed_gil_path))

    seed_dump = dump_gil_to_raw_json_object(seed_gil_path)
    seed_root = get_payload_root(seed_dump)
    root8_value = seed_root.get("8")
    root8_msg: Dict[str, Any]
    if isinstance(root8_value, dict):
        root8_msg = root8_value
    elif isinstance(root8_value, str) and root8_value.startswith("<binary_data>"):
        msg = binary_data_text_to_numeric_message(root8_value, max_depth=32)
        if not isinstance(msg, dict):
            raise TypeError(f"binary_data_text_to_numeric_message(root8) returned {type(msg).__name__}")
        root8_msg = dict(msg)
    else:
        raise ValueError("seed gil 缺少 root8 段（期望为 dict 或 <binary_data> message）。")

    entries0 = root8_msg.get("1")
    if isinstance(entries0, dict):
        entries0 = [entries0]
    if entries0 is None:
        entries0 = []
    if not isinstance(entries0, list):
        raise ValueError("seed gil 字段 root8/1 结构异常（期望为 list/dict/None）。")

    any_exemplar: Optional[Dict[str, Any]] = None
    preferred_any_exemplar: Optional[Dict[str, Any]] = None
    exemplar_by_type_code: Dict[int, Dict[str, Any]] = {}
    for entry in entries0:
        if not isinstance(entry, dict):
            continue
        if any_exemplar is None:
            any_exemplar = entry
        v8 = entry.get("8")
        if isinstance(v8, int) and int(v8) not in exemplar_by_type_code:
            exemplar_by_type_code[int(v8)] = entry
        # 同上：优先选“空模型元件”父实例样本作为 unknown type 的 fallback 原型。
        if preferred_any_exemplar is None and isinstance(v8, int) and int(v8) == 10005018:
            preferred_any_exemplar = entry

    if any_exemplar is None:
        raise RuntimeError("seed gil 的 root8/1 未找到任何可克隆的实例 entry（内部错误）。")
    if preferred_any_exemplar is not None:
        any_exemplar = preferred_any_exemplar

    _SEED_ROOT8_INSTANCE_EXEMPLARS_CACHE = (any_exemplar, dict(exemplar_by_type_code))
    return _SEED_ROOT8_INSTANCE_EXEMPLARS_CACHE


# === preview transform（模板/父实例坐标） ===
# 观测：官方编辑器的“元件挂装饰物”样例中，模板 entry 与 root8 父实例都带有 transform(pos/rot/scale)；
# 若新增模板/自举父实例时不写入/退化为 0，可能表现为“都在原点/不可见/重叠在一起”。
_DEFAULT_PREVIEW_ANCHOR_POS: Tuple[float, float, float] = (
    8.000175476074219,
    3.19976806640625,
    -6.199999809265137,
)
_DEFAULT_PREVIEW_STEP_POS: Tuple[float, float, float] = (
    0.43920135498046875,
    0.0,
    -4.842107772827148,
)


def _build_vec3_message_omit_zeros(x: float, y: float, z: float) -> Dict[str, float]:
    out: Dict[str, float] = {}
    fx = float(x)
    fy = float(y)
    fz = float(z)
    if fx != 0.0:
        out["1"] = fx
    if fy != 0.0:
        out["2"] = fy
    if fz != 0.0:
        out["3"] = fz
    return out


def _compute_default_preview_position(index: int) -> Tuple[float, float, float]:
    i = int(index)
    bx, by, bz = _DEFAULT_PREVIEW_ANCHOR_POS
    sx, sy, sz = _DEFAULT_PREVIEW_STEP_POS
    return (float(bx + sx * i), float(by + sy * i), float(bz + sz * i))


def _upsert_transform_position_in_sections(sections: List[Any], *, pos: Tuple[float, float, float]) -> None:
    """
    对齐真源样例：在 section_list 中确保存在 section_id=1 的 transform 段，并写入 pos(vec3)。

    约定：
    - item['1'] == 1
    - item['11'] 为 transform 容器，形如：{1: vec3(pos), 2: bytes(rot), 3: vec3(scale), 501: guid}
    """
    empty_bytes = "<binary_data> "
    default_scale = {"1": 1.0, "2": 1.0, "3": 1.0}
    default_guid = 4294967295

    container: Optional[Dict[str, Any]] = None
    for item in list(sections):
        if isinstance(item, dict) and item.get("1") == 1:
            v11 = item.get("11")
            if isinstance(v11, dict):
                container = v11
            elif v11 is None:
                container = {}
                item["11"] = container
            elif isinstance(v11, str) and v11.startswith("<binary_data>"):
                msg = binary_data_text_to_numeric_message(v11, max_depth=16)
                if isinstance(msg, dict):
                    container = dict(msg)
                else:
                    container = {}
                item["11"] = container
            else:
                container = {}
                item["11"] = container
            break

    if container is None:
        container = {"2": empty_bytes, "3": dict(default_scale), "501": int(default_guid)}
        sections.insert(0, {"1": 1, "11": container})

    x, y, z = pos
    container["1"] = _build_vec3_message_omit_zeros(x, y, z)
    if "2" not in container:
        container["2"] = empty_bytes
    if "3" not in container:
        container["3"] = dict(default_scale)
    if "501" not in container:
        container["501"] = int(default_guid)


def _coerce_section_message_to_dict(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.startswith("<binary_data>"):
        msg = binary_data_text_to_numeric_message(value, max_depth=32)
        if not isinstance(msg, dict):
            raise TypeError(f"binary_data_text_to_numeric_message returned {type(msg).__name__}")
        return dict(msg)
    return None


def _extract_template_id_int_from_instance_record(record: Dict[str, Any]) -> Optional[int]:
    v2 = record.get("2")
    if isinstance(v2, dict):
        v21 = v2.get("1")
        if isinstance(v21, int):
            return int(v21)
    if isinstance(v2, list) and v2 and isinstance(v2[0], dict) and isinstance(v2[0].get("1"), int):
        return int(cast(int, v2[0].get("1")))
    return None


def _extract_instance_id_int_from_instance_record(record: Dict[str, Any]) -> Optional[int]:
    v1 = record.get("1")
    if isinstance(v1, int):
        return int(v1)
    if isinstance(v1, list) and v1 and isinstance(v1[0], int):
        return int(v1[0])
    return None


def _upsert_root8_instance_meta_name(meta_list: List[Any], name: str) -> None:
    name = str(name or "").strip()
    if name == "":
        return
    for idx, item in enumerate(list(meta_list)):
        if isinstance(item, dict) and item.get("1") == 1:
            item["11"] = {"1": str(name)}
            return
        if isinstance(item, str) and item.startswith("<binary_data>"):
            msg = binary_data_text_to_numeric_message(item, max_depth=16)
            if isinstance(msg, dict) and msg.get("1") == 1:
                msg2 = dict(msg)
                msg2["11"] = {"1": str(name)}
                meta_list[idx] = msg2
                return
    meta_list.insert(0, {"1": 1, "11": {"1": str(name)}})


def _clear_root8_instance_meta40_field50(meta_list: List[Any]) -> None:
    """
    清空父实例 meta40.field50（避免克隆 seed 时夹带旧的 attachment_id 引用）。
    """
    empty_bytes = "<binary_data> "
    for idx, item in enumerate(list(meta_list)):
        if isinstance(item, dict) and item.get("1") == 40:
            item["50"] = empty_bytes
            return
        if isinstance(item, str) and item.startswith("<binary_data>"):
            msg = binary_data_text_to_numeric_message(item, max_depth=16)
            if isinstance(msg, dict) and msg.get("1") == 40:
                msg2 = dict(msg)
                msg2["50"] = empty_bytes
                meta_list[idx] = msg2
                return
    meta_list.append({"1": 40, "50": empty_bytes})


def _ensure_root8_parent_instances_for_template_decorations(
    *,
    payload_root: Dict[str, Any],
    template_info_by_id_int: Dict[int, Dict[str, Any]],
    decorated_template_id_ints: List[int],
) -> Dict[str, Any]:
    """
    若 base `.gil` 中不存在某个 decorated template 的父实例（root5/root8），则自举生成一个 root8 父实例：
    - 优先令 record['1'](instance_id) == template_id_int（对齐观测到的“元件挂装饰物”真源样例口径）
    - record['2']['1'] = template_id_int
    - record['8'] = template_type_code（尽量对齐）
    - meta(id=1) 名称对齐 template name
    - meta(id=40).field50 清空（后续由 decorations writer 写入 field501 stream）
    """
    wanted = sorted({int(x) for x in list(decorated_template_id_ints or []) if isinstance(x, int)})
    if not wanted:
        return {"bootstrapped": 0, "parents": []}

    parents_by_template = collect_parent_instance_ids_by_template_id_from_payload_root(payload_root)

    # used ids：root5 + root8 的 record['1']
    used_ids: set[int] = set()
    for sec_key in ("5", "8"):
        sec_msg = _coerce_section_message_to_dict(payload_root.get(sec_key))
        if sec_msg is None:
            continue
        payload_root[sec_key] = sec_msg
        recs = _ensure_path_list_allow_scalar(sec_msg, "1")
        for rec in recs:
            if not isinstance(rec, dict):
                continue
            iid = _extract_instance_id_int_from_instance_record(rec)
            if isinstance(iid, int):
                used_ids.add(int(iid))

    # 确保 root8 可写
    root8_msg = _coerce_section_message_to_dict(payload_root.get("8"))
    if root8_msg is None:
        root8_msg = {}
    payload_root["8"] = root8_msg
    root8_entries = _ensure_path_list_allow_scalar(root8_msg, "1")

    seed_any, seed_by_type = _load_seed_root8_instance_exemplars()

    # template_id -> template entry（用于同步模板 entry 的 preview transform 坐标）
    template_section = _ensure_path_dict(payload_root, "4")
    template_entries = _ensure_path_list_allow_scalar(template_section, "1")
    template_entry_by_id: Dict[int, Dict[str, Any]] = {}
    for entry in template_entries:
        if not isinstance(entry, dict):
            continue
        tid0 = _extract_first_int_from_repeated_field(entry, "1")
        if isinstance(tid0, int) and int(tid0) not in template_entry_by_id:
            template_entry_by_id[int(tid0)] = entry

    created: List[Dict[str, Any]] = []
    for tid in wanted:
        existing_parents = parents_by_template.get(int(tid)) or []
        if existing_parents:
            continue

        info = template_info_by_id_int.get(int(tid)) or {}
        tpl_name = str(info.get("name") or "").strip() or f"template_{int(tid)}"
        tpl_type_code = info.get("type_code")
        type_code_int = int(tpl_type_code) if isinstance(tpl_type_code, int) else None

        exemplar = seed_by_type.get(int(type_code_int)) if isinstance(type_code_int, int) else None
        if exemplar is None:
            exemplar = seed_any

        cloned = json.loads(json.dumps(exemplar, ensure_ascii=False))

        # allocate parent instance id（优先使用 template_id_int 作为 instance_id）
        parent_instance_id_int = int(tid)
        if int(parent_instance_id_int) in used_ids:
            # 极端场景：instance_id 冲突（base 内已有同 ID 的 root5/root8 record）。
            # 回退到稳定的 0x4040xxxx 段位 id（低 16 位 <0x8000），避免负数风险。
            fallback = build_component_template_root_id_int(template_key=f"decorations_root8_parent_instance:{int(tid)}")
            if int(fallback) in used_ids:
                raise ValueError(
                    "无法为模板 decorations 自举 root8 父实例：instance_id 冲突且回退 ID 也已被占用。"
                    f" template_id={int(tid)} candidate={int(parent_instance_id_int)} fallback={int(fallback)}"
                )
            parent_instance_id_int = int(fallback)
        used_ids.add(int(parent_instance_id_int))

        cloned["1"] = int(parent_instance_id_int)
        cloned["2"] = {"1": int(tid)}
        if isinstance(type_code_int, int):
            cloned["8"] = int(type_code_int)

        meta_list = _ensure_path_list_allow_scalar(cloned, "5")
        _upsert_root8_instance_meta_name(meta_list, tpl_name)
        _clear_root8_instance_meta40_field50(meta_list)

        # 同步写入 preview transform（模板 entry + root8 父实例）
        preview_pos = _compute_default_preview_position(len(created))
        sections6 = _ensure_path_list_allow_scalar(cloned, "6")
        _upsert_transform_position_in_sections(sections6, pos=preview_pos)
        tpl_entry = template_entry_by_id.get(int(tid))
        if isinstance(tpl_entry, dict):
            sections7 = _ensure_path_list_allow_scalar(tpl_entry, "7")
            _upsert_transform_position_in_sections(sections7, pos=preview_pos)

        root8_entries.append(cloned)
        created.append(
            {
                "template_id_int": int(tid),
                "parent_instance_id_int": int(parent_instance_id_int),
                "template_name": str(tpl_name),
                "template_type_code_int": int(type_code_int) if isinstance(type_code_int, int) else None,
                "preview_pos": {"x": float(preview_pos[0]), "y": float(preview_pos[1]), "z": float(preview_pos[2])},
            }
        )

    return {"bootstrapped": int(len(created)), "parents": list(created)}


def _ensure_path_dict(root: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = root.get(key)
    if isinstance(value, dict):
        return value
    if value is None:
        new_value: Dict[str, Any] = {}
        root[key] = new_value
        return new_value
    raise ValueError(f"expected dict at key={key!r}, got {type(value).__name__}")


def _ensure_path_list_allow_scalar(root: Dict[str, Any], key: str) -> List[Any]:
    """
    dump-json 中 repeated 字段在“只有 1 个元素”时可能被输出为标量（int/dict/str）。
    这里将其统一为 list 视图，便于追加/遍历。
    """
    value = root.get(key)
    if isinstance(value, list):
        return value
    if value is None:
        new_value: List[Any] = []
        root[key] = new_value
        return new_value
    new_value = [value]
    root[key] = new_value
    return new_value


def _coerce_section_message(value: Any, *, max_depth: int) -> Optional[Dict[str, Any]]:
    """
    dump-json 中某些 message 字段可能表现为：
    - dict：已解码
    - "<binary_data> ..."：message bytes（需二次解码）
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.startswith("<binary_data>"):
        msg = binary_data_text_to_numeric_message(value, max_depth=int(max_depth))
        if not isinstance(msg, dict):
            raise TypeError(f"binary_data_text_to_numeric_message returned {type(msg).__name__}")
        return dict(msg)
    if value is None:
        return None
    return None


_ROOT6_TEMPLATE_TABS_SEED_NODE_CACHE: Dict[str, Any] | None = None


def _load_seed_root6_template_tabs_index_node() -> Dict[str, Any]:
    """
    为缺失 root4/6“模板页签索引表”的 base `.gil` 提供 bootstrap：
    - 部分 base 仅包含页签节点壳，但未包含 kind=100/400 的模板索引表（可能需在官方编辑器内“打开元件库”后才会生成）。
    - 写回新增模板时需要一个可写入的索引表节点；否则新增模板在编辑器内可能不可见/不稳定。

    当前策略：从 `ugc_file_tools/builtin_resources/seeds/template_instance_exemplars.gil` 抽取一个符合观测形态的节点，
    并清空其索引表（sub3['5']），作为可追加的模板索引节点原型。
    """
    global _ROOT6_TEMPLATE_TABS_SEED_NODE_CACHE
    if _ROOT6_TEMPLATE_TABS_SEED_NODE_CACHE is not None:
        return json.loads(json.dumps(_ROOT6_TEMPLATE_TABS_SEED_NODE_CACHE, ensure_ascii=False))

    from ugc_file_tools.repo_paths import ugc_file_tools_builtin_resources_root

    ugc_root = ugc_file_tools_builtin_resources_root()
    seed_gil_path = (ugc_root / "seeds" / "template_instance_exemplars.gil").resolve()
    if not seed_gil_path.is_file():
        raise FileNotFoundError(str(seed_gil_path))

    seed_dump = dump_gil_to_raw_json_object(seed_gil_path)
    seed_root = get_payload_root(seed_dump)
    seed_root6_value = seed_root.get("6")
    seed_root6 = _coerce_section_message(seed_root6_value, max_depth=32)
    if not isinstance(seed_root6, dict):
        raise ValueError("seed gil 缺少 root4/6 段（期望为 dict）。")

    nodes0 = seed_root6.get("1")
    if isinstance(nodes0, dict):
        nodes0 = [nodes0]
    if nodes0 is None:
        nodes0 = []
    if not isinstance(nodes0, list):
        raise ValueError("seed gil 字段 root4/6/1 结构异常（期望为 list/dict/None）。")

    best: Optional[Dict[str, Any]] = None
    best_score: Optional[tuple[int, int, int]] = None
    for node in nodes0:
        if not isinstance(node, dict):
            continue
        sub3 = node.get("3")
        if not isinstance(sub3, dict):
            continue
        if str(sub3.get("1") or "").strip() != "未分类页签":
            continue
        list5_value = sub3.get("5")
        items = list5_value if isinstance(list5_value, list) else ([list5_value] if isinstance(list5_value, dict) else [])
        items2 = [
            it
            for it in items
            if isinstance(it, dict) and isinstance(it.get("1"), int) and isinstance(it.get("2"), int)
        ]
        if not items2:
            continue
        has_400 = any(int(cast(int, it["1"])) == 400 for it in items2)
        has_100 = any(int(cast(int, it["1"])) == 100 for it in items2)
        if not (has_400 or has_100):
            continue
        score = (1 if has_400 else 0, int(len(items2)), 1 if has_100 else 0)
        if best_score is None or score > best_score:
            best_score = score
            best = node

    if best is None:
        raise ValueError("seed gil 未找到可用的 root4/6 模板页签索引节点（未分类页签 + kind=100/400）。")

    cloned = json.loads(json.dumps(best, ensure_ascii=False))
    sub3c = cloned.get("3")
    if not isinstance(sub3c, dict):
        raise ValueError("seed root6 template tabs node missing sub3(dict)")
    sub3c["5"] = []

    _ROOT6_TEMPLATE_TABS_SEED_NODE_CACHE = dict(cloned)
    return json.loads(json.dumps(_ROOT6_TEMPLATE_TABS_SEED_NODE_CACHE, ensure_ascii=False))


def _patch_root6_template_tabs_for_touched_templates(
    *,
    payload_root: Dict[str, Any],
    touched_template_id_ints: List[int],
) -> Dict[str, Any]:
    """
    将本次写回触及到的模板 ID 注册到 root4/6（页签/索引段），对齐真源样本：
    - `root4/6/1[*].3.1 == '未分类页签'` 的节点里，`sub3['5']` 会包含模板索引条目：
      - {1: 400, 2: template_id_int}
      - {1: 100, 2: template_id_int}

    观察：新增模板时，真源会追加上述两条；否则模板在编辑器“元件页签/模板列表”里可能不可见或不稳定。
    """
    ids = [int(x) for x in list(touched_template_id_ints or [])]
    if not ids:
        return {"changed": False, "items_added": 0, "touched_templates": 0, "target_node_found": False}

    root6_value = payload_root.get("6")
    root6 = _coerce_section_message(root6_value, max_depth=32)
    if root6 is None:
        root6 = {}
        payload_root["6"] = root6
    else:
        payload_root["6"] = root6

    nodes = _ensure_path_list_allow_scalar(root6, "1")

    target_node: Optional[Dict[str, Any]] = None
    target_sub3: Optional[Dict[str, Any]] = None
    target_node_index: Optional[int] = None
    target_score: Optional[tuple[int, int, int]] = None
    for node_index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        sub3_value = node.get("3")
        if not isinstance(sub3_value, dict):
            continue
        if str(sub3_value.get("1") or "").strip() != "未分类页签":
            continue

        list5_value = sub3_value.get("5")
        items = list5_value if isinstance(list5_value, list) else ([list5_value] if isinstance(list5_value, dict) else [])
        items2 = [
            it
            for it in items
            if isinstance(it, dict) and isinstance(it.get("1"), int) and isinstance(it.get("2"), int)
        ]
        if not items2:
            continue

        has_400 = any(int(cast(int, it["1"])) == 400 for it in items2)
        has_100 = any(int(cast(int, it["1"])) == 100 for it in items2)
        if not (has_400 or has_100):
            continue

        # 选择策略：
        # - 优先命中包含 kind=400 的“模板索引表节点”（对齐观测样本 root4/6/1[15].3.5）
        # - 次选：list 更长的候选（更像索引表而不是“默认选择指针”）
        score = (1 if has_400 else 0, int(len(items2)), 1 if has_100 else 0)
        if target_score is None or score > target_score:
            target_score = score
            target_node = node
            target_sub3 = sub3_value
            target_node_index = int(node_index)

    if target_node is None or target_sub3 is None or target_node_index is None:
        seed_node = _load_seed_root6_template_tabs_index_node()
        nodes.append(seed_node)
        target_node = seed_node
        sub3_value = target_node.get("3")
        if not isinstance(sub3_value, dict):
            raise ValueError("bootstrap root6 template tabs node missing sub3(dict)")
        target_sub3 = sub3_value
        target_node_index = int(len(nodes) - 1)
        target_score = None

    list5 = _ensure_path_list_allow_scalar(target_sub3, "5")
    existing: set[tuple[int, int]] = set()
    for it in list5:
        if not isinstance(it, dict):
            continue
        k = it.get("1")
        v = it.get("2")
        if isinstance(k, int) and isinstance(v, int):
            existing.add((int(k), int(v)))

    added = 0
    for tid in ids:
        if (400, int(tid)) not in existing:
            list5.append({"1": 400, "2": int(tid)})
            existing.add((400, int(tid)))
            added += 1
        if (100, int(tid)) not in existing:
            list5.append({"1": 100, "2": int(tid)})
            existing.add((100, int(tid)))
            added += 1

    return {
        "changed": bool(added),
        "items_added": int(added),
        "touched_templates": len(ids),
        "target_node_found": True,
        "target_node_index": int(target_node_index),
        "target_node_score": list(target_score) if target_score is not None else None,
    }


def _extract_first_int_from_repeated_field(node: Dict[str, Any], key: str) -> Optional[int]:
    value = node.get(key)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, list) and value and isinstance(value[0], int):
        return int(value[0])
    return None


def _set_template_name(entry: Dict[str, Any], name: str) -> None:
    meta_list = _ensure_path_list_allow_scalar(entry, "6")

    name_item: Optional[Dict[str, Any]] = None
    for item in meta_list:
        if not isinstance(item, dict):
            continue
        if item.get("1") == 1:
            name_item = item
            break
    if name_item is None:
        name_item = {"1": 1, "11": {"1": str(name)}}
        meta_list.insert(0, name_item)
        return

    container = name_item.get("11")
    if not isinstance(container, dict):
        container = {}
        name_item["11"] = container
    container["1"] = str(name)


def _try_extract_template_name(entry: Dict[str, Any]) -> str:
    """
    从模板 entry（root4/4/1）抽取模板名（meta id=1）。

    经验结构（对齐 `_set_template_name`）：
    - entry['6'] 为 meta repeated
      - item['1']==1 的 item['11']['1'] 或 item['11'] 为名称字符串
    """
    meta_list = entry.get("6")
    if isinstance(meta_list, dict):
        meta_list = [meta_list]
    if meta_list is None:
        meta_list = []
    if not isinstance(meta_list, list):
        return ""
    for item in meta_list:
        if not isinstance(item, dict):
            continue
        if item.get("1") != 1:
            continue
        v11 = item.get("11")
        if isinstance(v11, str):
            return _unwrap_protobuf_field1_string_from_misdecoded_text(v11)
        if isinstance(v11, dict):
            name_val = v11.get("1")
            if isinstance(name_val, str):
                return _unwrap_protobuf_field1_string_from_misdecoded_text(name_val)
    return ""


def _unwrap_protobuf_field1_string_from_misdecoded_text(text: str) -> str:
    """
    兼容一种“dump-json 误判”为文本的嵌套 message 形态：
    - 期望原始 bytes 为：0x0A + <len(varint)> + <utf8_bytes>
      （即：field_1 的 wire-level 编码，通常来自嵌套 message）
    """
    s = str(text or "")
    if s == "":
        return ""
    raw = s.encode("utf-8")
    if not raw or raw[0] != 0x0A:
        return s.strip()

    from ugc_file_tools.gil_dump_codec.protobuf_like import decode_varint

    length, next_offset, ok = decode_varint(raw, 1, len(raw))
    if not ok:
        return s.strip()
    end = int(next_offset) + int(length)
    if end != len(raw):
        return s.strip()
    return raw[next_offset:end].decode("utf-8", errors="strict").strip()


def _normalize_template_conflict_resolutions(
    *,
    project_root: Path,
    template_files: List[Path],
    raw_conflicts: List[Dict[str, str]] | None,
) -> Dict[str, Dict[str, str]]:
    """
    解析并规范化 TemplatesImportOptions.template_conflict_resolutions（selection-json 透传）为：
      resolved_template_json_file(casefold) -> {"action": str, "new_template_name": str?}
    """
    if raw_conflicts is None:
        return {}
    if not isinstance(raw_conflicts, list):
        raise TypeError("template_conflict_resolutions must be list[dict[str,str]] or None")

    templates_dir = (Path(project_root).resolve() / "元件库").resolve()
    allowed_files_cf: set[str] = {str(Path(p).resolve()).casefold() for p in list(template_files or [])}

    out: Dict[str, Dict[str, str]] = {}
    for idx, item in enumerate(raw_conflicts):
        if not isinstance(item, dict):
            raise TypeError(f"template_conflict_resolutions[{idx}] must be dict")
        template_json_file = str(item.get("template_json_file") or "").strip()
        if template_json_file == "":
            raise ValueError(f"template_conflict_resolutions[{idx}].template_json_file 不能为空")
        p = Path(template_json_file)
        if not p.is_absolute():
            raise ValueError(
                f"template_conflict_resolutions[{idx}].template_json_file must be absolute path: {template_json_file!r}"
            )
        rp = p.resolve()
        if not rp.is_file():
            raise FileNotFoundError(str(rp))
        if rp.suffix.lower() != ".json":
            raise ValueError(f"template_conflict_resolutions[{idx}].template_json_file 不是 .json：{str(rp)}")
        if rp.name == "templates_index.json":
            raise ValueError(
                f"template_conflict_resolutions[{idx}].template_json_file 不能为 templates_index.json：{str(rp)}"
            )
        try:
            rp.relative_to(templates_dir)
        except ValueError:
            raise ValueError(
                f"template_conflict_resolutions[{idx}].template_json_file 必须位于项目存档 元件库/ 下："
                f"{str(rp)} (root={str(templates_dir)})"
            )
        k = str(rp).casefold()
        if k in out:
            raise ValueError(
                "template_conflict_resolutions 中存在重复 template_json_file（忽略大小写）："
                f"{str(rp)!r}"
            )
        if k not in allowed_files_cf:
            raise ValueError(
                "template_conflict_resolutions 中的 template_json_file 未在本次写回范围内："
                f"{str(rp)}"
            )

        action = str(item.get("action") or "").strip().lower()
        if action not in {"overwrite", "add", "skip"}:
            raise ValueError(
                f"template_conflict_resolutions[{idx}].action 仅支持 overwrite/add/skip，实际为：{action!r}"
            )
        new_template_name = str(item.get("new_template_name") or "").strip()
        if action == "add" and new_template_name == "":
            raise ValueError(f"template_conflict_resolutions[{idx}] action=add 时 new_template_name 不能为空")
        obj: Dict[str, str] = {"action": action}
        if action == "add":
            obj["new_template_name"] = new_template_name
        out[k] = obj

    return dict(out)


def _load_template_config_json(path: Path) -> Optional[Dict[str, Any]]:
    p = Path(path).resolve()
    if not p.is_file():
        return None
    obj = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        return None
    template_id = obj.get("template_id")
    if not isinstance(template_id, str) or template_id.strip() == "":
        return None
    return obj


def _iter_template_config_files(project_root: Path) -> List[Path]:
    directory = (Path(project_root) / "元件库").resolve()
    if not directory.is_dir():
        return []
    files: List[Path] = []
    for p in sorted(directory.glob("*.json"), key=lambda x: x.as_posix()):
        if p.name == "templates_index.json":
            continue
        files.append(p.resolve())
    return files


def _resolve_included_template_files(*, project_root: Path, include_files: List[Path]) -> List[Path]:
    templates_dir = (Path(project_root).resolve() / "元件库").resolve()
    if not templates_dir.is_dir():
        raise FileNotFoundError(f"项目存档缺少 元件库/ 目录：{str(templates_dir)}")

    out: List[Path] = []
    seen: set[str] = set()
    for idx, raw in enumerate(list(include_files)):
        p = Path(raw).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"include_template_json_files[{idx}] 不存在：{str(p)}")
        if p.suffix.lower() != ".json":
            raise ValueError(f"include_template_json_files[{idx}] 不是 .json：{str(p)}")
        if p.name == "templates_index.json":
            continue
        try:
            p.relative_to(templates_dir)
        except ValueError:
            raise ValueError(
                f"include_template_json_files[{idx}] 必须位于项目存档 元件库/ 下：{str(p)} (root={str(templates_dir)})"
            )
        k = str(p).casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(p)

    out.sort(key=lambda x: x.as_posix().casefold())
    return out


def _read_placeholder_flag(template_obj: Dict[str, Any]) -> bool:
    metadata = template_obj.get("metadata")
    if not isinstance(metadata, dict):
        return False
    ugc = metadata.get("ugc")
    if not isinstance(ugc, dict):
        return False
    return bool(ugc.get("placeholder"))


def _read_source_type_code_int(template_obj: Dict[str, Any]) -> Optional[int]:
    metadata = template_obj.get("metadata")
    if not isinstance(metadata, dict):
        return None
    ugc = metadata.get("ugc")
    if not isinstance(ugc, dict):
        return None
    value = ugc.get("source_template_type_code_int")
    if isinstance(value, int):
        return int(value)
    return None


_ALL_DIGITS_RE = re.compile(r"^\d+$")


def _bump_template_root_id_int(value: int) -> int:
    """
    当基于 crc32 的稳定 ID 发生冲突时，按 low16 顺序 bump，避免同一次写回中重复 ID。

    约束对齐 `project_export_templates_gia.py`：low16 固定在 0x4000~0x7FFF（<0x8000）。
    """
    base = int(value) & 0xFFFF0000
    low = int(value) & 0xFFFF
    low2 = int(low) + 1
    if low2 > 0x7FFF:
        low2 = 0x4000
    if low2 < 0x4000:
        low2 = 0x4000
    return int(base | int(low2))


def _coerce_template_id_int(*, template_id_text: str) -> int:
    """
    元件库模板 JSON 的 template_id 是字符串（允许非数字）。

    写回 `.gil` 时，模板段(root4/4)的 template_id 是 int：
    - 若 template_id_text 全数字：直接使用 int(template_id_text)
    - 否则：按 `.gia` 导出同口径，基于 template_id_text 构造稳定的 0x4040xxxx（low16<0x8000）ID
    """
    text = str(template_id_text or "").strip()
    if text == "":
        raise ValueError("template_id_text is empty")
    if _ALL_DIGITS_RE.match(text):
        return int(text)
    return int(build_component_template_root_id_int(template_key=text))


def import_templates_from_project_archive_to_gil(
    *,
    project_archive_path: Path,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    options: TemplatesImportOptions,
) -> Dict[str, Any]:
    project_path = Path(project_archive_path).resolve()
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not project_path.is_dir():
        raise FileNotFoundError(str(project_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    mode = str(options.mode or "").strip().lower()
    if mode not in {"merge", "overwrite"}:
        raise ValueError(f"unsupported mode: {mode!r}")

    template_files: List[Path]
    if options.include_template_json_files is not None:
        template_files = _resolve_included_template_files(
            project_root=project_path,
            include_files=list(options.include_template_json_files),
        )
    else:
        template_files = _iter_template_config_files(project_path)
    if not template_files:
        return {
            "project_archive": str(project_path),
            "input_gil": str(input_path),
            "output_gil": str(output_path),
            "mode": mode,
            "filtered_by_selection": bool(options.include_template_json_files is not None),
            "templates_total": 0,
            "templates_updated": [],
            "templates_added": [],
            "templates_skipped_existing": [],
            "templates_skipped_placeholders": [],
            "templates_skipped_invalid_files": [],
        }

    raw_dump_object = dump_gil_to_raw_json_object(input_path)
    payload_root = get_payload_root(raw_dump_object)

    conflict_action_by_file_cf = _normalize_template_conflict_resolutions(
        project_root=project_path,
        template_files=list(template_files),
        raw_conflicts=options.template_conflict_resolutions,
    )

    template_section = _ensure_path_dict(payload_root, "4")
    template_entries = _ensure_path_list_allow_scalar(template_section, "1")

    existing_by_id: Dict[int, Dict[str, Any]] = {}
    existing_by_name: Dict[str, Dict[str, Any]] = {}
    used_template_names_cf: set[str] = set()
    exemplar_by_type_code: Dict[int, Dict[str, Any]] = {}
    any_exemplar: Optional[Dict[str, Any]] = None

    for entry in template_entries:
        if not isinstance(entry, dict):
            continue
        template_id_int = _extract_first_int_from_repeated_field(entry, "1")
        if not isinstance(template_id_int, int):
            continue
        existing_by_id[int(template_id_int)] = entry
        name0 = _try_extract_template_name(entry)
        if name0 != "":
            used_template_names_cf.add(str(name0).casefold())
            if name0 not in existing_by_name:
                existing_by_name[str(name0)] = entry
        if any_exemplar is None:
            any_exemplar = entry
        type_code_int = _extract_first_int_from_repeated_field(entry, "2")
        if isinstance(type_code_int, int) and int(type_code_int) not in exemplar_by_type_code:
            exemplar_by_type_code[int(type_code_int)] = entry

    bootstrapped_seed_exemplar = False
    if any_exemplar is None:
        # 极空 base / 空模板段：从 seed `.gil` 取一个可克隆的模板 entry 作为原型（不写入 seed 本体）。
        seed_any, seed_by_type_code = _load_seed_template_exemplars()
        any_exemplar = seed_any
        exemplar_by_type_code = dict(seed_by_type_code)
        bootstrapped_seed_exemplar = True

    used_template_id_ints: set[int] = set(existing_by_id.keys())

    templates_updated: List[str] = []
    templates_added: List[str] = []
    templates_added_as_new: List[str] = []
    templates_overwritten_by_name: List[str] = []
    templates_skipped_existing: List[str] = []
    templates_skipped_placeholders: List[str] = []
    templates_skipped_by_conflict: List[str] = []
    templates_skipped_invalid_files: List[str] = []

    decoration_records: List[TemplateDecorationRecord] = []
    template_info_by_id_int: Dict[int, Dict[str, Any]] = {}
    touched_template_id_ints: set[int] = set()
    level_variable_payloads_by_file_id = load_level_variable_payloads_by_file_id(project_root=project_path)
    custom_variable_missing_files_by_template: Dict[str, List[str]] = {}
    custom_variable_writeback_reports: List[Dict[str, Any]] = []

    def _apply_custom_variables_if_any(*, entry: Dict[str, Any], template_obj: Dict[str, Any], template_id_text: str) -> None:
        meta0 = template_obj.get("metadata")
        meta = meta0 if isinstance(meta0, dict) else {}
        refs = normalize_custom_variable_file_refs(meta.get("custom_variable_file"))
        if not refs:
            return

        merged_payloads: list[dict[str, Any]] = []
        missing: list[str] = []
        for file_id in refs:
            payloads = level_variable_payloads_by_file_id.get(str(file_id))
            if payloads is None:
                missing.append(str(file_id))
                continue
            merged_payloads.extend([p for p in payloads if isinstance(p, dict)])

        if missing:
            custom_variable_missing_files_by_template[str(template_id_text)] = list(missing)

        if not merged_payloads:
            return

        wr = upsert_custom_variables_from_level_variable_payloads(
            entry,
            group_list_key="8",
            variable_payloads=merged_payloads,
            overwrite_when_type_mismatched=True,
        )
        custom_variable_writeback_reports.append(
            {
                "template_id": str(template_id_text),
                "custom_variable_files": list(refs),
                "writeback": dict(wr),
            }
        )

    for template_file in template_files:
        obj = _load_template_config_json(template_file)
        if obj is None:
            templates_skipped_invalid_files.append(str(template_file))
            continue

        template_id_text = str(obj.get("template_id") or "").strip()
        template_name = str(obj.get("name") or "").strip()
        if template_name == "":
            template_name = template_id_text

        if bool(options.skip_placeholders) and _read_placeholder_flag(obj):
            templates_skipped_placeholders.append(template_id_text)
            continue

        file_cf = str(Path(template_file).resolve()).casefold()
        conflict_action = conflict_action_by_file_cf.get(file_cf, {}).get("action", "")
        if conflict_action == "skip":
            templates_skipped_by_conflict.append(template_id_text)
            continue
        if conflict_action == "add":
            new_name = str(conflict_action_by_file_cf.get(file_cf, {}).get("new_template_name", "") or "").strip()
            if new_name == "":
                raise ValueError(
                    f"template_conflict_resolutions action=add 缺少 new_template_name：{str(Path(template_file).resolve())}"
                )
            if new_name.casefold() in used_template_names_cf:
                raise ValueError(
                    "new_template_name 与 base/已写回模板重名（忽略大小写）："
                    f"{new_name!r} (file={str(Path(template_file).resolve())})"
                )
            template_name = new_name

        template_id_int = _coerce_template_id_int(template_id_text=template_id_text)
        if conflict_action == "overwrite":
            existing_entry_by_name = existing_by_name.get(str(obj.get("name") or "").strip() or template_id_text)
            if existing_entry_by_name is not None:
                # overwrite-by-name：模板本体不新增/不改 ID，但 decorations 仍应按“实际命中的模板ID”写回到 root27。
                existing_id_int = _extract_first_int_from_repeated_field(existing_entry_by_name, "1")
                if not isinstance(existing_id_int, int):
                    raise ValueError("base .gil 模板段存在 entry 但缺少 template_id（字段 '1'）")
                decoration_records.extend(
                    extract_template_decoration_records_from_template_obj(
                        template_obj=obj,
                        template_json_file=Path(template_file).resolve(),
                        parent_template_id_int=int(existing_id_int),
                    )
                )
                if int(existing_id_int) not in template_info_by_id_int:
                    type_code0 = _read_source_type_code_int(obj)
                    if type_code0 is None:
                        type_code0 = _extract_first_int_from_repeated_field(existing_entry_by_name, "2")
                    template_info_by_id_int[int(existing_id_int)] = {
                        "name": str(obj.get("name") or "").strip() or template_id_text,
                        "type_code": int(type_code0) if isinstance(type_code0, int) else None,
                    }
                _set_template_name(existing_entry_by_name, str(obj.get("name") or "").strip() or template_id_text)
                _apply_custom_variables_if_any(entry=existing_entry_by_name, template_obj=obj, template_id_text=template_id_text)
                touched_template_id_ints.add(int(existing_id_int))
                templates_overwritten_by_name.append(template_id_text)
                continue

        existing_entry = existing_by_id.get(int(template_id_int))
        if existing_entry is not None and conflict_action != "add":
            if mode == "merge":
                templates_skipped_existing.append(template_id_text)
                continue
            decoration_records.extend(
                extract_template_decoration_records_from_template_obj(
                    template_obj=obj,
                    template_json_file=Path(template_file).resolve(),
                    parent_template_id_int=int(template_id_int),
                )
            )
            if int(template_id_int) not in template_info_by_id_int:
                type_code0 = _read_source_type_code_int(obj)
                if type_code0 is None:
                    type_code0 = _extract_first_int_from_repeated_field(existing_entry, "2")
                template_info_by_id_int[int(template_id_int)] = {
                    "name": str(template_name),
                    "type_code": int(type_code0) if isinstance(type_code0, int) else None,
                }
            _set_template_name(existing_entry, template_name)
            _apply_custom_variables_if_any(entry=existing_entry, template_obj=obj, template_id_text=template_id_text)
            used_template_names_cf.add(str(template_name).casefold())
            touched_template_id_ints.add(int(template_id_int))
            templates_updated.append(template_id_text)
            continue

        source_type_code_int = _read_source_type_code_int(obj)
        base_entry: Optional[Dict[str, Any]] = None
        if isinstance(source_type_code_int, int):
            base_entry = exemplar_by_type_code.get(int(source_type_code_int))
            if base_entry is None:
                # base `.gil` 常见缺少“物件/元件模板”的 exemplar（只带 UI 模板）；
                # 此时从 seed `test2.gil` 取一个“物件模板形态”的原型来 clone，再替换 type_code。
                seed_any, seed_by_type_code = _load_seed_template_exemplars()
                base_entry = seed_by_type_code.get(int(source_type_code_int)) or seed_any
        if base_entry is None:
            base_entry = any_exemplar
        if base_entry is None:
            raise ValueError("目标 .gil 缺少模板段 root4/4/1，无法新增模板（无可克隆样本）。")

        # 新增：避免稳定哈希 ID 在同一次写回中撞车（crc32 low15 可能碰撞）。
        # 注意：默认行为下若与“已存在模板 ID”撞车，则视为“更新既有模板”；但当冲突策略 action=add 时会强制 bump 以新增。
        while int(template_id_int) in used_template_id_ints:
            template_id_int = _bump_template_root_id_int(int(template_id_int))

        decoration_records.extend(
            extract_template_decoration_records_from_template_obj(
                template_obj=obj,
                template_json_file=Path(template_file).resolve(),
                parent_template_id_int=int(template_id_int),
            )
        )
        if int(template_id_int) not in template_info_by_id_int:
            template_info_by_id_int[int(template_id_int)] = {
                "name": str(template_name),
                "type_code": int(source_type_code_int) if isinstance(source_type_code_int, int) else None,
            }
        cloned = json.loads(json.dumps(base_entry, ensure_ascii=False))
        cloned["1"] = [int(template_id_int)]
        if isinstance(source_type_code_int, int):
            cloned["2"] = [int(source_type_code_int)]
        _set_template_name(cloned, template_name)
        _apply_custom_variables_if_any(entry=cloned, template_obj=obj, template_id_text=template_id_text)
        template_entries.append(cloned)
        existing_by_id[int(template_id_int)] = cloned
        used_template_id_ints.add(int(template_id_int))
        used_template_names_cf.add(str(template_name).casefold())
        touched_template_id_ints.add(int(template_id_int))
        templates_added.append(template_id_text)
        if conflict_action == "add":
            templates_added_as_new.append(template_id_text)

    tabs_writeback_report = _patch_root6_template_tabs_for_touched_templates(
        payload_root=payload_root,
        touched_template_id_ints=sorted(touched_template_id_ints),
    )

    decorated_template_id_ints = sorted({int(r.parent_template_id_int) for r in decoration_records if isinstance(r, TemplateDecorationRecord)})
    root8_bootstrap_report = _ensure_root8_parent_instances_for_template_decorations(
        payload_root=payload_root,
        template_info_by_id_int=dict(template_info_by_id_int),
        decorated_template_id_ints=list(decorated_template_id_ints),
    )

    decorations_report = apply_template_decorations_writeback_to_payload_root(
        payload_root=payload_root,
        decoration_records=list(decoration_records),
    )

    # === 同步更新时间戳(root40) ===
    # 观测：部分真源/官方侧流程对 payload_root['40']（时间戳）存在缓存/刷新依赖；
    # 若我们写回了模板/装饰物/root8 父实例但仍沿用 base 的 root40，可能表现为“内容已写入但编辑器内仍不可见”。
    # 因此：只要本次写回确实触及到模板或 decorations，就刷新 root40。
    changed_any = False
    if touched_template_id_ints:
        changed_any = True
    if int(root8_bootstrap_report.get("bootstrapped") or 0) > 0:
        changed_any = True
    if int(decorations_report.get("decorations_total") or 0) > 0:
        changed_any = True
    if bool(tabs_writeback_report.get("changed")):
        changed_any = True
    if changed_any:
        payload_root["40"] = int(time.time())

    payload_bytes = encode_message(payload_root)
    container_spec = read_gil_container_spec(input_path)
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=payload_bytes, container_spec=container_spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)

    return {
        "project_archive": str(project_path),
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "mode": mode,
        "bootstrapped_seed_exemplar": bool(bootstrapped_seed_exemplar),
        "filtered_by_selection": bool(options.include_template_json_files is not None),
        "templates_total": len(template_files),
        "custom_variables_writeback": {
            "templates_with_custom_variable_file": len(custom_variable_writeback_reports),
            "missing_variable_files_by_template": dict(custom_variable_missing_files_by_template),
            "writeback_reports": list(custom_variable_writeback_reports),
        },
        "template_tabs_writeback": dict(tabs_writeback_report),
        "template_decorations_root8_parent_bootstrap": dict(root8_bootstrap_report),
        "decorations_writeback": dict(decorations_report),
        "templates_updated": sorted(set(templates_updated)),
        "templates_added": sorted(set(templates_added)),
        "templates_added_as_new": sorted(set(templates_added_as_new)),
        "templates_overwritten_by_name": sorted(set(templates_overwritten_by_name)),
        "templates_skipped_existing": sorted(set(templates_skipped_existing)),
        "templates_skipped_placeholders": sorted(set(templates_skipped_placeholders)),
        "templates_skipped_by_conflict": sorted(set(templates_skipped_by_conflict)),
        "templates_skipped_invalid_files": sorted(set(templates_skipped_invalid_files)),
    }


__all__ = [
    "TemplatesImportOptions",
    "import_templates_from_project_archive_to_gil",
]


