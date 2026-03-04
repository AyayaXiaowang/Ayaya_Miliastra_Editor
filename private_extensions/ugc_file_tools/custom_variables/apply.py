from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.gil_dump_codec.protobuf_like import parse_binary_data_hex_text

from .coerce import coerce_default_float, coerce_default_int, coerce_default_string, normalize_custom_variable_name_field2
from .refs import TextPlaceholderVarRef
from .specs import build_custom_variable_item_from_spec, infer_custom_variable_spec_from_default
from .value_message import (
    build_custom_variable_type_descriptor,
    build_custom_variable_value_message,
    build_dict_custom_variable_item,
)

__all__ = [
    "collect_player_template_custom_variable_targets_from_payload_root",
    "extract_instance_entry_name_from_root4_5_1_entry",
    "find_root4_5_1_entry_by_name",
    "ensure_override_variables_group1_container",
    "ensure_int_custom_variable_in_asset_entry",
    "ensure_float_custom_variable_in_asset_entry",
    "ensure_config_id_custom_variable_in_asset_entry",
    "ensure_string_custom_variable_in_asset_entry",
    "ensure_dict_custom_variable_in_asset_entry",
    "ensure_custom_variables_from_variable_defaults",
    "ensure_text_placeholder_referenced_custom_variables",
]


def _as_list_allow_scalar(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _extract_first_int_from_repeated_field(node: Dict[str, Any], key: str) -> Optional[int]:
    value = node.get(key)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, list) and value and isinstance(value[0], int):
        return int(value[0])
    return None


def _is_player_template_wrapper_root5_entry(entry: Dict[str, Any]) -> bool:
    """
    识别 root4/5/1 下的“玩家模板 wrapper 条目”（战斗预设）：
    - meta list(字段 '5') 内存在 item['1']==3
    - item['12'] 为 dict 且至少包含固定配置字段 '5' 与 '6'（players 字段 '4' 可能缺失表示“默认/全体/特殊”）

    说明：该判定语义来自 `ugc_file_tools/save_patchers/player_templates.py` 的真源样本总结；
    这里保持为“可解释的结构特征”，避免依赖固定路径或模板名。
    """
    meta = entry.get("5")
    for item in _as_list_allow_scalar(meta):
        if not isinstance(item, dict):
            continue
        if item.get("1") != 3:
            continue
        box = item.get("12")
        if not isinstance(box, dict):
            continue
        if not isinstance(box.get("5"), int):
            return False
        if not isinstance(box.get("6"), int):
            return False
        return True
    return False


