from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    get_children_guids_from_parent_record as _get_children_guids_from_parent_record,
    set_children_guids_to_parent_record as _set_children_guids_to_parent_record,
    set_rect_transform_layer as _set_rect_transform_layer,
    try_extract_rect_transform_layer as _try_extract_rect_transform_layer,
)
from .web_ui_import_item_display import find_item_display_binding_message_node, find_item_display_blob
from .web_ui_import_component_groups import ComponentGroupsState
from .web_ui_import_context import WebUiImportContext
from .web_ui_import_rect import try_extract_textbox_text_node


def finalize_component_groups(
    ctx: WebUiImportContext,
    *,
    groups: ComponentGroupsState,
    group_child_entries: Dict[str, List[Tuple[int, int, int]]],
    import_order_by_guid: Dict[int, int],
) -> Tuple[int, int]:
    # --- finalize component groups: set group.children + ensure grouped children not in layout.children
    grouped_components_total = 0
    grouped_component_children_total = 0
    if not groups.group_records:
        return 0, 0

    record_by_guid_now: Dict[int, Dict[str, Any]] = {}
    for rec in ctx.ui_record_list:
        if not isinstance(rec, dict):
            continue
        g = rec.get("501")
        # 兼容：部分 record 的 guid 字段可能是 repeated(list[int]) 形态；这里取“第一个 int”作为主 guid 建索引。
        if isinstance(g, int):
            record_by_guid_now[int(g)] = rec
        elif isinstance(g, list):
            for item in g:
                if isinstance(item, int):
                    record_by_guid_now[int(item)] = rec
                    break

    grouped_child_guids_all: set[int] = set()
    for gk, grp in groups.group_records.items():
        group_guid_value = groups.group_guids.get(gk)
        if not isinstance(group_guid_value, int) or int(group_guid_value) <= 0:
            continue

        # 组 children 的“主来源”应当来自本次导入的归属记录（按 ui_key->group_key 推导的结果）。
        # 同时再做一次 parent 扫描兜底：若某个控件已经把 parent(504) 改成 group_guid，但漏记进 entries，也要补上，
        # 否则会出现“有 parent 但不在 children 列表 → 游戏里不展示”。
        entries2: List[Tuple[int, int, int]] = []
        seen_child: set[int] = set()

        for layer_v, order_v, guid_v in (group_child_entries.get(gk) or []):
            gid = int(guid_v)
            if gid in seen_child:
                continue
            seen_child.add(gid)
            entries2.append((int(layer_v), int(order_v), gid))

        for guid_value, order_value in import_order_by_guid.items():
            gid = int(guid_value)
            if gid in seen_child:
                continue
            rec = record_by_guid_now.get(gid)
            if not isinstance(rec, dict):
                continue
            parent_value = rec.get("504")
            if not isinstance(parent_value, int) or int(parent_value) != int(group_guid_value):
                continue
            layer_value = _try_extract_rect_transform_layer(rec)
            layer_int = int(layer_value) if isinstance(layer_value, int) else 0
            entries2.append((layer_int, int(order_value), gid))
            seen_child.add(gid)

        # --- 关键：按钮“文字层级”修正（sibling 顺序 + layer 双保险）
        # 某些“文字按钮”在 Web 导出时会同时包含 TextBox（文字）与 ItemDisplay（可交互锚点）。
        # 若仅按 RectTransform.layer 排序，ItemDisplay 可能被排到最上层，遮挡/压制文字（层级面板顺序也会反直觉）。
        # 规则：当一个组同时存在 TextBox 与 ItemDisplay 时：
        # - 强制把 ItemDisplay 放到该组 children 的最底部（排序最后）；
        # - 并把 ItemDisplay 的 RectTransform.layer 下调到“组内最小 layer - 1”，避免遮挡文字/边框。
        # 其余控件仍按 layer desc + 导入顺序稳定排序。
        has_textbox = False
        has_item_display = False
        for _layer_v, _order_v, gid in entries2:
            rec = record_by_guid_now.get(int(gid))
            if not isinstance(rec, dict):
                continue
            if try_extract_textbox_text_node(rec) is not None:
                has_textbox = True
            if find_item_display_blob(rec) is not None or find_item_display_binding_message_node(rec) is not None:
                has_item_display = True
            if has_textbox and has_item_display:
                break

        def sort_key(t: Tuple[int, int, int]) -> Tuple[int, int, int]:
            layer_v, order_v, gid = t
            if has_textbox and has_item_display:
                rec = record_by_guid_now.get(int(gid))
                if isinstance(rec, dict) and (
                    find_item_display_blob(rec) is not None or find_item_display_binding_message_node(rec) is not None
                ):
                    # 极大 layer：确保 ItemDisplay 最后
                    return (10**9, int(order_v), int(gid))
            return (-int(layer_v), int(order_v), int(gid))

        entries2.sort(key=sort_key)
        ordered_guids = [int(g) for _layer, _order, g in entries2]

        # 在确定 children 顺序后，再做一次 layer 修正（用 record 内的真实 layer 计算，避免依赖 widget 层的临时值）
        if has_textbox and has_item_display:
            non_item_min_layer: int | None = None
            item_display_guids2: List[int] = []
            for gid in ordered_guids:
                rec = record_by_guid_now.get(int(gid))
                if not isinstance(rec, dict):
                    continue
                if find_item_display_blob(rec) is not None or find_item_display_binding_message_node(rec) is not None:
                    item_display_guids2.append(int(gid))
                    continue
                layer_v2 = _try_extract_rect_transform_layer(rec)
                layer_int2 = int(layer_v2) if isinstance(layer_v2, int) else 0
                if non_item_min_layer is None or layer_int2 < non_item_min_layer:
                    non_item_min_layer = layer_int2
            if non_item_min_layer is None:
                non_item_min_layer = 0
            target_layer2 = int(non_item_min_layer) - 1
            if target_layer2 < 0:
                target_layer2 = 0
            for gid in item_display_guids2:
                rec = record_by_guid_now.get(int(gid))
                if not isinstance(rec, dict):
                    continue
                _set_rect_transform_layer(rec, int(target_layer2))

        _set_children_guids_to_parent_record(grp, ordered_guids)
        grouped_components_total += 1
        grouped_component_children_total += int(len(ordered_guids))
        for g in ordered_guids:
            grouped_child_guids_all.add(int(g))

    # 保险：从 layout.children 中剔除所有“已归属到组容器”的 child guid
    if grouped_child_guids_all:
        layout_children_now = _get_children_guids_from_parent_record(ctx.layout_record)
        new_layout_children = [int(g) for g in layout_children_now if int(g) not in grouped_child_guids_all]
        if new_layout_children != layout_children_now:
            _set_children_guids_to_parent_record(ctx.layout_record, new_layout_children)

    return int(grouped_components_total), int(grouped_component_children_total)

