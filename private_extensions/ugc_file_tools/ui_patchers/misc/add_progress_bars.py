from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ugc_file_tools.gil_dump_codec.protobuf_like import (
    format_binary_data_hex_text,
    parse_binary_data_hex_text,
)
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.ui_parsers.progress_bars import find_progressbar_binding_blob as _find_progressbar_binding_blob
from ugc_file_tools.ui.readable_dump import (
    choose_best_rect_transform_state as _choose_best_rect_transform_state,
    choose_best_rect_transform_states as _choose_best_rect_transform_states,
    extract_primary_guid as _extract_primary_guid,
    extract_ui_record_list as _extract_ui_record_list,
    find_rect_transform_state_lists as _find_rect_transform_state_lists,
)

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    dump_gil_to_raw_json_object as _dump_gil_to_raw_json_object_lossless,
    write_back_modified_gil_by_reencoding_payload as _write_back_modified_gil_by_reencoding_payload,
)


@dataclass(frozen=True, slots=True)
class AddedProgressbarRecord:
    guid: int
    corner: str
    anchored_position: Tuple[float, float]
    canvas_position: Tuple[float, float]


def add_progressbars_to_corners(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    corners: Sequence[str],
    canvas_size: Tuple[float, float],
    margin: Tuple[float, float],
    parent_guid: Optional[int] = None,
    name_prefix: str = "进度条_角落",
    verify_with_dll_dump: bool = True,
) -> Dict[str, Any]:
    """
    在指定父组下新增若干进度条控件，并写回为新的 `.gil`。

    约束：
    - 不依赖 JSON→GIL（DLL 未实现）；直接把 DLL dump-json 的树结构做修改后，用自研 protobuf-like encoder 写回。
    - 目前仅实现“复制已有进度条 record 作为模板”，并修改 guid + 位置；其它配置（绑定/样式/颜色等）沿用模板。
    """
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    canvas_width, canvas_height = float(canvas_size[0]), float(canvas_size[1])
    if canvas_width <= 0 or canvas_height <= 0:
        raise ValueError(f"invalid canvas_size: {canvas_size!r}")

    margin_x, margin_y = float(margin[0]), float(margin[1])
    if margin_x < 0 or margin_y < 0:
        raise ValueError(f"invalid margin: {margin!r}")

    normalized_corners = [_normalize_corner_name(corner) for corner in corners]
    if not normalized_corners:
        raise ValueError("corners is empty")

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    ui_record_list = _extract_ui_record_list(raw_dump_object)

    inferred_parent_guid = _infer_parent_guid_for_progressbars(ui_record_list)
    if parent_guid is None:
        parent_guid = inferred_parent_guid
    if parent_guid is None:
        raise RuntimeError("无法推断进度条父组 GUID，请显式传入 --parent-guid。")

    parent_record = _find_record_by_guid(ui_record_list, int(parent_guid))
    if parent_record is None:
        raise RuntimeError(f"未找到 parent_guid={int(parent_guid)} 对应的 UI record。")

    template_record = _find_template_progressbar_record(ui_record_list, parent_guid=int(parent_guid))
    if template_record is None:
        raise RuntimeError("未找到可作为模板的进度条 record（缺少绑定 blob）。")

    template_size = _extract_template_size_from_progressbar_record(template_record)
    if template_size is None:
        raise RuntimeError("无法从模板进度条 record 中解析尺寸（RectTransform size）。")
    template_width, template_height = template_size

    existing_guids = _collect_all_widget_guids(ui_record_list)
    if not existing_guids:
        raise RuntimeError("无法从 UI record list 中收集 GUID（疑似 dump 结构异常）。")
    max_guid = max(existing_guids)

    new_records: List[Dict[str, Any]] = []
    added_records_meta: List[AddedProgressbarRecord] = []

    for index, corner in enumerate(normalized_corners):
        new_guid = _allocate_next_guid(existing_guids, start=max_guid + 1 + index)
        existing_guids.add(int(new_guid))

        center_canvas_x, center_canvas_y = _resolve_corner_canvas_center(
            corner=corner,
            canvas_size=(canvas_width, canvas_height),
            margin=(margin_x, margin_y),
            widget_size=(template_width, template_height),
        )
        anchored_x = center_canvas_x - canvas_width / 2.0
        anchored_y = center_canvas_y - canvas_height / 2.0

        cloned = copy.deepcopy(template_record)
        _set_widget_guid(cloned, new_guid)
        _set_widget_name(cloned, f"{name_prefix}{index + 1}")
        _set_widget_parent_guid_field504(cloned, int(parent_guid))
        _set_widget_anchored_position(cloned, anchored_x, anchored_y)

        new_records.append(cloned)
        added_records_meta.append(
            AddedProgressbarRecord(
                guid=int(new_guid),
                corner=corner,
                anchored_position=(float(anchored_x), float(anchored_y)),
                canvas_position=(float(center_canvas_x), float(center_canvas_y)),
            )
        )

    # 父组的 children guid 列表（field 503 的 <binary_data>）需要追加新 GUID
    _append_children_guids_to_parent_record(parent_record, [r.guid for r in added_records_meta])

    # 将新 record 附加到 UI record list
    ui_record_list.extend(new_records)

    # 写回 .gil（避免全量重编码导致“非规范存档”被规范化，从而游戏拒识）
    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_path,
        output_gil_path=output_path,
    )

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "parent_guid": int(parent_guid),
        "inferred_parent_guid": int(inferred_parent_guid) if inferred_parent_guid is not None else None,
        "template_guid": int(_extract_primary_guid(template_record) or 0),
        "template_size": {"x": template_width, "y": template_height},
        "canvas_size": {"x": canvas_width, "y": canvas_height},
        "margin": {"x": margin_x, "y": margin_y},
        "added_total": len(added_records_meta),
        "added": [
            {
                "guid": item.guid,
                "corner": item.corner,
                "anchored_position": {"x": item.anchored_position[0], "y": item.anchored_position[1]},
                "canvas_position": {"x": item.canvas_position[0], "y": item.canvas_position[1]},
            }
            for item in added_records_meta
        ],
    }

    if verify_with_dll_dump:
        verify_dump = _dump_gil_to_raw_json_object(output_path)
        verify_ui_records = _extract_ui_record_list(verify_dump)
        report["verify"] = {
            "ui_record_total": len(verify_ui_records),
            "added_guids_exist": all(_find_record_by_guid(verify_ui_records, item.guid) is not None for item in added_records_meta),
        }

    return report


