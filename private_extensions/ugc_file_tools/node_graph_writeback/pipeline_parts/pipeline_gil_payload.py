from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from ..gil_dump import _first_dict


def _extract_graph_id_int_from_graph_entry(entry: Dict[str, Any]) -> Optional[int]:
    header = _first_dict(entry.get("1"))
    if not isinstance(header, dict):
        return None
    value = header.get("5")
    if isinstance(value, int):
        return int(value)
    if isinstance(value, dict):
        inner = value.get("int")
        if isinstance(inner, int):
            return int(inner)
    return None


def _remove_existing_graph_entries_by_graph_id_inplace(*, groups_list: list[Any], graph_id_int: int) -> Tuple[int, int]:
    """
    在 section['1'](groups) 中删除 header.graph_id == graph_id_int 的旧 GraphEntry。
    返回 (removed_entries_count, removed_groups_count)。
    """
    target_graph_id = int(graph_id_int)
    removed_entries_count = 0
    removed_groups_count = 0
    kept_groups: list[Any] = []

    for group in list(groups_list):
        if not isinstance(group, dict):
            kept_groups.append(group)
            continue

        entries_value = group.get("1")
        single_entry_container = False
        if isinstance(entries_value, list):
            entries_list = list(entries_value)
        elif isinstance(entries_value, dict):
            entries_list = [entries_value]
            single_entry_container = True
        else:
            kept_groups.append(group)
            continue

        kept_entries: list[Any] = []
        for entry in list(entries_list):
            if isinstance(entry, dict):
                existing_graph_id = _extract_graph_id_int_from_graph_entry(entry)
                if isinstance(existing_graph_id, int) and int(existing_graph_id) == int(target_graph_id):
                    removed_entries_count += 1
                    continue
            kept_entries.append(entry)

        if kept_entries:
            if len(kept_entries) != len(entries_list):
                if bool(single_entry_container) and len(kept_entries) == 1 and isinstance(kept_entries[0], dict):
                    group["1"] = dict(kept_entries[0])
                else:
                    group["1"] = list(kept_entries)
            kept_groups.append(group)
        else:
            removed_groups_count += 1

    if removed_entries_count > 0:
        groups_list[:] = list(kept_groups)
    return int(removed_entries_count), int(removed_groups_count)


def _try_replace_existing_graph_entry_by_graph_id_inplace(
    *,
    groups_list: list[Any],
    graph_id_int: int,
    new_entry: Dict[str, Any],
) -> bool:
    """
    尝试在 section['1'](groups) 中就地替换 header.graph_id == graph_id_int 的 GraphEntry：
    - **保持 group 顺序不变**（避免 overwrite 导致 group_index 整体漂移）
    - **保持 group 自身的其它字段不变**（潜在的目录/分组元数据）

    返回：
    - True：且仅当找到 **唯一** 命中 entry 并完成就地替换；
    - False：未找到或存在重复命中（由上层决定是否走 remove+append 进行去重/重建）。
    """
    target_graph_id = int(graph_id_int)
    matches: list[tuple[Dict[str, Any], str, int]] = []

    for group in list(groups_list):
        if not isinstance(group, dict):
            continue

        entries_value = group.get("1")
        if isinstance(entries_value, dict):
            existing_graph_id = _extract_graph_id_int_from_graph_entry(entries_value)
            if isinstance(existing_graph_id, int) and int(existing_graph_id) == int(target_graph_id):
                matches.append((group, "dict", 0))
            continue

        if isinstance(entries_value, list):
            for idx, entry in enumerate(list(entries_value)):
                if not isinstance(entry, dict):
                    continue
                existing_graph_id = _extract_graph_id_int_from_graph_entry(entry)
                if isinstance(existing_graph_id, int) and int(existing_graph_id) == int(target_graph_id):
                    matches.append((group, "list", int(idx)))
            continue

    if len(matches) != 1:
        return False

    group0, kind0, index0 = matches[0]
    if kind0 == "dict":
        group0["1"] = dict(new_entry)
        return True

    if kind0 == "list":
        entries_value0 = group0.get("1")
        if not isinstance(entries_value0, list):
            return False
        entries_list0 = list(entries_value0)
        if index0 < 0 or index0 >= len(entries_list0):
            return False
        entries_list0[index0] = dict(new_entry)
        group0["1"] = entries_list0
        return True

    return False


def _bootstrap_node_graph_section_inplace(*, payload_root: Dict[str, Any]) -> Dict[str, Any]:
    """
    在 base_gil 的 payload_root 中自举创建节点图段（payload['10']），用于“空存档 → 写入节点图”的场景。

    说明：
    - 空存档通常缺失 payload['10']；
    - 这里构造一个最小可用结构（groups 为空），避免依赖 template_gil 拷贝整段元数据。
    """
    section = payload_root.get("10")
    if isinstance(section, dict):
        return section

    # 经验结构（来自真源样本）：field_10.message keys = 1/2/3/5/7
    section = {
        "1": [],  # groups
        "2": [],  # aux list（可为空）
        "3": {"1": 2, "2": {"1": "复合节点"}},  # composite nodes title（最小占位）
        "5": {"2": [], "3": []},  # composite nodes table（最小占位）
        "7": 0,  # group count（若与实际 group 数一致则可更新）
    }
    payload_root["10"] = section
    return section

