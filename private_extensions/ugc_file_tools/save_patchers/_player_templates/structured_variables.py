from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from .common import (
    GROUP1_ID,
    GROUP1_INDEX,
    GROUP_ITEM_BOX_KEY,
    GROUP_ITEM_ID_KEY,
    GROUP_ITEM_INDEX_KEY,
    GROUP_ITEM_VAR_LIST_KEY,
    ROOT4_VARIABLE_GROUP_LIST_KEY,
    ROOT5_REF_BOX_KEY,
    ROOT5_META_LIST_KEY,
    ROOT5_VARIABLE_GROUP_LIST_KEY,
    ROOT_ENTRY_ID_KEY,
    ROLE_EDIT_SUFFIX,
    VARIABLES_PREVIEW_LIMIT,
)
from .structured_entries import (
    PlayerTemplateEntry,
    _extract_name_from_entry_meta_list,
    _find_root4_entry_index_by_id,
    _find_root5_entry_index_by_name,
    _get_root4_entries,
    _get_root5_entries,
    _is_player_template_like_root5_entry,
    _iter_root5_indices_by_ref_id,
    list_player_templates,
)

# variable def item keys (string field numbers)
VAR_DEF_NAME_KEY = "2"
VAR_DEF_TYPE_CODE_KEY = "3"
VAR_DEF_META_KEY = "4"
VAR_DEF_FLAG_KEY = "5"
VAR_DEF_TYPE_BOX_KEY = "6"

VAR_META_TYPE_CODE_KEY = "1"
VAR_META_CONCRETE_KEY = "2"

VAR_META_CONCRETE_TYPE_CODE_KEY = "1"
VAR_META_CONCRETE_EMPTY_BYTES_KEY = "2"

VAR_TYPE_BOX_TYPE_CODE_KEY = "1"
VAR_TYPE_BOX_EMPTY_BYTES_KEY = "2"

EMPTY_BYTES = b""

# type-specific default field number（来自真源样本：字符串16、字符串列表21、整数13、整数列表18、配置ID30）
DEFAULT_FIELD_BY_TYPE_CODE: Dict[int, str] = {
    1: "11",
    3: "13",
    6: "16",
    8: "18",
    11: "21",
    20: "30",
}


def _ensure_group1_variable_def_list(container_list: Any) -> List[Dict[str, Any]]:
    """确保 group1(1/1) 变量定义列表存在并返回该 list。"""
    if not isinstance(container_list, list):
        raise ValueError("variables container is not list")
    for item in container_list:
        if not isinstance(item, dict):
            continue
        if item.get(GROUP_ITEM_ID_KEY) != GROUP1_ID or item.get(GROUP_ITEM_INDEX_KEY) != GROUP1_INDEX:
            continue
        box = item.get(GROUP_ITEM_BOX_KEY)
        if box is None or isinstance(box, (bytes, bytearray)):
            box = {}
            item[GROUP_ITEM_BOX_KEY] = box
        if not isinstance(box, dict):
            raise ValueError(f"variables box is not dict: {type(box).__name__}")
        lst = box.get(GROUP_ITEM_VAR_LIST_KEY)
        if lst is None:
            box[GROUP_ITEM_VAR_LIST_KEY] = []
            return box[GROUP_ITEM_VAR_LIST_KEY]
        if isinstance(lst, dict):
            box[GROUP_ITEM_VAR_LIST_KEY] = [lst]
            return box[GROUP_ITEM_VAR_LIST_KEY]
        if isinstance(lst, list):
            return lst

    # 没有 group1 容器则创建
    new_item: Dict[str, Any] = {
        GROUP_ITEM_ID_KEY: GROUP1_ID,
        GROUP_ITEM_INDEX_KEY: GROUP1_INDEX,
        GROUP_ITEM_BOX_KEY: {GROUP_ITEM_VAR_LIST_KEY: []},
    }
    container_list.append(new_item)
    return new_item[GROUP_ITEM_BOX_KEY][GROUP_ITEM_VAR_LIST_KEY]