def _normalize_corner_name(text: str) -> str:
    value = str(text or "").strip().lower().replace("_", "-")
    alias = {
        "tl": "top-left",
        "tr": "top-right",
        "bl": "bottom-left",
        "br": "bottom-right",
        "left-top": "top-left",
        "right-top": "top-right",
        "left-bottom": "bottom-left",
        "right-bottom": "bottom-right",
        "左上": "top-left",
        "右上": "top-right",
        "左下": "bottom-left",
        "右下": "bottom-right",
    }
    value = alias.get(value, value)
    allowed = {"top-left", "top-right", "bottom-left", "bottom-right"}
    if value not in allowed:
        raise ValueError(f"unsupported corner: {text!r} (normalized={value!r})")
    return value


def _resolve_corner_canvas_center(
    *,
    corner: str,
    canvas_size: Tuple[float, float],
    margin: Tuple[float, float],
    widget_size: Tuple[float, float],
) -> Tuple[float, float]:
    canvas_width, canvas_height = float(canvas_size[0]), float(canvas_size[1])
    margin_x, margin_y = float(margin[0]), float(margin[1])
    widget_width, widget_height = float(widget_size[0]), float(widget_size[1])

    half_w = widget_width / 2.0
    half_h = widget_height / 2.0

    if corner == "top-left":
        return margin_x + half_w, canvas_height - margin_y - half_h
    if corner == "top-right":
        return canvas_width - margin_x - half_w, canvas_height - margin_y - half_h
    if corner == "bottom-left":
        return margin_x + half_w, margin_y + half_h
    if corner == "bottom-right":
        return canvas_width - margin_x - half_w, margin_y + half_h
    raise ValueError(f"unknown corner: {corner!r}")


def _dump_gil_to_raw_json_object(input_gil_file_path: Path) -> Dict[str, Any]:
    return _dump_gil_to_raw_json_object_lossless(Path(input_gil_file_path).resolve())


def _collect_all_widget_guids(ui_record_list: List[Any]) -> set[int]:
    guids: set[int] = set()
    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        guid_value = _extract_primary_guid(record)
        if isinstance(guid_value, int):
            guids.add(int(guid_value))
    return guids


