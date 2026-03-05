from __future__ import annotations

import copy
from typing import Any, Dict, Tuple

from ..gil_dump import _ensure_list, _first_dict
from .pipeline_gil_payload import (
    _remove_existing_graph_entries_by_graph_id_inplace,
    _try_replace_existing_graph_entry_by_graph_id_inplace,
)


def _try_find_existing_graph_entry_in_groups_list(*, groups: list[Any], graph_id_int: int) -> Dict[str, Any] | None:
    """在 base payload 的 groups_list 中查找指定 graph_id 的 entry；找不到返回 None（不抛错）。"""
    target = int(graph_id_int)
    for group in list(groups):
        if not isinstance(group, dict):
            continue
        entries_value = group.get("1")
        if isinstance(entries_value, list):
            entries_list = [x for x in entries_value if isinstance(x, dict)]
        elif isinstance(entries_value, dict):
            entries_list = [entries_value]
        else:
            continue
        for entry in entries_list:
            header0 = _first_dict(entry.get("1"))
            if not isinstance(header0, dict):
                continue
            gid0 = header0.get("5")
            if isinstance(gid0, int) and int(gid0) == int(target):
                return entry
    return None


def _overwrite_or_remove_existing_entry_inplace(
    *, groups_list: list[Any], graph_id_int: int, new_entry: Dict[str, Any]
) -> Tuple[bool, int, int]:
    replaced_in_place = _try_replace_existing_graph_entry_by_graph_id_inplace(
        groups_list=groups_list,
        graph_id_int=int(graph_id_int),
        new_entry=dict(new_entry),
    )
    if bool(replaced_in_place):
        return True, 1, 0
    replaced_entries, replaced_groups = _remove_existing_graph_entries_by_graph_id_inplace(
        groups_list=groups_list,
        graph_id_int=int(graph_id_int),
    )
    return False, int(replaced_entries), int(replaced_groups)


def append_new_group_from_template_inplace(
    *,
    section: Dict[str, Any],
    groups_list: list[Any],
    template_group: Dict[str, Any],
    new_entry: Dict[str, Any],
) -> None:
    """
    新增 group（保持模板 group 元数据），并尽量维持 field_7(group_count) 的“真源一致性更新策略”。
    """
    new_group: Dict[str, Any] = {}
    for key, value in template_group.items():
        if key == "1":
            continue
        new_group[str(key)] = copy.deepcopy(value)
    new_group["1"] = [new_entry]

    old_group_count = int(len([item for item in list(groups_list) if isinstance(item, dict)]))
    old_field_7 = section.get("7")
    groups_list.append(new_group)
    new_group_count = int(len([item for item in list(groups_list) if isinstance(item, dict)]))
    if isinstance(old_field_7, int) and int(old_field_7) == int(old_group_count):
        section["7"] = int(new_group_count)


def append_new_group_pure_json_inplace(*, section: Dict[str, Any], groups_list: list[Any], new_entry: Dict[str, Any]) -> None:
    groups_list.append({"1": [new_entry]})
    section["7"] = int(len([item for item in list(groups_list) if isinstance(item, dict)]))


def ensure_groups_list_in_section(*, section: Dict[str, Any]) -> list[Any]:
    return _ensure_list(section, "1")


def apply_overwrite_policy_and_append_if_needed_for_template_clone(
    *,
    section: Dict[str, Any],
    groups_list: list[Any],
    template_group: Dict[str, Any],
    allocated_graph_id: int,
    new_graph_id_int: int | None,
    new_entry: Dict[str, Any],
) -> Tuple[int, int, bool]:
    replaced_existing_graph_entries = 0
    replaced_existing_graph_groups = 0
    replaced_in_place = False

    if new_graph_id_int is not None:
        replaced_in_place, replaced_existing_graph_entries, replaced_existing_graph_groups = _overwrite_or_remove_existing_entry_inplace(
            groups_list=groups_list,
            graph_id_int=int(allocated_graph_id),
            new_entry=dict(new_entry),
        )

    if not bool(replaced_in_place):
        append_new_group_from_template_inplace(
            section=section,
            groups_list=groups_list,
            template_group=dict(template_group),
            new_entry=dict(new_entry),
        )

    return int(replaced_existing_graph_entries), int(replaced_existing_graph_groups), bool(replaced_in_place)


def apply_overwrite_policy_and_append_if_needed_for_pure_json(
    *,
    section: Dict[str, Any],
    groups_list: list[Any],
    allocated_graph_id: int,
    new_graph_id_int: int | None,
    new_entry: Dict[str, Any],
) -> Tuple[int, int, bool]:
    replaced_existing_graph_entries = 0
    replaced_existing_graph_groups = 0
    replaced_in_place = False

    if new_graph_id_int is not None:
        replaced_in_place, replaced_existing_graph_entries, replaced_existing_graph_groups = _overwrite_or_remove_existing_entry_inplace(
            groups_list=groups_list,
            graph_id_int=int(allocated_graph_id),
            new_entry=dict(new_entry),
        )

    if not bool(replaced_in_place):
        append_new_group_pure_json_inplace(section=section, groups_list=groups_list, new_entry=dict(new_entry))

    return int(replaced_existing_graph_entries), int(replaced_existing_graph_groups), bool(replaced_in_place)


__all__ = [
    "_try_find_existing_graph_entry_in_groups_list",
    "apply_overwrite_policy_and_append_if_needed_for_template_clone",
    "apply_overwrite_policy_and_append_if_needed_for_pure_json",
    "ensure_groups_list_in_section",
]