def _build_custom_variable_def_item(*, name: str, type_code: int, default_value: Any) -> Dict[str, Any]:
    """构造一条玩家模板的自定义变量定义 dict（用于 group1 变量列表）。"""
    tc = int(type_code)
    default_field = DEFAULT_FIELD_BY_TYPE_CODE.get(tc)
    if default_field is None:
        raise ValueError(f"暂不支持该自定义变量类型写回：type_code={tc}")

    # 默认值编码（尽量与真源一致：0/空通常用 empty bytes）
    default_payload: Any = EMPTY_BYTES
    if tc in (1, 3):
        v = int(default_value) if default_value is not None else 0
        default_payload = (EMPTY_BYTES if v == 0 else {VAR_META_TYPE_CODE_KEY: int(v)})
    elif tc == 6:
        s = str(default_value) if default_value is not None else ""
        default_payload = (EMPTY_BYTES if s == "" else {VAR_META_TYPE_CODE_KEY: s})
    elif tc == 20:
        v = int(default_value) if default_value is not None else 0
        default_payload = (
            EMPTY_BYTES if v == 0 else {VAR_META_TYPE_CODE_KEY: {VAR_META_TYPE_CODE_KEY: GROUP1_ID, GROUP_ITEM_INDEX_KEY: int(v)}}
        )
    else:
        # 列表：先只支持空默认（与真源样本一致）
        default_payload = EMPTY_BYTES

    return {
        VAR_DEF_NAME_KEY: str(name),
        VAR_DEF_TYPE_CODE_KEY: int(tc),
        VAR_DEF_META_KEY: {
            VAR_META_TYPE_CODE_KEY: int(tc),
            VAR_META_CONCRETE_KEY: {VAR_META_CONCRETE_TYPE_CODE_KEY: int(tc), VAR_META_CONCRETE_EMPTY_BYTES_KEY: EMPTY_BYTES},
            default_field: default_payload,
        },
        VAR_DEF_FLAG_KEY: GROUP1_ID,
        VAR_DEF_TYPE_BOX_KEY: {VAR_TYPE_BOX_TYPE_CODE_KEY: int(tc), VAR_TYPE_BOX_EMPTY_BYTES_KEY: EMPTY_BYTES},
    }


def add_custom_variable_to_template_inplace(
    payload_root: Dict[str, Any],
    *,
    template_name: str,
    variable_name: str,
    type_code: int,
    default_value: Any,
) -> Dict[str, Any]:
    """给玩家模板追加一条“自定义变量定义”。"""
    target = str(template_name or "").strip()
    if target == "":
        raise ValueError("template_name 不能为空")
    var_name = str(variable_name or "").strip()
    if var_name == "":
        raise ValueError("variable_name 不能为空")
    tc = int(type_code)
    if tc <= 0:
        raise ValueError(f"invalid type_code: {type_code!r}")

    root5_index = _find_root5_entry_index_by_name(payload_root, name=target)
    root5_entries = _get_root5_entries(payload_root)
    e5 = root5_entries[root5_index]
    ref_box = e5.get(ROOT5_REF_BOX_KEY)
    ref_id = ref_box.get(ROOT_ENTRY_ID_KEY) if isinstance(ref_box, dict) else None
    if not isinstance(ref_id, int):
        raise ValueError(f"模板 {target!r} 缺少 root4 引用：entry['2']['1']")
    root4_index = _find_root4_entry_index_by_id(payload_root, entry_id=int(ref_id))
    root4_entries = _get_root4_entries(payload_root)
    e4 = root4_entries[root4_index]

    vlist5 = _ensure_group1_variable_def_list(e5.setdefault(ROOT5_VARIABLE_GROUP_LIST_KEY, []))
    vlist4 = _ensure_group1_variable_def_list(e4.setdefault(ROOT4_VARIABLE_GROUP_LIST_KEY, []))

    for item in vlist5:
        if isinstance(item, dict) and str(item.get(VAR_DEF_NAME_KEY) or "").strip() == var_name:
            return {
                "template_name": target,
                "variable_name": var_name,
                "created": False,
                "reason": "already_exists",
                "root5_index": int(root5_index),
                "root4_entry_id": int(ref_id),
            }

    new_item = _build_custom_variable_def_item(name=var_name, type_code=int(tc), default_value=default_value)
    vlist5.append(dict(new_item))
    vlist4.append(dict(new_item))

    # 同步到所有引用同一 root4 的 wrapper，保持一致
    ref_indices = _iter_root5_indices_by_ref_id(payload_root, ref_id=int(ref_id))
    updated_wrappers: List[int] = []
    for i in ref_indices:
        wrapper = root5_entries[i]
        if wrapper is e5:
            updated_wrappers.append(int(i))
            continue
        if not isinstance(wrapper, dict):
            continue
        vlist_other = _ensure_group1_variable_def_list(wrapper.setdefault(ROOT5_VARIABLE_GROUP_LIST_KEY, []))
        exists = any(isinstance(it, dict) and str(it.get(VAR_DEF_NAME_KEY) or "").strip() == var_name for it in vlist_other)
        if not exists:
            vlist_other.append(dict(new_item))
        updated_wrappers.append(int(i))

    return {
        "template_name": target,
        "variable_name": var_name,
        "type_code": int(tc),
        "default_value": default_value,
        "created": True,
        "root5_index": int(root5_index),
        "root4_entry_id": int(ref_id),
        "updated_root5_wrappers_total": int(len(updated_wrappers)),
        "updated_root5_wrappers": updated_wrappers,
    }