def _allocate_next_guid(existing_guids: set[int], start: int) -> int:
    candidate = int(start)
    while candidate in existing_guids:
        candidate += 1
    return candidate


def _infer_parent_guid_for_progressbars(ui_record_list: List[Any]) -> Optional[int]:
    parent_candidates: set[int] = set()
    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        binding_hit = _find_progressbar_binding_blob(record)
        if binding_hit is None:
            # 兼容：部分存档的 binding 不再是 <binary_data> blob，而是展开为 dict message（常见于 505/[3]/503/20）
            component_list = record.get("505")
            if not (isinstance(component_list, list) and len(component_list) > 3):
                continue
            component = component_list[3]
            nested = component.get("503") if isinstance(component, dict) else None
            candidate = nested.get("20") if isinstance(nested, dict) else None
            if not (isinstance(candidate, dict) and all(str(k) in candidate for k in ("504", "505", "506"))):
                continue
        parent_value = record.get("504")
        if isinstance(parent_value, int):
            parent_candidates.add(int(parent_value))
    if len(parent_candidates) == 1:
        return next(iter(parent_candidates))
    return None


def _find_record_by_guid(ui_record_list: List[Any], guid: int) -> Optional[Dict[str, Any]]:
    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        guid_value = _extract_primary_guid(record)
        if isinstance(guid_value, int) and int(guid_value) == int(guid):
            return record
    return None


def _find_template_progressbar_record(ui_record_list: List[Any], *, parent_guid: int) -> Optional[Dict[str, Any]]:
    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        parent_value = record.get("504")
        if not isinstance(parent_value, int) or int(parent_value) != int(parent_guid):
            continue
        binding_hit = _find_progressbar_binding_blob(record)
        if binding_hit is None:
            # 兼容：binding 展开为 dict message 的存档
            component_list = record.get("505")
            if not (isinstance(component_list, list) and len(component_list) > 3):
                continue
            component = component_list[3]
            nested = component.get("503") if isinstance(component, dict) else None
            candidate = nested.get("20") if isinstance(nested, dict) else None
            if not (isinstance(candidate, dict) and all(str(k) in candidate for k in ("504", "505", "506"))):
                continue
        return record
    return None


