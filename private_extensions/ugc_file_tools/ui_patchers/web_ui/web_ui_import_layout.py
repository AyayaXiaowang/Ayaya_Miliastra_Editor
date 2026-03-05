from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.ui_parsers.progress_bars import find_progressbar_binding_blob as _find_progressbar_binding_blob

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    find_record_by_guid as _find_record_by_guid,
    get_children_guids_from_parent_record as _get_children_guids_from_parent_record,
    set_children_guids_to_parent_record as _set_children_guids_to_parent_record,
    try_extract_rect_transform_layer as _try_extract_rect_transform_layer,
)
from .web_ui_import_rect import has_rect_transform_state, try_extract_rect_transform_from_state, try_extract_widget_name
from .web_ui_import_grouping import is_group_container_record_shape


def reorder_layout_children_by_layer_desc(
    *,
    layout_record: Dict[str, Any],
    ui_record_list: List[Any],
) -> Dict[str, Any]:
    """
    调整 layout_record 的 children 顺序：layer 越大（越前景），越靠前。
    仅改变 children guid 列表顺序，不修改任何控件层级数值。
    """
    children = _get_children_guids_from_parent_record(layout_record)
    if not children:
        return {"reordered": False, "children_total": 0}

    items: List[Tuple[int, int, int, int]] = []  # (overlay_priority, -layer_sort, original_index, guid)
    missing_layer_total = 0
    for idx, guid in enumerate(children):
        record = _find_record_by_guid(ui_record_list, int(guid))
        layer_value: Optional[int] = None
        overlay_priority = 0
        if isinstance(record, dict):
            layer_value = _try_extract_rect_transform_layer(record)
            if layer_value is None:
                # 兼容：组容器自身没有 RectTransform.layer（参考“打组.gil/全是进度条组合.gil”），
                # 但它的 children 具有 layer。排序时用 “max child layer” 作为该组的有效 layer，
                # 避免把整组推到排序末尾导致遮挡顺序异常（表现为“游戏里看起来少了很多”）。
                try_children = _get_children_guids_from_parent_record(record)
                if try_children:
                    child_layers: List[int] = []
                    for child_guid in try_children:
                        child_record = _find_record_by_guid(ui_record_list, int(child_guid))
                        if not isinstance(child_record, dict):
                            continue
                        child_layer = _try_extract_rect_transform_layer(child_record)
                        if isinstance(child_layer, int):
                            child_layers.append(int(child_layer))
                    if child_layers:
                        layer_value = max(child_layers)
                name = try_extract_widget_name(record)
                if isinstance(name, str) and name.startswith("组件组_通关标记_"):
                    # 避免“表里顺序”被压到最底部：通关标记组在同层级中应更靠前
                    overlay_priority = -1
        if layer_value is None:
            missing_layer_total += 1
            layer_sort = -10**9
        else:
            layer_sort = int(layer_value)
        items.append((int(overlay_priority), -int(layer_sort), int(idx), int(guid)))

    new_children = [guid for _overlay_p, _neg_layer, _idx, guid in sorted(items, key=lambda t: (t[0], t[1], t[2]))]
    if new_children == children:
        return {"reordered": False, "children_total": int(len(children)), "missing_layer_total": int(missing_layer_total)}

    _set_children_guids_to_parent_record(layout_record, new_children)
    return {"reordered": True, "children_total": int(len(children)), "missing_layer_total": int(missing_layer_total)}