def _find_player_template_entry_by_name(payload_root: Dict[str, Any], *, template_name: str) -> PlayerTemplateEntry:
    """按模板名定位唯一的玩家模板条目（基于 list_player_templates 的去重视图）。"""
    target = str(template_name or "").strip()
    if target == "":
        raise ValueError("template_name 不能为空")

    entries = list_player_templates(payload_root)
    hits = [t for t in entries if str(t.name) == target]
    if not hits:
        available = [t.name for t in entries]
        raise ValueError(f"未找到玩家模板：{target!r}（available={available!r}）")
    if len(hits) > 1:
        ids = [int(t.root4_entry_id) for t in hits]
        raise ValueError(f"存在多个同名玩家模板：{target!r}（root4_entry_ids={ids!r}）")
    return hits[0]


def _extract_group1_variable_def_items(group_list: Any) -> List[Dict[str, Any]]:
    """
    从 root5['7']/root4['8'] 的 group_list 中提取 group1(1/1) 的变量定义列表（dict item）。

    group1 容器形态（与 add_custom_variable_to_template_inplace 的写回一致）：
    - list item：item['1']==1 && item['2']==1
    - item['11']['1']：变量定义列表（list 或 dict）
    """
    if not isinstance(group_list, list):
        return []

    for item in group_list:
        if not isinstance(item, dict):
            continue
        if item.get(GROUP_ITEM_ID_KEY) != GROUP1_ID or item.get(GROUP_ITEM_INDEX_KEY) != GROUP1_INDEX:
            continue
        box = item.get(GROUP_ITEM_BOX_KEY)
        if not isinstance(box, dict):
            return []
        lst = box.get(GROUP_ITEM_VAR_LIST_KEY)
        if lst is None:
            return []
        if isinstance(lst, dict):
            return [dict(lst)]
        if isinstance(lst, list):
            return [dict(x) for x in lst if isinstance(x, dict)]
        return []

    return []


def _extract_group1_variable_names(group_list: Any) -> List[str]:
    """从 group_list 中提取 group1 变量名列表（按出现顺序）。"""
    items = _extract_group1_variable_def_items(group_list)
    out: List[str] = []
    for it in items:
        name = it.get(VAR_DEF_NAME_KEY)
        if isinstance(name, str) and name.strip():
            out.append(str(name).strip())
    return out