def _extract_template_size_from_progressbar_record(record: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    rect_transform_candidates = _find_rect_transform_state_lists(record)
    _path, states = _choose_best_rect_transform_states(rect_transform_candidates)
    transform = _choose_best_rect_transform_state(states)
    if not isinstance(transform, dict):
        return None
    size = transform.get("size")
    if not isinstance(size, dict):
        return None
    x = size.get("x")
    y = size.get("y")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return None
    return float(x), float(y)


def _set_widget_guid(record: Dict[str, Any], new_guid: int) -> None:
    guid_field = record.get("501")
    if isinstance(guid_field, int):
        old_guid = int(guid_field)
        record["501"] = int(new_guid)
    else:
        guid_list = guid_field
        if not isinstance(guid_list, list) or not guid_list:
            raise ValueError("record missing guid list at field 501")
        old_guid_value = guid_list[0]
        if not isinstance(old_guid_value, int):
            raise ValueError("record field 501[0] must be int")
        old_guid = int(old_guid_value)
        guid_list[0] = int(new_guid)

    meta_list = record.get("502")
    if not isinstance(meta_list, list) or not meta_list:
        # 部分 record 不存在需要同步写入的“重复 guid”字段
        return
    # 同步所有 meta[*]/11/501 == old_guid 的条目（兼容布局 root / 控件实例等不同形态）
    for meta in meta_list:
        if not isinstance(meta, dict):
            continue
        node11 = meta.get("11")
        if not isinstance(node11, dict):
            continue
        current = node11.get("501")
        if isinstance(current, int) and int(current) == old_guid:
            node11["501"] = int(new_guid)


def _set_widget_parent_guid_field504(record: Dict[str, Any], parent_guid: int) -> None:
    record["504"] = int(parent_guid)


def set_widget_parent_guid_field504(record: Dict[str, Any], parent_guid: int) -> None:
    """
    Public API (no leading underscores).

    Import policy: cross-module imports must not import underscored private names.
    """
    _set_widget_parent_guid_field504(record, int(parent_guid))


def _set_widget_name(record: Dict[str, Any], new_name: str) -> None:
    component_list = record.get("505")
    if not isinstance(component_list, list) or not component_list:
        raise ValueError("record missing component list at field 505")
    name_component = component_list[0]
    if not isinstance(name_component, dict):
        raise ValueError("record field 505[0] must be dict")
    node12 = name_component.get("12")
    if not isinstance(node12, dict):
        raise ValueError("record field 505[0]/12 must be dict")
    node12["501"] = str(new_name)


def set_widget_name(record: Dict[str, Any], new_name: str) -> None:
    """Public API (no leading underscores)."""
    _set_widget_name(record, str(new_name))


def _set_widget_anchored_position(record: Dict[str, Any], anchored_x: float, anchored_y: float) -> None:
    component_list = record.get("505")
    if not isinstance(component_list, list) or len(component_list) < 3:
        raise ValueError("record missing RectTransform component at field 505[2]")
    rect_component = component_list[2]
    if not isinstance(rect_component, dict):
        raise ValueError("record field 505[2] must be dict")
    node503 = rect_component.get("503")
    if not isinstance(node503, dict):
        raise ValueError("record field 505[2]/503 must be dict")
    node13 = node503.get("13")
    if not isinstance(node13, dict):
        raise ValueError("record field 505[2]/503/13 must be dict")
    node12 = node13.get("12")
    if not isinstance(node12, dict):
        raise ValueError("record field 505[2]/503/13/12 must be dict")
    state_list = node12.get("501")
    if not isinstance(state_list, list) or not state_list:
        raise ValueError("record field 505[2]/503/13/12/501 must be list and non-empty")
    state0 = state_list[0]
    if not isinstance(state0, dict):
        raise ValueError("record rect state[0] must be dict")
    transform = state0.get("502")
    if not isinstance(transform, dict):
        raise ValueError("record rect state[0]/502 must be dict")
    pos = transform.get("504")
    if not isinstance(pos, dict):
        raise ValueError("record rect state[0]/502/504 must be dict")
    pos["501"] = float(anchored_x)
    pos["502"] = float(anchored_y)


def _append_children_guids_to_parent_record(parent_record: Dict[str, Any], child_guids: List[int]) -> None:
    field503 = parent_record.get("503")
    if field503 is None:
        field503 = [""]
        parent_record["503"] = field503
    if isinstance(field503, str):
        field503 = [field503]
        parent_record["503"] = field503
    if isinstance(field503, list) and not field503:
        field503.append("")
    if not isinstance(field503, list) or not field503:
        raise ValueError("parent_record missing children list at field 503")

    first = field503[0]
    if not isinstance(first, str):
        raise ValueError("parent_record field 503[0] must be str")
    if first == "":
        existing_bytes = b""
    else:
        if not first.startswith("<binary_data>"):
            raise ValueError("parent_record field 503[0] must be '<binary_data>' string or empty string")
        existing_bytes = parse_binary_data_hex_text(first)
    existing_ids = _decode_varint_stream(existing_bytes)

    new_bytes = bytearray(existing_bytes)
    for guid in child_guids:
        new_bytes.extend(_encode_varint(int(guid)))

    field503[0] = format_binary_data_hex_text(bytes(new_bytes))

    # 额外校验：追加后可解析
    appended_ids = _decode_varint_stream(bytes(new_bytes))
    if len(appended_ids) != len(existing_ids) + len(child_guids):
        raise RuntimeError("parent children varint list parse mismatch after append")


def _decode_varint_stream(data: bytes) -> List[int]:
    values: List[int] = []
    offset = 0
    end_offset = len(data)
    while offset < end_offset:
        value, offset, ok = _decode_varint(data, offset)
        if not ok:
            raise ValueError("invalid varint stream")
        values.append(int(value))
    return values


def _decode_varint(data: bytes, offset: int) -> Tuple[int, int, bool]:
    value = 0
    shift_bits = 0
    current_offset = offset
    while True:
        if current_offset >= len(data):
            return 0, current_offset, False
        current_byte = data[current_offset]
        current_offset += 1
        value |= (current_byte & 0x7F) << shift_bits
        if (current_byte & 0x80) == 0:
            return value, current_offset, True
        shift_bits += 7
        if shift_bits >= 64:
            return 0, current_offset, False


def _encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError(f"varint value must be >= 0, got {value}")
    parts: List[int] = []
    remaining = int(value)
    while True:
        byte_value = remaining & 0x7F
        remaining >>= 7
        if remaining:
            parts.append(byte_value | 0x80)
        else:
            parts.append(byte_value)
            break
    return bytes(parts)


