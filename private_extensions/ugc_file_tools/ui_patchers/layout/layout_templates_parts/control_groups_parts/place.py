from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.ui.readable_dump import extract_ui_record_list as _extract_ui_record_list

from ..shared import (
    DEFAULT_CANVAS_SIZE_BY_STATE_INDEX,
    _GROUP_CONTAINER_META0,
    _GROUP_TEMPLATE_META12,
    _allocate_next_guid,
    _append_children_guids_to_parent_record,
    _collect_all_widget_guids,
    _dump_gil_to_raw_json_object,
    _find_record_by_guid,
    _force_record_to_group_container_shape,
    _get_children_guids_from_parent_record,
    _set_children_guids_to_parent_record,
    _set_rect_transform_layer,
    _set_widget_guid,
    _set_widget_name,
    _set_widget_parent_guid_field504,
    _write_back_modified_gil_by_reencoding_payload,
    _build_group_meta13_template_ref,
    _build_meta_self_guid,
)
from .helpers import _apply_bbox_transform_to_children, _assert_children_are_custom_placeable_controls


def place_control_group_template_in_layout(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    template_root_guid: int,
    layout_guid: int,
    instance_name: str,
    # 可选：写回位置/大小（对 children 做 bbox 平移/缩放；state0=电脑, state1=手机）
    pc_canvas_position: Optional[Tuple[float, float]] = None,
    pc_size: Optional[Tuple[float, float]] = None,
    mobile_canvas_position: Optional[Tuple[float, float]] = None,
    mobile_size: Optional[Tuple[float, float]] = None,
    layer: Optional[int] = None,
    verify_with_dll_dump: bool = True,
) -> Dict[str, Any]:
    """
    将“控件组模板 root”（由 `save_control_group_as_template` 生成的 template_root_guid）实例化到某个布局 root 下：
    - 新建一个组容器 record（parent=layout_guid, children=克隆后的子控件 GUID 列表）
    - 克隆 template_root 的 children 到该组容器下（只改 guid/parent）
    - 组容器写入 meta13 指向 template_root_guid（与库内 group 的指针一致），便于后续继续对齐模板语义
    """
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    template_root_guid = int(template_root_guid)
    layout_guid = int(layout_guid)
    instance_name = str(instance_name or "").strip()
    if instance_name == "":
        raise ValueError("instance_name 不能为空")

    if (pc_canvas_position is None) != (pc_size is None):
        raise ValueError("pc_canvas_position 与 pc_size 必须同时提供或同时省略")
    if (mobile_canvas_position is None) != (mobile_size is None):
        raise ValueError("mobile_canvas_position 与 mobile_size 必须同时提供或同时省略")

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    ui_record_list = _extract_ui_record_list(raw_dump_object)

    existing_guids = _collect_all_widget_guids(ui_record_list)
    if not existing_guids:
        raise RuntimeError("无法收集现有 GUID（疑似 dump 结构异常）。")

    template_root_record = _find_record_by_guid(ui_record_list, int(template_root_guid))
    if template_root_record is None:
        raise RuntimeError(f"未找到 template_root_guid={int(template_root_guid)} 对应的 UI record。")
    if "504" in template_root_record:
        raise ValueError("template_root_record 不应包含 parent(504)；请传入真正的模板 root GUID。")

    template_children_guids = _get_children_guids_from_parent_record(template_root_record)
    if not template_children_guids:
        raise ValueError("template_root_record 的 children 为空，无法实例化。")

    template_child_records: List[Dict[str, Any]] = []
    for child_guid in template_children_guids:
        child_record = _find_record_by_guid(ui_record_list, int(child_guid))
        if child_record is None:
            raise RuntimeError(f"template_root 的 child guid={int(child_guid)} 未找到对应 record。")
        template_child_records.append(child_record)

    _assert_children_are_custom_placeable_controls(
        child_records=template_child_records,
        context="place_control_group_template_in_layout",
    )

    layout_record = _find_record_by_guid(ui_record_list, int(layout_guid))
    if layout_record is None:
        raise RuntimeError(f"未找到 layout_guid={int(layout_guid)} 对应的 UI record。")

    reserved = set(existing_guids)
    instance_guid = _allocate_next_guid(reserved, start=max(reserved) + 1)
    reserved.add(int(instance_guid))

    cloned_child_guids: List[int] = []
    next_start = int(instance_guid) + 1
    for _ in template_children_guids:
        new_guid = _allocate_next_guid(reserved, start=next_start)
        reserved.add(int(new_guid))
        next_start = int(new_guid) + 1
        cloned_child_guids.append(int(new_guid))

    # 1) 组容器实例：以 template_root 结构为基底，但写成“实例”语义（parent=layout, meta13 指向 template_root）
    instance_record = copy.deepcopy(template_root_record)
    _set_widget_guid(instance_record, int(instance_guid))
    _set_widget_name(instance_record, instance_name)
    _set_widget_parent_guid_field504(instance_record, int(layout_guid))
    _set_children_guids_to_parent_record(instance_record, [int(g) for g in cloned_child_guids])

    instance_record["502"] = [
        copy.deepcopy(_GROUP_CONTAINER_META0),
        _build_meta_self_guid(int(instance_guid)),
        dict(_GROUP_TEMPLATE_META12),
        _build_group_meta13_template_ref(int(template_root_guid)),
    ]
    _force_record_to_group_container_shape(instance_record)

    # 2) 克隆 children 到组容器实例下
    cloned_child_records: List[Dict[str, Any]] = []
    for src_child_record, new_child_guid in zip(template_child_records, cloned_child_guids, strict=True):
        cloned = copy.deepcopy(src_child_record)
        _set_widget_guid(cloned, int(new_child_guid))
        _set_widget_parent_guid_field504(cloned, int(instance_guid))
        cloned_child_records.append(cloned)

    # 3) 可选：对 children 做“整体放置”（按 bbox 平移/缩放），因为组容器本身不一定包含 RectTransform
    canvas_size_by_state_index = dict(DEFAULT_CANVAS_SIZE_BY_STATE_INDEX)
    if pc_canvas_position is not None and pc_size is not None:
        _apply_bbox_transform_to_children(
            child_records=cloned_child_records,
            state_index=0,
            target_center=(float(pc_canvas_position[0]), float(pc_canvas_position[1])),
            target_size=(float(pc_size[0]), float(pc_size[1])),
            canvas_size_by_state_index=canvas_size_by_state_index,
        )
    if mobile_canvas_position is not None and mobile_size is not None:
        _apply_bbox_transform_to_children(
            child_records=cloned_child_records,
            state_index=1,
            target_center=(float(mobile_canvas_position[0]), float(mobile_canvas_position[1])),
            target_size=(float(mobile_size[0]), float(mobile_size[1])),
            canvas_size_by_state_index=canvas_size_by_state_index,
        )
    if layer is not None:
        for rec in cloned_child_records:
            component_list = rec.get("505")
            if not isinstance(component_list, list) or len(component_list) < 3:
                continue
            rect_component = component_list[2]
            if not isinstance(rect_component, dict):
                continue
            node503 = rect_component.get("503")
            if not isinstance(node503, dict):
                continue
            node13 = node503.get("13")
            if not isinstance(node13, dict):
                continue
            node12 = node13.get("12")
            if not isinstance(node12, dict):
                continue
            _set_rect_transform_layer(rec, int(layer))

    # 4) 将组容器作为 layout 的 children 追加，并写回 record list
    _append_children_guids_to_parent_record(layout_record, [int(instance_guid)])
    ui_record_list.append(instance_record)
    ui_record_list.extend(cloned_child_records)

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_path,
        output_gil_path=output_path,
    )

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "template_root_guid": int(template_root_guid),
        "layout_guid": int(layout_guid),
        "created_instance": {
            "guid": int(instance_guid),
            "name": instance_name,
            "children_guids": list(int(g) for g in cloned_child_guids),
        },
    }

    if verify_with_dll_dump:
        verify_dump = _dump_gil_to_raw_json_object(output_path)
        verify_ui_records = _extract_ui_record_list(verify_dump)
        verify_instance = _find_record_by_guid(verify_ui_records, int(instance_guid))
        verify_layout = _find_record_by_guid(verify_ui_records, int(layout_guid))
        report["verify"] = {
            "ui_record_total": len(verify_ui_records),
            "instance_exists": bool(verify_instance is not None),
            "layout_exists": bool(verify_layout is not None),
            "instance_parent_ok": bool(
                verify_instance is not None and int(verify_instance.get("504") or 0) == int(layout_guid)
            ),
            "layout_children_contains_instance": (
                (int(instance_guid) in set(_get_children_guids_from_parent_record(verify_layout)))
                if verify_layout is not None
                else None
            ),
            "instance_children_parent_ok": all(
                (_find_record_by_guid(verify_ui_records, int(g)) or {}).get("504") == int(instance_guid)
                for g in cloned_child_guids
            ),
        }

    return report


__all__ = ["place_control_group_template_in_layout"]