def copy_template_custom_variable_defs_inplace(
    dst_payload_root: Dict[str, Any],
    *,
    dst_template_name: str,
    src_payload_root: Dict[str, Any],
    src_template_name: str,
) -> Dict[str, Any]:
    """
    将 src 模板上的“自定义变量定义（group1）”拷贝到 dst 模板（写回 root5['7'] 与 root4['8']）。

    说明：
    - 以模板名定位条目（基于 list_player_templates 的 root4 去重视图，避免 root5 同名 wrapper 导致歧义）。
    - 同步更新所有引用同一 root4_entry_id 的 root5 wrapper，避免出现不一致。
    """
    src_name = str(src_template_name or "").strip()
    dst_name = str(dst_template_name or "").strip()
    if src_name == "":
        raise ValueError("src_template_name 不能为空")
    if dst_name == "":
        raise ValueError("dst_template_name 不能为空")

    src_entry = _find_player_template_entry_by_name(src_payload_root, template_name=src_name)
    dst_entry = _find_player_template_entry_by_name(dst_payload_root, template_name=dst_name)

    src_root5_entries = _get_root5_entries(src_payload_root)
    src_root4_entries = _get_root4_entries(src_payload_root)
    dst_root5_entries = _get_root5_entries(dst_payload_root)
    dst_root4_entries = _get_root4_entries(dst_payload_root)

    src_e5 = src_root5_entries[int(src_entry.root5_index)]
    src_e4 = src_root4_entries[int(src_entry.root4_index)]

    # 深拷贝：避免引用同一 dict/list 导致后续写回互相污染
    src_group7 = copy.deepcopy(src_e5.get(ROOT5_VARIABLE_GROUP_LIST_KEY))
    src_group8 = copy.deepcopy(src_e4.get(ROOT4_VARIABLE_GROUP_LIST_KEY))

    src_var_names = _extract_group1_variable_names(src_group7)
    if not src_var_names:
        raise ValueError(f"源模板未找到任何 group1 变量定义：template={src_name!r}")

    dst_before_names = _extract_group1_variable_names(dst_root5_entries[int(dst_entry.root5_index)].get(ROOT5_VARIABLE_GROUP_LIST_KEY))

    # root4: template body
    dst_e4 = dst_root4_entries[int(dst_entry.root4_index)]
    if src_group8 is None:
        dst_e4.pop(ROOT4_VARIABLE_GROUP_LIST_KEY, None)
    else:
        dst_e4[ROOT4_VARIABLE_GROUP_LIST_KEY] = copy.deepcopy(src_group8)

    # root5: all wrappers referencing same root4_entry_id
    ref_indices = _iter_root5_indices_by_ref_id(dst_payload_root, ref_id=int(dst_entry.root4_entry_id))
    updated_wrappers: List[int] = []
    skipped_wrappers: List[int] = []
    for i in ref_indices:
        wrapper = dst_root5_entries[int(i)]
        if not isinstance(wrapper, dict):
            skipped_wrappers.append(int(i))
            continue
        if not _is_player_template_like_root5_entry(wrapper):
            skipped_wrappers.append(int(i))
            continue
        name = _extract_name_from_entry_meta_list(wrapper.get(ROOT5_META_LIST_KEY))
        if name.endswith(ROLE_EDIT_SUFFIX):
            skipped_wrappers.append(int(i))
            continue
        if str(name) != dst_name:
            skipped_wrappers.append(int(i))
            continue

        if src_group7 is None:
            wrapper.pop(ROOT5_VARIABLE_GROUP_LIST_KEY, None)
        else:
            wrapper[ROOT5_VARIABLE_GROUP_LIST_KEY] = copy.deepcopy(src_group7)
        updated_wrappers.append(int(i))

    dst_after_names = _extract_group1_variable_names(dst_root5_entries[int(dst_entry.root5_index)].get(ROOT5_VARIABLE_GROUP_LIST_KEY))

    return {
        "src_template_name": src_name,
        "dst_template_name": dst_name,
        "src_vars_total": int(len(src_var_names)),
        "src_vars_preview": src_var_names[:VARIABLES_PREVIEW_LIMIT],
        "dst_before_vars_total": int(len(dst_before_names)),
        "dst_before_vars_preview": dst_before_names[:VARIABLES_PREVIEW_LIMIT],
        "dst_after_vars_total": int(len(dst_after_names)),
        "dst_after_vars_preview": dst_after_names[:VARIABLES_PREVIEW_LIMIT],
        "dst_root4_entry_id": int(dst_entry.root4_entry_id),
        "updated_root5_wrappers_total": int(len(updated_wrappers)),
        "updated_root5_wrappers": updated_wrappers,
        "skipped_root5_wrappers_total": int(len(skipped_wrappers)),
        "skipped_root5_wrappers": skipped_wrappers,
    }