def collect_player_template_custom_variable_targets_from_payload_root(
    payload_root: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    从 payload_root 中抽取“玩家模板(战斗预设)自定义变量写回目标”，用于把 UI 引用到的 玩家自身 变量
    同步写入到玩家模板条目中。

    经验结构（真源样本总结）：
    - 玩家模板 wrapper 条目在 root4/5/1：变量列表位于 entry['7'] 的 group1 容器内
    - 对应的模板条目在 root4/4/1：变量列表位于 entry['8'] 的 group1 容器内
    - wrapper 通过 entry['2']['1'] 引用 root4 entry_id（template_id_int）

    返回：每个 root4_entry_id 对应一个 target dict：
    - root4_entry_id: int
    - template_names: list[str]（来自 wrapper name；去重保持顺序）
    - root5_wrappers: list[dict]（所有引用同一 root4_entry_id 的 wrapper 条目；已排除 "(角色编辑)"）
    - root4_entry: dict | None（root4/4/1 中匹配到的条目；可能缺失）
    """
    if not isinstance(payload_root, dict):
        return []

    section5 = payload_root.get("5")
    if not isinstance(section5, dict):
        return []
    entry_list0 = section5.get("1")
    entry_list = [x for x in _as_list_allow_scalar(entry_list0) if isinstance(x, dict)]
    if not entry_list:
        return []

    # 1) 收集 wrapper：root4_entry_id -> wrappers
    wrappers_by_root4_id: Dict[int, List[Dict[str, Any]]] = {}
    names_by_root4_id: Dict[int, List[str]] = {}
    for e in entry_list:
        if not isinstance(e, dict):
            continue
        if not _is_player_template_wrapper_root5_entry(e):
            continue
        name = extract_instance_entry_name_from_root4_5_1_entry(e)
        if not name:
            continue
        # 角色编辑条目不承载玩家模板变量定义（真源样本总结）；这里主动跳过，避免把变量写到错误入口。
        if str(name).endswith("(角色编辑)"):
            continue
        ref_box = e.get("2")
        ref_id = ref_box.get("1") if isinstance(ref_box, dict) else None
        if not isinstance(ref_id, int) or int(ref_id) <= 0:
            continue
        rid = int(ref_id)
        wrappers_by_root4_id.setdefault(rid, []).append(e)
        bucket = names_by_root4_id.setdefault(rid, [])
        if name not in bucket:
            bucket.append(str(name))

    if not wrappers_by_root4_id:
        return []

    # 2) root4 entry map：entry_id -> entry
    root4_section = payload_root.get("4")
    root4_entries_raw = root4_section.get("1") if isinstance(root4_section, dict) else None
    root4_entries = [x for x in _as_list_allow_scalar(root4_entries_raw) if isinstance(x, dict)]
    root4_by_id: Dict[int, Dict[str, Any]] = {}
    for e4 in root4_entries:
        rid = _extract_first_int_from_repeated_field(e4, "1")
        if not isinstance(rid, int) or int(rid) <= 0:
            continue
        if int(rid) not in root4_by_id:
            root4_by_id[int(rid)] = e4

    # 3) build targets (stable: follow wrappers scan order)
    targets: List[Dict[str, Any]] = []
    for rid, wrappers in wrappers_by_root4_id.items():
        targets.append(
            {
                "root4_entry_id": int(rid),
                "template_names": list(names_by_root4_id.get(int(rid), [])),
                "root5_wrappers": list(wrappers),
                "root4_entry": root4_by_id.get(int(rid)),
            }
        )
    return targets


def extract_instance_entry_name_from_root4_5_1_entry(asset_entry: Dict[str, Any]) -> str:
    """
    从 DLL dump-json 的 root4['5']['1'] 条目中提取“名称”（样本：关卡实体）。

    结构（样本）：
      entry['5'] = [{'1': 1, '11': {'1': '<name>'}}, ...]
    """
    name_list = asset_entry.get("5")
    if not isinstance(name_list, list):
        return ""
    for item in name_list:
        if not isinstance(item, dict):
            continue
        if item.get("1") != 1:
            continue
        name_container = item.get("11")
        if not isinstance(name_container, dict):
            continue
        name_value = name_container.get("1")
        if isinstance(name_value, str):
            # 兼容：写回侧可能使用 lossless dump（utf8 字段保留为 "<binary_data> .."），此时需要解码为文本比较。
            if name_value.startswith("<binary_data>"):
                raw_bytes = parse_binary_data_hex_text(name_value)
                decoded_text = raw_bytes.decode("utf-8", errors="replace")
                if "\x00" in decoded_text:
                    decoded_text = decoded_text.split("\x00", 1)[0]
                return str(decoded_text).strip()
            if "\x00" in name_value:
                return str(name_value.split("\x00", 1)[0]).strip()
            return str(name_value).strip()
    return ""


def find_root4_5_1_entry_by_name(entry_list: List[Any], name: str) -> Optional[Dict[str, Any]]:
    target = str(name or "").strip()
    if target == "":
        return None
    for entry in entry_list:
        if not isinstance(entry, dict):
            continue
        if extract_instance_entry_name_from_root4_5_1_entry(entry) == target:
            return entry
    return None


def _ensure_override_variables_group1_container_by_group_list_key(
    asset_entry: Dict[str, Any],
    *,
    group_list_key: str,
) -> Dict[str, Any]:
    """
    确保 asset_entry[group_list_key] 内存在 group_id=1 的变量容器，并返回该 group_item：
      group_item = {'1': 1, '2': 1, '11': {'1': [variable_item, ...]}}
    """
    key = str(group_list_key or "").strip()
    if key == "":
        raise ValueError("group_list_key 不能为空")

    group_list = asset_entry.get(key)
    if isinstance(group_list, dict):
        group_list = [group_list]
        asset_entry[key] = group_list
    if not isinstance(group_list, list):
        group_list = []
        asset_entry[key] = group_list

    def _coerce_section_message(value: Any, *, max_depth: int) -> Optional[Dict[str, Any]]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.startswith("<binary_data>"):
            from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import binary_data_text_to_numeric_message

            msg = binary_data_text_to_numeric_message(value, max_depth=int(max_depth))
            if not isinstance(msg, dict):
                raise TypeError(f"binary_data_text_to_numeric_message returned {type(msg).__name__}")
            return dict(msg)
        if value is None:
            return None
        return None

    # 收集所有 group1 item（兼容存在重复/占位容器的样本）：优先保证最终只保留 1 个 group1。
    group1_indices: list[int] = []
    for idx, item in enumerate(list(group_list)):
        if not isinstance(item, dict):
            continue
        if item.get("1") != 1:
            continue
        if item.get("2") != 1:
            continue
        group1_indices.append(int(idx))

    if not group1_indices:
        group_list.append({"1": 1, "2": 1, "11": {}})
        group1_indices = [int(len(group_list) - 1)]

    primary_idx = int(group1_indices[0])

    def _ensure_variable_items_list(container: Dict[str, Any]) -> List[Any]:
        items0 = container.get("1")
        # 兼容 DLL dump-json：repeated message 在“只有 1 个元素”时可能被折叠为 dict 而非 list。
        if isinstance(items0, dict):
            container["1"] = [items0]
        elif items0 is None:
            container["1"] = []
        elif isinstance(items0, list):
            pass
        else:
            container["1"] = [items0]
        items_any = container.get("1")
        if not isinstance(items_any, list):
            raise RuntimeError("internal error: container['1'] is not list")
        return items_any

    # 先把所有 group1 的 container 都解包为 dict，并把变量列表规范化为 list
    containers_by_idx: Dict[int, Dict[str, Any]] = {}
    items_by_idx: Dict[int, List[Any]] = {}
    for idx in list(group1_indices):
        gi = group_list[int(idx)]
        if not isinstance(gi, dict):
            continue
        container0 = gi.get("11")
        container = _coerce_section_message(container0, max_depth=32)
        if container is None:
            container = {}
        gi["11"] = container
        containers_by_idx[int(idx)] = container
        items_by_idx[int(idx)] = _ensure_variable_items_list(container)

    primary_group = group_list[primary_idx]
    if not isinstance(primary_group, dict):
        raise RuntimeError("internal error: primary group item is not dict")
    primary_container = containers_by_idx.get(primary_idx) or {}
    primary_group["11"] = primary_container
    primary_items = items_by_idx.get(primary_idx)
    if primary_items is None:
        primary_items = _ensure_variable_items_list(primary_container)

    # 合并其它重复 group1 内的变量条目（按 variable_name 去重，first-wins；保留 primary 顺序）
    seen_names_cf: set[str] = set()
    for it in list(primary_items):
        if not isinstance(it, dict):
            continue
        nm = normalize_custom_variable_name_field2(it.get("2"))
        if nm:
            seen_names_cf.add(nm.casefold())

    for idx in list(group1_indices[1:]):
        other_items = items_by_idx.get(int(idx)) or []
        for it in list(other_items):
            if not isinstance(it, dict):
                continue
            nm = normalize_custom_variable_name_field2(it.get("2"))
            if not nm:
                continue
            k = nm.casefold()
            if k in seen_names_cf:
                continue
            seen_names_cf.add(k)
            primary_items.append(it)

    # 删除多余 group1 item（保持 primary 位于最前）
    for idx in reversed(list(group1_indices[1:])):
        group_list.pop(int(idx))

    # 最终保证 primary_container['1'] 为 list
    primary_container["1"] = primary_items
    return primary_group


def ensure_override_variables_group1_container(asset_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    确保 asset_entry['7'] 内存在 group_id=1 的变量容器，并返回该 group_item：
      group_item = {'1': 1, '2': 1, '11': {'1': [variable_item, ...]}}
    """
    return _ensure_override_variables_group1_container_by_group_list_key(asset_entry, group_list_key="7")


def ensure_int_custom_variable_in_asset_entry(
    asset_entry: Dict[str, Any],
    *,
    variable_name: str,
    default_value: int,
    group_list_key: str = "7",
) -> bool:
    """确保整数自定义变量存在（type_code=3）。返回 True=本次创建。"""
    name = str(variable_name or "").strip()
    if name == "":
        raise ValueError("variable_name 不能为空")

    group_item = _ensure_override_variables_group1_container_by_group_list_key(asset_entry, group_list_key=str(group_list_key))
    container = group_item.get("11")
    if not isinstance(container, dict):
        raise RuntimeError("internal error: group_item['11'] is not dict")
    variable_items = container.get("1")
    if not isinstance(variable_items, list):
        raise RuntimeError("internal error: group_item['11']['1'] is not list")

    for item in variable_items:
        if not isinstance(item, dict):
            continue
        if normalize_custom_variable_name_field2(item.get("2")) == name:
            return False

    variable_items.append(
        {
            "2": name,
            "3": 3,
            "4": build_custom_variable_value_message(var_type_int=3, default_value=int(default_value)),
            "5": 1,
            "6": build_custom_variable_type_descriptor(var_type_int=3),
        }
    )
    return True


def ensure_config_id_custom_variable_in_asset_entry(
    asset_entry: Dict[str, Any],
    *,
    variable_name: str,
    default_value: int,
    group_list_key: str = "7",
) -> bool:
    """确保配置ID自定义变量存在（type_code=20）。返回 True=本次创建。"""
    name = str(variable_name or "").strip()
    if name == "":
        raise ValueError("variable_name 不能为空")

    group_item = _ensure_override_variables_group1_container_by_group_list_key(asset_entry, group_list_key=str(group_list_key))
    container = group_item.get("11")
    if not isinstance(container, dict):
        raise RuntimeError("internal error: group_item['11'] is not dict")
    variable_items = container.get("1")
    if not isinstance(variable_items, list):
        raise RuntimeError("internal error: group_item['11']['1'] is not list")

    for item in variable_items:
        if not isinstance(item, dict):
            continue
        if normalize_custom_variable_name_field2(item.get("2")) == name:
            return False

    variable_items.append(
        {
            "2": name,
            "3": 20,
            "4": build_custom_variable_value_message(var_type_int=20, default_value=int(default_value)),
            "5": 1,
            "6": build_custom_variable_type_descriptor(var_type_int=20),
        }
    )
    return True


def ensure_float_custom_variable_in_asset_entry(
    asset_entry: Dict[str, Any],
    *,
    variable_name: str,
    default_value: float,
    group_list_key: str = "7",
) -> bool:
    """确保浮点自定义变量存在（type_code=5）。返回 True=本次创建。"""
    name = str(variable_name or "").strip()
    if name == "":
        raise ValueError("variable_name 不能为空")

    group_item = _ensure_override_variables_group1_container_by_group_list_key(asset_entry, group_list_key=str(group_list_key))
    container = group_item.get("11")
    if not isinstance(container, dict):
        raise RuntimeError("internal error: group_item['11'] is not dict")
    variable_items = container.get("1")
    if not isinstance(variable_items, list):
        raise RuntimeError("internal error: group_item['11']['1'] is not list")

    for item in variable_items:
        if not isinstance(item, dict):
            continue
        if normalize_custom_variable_name_field2(item.get("2")) == name:
            return False

    variable_items.append(
        {
            "2": name,
            "3": 5,
            "4": build_custom_variable_value_message(var_type_int=5, default_value=float(default_value)),
            "5": 1,
            "6": build_custom_variable_type_descriptor(var_type_int=5),
        }
    )
    return True


def ensure_string_custom_variable_in_asset_entry(
    asset_entry: Dict[str, Any],
    *,
    variable_name: str,
    default_value: str,
    group_list_key: str = "7",
) -> bool:
    """确保字符串自定义变量存在（type_code=6）。返回 True=本次创建。"""
    name = str(variable_name or "").strip()
    if name == "":
        raise ValueError("variable_name 不能为空")

    group_item = _ensure_override_variables_group1_container_by_group_list_key(asset_entry, group_list_key=str(group_list_key))
    container = group_item.get("11")
    if not isinstance(container, dict):
        raise RuntimeError("internal error: group_item['11'] is not dict")
    variable_items = container.get("1")
    if not isinstance(variable_items, list):
        raise RuntimeError("internal error: group_item['11']['1'] is not list")

    for item in variable_items:
        if not isinstance(item, dict):
            continue
        if normalize_custom_variable_name_field2(item.get("2")) == name:
            return False

    variable_items.append(
        {
            "2": name,
            "3": 6,
            "4": build_custom_variable_value_message(var_type_int=6, default_value=str(default_value or "")),
            "5": 1,
            "6": build_custom_variable_type_descriptor(var_type_int=6),
        }
    )
    return True


def ensure_dict_custom_variable_in_asset_entry(
    asset_entry: Dict[str, Any],
    *,
    variable_name: str,
    dict_key_type_int: int,
    dict_value_type_int: int,
    default_value_by_key: Dict[str, Any],
    extra_legacy_scalar_prefixes: Optional[List[str]] = None,
    group_list_key: str = "7",
) -> tuple[bool, int]:
    """
    在目标实体条目上确保存在一个字典自定义变量（type_code=27）。

    返回：(created, keys_added_total)
    - created=True：本次新建了 dict 变量
    - keys_added_total：对已有 dict 变量增量补齐的键数量（新建时为全部键数）
    """
    name = str(variable_name or "").strip()
    if name == "":
        raise ValueError("variable_name 不能为空")

    key_vt = int(dict_key_type_int)
    val_vt = int(dict_value_type_int)
    if key_vt != 6:
        raise ValueError(f"字典变量目前仅支持 key_type=字符串(6)，实际：{key_vt}")
    if val_vt not in (3, 5, 6):
        raise ValueError(f"字典变量目前仅支持 value_type=整数(3)/浮点数(5)/字符串(6)，实际：{val_vt}")

    # 目标容器：group_id=1 的 override variables
    group_item = _ensure_override_variables_group1_container_by_group_list_key(asset_entry, group_list_key=str(group_list_key))
    container = group_item.get("11")
    if not isinstance(container, dict):
        raise RuntimeError("internal error: group_item['11'] is not dict")
    variable_items = container.get("1")
    if not isinstance(variable_items, list):
        raise RuntimeError("internal error: group_item['11']['1'] is not list")

    def _remove_legacy_scalar_variables_by_prefix(prefixes: list[str]) -> int:
        removed = 0
        if not prefixes:
            return 0
        keep: list[Any] = []
        for item in list(variable_items):
            if not isinstance(item, dict):
                keep.append(item)
                continue
            # legacy 标量变量：可能是字符串/整数/浮点等（历史写回曾把 dict.key 写成独立标量变量名）。
            # 这里按前缀清理时不限定 type_code，避免留下“ui_page_xxx.key”这类变量导致编辑器列表看似重复。
            if int(item.get("3") or 0) in (27,):
                keep.append(item)
                continue
            item_name = normalize_custom_variable_name_field2(item.get("2"))
            if not item_name:
                keep.append(item)
                continue
            if any(item_name.startswith(p) for p in prefixes):
                removed += 1
                continue
            keep.append(item)
        if removed:
            variable_items[:] = keep
        return int(removed)

    existing_item: Dict[str, Any] | None = None
    for item in variable_items:
        if not isinstance(item, dict):
            continue
        if normalize_custom_variable_name_field2(item.get("2")) == name:
            existing_item = item
            break

    # 需要写入的 keys（稳定排序）
    keys_sorted = sorted({str(k).strip() for k in (default_value_by_key or {}).keys() if str(k).strip() != ""})
    if not keys_sorted:
        keys_sorted = []

    def _ensure_list(node: Any) -> list:
        if isinstance(node, list):
            return node
        if isinstance(node, dict):
            return [node]
        return []

    def _extract_key_text_from_key_node(key_node: Dict[str, Any]) -> str:
        """
        从字典 key 节点里提取“可读 key 文本”。

        关键：写回链路可能使用 prefer_raw_hex_for_utf8 的 lossless dump，
        因此 utf8 字段可能以 `"<binary_data> ..."` 形式出现。若不解码，会把
        "<binary_data> xx xx" 当作 key 文本，导致“已存在 key 无法命中”并重复追加。
        """
        raw = key_node.get("16")

        def _normalize_utf8_like(value: Any) -> str:
            def _decode_binary_data_text(s: str) -> str:
                b = parse_binary_data_hex_text(s)

                # 兼容：某些 lossless dump 会把“字符串字段”整体编码为 protobuf length-delimited 字段：
                #   <field_key_varint><len_varint><utf8_bytes>
                # 常见开头：0x0A（field=1, wire=2）
                def _read_varint(buf: bytes, start: int) -> tuple[int, int] | None:
                    acc = 0
                    shift = 0
                    i = int(start)
                    while i < len(buf) and shift < 64:
                        byte = int(buf[i])
                        i += 1
                        acc |= (byte & 0x7F) << shift
                        if (byte & 0x80) == 0:
                            return (int(acc), int(i))
                        shift += 7
                    return None

                payload = b
                v_key = _read_varint(b, 0)
                if v_key is not None:
                    key, pos = v_key
                    wire = int(key) & 0x7
                    if wire == 2:
                        v_len = _read_varint(b, pos)
                        if v_len is not None:
                            ln, pos2 = v_len
                            ln_i = int(ln)
                            if ln_i >= 0 and pos2 + ln_i <= len(b):
                                cand = b[pos2 : pos2 + ln_i]
                                if pos2 + ln_i == len(b):
                                    payload = cand

                text = payload.decode("utf-8", errors="replace")
                if "\x00" in text:
                    text = text.split("\x00", 1)[0]
                while text and ord(text[0]) < 32:
                    text = text[1:]
                while text and ord(text[-1]) < 32:
                    text = text[:-1]
                return str(text).strip()

            if isinstance(value, str):
                s = value
                if s.startswith("<binary_data>"):
                    return _decode_binary_data_text(s)
                if "\x00" in s:
                    s = s.split("\x00", 1)[0]
                while s and ord(s[0]) < 32:
                    s = s[1:]
                while s and ord(s[-1]) < 32:
                    s = s[:-1]
                return str(s).strip()

            if isinstance(value, dict):
                v1 = value.get("1")
                if isinstance(v1, str):
                    return _normalize_utf8_like(v1)
                v2 = value.get("2")
                if isinstance(v2, str):
                    return _normalize_utf8_like(v2)
                if isinstance(v1, dict):
                    s1 = _normalize_utf8_like(v1)
                    if s1:
                        return s1
                if isinstance(v2, dict):
                    s2 = _normalize_utf8_like(v2)
                    if s2:
                        return s2
                return ""

            return str(value if value is not None else "").strip()

        return _normalize_utf8_like(raw)

    legacy_prefixes: list[str] = [f"{name}."]
    extra = list(extra_legacy_scalar_prefixes or [])
    for p in extra:
        pp = str(p or "").strip()
        if pp and pp not in legacy_prefixes:
            legacy_prefixes.append(pp)

    if existing_item is None:
        _remove_legacy_scalar_variables_by_prefix(legacy_prefixes)
        variable_items.append(
            build_dict_custom_variable_item(
                variable_name=name,
                default_value_by_key=dict(default_value_by_key or {}),
                dict_key_type_int=int(key_vt),
                dict_value_type_int=int(val_vt),
            )
        )
        return True, int(len(keys_sorted))

    # 已存在：必须是字典变量
    if int(existing_item.get("3") or 0) != 27:
        raise ValueError(f"自定义变量同名但类型不是字典：{name!r} type_code={existing_item.get('3')!r}")

    _remove_legacy_scalar_variables_by_prefix(legacy_prefixes)

    value_node = existing_item.get("4")
    if not isinstance(value_node, dict):
        raise ValueError(f"字典自定义变量缺少 value 节点：{name!r}")
    map_node = value_node.get("37")
    if not isinstance(map_node, dict):
        map_node = {}
        value_node["37"] = map_node

    keys_list = _ensure_list(map_node.get("501"))
    vals_list = _ensure_list(map_node.get("502"))
    map_node["501"] = keys_list
    map_node["502"] = vals_list
    map_node["503"] = 6
    map_node["504"] = int(val_vt)

    # 兼容/自愈：稳定去重（按解码后的 key 文本），并保持 keys/values 对齐
    if len(keys_list) == len(vals_list) and keys_list:
        keep_keys: list[Any] = []
        keep_vals: list[Any] = []
        seen: set[str] = set()
        removed_total = 0
        for kn, vn in zip(list(keys_list), list(vals_list)):
            if not isinstance(kn, dict):
                keep_keys.append(kn)
                keep_vals.append(vn)
                continue
            k_text = _extract_key_text_from_key_node(kn)
            if not k_text:
                keep_keys.append(kn)
                keep_vals.append(vn)
                continue
            if k_text in seen:
                removed_total += 1
                continue
            seen.add(k_text)
            keep_keys.append(kn)
            keep_vals.append(vn)
        if removed_total:
            keys_list[:] = keep_keys
            vals_list[:] = keep_vals

    existing_keys: set[str] = set()
    for kn in keys_list:
        if not isinstance(kn, dict):
            continue
        k_text = _extract_key_text_from_key_node(kn)
        if k_text:
            existing_keys.add(k_text)

    keys_added_total = 0
    for key in keys_sorted:
        if key in existing_keys:
            continue
        keys_list.append(build_custom_variable_value_message(var_type_int=6, default_value=key))
        vals_list.append(build_custom_variable_value_message(var_type_int=int(val_vt), default_value=(default_value_by_key or {}).get(key)))
        keys_added_total += 1

    return False, int(keys_added_total)


def ensure_custom_variables_from_variable_defaults(
    raw_dump_object: Dict[str, Any],
    *,
    variable_defaults: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    将 `variable_defaults` 显式声明的变量补齐到实体自定义变量（root4/5/1）。

    说明：
    - 该函数只负责“按 default_map 创建缺失变量”，不依赖占位符扫描；
    - 类型推断遵循 Graph_Generater 的类型体系，并支持变量名中的显式类型标注（`..._<类型名>__...`）；
    - 安全策略：同名已存在则不覆盖（避免覆盖真源/运行期数据）；导出链路若需强制修复类型应使用专用 fixer。
    """
    if not isinstance(variable_defaults, dict) or not variable_defaults:
        return {"created_total": 0, "existed_total": 0, "targets": {}, "variables": []}

    root4 = raw_dump_object.get("4")
    if not isinstance(root4, dict):
        raise ValueError("DLL dump JSON 缺少根字段 '4'（期望为 dict）。")
    section5 = root4.get("5")
    if not isinstance(section5, dict):
        raise ValueError("DLL dump JSON 缺少字段 '4/5'（期望为 dict）。")
    entry_list = section5.get("1")
    if not isinstance(entry_list, list):
        raise ValueError("DLL dump JSON 缺少字段 '4/5/1'（期望为 list）。")

    level_entry = find_root4_5_1_entry_by_name(entry_list, "关卡实体")
    if level_entry is None:
        raise RuntimeError("未在 root4/5/1 中找到 name=关卡实体 的条目，无法写入关卡变量。")

    player_entity_entry = find_root4_5_1_entry_by_name(entry_list, "玩家实体")
    role_editor_entry = find_root4_5_1_entry_by_name(entry_list, "默认模版(角色编辑)")
    player_template_targets = collect_player_template_custom_variable_targets_from_payload_root(root4)

    def _iter_target_entries(group_name: str) -> list[tuple[Dict[str, Any], str, str]]:
        g = str(group_name or "").strip()
        if g == "关卡":
            return [(level_entry, "7", "关卡实体")]
        if g == "玩家自身":
            out: list[tuple[Dict[str, Any], str, str]] = []
            if player_entity_entry is not None:
                out.append((player_entity_entry, "7", "玩家实体"))
            # 玩家模板（战斗预设）：同时写 root5 wrapper('7') + root4 entry('8')
            for t in list(player_template_targets or []):
                wrappers = t.get("root5_wrappers")
                if isinstance(wrappers, list):
                    for w in wrappers:
                        if isinstance(w, dict):
                            name = extract_instance_entry_name_from_root4_5_1_entry(w) or "<玩家模板>"
                            out.append((w, "7", f"玩家模板:{name}"))
                e4 = t.get("root4_entry")
                if isinstance(e4, dict):
                    names = t.get("template_names")
                    label_name = ""
                    if isinstance(names, list) and names:
                        label_name = str(names[0])
                    label = f"玩家模板(模板段):{label_name}" if label_name else "玩家模板(模板段)"
                    out.append((e4, "8", label))
            if out:
                return out
            if role_editor_entry is not None:
                return [(role_editor_entry, "7", "默认模版(角色编辑)")]
            raise RuntimeError(
                "variable_defaults 引用了 玩家自身.<变量>，但存档中未找到 玩家实体 / 玩家模板(wrapper) / 默认模版(角色编辑) 条目。"
            )
        raise ValueError(f"未知变量组名：{g!r}（仅支持：关卡 / 玩家自身）")

    def _build_player_targets_labels_no_raise() -> list[str]:
        labels: list[str] = []
        if player_entity_entry is not None:
            labels.append("玩家实体")
        for t in list(player_template_targets or []):
            wrappers = t.get("root5_wrappers")
            if isinstance(wrappers, list):
                for w in wrappers:
                    if not isinstance(w, dict):
                        continue
                    name = extract_instance_entry_name_from_root4_5_1_entry(w) or "<玩家模板>"
                    labels.append(f"玩家模板:{name}")
            e4 = t.get("root4_entry")
            if isinstance(e4, dict):
                names = t.get("template_names")
                label_name = ""
                if isinstance(names, list) and names:
                    label_name = str(names[0])
                labels.append(f"玩家模板(模板段):{label_name}" if label_name else "玩家模板(模板段)")
        if not labels and role_editor_entry is not None:
            labels.append("默认模版(角色编辑)")
        # 去重保持顺序
        seen: set[str] = set()
        deduped: list[str] = []
        for x in labels:
            k = str(x)
            if k in seen:
                continue
            seen.add(k)
            deduped.append(k)
        return deduped

    created_total = 0
    existed_total = 0
    variables_report: List[Dict[str, Any]] = []

    for full_name, default_value in variable_defaults.items():
        full = str(full_name or "").strip()
        if "." not in full:
            continue
        group_part, var_part = full.split(".", 1)
        g = str(group_part or "").strip()
        n = str(var_part or "").strip()
        if g == "" or n == "":
            continue

        spec = infer_custom_variable_spec_from_default(group_name=g, variable_name=n, default_value=default_value)
        targets = _iter_target_entries(spec.group_name)
        created_in: list[str] = []
        existed_in: list[str] = []
        for target_entry, group_list_key, target_label in targets:
            group_item = _ensure_override_variables_group1_container_by_group_list_key(
                target_entry, group_list_key=str(group_list_key)
            )
            container = group_item.get("11")
            if not isinstance(container, dict):
                raise RuntimeError("internal error: group_item['11'] is not dict")
            variable_items = container.get("1")
            if not isinstance(variable_items, list):
                raise RuntimeError("internal error: group_item['11']['1'] is not list")

            already = False
            for item in variable_items:
                if not isinstance(item, dict):
                    continue
                if normalize_custom_variable_name_field2(item.get("2")) == spec.variable_name:
                    already = True
                    break
            if already:
                existed_total += 1
                existed_in.append(str(target_label))
                continue

            variable_items.append(build_custom_variable_item_from_spec(spec))
            created_total += 1
            created_in.append(str(target_label))

        variables_report.append(
            {
                "group": str(spec.group_name),
                "variable_name": str(spec.variable_name),
                "type_code": int(spec.var_type_int),
                "dict_key_type": int(spec.dict_key_type_int) if spec.dict_key_type_int is not None else None,
                "dict_value_type": int(spec.dict_value_type_int) if spec.dict_value_type_int is not None else None,
                "default_value_source": "user",
                "created": bool(created_in),
                "target_entity_name": (created_in[0] if created_in else (existed_in[0] if existed_in else "")),
                "created_in": created_in,
                "existed_in": existed_in,
            }
        )

    return {
        "created_total": int(created_total),
        "existed_total": int(existed_total),
        "targets": {
            "关卡": ["关卡实体"],
            "玩家自身": _build_player_targets_labels_no_raise(),
        },
        "variables": variables_report,
    }


def ensure_text_placeholder_referenced_custom_variables(
    raw_dump_object: Dict[str, Any],
    *,
    variable_refs: set[TextPlaceholderVarRef],
    variable_defaults: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """把文本占位符引用到的变量补齐到实体自定义变量。

    约定：
    - lv -> 关卡变量组 -> 写入 关卡实体（root4/5/1）
    - ps/p1..p8 -> 玩家自身变量组 -> 写入 玩家实体（若存在）与 玩家模板(战斗预设)条目（若存在）；否则回退到 默认模版(角色编辑)
    - 标量占位符：创建字符串变量 type_code=6，默认值为空字符串
    - 字典字段路径：创建字典变量 type_code=27（key_type=字符串；value_type 由后缀或 default 推断）
    """
    if not variable_refs:
        return {"created_total": 0, "existed_total": 0, "targets": {}, "variables": []}

    root4 = raw_dump_object.get("4")
    if not isinstance(root4, dict):
        raise ValueError("DLL dump JSON 缺少根字段 '4'（期望为 dict）。")
    section5 = root4.get("5")
    if not isinstance(section5, dict):
        raise ValueError("DLL dump JSON 缺少字段 '4/5'（期望为 dict）。")
    entry_list = section5.get("1")
    if not isinstance(entry_list, list):
        raise ValueError("DLL dump JSON 缺少字段 '4/5/1'（期望为 list）。")

    level_entry = find_root4_5_1_entry_by_name(entry_list, "关卡实体")
    if level_entry is None:
        raise RuntimeError("未在 root4/5/1 中找到 name=关卡实体 的条目，无法写入关卡变量。")

    player_entity_entry = find_root4_5_1_entry_by_name(entry_list, "玩家实体")
    role_editor_entry = find_root4_5_1_entry_by_name(entry_list, "默认模版(角色编辑)")
    player_template_targets = collect_player_template_custom_variable_targets_from_payload_root(root4)

    created_total = 0
    existed_total = 0
    variables_report: List[Dict[str, Any]] = []

    def _iter_target_entries(group_name: str) -> list[tuple[Dict[str, Any], str, str]]:
        g = str(group_name or "").strip()
        if g == "关卡":
            return [(level_entry, "7", "关卡实体")]
        if g == "玩家自身":
            out: list[tuple[Dict[str, Any], str, str]] = []
            if player_entity_entry is not None:
                out.append((player_entity_entry, "7", "玩家实体"))
            for t in list(player_template_targets or []):
                wrappers = t.get("root5_wrappers")
                if isinstance(wrappers, list):
                    for w in wrappers:
                        if isinstance(w, dict):
                            name = extract_instance_entry_name_from_root4_5_1_entry(w) or "<玩家模板>"
                            out.append((w, "7", f"玩家模板:{name}"))
                e4 = t.get("root4_entry")
                if isinstance(e4, dict):
                    names = t.get("template_names")
                    label_name = ""
                    if isinstance(names, list) and names:
                        label_name = str(names[0])
                    label = f"玩家模板(模板段):{label_name}" if label_name else "玩家模板(模板段)"
                    out.append((e4, "8", label))
            if out:
                return out
            if role_editor_entry is not None:
                return [(role_editor_entry, "7", "默认模版(角色编辑)")]
            raise RuntimeError(
                "文本占位符引用了 玩家自身.<变量>，但存档中未找到 玩家实体 / 玩家模板(wrapper) / 默认模版(角色编辑) 条目。"
            )
        raise ValueError(f"未知变量组名：{g!r}（仅支持：关卡 / 玩家自身）")

    def _build_player_targets_labels_no_raise() -> list[str]:
        labels: list[str] = []
        if player_entity_entry is not None:
            labels.append("玩家实体")
        for t in list(player_template_targets or []):
            wrappers = t.get("root5_wrappers")
            if isinstance(wrappers, list):
                for w in wrappers:
                    if not isinstance(w, dict):
                        continue
                    name = extract_instance_entry_name_from_root4_5_1_entry(w) or "<玩家模板>"
                    labels.append(f"玩家模板:{name}")
            e4 = t.get("root4_entry")
            if isinstance(e4, dict):
                names = t.get("template_names")
                label_name = ""
                if isinstance(names, list) and names:
                    label_name = str(names[0])
                labels.append(f"玩家模板(模板段):{label_name}" if label_name else "玩家模板(模板段)")
        if not labels and role_editor_entry is not None:
            labels.append("默认模版(角色编辑)")
        seen: set[str] = set()
        deduped: list[str] = []
        for x in labels:
            k = str(x)
            if k in seen:
                continue
            seen.add(k)
            deduped.append(k)
        return deduped

    scalar_refs: set[tuple[str, str]] = set()
    dict_key_paths_by_var: Dict[tuple[str, str], set[tuple[str, ...]]] = {}
    for group_name, var_name, field_path in variable_refs:
        g = str(group_name or "").strip()
        n = str(var_name or "").strip()
        fp = tuple(str(x) for x in (field_path or ()))
        if g == "" or n == "":
            continue
        if not fp:
            scalar_refs.add((g, n))
            continue
        dict_key_paths_by_var.setdefault((g, n), set()).add(fp)

    # ===== 标量：字符串变量 =====
    for group_name, var_name in sorted(scalar_refs):
        g = str(group_name or "").strip()
        n = str(var_name or "").strip()
        if g == "" or n == "":
            continue
        targets = _iter_target_entries(g)
        full_name = f"{g}.{n}"
        default_source = "builtin"
        default_value = ""
        if variable_defaults and full_name in variable_defaults:
            default_value = coerce_default_string(variable_defaults[full_name])
            default_source = "user"
        created_in: list[str] = []
        existed_in: list[str] = []
        for target_entry, group_list_key, target_label in targets:
            created = ensure_string_custom_variable_in_asset_entry(
                target_entry,
                variable_name=n,
                default_value=str(default_value),
                group_list_key=str(group_list_key),
            )
            if created:
                created_total += 1
                created_in.append(str(target_label))
            else:
                existed_total += 1
                existed_in.append(str(target_label))
        variables_report.append(
            {
                "group": g,
                "variable_name": n,
                "roles": ["text_placeholder_scalar"],
                "type_code": 6,
                "default_value": str(default_value),
                "default_value_source": default_source,
                "created": bool(created_in),
                "target_entity_name": (created_in[0] if created_in else (existed_in[0] if existed_in else "")),
                "created_in": created_in,
                "existed_in": existed_in,
            }
        )

    # ===== 字典字段路径：字典变量（{{lv.dict.key}}）=====
    def _infer_value_type_int_by_suffix(var_name: str) -> int:
        lowered = str(var_name or "").strip().lower()
        if lowered.endswith(("_int", "_i")):
            return 3
        if lowered.endswith(("_float", "_f")):
            return 5
        if lowered.endswith(("_text", "_str", "_s")):
            return 6
        return 0

    def _infer_value_type_int_from_default_values(default_map: dict) -> int:
        # 仅支持：int / float / str
        kinds: set[int] = set()
        for v in default_map.values():
            if isinstance(v, bool):
                continue
            if isinstance(v, int):
                kinds.add(3)
                continue
            if isinstance(v, float):
                kinds.add(5)
                continue
            if isinstance(v, str):
                kinds.add(6)
                continue
            if v is None:
                continue
        if not kinds:
            return 0
        if len(kinds) != 1:
            raise ValueError(
                f"文本占位符字典默认值类型混杂，无法写回单一 value_type：kinds={sorted(kinds)}（请将不同类型拆分为多个字典变量，例如 *_text / *_int）。"
            )
        return list(kinds)[0]

    for (group_name, dict_var_name), key_paths in sorted(dict_key_paths_by_var.items()):
        g = str(group_name or "").strip()
        n = str(dict_var_name or "").strip()
        if g == "" or n == "":
            continue
        targets = _iter_target_entries(g)

        keys_used = sorted({".".join(path) for path in key_paths if path and all(str(x).strip() for x in path)})
        if not keys_used:
            continue

        full_name = f"{g}.{n}"
        raw_default_obj = variable_defaults.get(full_name) if (variable_defaults and full_name in variable_defaults) else None
        default_map_by_key: dict[str, Any] = raw_default_obj if isinstance(raw_default_obj, dict) else {}

        value_type_int = _infer_value_type_int_by_suffix(n)
        inferred_by_default = _infer_value_type_int_from_default_values(default_map_by_key) if default_map_by_key else 0
        if value_type_int == 0:
            value_type_int = inferred_by_default
        if value_type_int == 0:
            value_type_int = 6

        if value_type_int not in (3, 5, 6):
            raise ValueError(f"暂不支持该文本占位符字典 value_type：{value_type_int}（variable={n!r}）")

        default_value_by_key: dict[str, Any] = {}
        for k in keys_used:
            if k in default_map_by_key:
                default_value_by_key[k] = default_map_by_key[k]
                continue
            if value_type_int == 3:
                default_value_by_key[k] = 0
            elif value_type_int == 5:
                default_value_by_key[k] = 0.0
            else:
                default_value_by_key[k] = ""

        # legacy 清理策略：与旧实现保持一致
        extra_legacy_prefixes: list[str] = []
        lowered_name = n.lower()
        base_name = ""
        if lowered_name.endswith("_text") or lowered_name.endswith("_int") or lowered_name.endswith("_float"):
            base_name = n.rsplit("_", 1)[0].strip()
        if base_name:
            base_full = f"{g}.{base_name}"
            if not (variable_defaults and base_full in variable_defaults):
                extra_legacy_prefixes.append(f"{base_name}.")

        created_in2: list[str] = []
        existed_in2: list[str] = []
        keys_added_total_sum = 0
        keys_added_total_by_target: list[dict[str, int]] = []
        for target_entry, group_list_key, target_label in targets:
            created, merged_keys_added = ensure_dict_custom_variable_in_asset_entry(
                target_entry,
                variable_name=n,
                dict_key_type_int=6,
                dict_value_type_int=int(value_type_int),
                default_value_by_key=dict(default_value_by_key),
                extra_legacy_scalar_prefixes=extra_legacy_prefixes,
                group_list_key=str(group_list_key),
            )
            keys_added_total_sum += int(merged_keys_added)
            keys_added_total_by_target.append({str(target_label): int(merged_keys_added)})
            if created:
                created_total += 1
                created_in2.append(str(target_label))
            else:
                existed_total += 1
                existed_in2.append(str(target_label))
        variables_report.append(
            {
                "group": g,
                "variable_name": n,
                "roles": ["text_placeholder_dict"],
                "type_code": 27,
                "dict_key_type": 6,
                "dict_value_type": int(value_type_int),
                "keys_total": int(len(keys_used)),
                "keys_added_total": int(keys_added_total_sum),
                "keys_added_total_by_target": keys_added_total_by_target,
                "default_value_source": "user" if isinstance(raw_default_obj, dict) else "builtin",
                "created": bool(created_in2),
                "target_entity_name": (created_in2[0] if created_in2 else (existed_in2[0] if existed_in2 else "")),
                "created_in": created_in2,
                "existed_in": existed_in2,
            }
        )

    return {
        "created_total": int(created_total),
        "existed_total": int(existed_total),
        "targets": {"关卡": ["关卡实体"], "玩家自身": _build_player_targets_labels_no_raise()},
        "variables": variables_report,
    }

