from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.ui.readable_dump import extract_ui_record_list as _extract_ui_record_list

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    DEFAULT_CANVAS_SIZE_BY_STATE_INDEX,
    dump_gil_to_raw_json_object as _dump_gil_to_raw_json_object,
    find_record_by_guid as _find_record_by_guid,
    set_rect_state_canvas_position_and_size as _set_rect_state_canvas_position_and_size,
    set_rect_transform_layer as _set_rect_transform_layer,
    set_widget_name as _set_widget_name,
    write_back_modified_gil_by_reencoding_payload as _write_back_modified_gil_by_reencoding_payload,
)


@dataclass(frozen=True, slots=True)
class ControlVariantPatch:
    guid: int
    new_name: Optional[str] = None
    visible: Optional[bool] = None
    layer: Optional[int] = None
    pc_canvas_position: Optional[Tuple[float, float]] = None
    pc_size: Optional[Tuple[float, float]] = None
    mobile_canvas_position: Optional[Tuple[float, float]] = None
    mobile_size: Optional[Tuple[float, float]] = None


def apply_control_variant_patches_in_gil(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    patches: List[ControlVariantPatch],
    verify_with_dll_dump: bool = True,
) -> Dict[str, Any]:
    """
    通用“控件属性写回”：
    - 名称（505[*]/12/501）
    - 初始可见性（505[*]/503/503）
    - RectTransform 层级（505[2]/503/13/12/503）
    - RectTransform 位置/大小（state0=电脑, state1=手机；固定锚点 anchor_min==anchor_max）

    约束：
    - 使用 dump-json（数值键结构）作为结构真源，再用自研 encoder 重编码 payload 写回新的 `.gil`。
    - 不使用 try/except；结构不一致直接抛错。
    """
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    patch_by_guid: Dict[int, ControlVariantPatch] = {}
    for patch in patches:
        guid_int = int(patch.guid)
        if guid_int in patch_by_guid:
            raise ValueError(f"patch guid duplicated: {guid_int}")
        patch_by_guid[guid_int] = patch

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    ui_record_list = _extract_ui_record_list(raw_dump_object)

    patched_total = 0
    changes: List[Dict[str, Any]] = []

    for guid_int, patch in patch_by_guid.items():
        record = _find_record_by_guid(ui_record_list, int(guid_int))
        if record is None:
            raise RuntimeError(f"未找到 guid={int(guid_int)} 对应的 UI record")

        change: Dict[str, Any] = {"guid": int(guid_int)}

        if patch.new_name is not None:
            name_text = str(patch.new_name or "").strip()
            if name_text == "":
                raise ValueError("new_name 不能为空字符串")
            _set_widget_name(record, name_text)
            change["new_name"] = name_text

        visibility_changed_total = _apply_visibility_patch(record, visible=patch.visible)
        if visibility_changed_total > 0:
            change["visibility_changed_total"] = int(visibility_changed_total)
            change["visible"] = bool(patch.visible)

        if patch.layer is not None:
            _set_rect_transform_layer(record, int(patch.layer))
            change["layer"] = int(patch.layer)

        if (patch.pc_canvas_position is None) != (patch.pc_size is None):
            raise ValueError("pc_canvas_position 与 pc_size 必须同时提供或同时省略")
        if (patch.mobile_canvas_position is None) != (patch.mobile_size is None):
            raise ValueError("mobile_canvas_position 与 mobile_size 必须同时提供或同时省略")

        if patch.pc_canvas_position is not None and patch.pc_size is not None:
            _set_rect_state_canvas_position_and_size(
                record=record,
                state_index=0,
                canvas_position=(float(patch.pc_canvas_position[0]), float(patch.pc_canvas_position[1])),
                size=(float(patch.pc_size[0]), float(patch.pc_size[1])),
                canvas_size_by_state_index=dict(DEFAULT_CANVAS_SIZE_BY_STATE_INDEX),
            )
            change["pc"] = {
                "canvas_position": {"x": float(patch.pc_canvas_position[0]), "y": float(patch.pc_canvas_position[1])},
                "size": {"x": float(patch.pc_size[0]), "y": float(patch.pc_size[1])},
            }

        if patch.mobile_canvas_position is not None and patch.mobile_size is not None:
            _set_rect_state_canvas_position_and_size(
                record=record,
                state_index=1,
                canvas_position=(float(patch.mobile_canvas_position[0]), float(patch.mobile_canvas_position[1])),
                size=(float(patch.mobile_size[0]), float(patch.mobile_size[1])),
                canvas_size_by_state_index=dict(DEFAULT_CANVAS_SIZE_BY_STATE_INDEX),
            )
            change["mobile"] = {
                "canvas_position": {
                    "x": float(patch.mobile_canvas_position[0]),
                    "y": float(patch.mobile_canvas_position[1]),
                },
                "size": {"x": float(patch.mobile_size[0]), "y": float(patch.mobile_size[1])},
            }

        patched_total += 1
        changes.append(change)

    if patched_total <= 0:
        raise RuntimeError("未应用任何 patch（patches 为空）")

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_path,
        output_gil_path=output_path,
    )

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "requested_patch_total": len(patches),
        "patched_total": int(patched_total),
        "changes": changes,
    }

    if verify_with_dll_dump:
        verify_dump = _dump_gil_to_raw_json_object(output_path)
        verify_records = _extract_ui_record_list(verify_dump)
        ok = True
        for patch in patches:
            if _find_record_by_guid(verify_records, int(patch.guid)) is None:
                ok = False
                break
        report["verify"] = {"ok": bool(ok), "patched_guids_exist": bool(ok)}

    return report


def _apply_visibility_patch(record: Dict[str, Any], visible: Optional[bool]) -> int:
    if visible is None:
        return 0
    component_list = record.get("505")
    if not isinstance(component_list, list):
        return 0
    new_flag_value = 1 if bool(visible) else 0
    changed = 0
    for component in component_list:
        if not isinstance(component, dict):
            continue
        nested = component.get("503")
        if not isinstance(nested, dict):
            continue
        flag_value = nested.get("503")
        if not isinstance(flag_value, int):
            continue
        if int(flag_value) == int(new_flag_value):
            continue
        nested["503"] = int(new_flag_value)
        changed += 1
    return int(changed)


__all__ = [
    "ControlVariantPatch",
    "apply_control_variant_patches_in_gil",
]