def _build_player_template_custom_variable_def_item(*, name: str, type_code: int, default_value: Any) -> Dict[str, Any]:
    """
    构造“玩家模板自定义变量定义”条目（可写入 root5['7'] / root4['8'] 的 group1 变量列表）。

    约定：默认值字段号 = type_code + 10（与真源样本一致）。
    """
    var_name = str(name or "").strip()
    if var_name == "":
        raise ValueError("variable name 不能为空")

    tc = int(type_code)
    if tc <= 0:
        raise ValueError(f"invalid type_code: {type_code!r}")

    default_field = str(int(tc) + 10)

    # 默认值编码（尽量对齐真源：零/空/None 常用 empty bytes 表达）
    default_payload: Any = EMPTY_BYTES
    if tc in (1, 2, 3):
        v = int(default_value) if default_value is not None else 0
        default_payload = (EMPTY_BYTES if int(v) == 0 else {VAR_META_TYPE_CODE_KEY: int(v)})
    elif tc == 6:
        s = str(default_value) if default_value is not None else ""
        default_payload = (EMPTY_BYTES if s == "" else {VAR_META_TYPE_CODE_KEY: s})
    elif tc in (8, 11):
        # 列表：当前仅强支持空默认（与常见真源样本一致）
        if default_value is None:
            default_payload = EMPTY_BYTES
        elif isinstance(default_value, list) and len(default_value) == 0:
            default_payload = EMPTY_BYTES
        else:
            raise ValueError(f"列表类型默认值暂不支持非空写回：type_code={tc} default_value={default_value!r}")
    elif tc == 20:
        v = int(default_value) if default_value is not None else 0
        default_payload = (
            EMPTY_BYTES if int(v) == 0 else {VAR_META_TYPE_CODE_KEY: {VAR_META_TYPE_CODE_KEY: GROUP1_ID, GROUP_ITEM_INDEX_KEY: int(v)}}
        )
    else:
        raise ValueError(f"暂不支持该自定义变量类型写回：type_code={tc}")

    return {
        VAR_DEF_NAME_KEY: str(var_name),
        VAR_DEF_TYPE_CODE_KEY: int(tc),
        VAR_DEF_META_KEY: {
            VAR_META_TYPE_CODE_KEY: int(tc),
            VAR_META_CONCRETE_KEY: {VAR_META_CONCRETE_TYPE_CODE_KEY: int(tc), VAR_META_CONCRETE_EMPTY_BYTES_KEY: EMPTY_BYTES},
            default_field: default_payload,
        },
        VAR_DEF_FLAG_KEY: GROUP1_ID,
        VAR_DEF_TYPE_BOX_KEY: {VAR_TYPE_BOX_TYPE_CODE_KEY: int(tc), VAR_TYPE_BOX_EMPTY_BYTES_KEY: EMPTY_BYTES},
    }


def _replace_group1_var_defs_in_group_list(group_list: Any, *, var_def_items: List[Dict[str, Any]]) -> List[Any]:
    """将 group_list 中的 group1(1/1) 变量列表替换为指定 items（保留其它 group）。"""
    out: List[Any] = []
    if isinstance(group_list, list):
        for item in group_list:
            if isinstance(item, dict) and item.get(GROUP_ITEM_ID_KEY) == GROUP1_ID and item.get(GROUP_ITEM_INDEX_KEY) == GROUP1_INDEX:
                continue
            out.append(copy.deepcopy(item))
    elif isinstance(group_list, dict):
        if not (group_list.get(GROUP_ITEM_ID_KEY) == GROUP1_ID and group_list.get(GROUP_ITEM_INDEX_KEY) == GROUP1_INDEX):
            out.append(copy.deepcopy(group_list))
    elif group_list is None or isinstance(group_list, (bytes, bytearray)):
        out = []
    else:
        raise ValueError(f"group_list 结构异常（期望 list/dict/bytes/None）：{type(group_list).__name__}")

    out.append(
        {
            GROUP_ITEM_ID_KEY: GROUP1_ID,
            GROUP_ITEM_INDEX_KEY: GROUP1_INDEX,
            GROUP_ITEM_BOX_KEY: {GROUP_ITEM_VAR_LIST_KEY: [dict(x) for x in list(var_def_items or [])]},
        }
    )
    return out