def find_progressbar_binding_message_node(record: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    兼容某些存档的进度条绑定结构：并非 `<binary_data>` blob，而是已经展开为 dict message 的形态。

    识别策略（尽量保守）：
    - 在 record 的 component_list(505) 中找到 component['503']['20'] 为 dict
    - 且该 dict 至少包含一个变量绑定槽位（504/505/506），其值为 dict 且包含 group_id(501:int)
    """
    component_list = record.get("505")
    if not isinstance(component_list, list):
        return None
    for i, component in enumerate(component_list):
        if not isinstance(component, dict):
            continue
        nested = component.get("503")
        if not isinstance(nested, dict):
            continue
        node20 = nested.get("20")
        if not isinstance(node20, dict):
            continue

        has_any_binding = False
        for key in ("504", "505", "506"):
            item = node20.get(key)
            if isinstance(item, dict) and isinstance(item.get("501"), int):
                has_any_binding = True
                break
        if not has_any_binding:
            continue

        return f"505/[{i}]/503/20(message)", node20
    return None


def should_skip_cloning_base_layout_child(record: Dict[str, Any]) -> Optional[str]:
    """
    新建布局克隆固有 children 时的过滤规则。

    目标：保留“固有 HUD 控件”，但过滤掉 base `.gil` 内仅用于演示/样式的控件，避免每次导入都带上“无意义的示例控件”。
    """
    name = try_extract_widget_name(record)
    # 关键：跳过“纯组容器”record（Web 导入的组件组容器，或历史打组产物）。
    #
    # 原因：
    # - 组容器 record 自身可能包含 children(varint stream)，其 children 指向布局内的具体控件 GUID；
    # - 若把组容器当作“固有内容”进行 clone_children（只克隆第一层 children record），
    #   会导致“新布局的组容器”仍引用旧 GUID（上一页控件），产生跨布局串页与 parent/children 不一致。
    # - 因此：clone base_layout 时不克隆纯组容器，仅保留真正的可放置 HUD 控件（通常带 RectTransform）。
    if is_group_container_record_shape(record):
        return "skip_group_container_record_shape"
    # 样本（进度条样式.gil）：基底布局 children 末尾包含 3 个名为“进度条”的示例控件，并非固有 HUD。
    # 若不过滤，会导致任何新布局都自带这 3 个“进度条”实例（用户侧会误以为是导入产物的一部分）。
    if name == "进度条" and (_find_progressbar_binding_blob(record) is not None or find_progressbar_binding_message_node(record) is not None):
        return "skip_base_sample_progressbars_named_进度条"
    return None


def looks_like_template_library_entry(record: Dict[str, Any]) -> bool:
    # 模板库条目的典型特征（见 ui_patchers/claude.md）：
    # - record['502'] 为 repeated dict
    # - 且某些条目包含 '13'，其内部的 field_501(varint) 指向 template_root_guid
    items = record.get("502")
    if not isinstance(items, list):
        return False
    for it in items:
        if isinstance(it, dict) and "13" in it:
            return True
    return False


def has_any_children(record: Dict[str, Any]) -> bool:
    return bool(_get_children_guids_from_parent_record(record))


def prefer_center_pivot_and_fixed_anchor_score(record: Dict[str, Any]) -> int:
    # prefer center pivot/anchor if present (but not required)
    score = 0
    t0 = try_extract_rect_transform_from_state(record, state_index=0)
    if isinstance(t0, dict):
        pivot = t0.get("506")
        if isinstance(pivot, dict):
            px = pivot.get("501")
            py = pivot.get("502")
            if isinstance(px, (int, float)) and isinstance(py, (int, float)) and float(px) == 0.5 and float(py) == 0.5:
                score += 2
        anchor_min = t0.get("502")
        anchor_max = t0.get("503")
        if isinstance(anchor_min, dict) and isinstance(anchor_max, dict):
            ax = anchor_min.get("501")
            ay = anchor_min.get("502")
            bx = anchor_max.get("501")
            by = anchor_max.get("502")
            if (
                isinstance(ax, (int, float))
                and isinstance(ay, (int, float))
                and isinstance(bx, (int, float))
                and isinstance(by, (int, float))
                and float(ax) == float(bx)
                and float(ay) == float(by)
            ):
                score += 1
    return score


def is_record_child_of_any_parent(ui_record_list: List[Any], guid: int) -> bool:
    g = int(guid)
    for parent in ui_record_list:
        if not isinstance(parent, dict):
            continue
        if g in _get_children_guids_from_parent_record(parent):
            return True
    return False