def set_template_custom_variable_defs_inplace(
    payload_root: Dict[str, Any],
    *,
    template_name: str,
    variables: List[Tuple[str, int, Any]],
) -> Dict[str, Any]:
    """
    以“变量规格列表”覆盖指定玩家模板的自定义变量定义（group1）。

    - 写回：root5['7'] 与 root4['8']
    - 同步更新：所有引用同一 root4_entry_id 的 root5 wrapper（避免不一致）
    """
    target = str(template_name or "").strip()
    if target == "":
        raise ValueError("template_name 不能为空")

    entry = _find_player_template_entry_by_name(payload_root, template_name=target)
    root5_entries = _get_root5_entries(payload_root)
    root4_entries = _get_root4_entries(payload_root)

    e5_rep = root5_entries[int(entry.root5_index)]
    e4 = root4_entries[int(entry.root4_index)]

    before_names = _extract_group1_variable_names(e5_rep.get(ROOT5_VARIABLE_GROUP_LIST_KEY))

    # build var def items (keep input order; validate uniqueness)
    seen: set[str] = set()
    var_def_items: List[Dict[str, Any]] = []
    for name, type_code, default_value in list(variables or []):
        nm = str(name or "").strip()
        if nm == "":
            raise ValueError("variables 中存在空 variable_name")
        if nm in seen:
            raise ValueError(f"variables 存在重复 variable_name：{nm!r}")
        seen.add(nm)
        var_def_items.append(
            _build_player_template_custom_variable_def_item(name=nm, type_code=int(type_code), default_value=default_value)
        )

    if not var_def_items:
        raise ValueError("variables 不能为空（至少需要 1 个变量定义）")

    new_group7 = _replace_group1_var_defs_in_group_list(e5_rep.get(ROOT5_VARIABLE_GROUP_LIST_KEY), var_def_items=var_def_items)
    new_group8 = _replace_group1_var_defs_in_group_list(e4.get(ROOT4_VARIABLE_GROUP_LIST_KEY), var_def_items=var_def_items)
    e5_rep[ROOT5_VARIABLE_GROUP_LIST_KEY] = new_group7
    e4[ROOT4_VARIABLE_GROUP_LIST_KEY] = new_group8

    ref_indices = _iter_root5_indices_by_ref_id(payload_root, ref_id=int(entry.root4_entry_id))
    updated_wrappers: List[int] = []
    skipped_wrappers: List[int] = []
    for i in ref_indices:
        wrapper = root5_entries[int(i)]
        if not isinstance(wrapper, dict):
            skipped_wrappers.append(int(i))
            continue
        if not _is_player_template_like_root5_entry(wrapper):
            skipped_wrappers.append(int(i))
            continue
        name = _extract_name_from_entry_meta_list(wrapper.get(ROOT5_META_LIST_KEY))
        if name.endswith(ROLE_EDIT_SUFFIX):
            skipped_wrappers.append(int(i))
            continue
        if str(name) != target:
            skipped_wrappers.append(int(i))
            continue
        wrapper[ROOT5_VARIABLE_GROUP_LIST_KEY] = copy.deepcopy(new_group7)
        updated_wrappers.append(int(i))

    after_names = _extract_group1_variable_names(e5_rep.get(ROOT5_VARIABLE_GROUP_LIST_KEY))

    return {
        "template_name": target,
        "before_vars_total": int(len(before_names)),
        "before_vars_preview": before_names[:VARIABLES_PREVIEW_LIMIT],
        "after_vars_total": int(len(after_names)),
        "after_vars_preview": after_names[:VARIABLES_PREVIEW_LIMIT],
        "root4_entry_id": int(entry.root4_entry_id),
        "updated_root5_wrappers_total": int(len(updated_wrappers)),
        "updated_root5_wrappers": updated_wrappers,
        "skipped_root5_wrappers_total": int(len(skipped_wrappers)),
        "skipped_root5_wrappers": skipped_wrappers,
    }

