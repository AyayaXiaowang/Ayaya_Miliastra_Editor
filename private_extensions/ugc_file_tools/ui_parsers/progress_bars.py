from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from engine.configs.specialized.ui_widget_configs import (
    PROGRESSBAR_COLOR_HEX_BY_CODE,
    PROGRESSBAR_COLOR_NAME_BY_CODE,
)
from ugc_file_tools.ui.readable_dump import (
    choose_best_rect_transform_state as _choose_best_rect_transform_state,
    choose_best_rect_transform_states as _choose_best_rect_transform_states,
    extract_primary_guid as _extract_primary_guid,
    extract_primary_name as _extract_primary_name,
    extract_ui_record_list as _extract_ui_record_list,
    extract_visibility_flag_values as _extract_visibility_flag_values,
    find_rect_transform_state_lists as _find_rect_transform_state_lists,
)

DEFAULT_DEVICE_TEMPLATE_BY_STATE_INDEX: Dict[int, str] = {
    0: "电脑",
    1: "手机",
    2: "主机",
    3: "手柄主机",
}


def _build_canvas_size_by_state_index(
    pc_canvas_size: Optional[Tuple[float, float]],
) -> Dict[int, Tuple[float, float]]:
    """
    约定：RectTransform 的 state_index 对应“设备模板”。

    经样本验证（test5/test6）：
    - state 0：电脑模板（默认 1600x900，可由 CLI --canvas-size 覆盖）
    - state 1：手机模板（1280x720）
    - state 2：主机模板（1920x1080）
    - state 3：手柄主机模板（1280x720）
    """
    if pc_canvas_size is None:
        return {}
    pc_w, pc_h = float(pc_canvas_size[0]), float(pc_canvas_size[1])
    return {
        0: (pc_w, pc_h),
        1: (1280.0, 720.0),
        2: (1920.0, 1080.0),
        3: (1280.0, 720.0),
    }


def _infer_anchor_preset_name(
    anchor_min: Optional[Dict[str, Any]],
    anchor_max: Optional[Dict[str, Any]],
) -> Optional[str]:
    """
    将固定锚点（anchor_min == anchor_max）的 (x,y) 映射到编辑器“九宫格锚点”的中文名称。
    stretch（anchor_min != anchor_max）返回 None。
    """
    if not isinstance(anchor_min, dict) or not isinstance(anchor_max, dict):
        return None
    ax = anchor_min.get("x")
    ay = anchor_min.get("y")
    bx = anchor_max.get("x")
    by = anchor_max.get("y")
    if not isinstance(ax, (int, float)) or not isinstance(ay, (int, float)):
        return None
    if not isinstance(bx, (int, float)) or not isinstance(by, (int, float)):
        return None
    if float(ax) != float(bx) or float(ay) != float(by):
        return None

    def _snap(value: float) -> Optional[float]:
        # 锚点通常是 0 / 0.5 / 1，但考虑浮点误差，做一次吸附。
        for candidate in (0.0, 0.5, 1.0):
            if abs(float(value) - candidate) <= 1e-4:
                return candidate
        return None

    sx = _snap(float(ax))
    sy = _snap(float(ay))
    if sx is None or sy is None:
        return None

    name_by_anchor = {
        (0.0, 0.0): "左下",
        (0.5, 0.0): "下",
        (1.0, 0.0): "右下",
        (0.0, 0.5): "左",
        (0.5, 0.5): "居中",
        (1.0, 0.5): "右",
        (0.0, 1.0): "左上",
        (0.5, 1.0): "上",
        (1.0, 1.0): "右上",
    }
    return name_by_anchor.get((sx, sy))


def build_progressbar_dump(
    dll_dump_object: Dict[str, Any],
    *,
    canvas_size: Optional[Tuple[float, float]] = (1600.0, 900.0),
    include_raw_binding_blob_hex: bool = False,
) -> Dict[str, Any]:
    """
    从 raw dump-json（数值键结构）中解析“进度条”控件。

    识别规则（当前样本已验证）：record 内存在某个 <binary_data> blob，其 protobuf-like message 同时包含：
    - field_504 / field_505 / field_506：三个变量绑定（current/min/max），嵌套结构里包含 group_id；变量名可能缺失（表示未绑定）
    - 可选：field_501/502/503：枚举配置（形状/样式/颜色）
    """
    ui_record_list = _extract_ui_record_list(dll_dump_object)
    canvas_size_by_state_index = _build_canvas_size_by_state_index(canvas_size)

    progressbars: List[Dict[str, Any]] = []
    for record_list_index, record in enumerate(ui_record_list):
        if not isinstance(record, dict):
            continue
        parsed = _try_parse_progressbar_record(
            record,
            record_list_index=record_list_index,
            canvas_size_by_state_index=canvas_size_by_state_index,
            include_raw_binding_blob_hex=include_raw_binding_blob_hex,
        )
        if parsed is None:
            continue
        progressbars.append(parsed)

    progressbars.sort(key=lambda item: int(item.get("guid", 0) or 0))

    progressbars_by_guid: Dict[int, Any] = {}
    for progressbar in progressbars:
        guid_value = progressbar.get("guid")
        if isinstance(guid_value, int):
            progressbars_by_guid[int(guid_value)] = progressbar

    return {
        "ui_record_total": len(ui_record_list),
        "progressbar_total": len(progressbars),
        "progressbars": progressbars,
        "progressbars_by_guid": progressbars_by_guid,
        "assumptions": {
            "canvas_size": {"x": canvas_size[0], "y": canvas_size[1]} if canvas_size is not None else None,
            "canvas_size_by_state_index": {
                str(state_index): {"x": wh[0], "y": wh[1]} for state_index, wh in canvas_size_by_state_index.items()
            }
            if canvas_size_by_state_index
            else None,
            "device_template_by_state_index": {
                str(state_index): name for state_index, name in DEFAULT_DEVICE_TEMPLATE_BY_STATE_INDEX.items()
            },
            "canvas_position_formula": (
                "if anchor_min==anchor_max: canvas_pos = anchored_position + (anchor_min.x*canvas_size.x, anchor_min.y*canvas_size.y)"
                if canvas_size is not None
                else None
            ),
        },
    }


def _try_parse_progressbar_record(
    record: Dict[str, Any],
    *,
    record_list_index: int,
    canvas_size_by_state_index: Dict[int, Tuple[float, float]],
    include_raw_binding_blob_hex: bool,
) -> Optional[Dict[str, Any]]:
    guid_value = _extract_primary_guid(record)
    if guid_value is None:
        return None

    binding_blob_hit = _find_progressbar_binding_blob(record)
    if binding_blob_hit is None:
        return None

    binding_blob_path, binding_blob_bytes = binding_blob_hit
    progress_config = _decode_progressbar_binding_blob(binding_blob_bytes)
    if progress_config is None:
        return None

    index_id_value = record.get("504")
    index_id_int = int(index_id_value) if isinstance(index_id_value, int) else None

    name_text = _extract_primary_name(record)
    visibility_flag_values = _extract_visibility_flag_values(record)
    is_visible = all(flag_value == 1 for flag_value in visibility_flag_values)

    rect_transform_candidates = _find_rect_transform_state_lists(record)
    chosen_transform_path, chosen_transform_states = _choose_best_rect_transform_states(
        rect_transform_candidates
    )
    chosen_transform = _choose_best_rect_transform_state(chosen_transform_states)
    record_metadata = _extract_progressbar_record_metadata(record)

    anchored_position: Optional[Dict[str, Any]] = None
    anchor_min: Optional[Dict[str, Any]] = None
    anchor_max: Optional[Dict[str, Any]] = None
    size: Optional[Dict[str, Any]] = None
    canvas_position: Optional[Dict[str, Any]] = None

    if isinstance(chosen_transform, dict):
        anchored_position = chosen_transform.get("anchored_position")
        anchor_min = chosen_transform.get("anchor_min")
        anchor_max = chosen_transform.get("anchor_max")
        size = chosen_transform.get("size")

    pc_canvas_size = canvas_size_by_state_index.get(0)
    if (
        pc_canvas_size is not None
        and isinstance(anchored_position, dict)
        and isinstance(anchored_position.get("x"), (int, float))
        and isinstance(anchored_position.get("y"), (int, float))
    ):
        resolved_canvas_position = _resolve_canvas_position_from_rect_transform(
            anchored_position=anchored_position,
            anchor_min=anchor_min,
            anchor_max=anchor_max,
            canvas_size=(float(pc_canvas_size[0]), float(pc_canvas_size[1])),
        )
        if resolved_canvas_position is not None:
            canvas_position = resolved_canvas_position

    rect_transform_states = chosen_transform_states
    if canvas_size_by_state_index:
        rect_transform_states = _enrich_rect_transform_states_with_canvas_positions(
            rect_transform_states=chosen_transform_states,
            canvas_size_by_state_index=canvas_size_by_state_index,
        )

    output: Dict[str, Any] = {
        "record_list_index": int(record_list_index),
        "guid": int(guid_value),
        "index_id": index_id_int,
        "name": name_text,
        "visible": is_visible,
        "visibility_flag_values": visibility_flag_values,
        "rect_transform": chosen_transform,
        "rect_transform_states": rect_transform_states,
        "rect_transform_source_path": chosen_transform_path,
        "position": {
            "anchored": anchored_position,
            "canvas": canvas_position,
        },
        "size": size,
        "progressbar": progress_config,
        "metadata": record_metadata,
        "source": {
            "binding_blob_path": binding_blob_path,
            "binding_blob_byte_length": len(binding_blob_bytes),
        },
    }

    if include_raw_binding_blob_hex:
        output["source"]["binding_blob_hex"] = binding_blob_bytes.hex()

    return output


def _resolve_canvas_position_from_rect_transform(
    *,
    anchored_position: Dict[str, Any],
    anchor_min: Optional[Dict[str, Any]],
    anchor_max: Optional[Dict[str, Any]],
    canvas_size: Tuple[float, float],
) -> Optional[Dict[str, float]]:
    """
    将 RectTransform 的 anchored_position 转成“画布坐标”（左下角为原点）。

    仅在 anchor_min == anchor_max（固定锚点）时可可靠计算：
      canvas = (anchor * canvas_size) + anchored_position

    stretch 情况需要更完整的布局语义，这里不推断。
    """
    if not isinstance(anchor_min, dict) or not isinstance(anchor_max, dict):
        return None

    ax = anchor_min.get("x")
    ay = anchor_min.get("y")
    bx = anchor_max.get("x")
    by = anchor_max.get("y")

    if not isinstance(ax, (int, float)) or not isinstance(ay, (int, float)):
        return None
    if not isinstance(bx, (int, float)) or not isinstance(by, (int, float)):
        return None
    if float(ax) != float(bx) or float(ay) != float(by):
        return None

    canvas_width, canvas_height = float(canvas_size[0]), float(canvas_size[1])
    x = float(anchored_position["x"])
    y = float(anchored_position["y"])
    return {
        "x": float(ax) * canvas_width + x,
        "y": float(ay) * canvas_height + y,
    }


def _enrich_rect_transform_states_with_canvas_positions(
    *,
    rect_transform_states: List[Dict[str, Any]],
    canvas_size_by_state_index: Dict[int, Tuple[float, float]],
) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for state in rect_transform_states:
        if not isinstance(state, dict):
            continue
        transform = state.get("transform")
        canvas_position: Optional[Dict[str, float]] = None
        anchor_preset: Optional[str] = None

        state_index_value = state.get("state_index")
        state_index_int = int(state_index_value) if isinstance(state_index_value, int) else None
        canvas_size = canvas_size_by_state_index.get(state_index_int) if state_index_int is not None else None
        device_template = (
            DEFAULT_DEVICE_TEMPLATE_BY_STATE_INDEX.get(state_index_int) if state_index_int is not None else None
        )

        if isinstance(transform, dict):
            anchor_preset = _infer_anchor_preset_name(transform.get("anchor_min"), transform.get("anchor_max"))
            anchored_position = transform.get("anchored_position")
            if (
                isinstance(anchored_position, dict)
                and isinstance(anchored_position.get("x"), (int, float))
                and isinstance(anchored_position.get("y"), (int, float))
            ):
                if canvas_size is not None:
                    canvas_position = _resolve_canvas_position_from_rect_transform(
                        anchored_position=anchored_position,
                        anchor_min=transform.get("anchor_min"),
                        anchor_max=transform.get("anchor_max"),
                        canvas_size=canvas_size,
                    )

        out_state = dict(state)
        out_state["canvas_position"] = canvas_position
        out_state["canvas_size"] = {"x": canvas_size[0], "y": canvas_size[1]} if canvas_size is not None else None
        out_state["device_template"] = device_template
        out_state["anchor_preset"] = anchor_preset
        enriched.append(out_state)

    return enriched


def _find_progressbar_binding_blob(record: Dict[str, Any]) -> Optional[Tuple[str, bytes]]:
    """
    在 record 的所有节点中寻找符合“进度条绑定 blob”签名的 <binary_data> 字符串。

    不使用 try/except：任何不可解析结构通过 ok 标志返回 None，避免误判或中断。
    """

    # fast-path：样本中固定出现在 505/[3]/503/20
    component_list = record.get("505")
    if isinstance(component_list, list) and len(component_list) > 3:
        component = component_list[3]
        if isinstance(component, dict):
            nested = component.get("503")
            if isinstance(nested, dict):
                candidate_text = nested.get("20")
                if isinstance(candidate_text, str):
                    candidate_bytes = _try_parse_binary_data_hex_text(candidate_text)
                    if candidate_bytes is not None and _looks_like_progressbar_binding_blob(candidate_bytes):
                        return "505/[3]/503/20", candidate_bytes

    for path_parts, node in _iter_nodes_with_paths(record):
        if not isinstance(node, str):
            continue
        if not node.startswith("<binary_data>"):
            continue
        candidate_bytes = _try_parse_binary_data_hex_text(node)
        if candidate_bytes is None:
            continue
        if not _looks_like_progressbar_binding_blob(candidate_bytes):
            continue
        return "/".join(path_parts), candidate_bytes

    return None


def _iter_nodes_with_paths(root_value: Any) -> Iterable[Tuple[Tuple[str, ...], Any]]:
    stack: List[Tuple[Tuple[str, ...], Any]] = [((), root_value)]
    while stack:
        path_parts, current_value = stack.pop()
        yield path_parts, current_value
        if isinstance(current_value, dict):
            for key, child in current_value.items():
                stack.append((path_parts + (str(key),), child))
        elif isinstance(current_value, list):
            for index, child in enumerate(current_value):
                stack.append((path_parts + (f"[{index}]",), child))


def _try_parse_binary_data_hex_text(text: str) -> Optional[bytes]:
    if not isinstance(text, str):
        return None
    if not text.startswith("<binary_data>"):
        return None
    hex_text = text.replace("<binary_data>", "").strip()
    if hex_text == "":
        return None

    compact = (
        hex_text.replace(" ", "")
        .replace("\n", "")
        .replace("\r", "")
        .replace("\t", "")
    )
    if compact == "":
        return None
    if len(compact) % 2 != 0:
        return None
    hexdigits = "0123456789abcdefABCDEF"
    if any(character not in hexdigits for character in compact):
        return None
    return bytes.fromhex(compact)


def _looks_like_progressbar_binding_blob(blob_bytes: bytes) -> bool:
    decoded_fields, ok = _parse_protobuf_like_fields(blob_bytes)
    if not ok:
        return False

    required_nested_fields = {504, 505, 506}
    seen_nested_fields: set[int] = set()

    for field_number, wire_type, value in decoded_fields:
        if wire_type != 2:
            continue
        if field_number not in required_nested_fields:
            continue
        if not isinstance(value, (bytes, bytearray)):
            continue
        nested_fields, nested_ok = _parse_protobuf_like_fields(bytes(value))
        if not nested_ok:
            continue
        if not _looks_like_variable_ref_nested_fields(nested_fields):
            continue
        seen_nested_fields.add(int(field_number))

    return seen_nested_fields == required_nested_fields


def _decode_progressbar_binding_blob(blob_bytes: bytes) -> Optional[Dict[str, Any]]:
    decoded_fields, ok = _parse_protobuf_like_fields(blob_bytes)
    if not ok:
        return None

    varint_by_field: Dict[int, int] = {}
    nested_by_field: Dict[int, bytes] = {}

    for field_number, wire_type, value in decoded_fields:
        if wire_type == 0 and isinstance(value, int):
            if field_number not in varint_by_field:
                varint_by_field[int(field_number)] = int(value)
        if wire_type == 2 and isinstance(value, (bytes, bytearray)):
            if field_number not in nested_by_field:
                nested_by_field[int(field_number)] = bytes(value)

    shape_code = int(varint_by_field.get(501, 0))
    style_code = int(varint_by_field.get(502, 0))
    color_code = int(varint_by_field.get(503, 0))

    current_variable = _decode_variable_ref_from_nested_message(nested_by_field.get(504))
    min_variable = _decode_variable_ref_from_nested_message(nested_by_field.get(505))
    max_variable = _decode_variable_ref_from_nested_message(nested_by_field.get(506))
    if current_variable is None or min_variable is None or max_variable is None:
        return None

    return {
        "shape": _map_progressbar_shape(shape_code),
        "style": _map_progressbar_style(style_code),
        "color": _map_progressbar_color(color_code),
        "value_bindings": {
            "current": current_variable,
            "min": min_variable,
            "max": max_variable,
        },
        "raw_codes": {
            "shape_code": shape_code,
            "style_code": style_code,
            "color_code": color_code,
        },
    }




# === Public facade (stable, cross-module) ===
#
# NOTE:
# - External modules must not import underscored private helpers from this module.
# - Keep these wrappers stable; internal implementations may evolve freely.


def find_progressbar_binding_blob(record: Dict[str, Any]) -> Optional[Tuple[str, bytes]]:
    return _find_progressbar_binding_blob(record)


def decode_progressbar_binding_blob(blob_bytes: bytes) -> Optional[Dict[str, Any]]:
    return _decode_progressbar_binding_blob(blob_bytes)


def _map_progressbar_shape(code: int) -> Dict[str, Any]:
    name_by_code = {
        0: "横向",
        1: "纵向",
        2: "圆环",
    }
    return {"code": int(code), "name": name_by_code.get(int(code))}


def _map_progressbar_style(code: int) -> Dict[str, Any]:
    name_by_code = {
        0: "百分比",
        1: "不显示",
        2: "当前值",
        3: "真实比例",
    }
    return {"code": int(code), "name": name_by_code.get(int(code))}


def _map_progressbar_color(code: int) -> Dict[str, Any]:
    code_int = int(code)
    return {
        "code": int(code_int),
        "name": PROGRESSBAR_COLOR_NAME_BY_CODE.get(int(code_int)),
        "hex": PROGRESSBAR_COLOR_HEX_BY_CODE.get(int(code_int)),
    }


def _extract_progressbar_record_metadata(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    从 record 中提取“进度条以外”的附加元信息（目前主要来自 record['502'] 里的 <binary_data> 小 blob）。

    典型样本（test5）：
    - 502/[2]/13：指向某个“控件组/模板”的 GUID（varint）
    - 502/[2]/14：一串 GUID 列表（length-delimited 内为 varint stream）
    - 502/[1]/12：一个很小的 varint（用途待确认，暂保留为 raw）
    """
    record_502 = record.get("502")
    if not isinstance(record_502, list):
        return {}

    binary_entries: List[Dict[str, Any]] = []
    control_group_ref_guid: Optional[int] = None
    referenced_guids: List[int] = []

    for index, element in enumerate(record_502):
        if not isinstance(element, dict):
            continue
        for key, value in element.items():
            if not isinstance(value, str) or not value.startswith("<binary_data>"):
                continue
            data_bytes = _try_parse_binary_data_hex_text(value)
            if data_bytes is None:
                continue

            decoded_fields, ok = _parse_protobuf_like_fields(data_bytes)
            decoded_summary = _summarize_protobuf_like_fields(decoded_fields, ok=ok)
            entry_path = f"502/[{index}]/{str(key)}"
            binary_entries.append(
                {
                    "path": entry_path,
                    "byte_length": len(data_bytes),
                    "decoded": decoded_summary,
                }
            )

            if not ok:
                continue

            inferred_ref_guid = _try_infer_ref_guid_from_fields(decoded_fields)
            if inferred_ref_guid is not None:
                control_group_ref_guid = inferred_ref_guid

            inferred_guid_list = _try_infer_guid_list_from_fields(decoded_fields)
            if inferred_guid_list:
                referenced_guids.extend(inferred_guid_list)

    unique_referenced = _dedupe_int_list(referenced_guids)

    return {
        "record_502_binary_entries": binary_entries,
        "control_group_ref_guid": control_group_ref_guid,
        "referenced_guids": unique_referenced,
    }


def _summarize_protobuf_like_fields(decoded_fields: List[Tuple[int, int, Any]], *, ok: bool) -> Dict[str, Any]:
    field_rows: List[Dict[str, Any]] = []
    for field_number, wire_type, value in decoded_fields:
        if wire_type == 0 and isinstance(value, int):
            field_rows.append(
                {
                    "field": int(field_number),
                    "wire_type": 0,
                    "value": int(value),
                }
            )
            continue

        if wire_type == 2 and isinstance(value, (bytes, bytearray)):
            value_bytes = bytes(value)
            varint_stream = _try_decode_varint_stream(value_bytes, max_items=64)
            field_rows.append(
                {
                    "field": int(field_number),
                    "wire_type": 2,
                    "byte_length": len(value_bytes),
                    "varint_stream": varint_stream,
                }
            )
            continue

        if wire_type in (1, 5) and isinstance(value, (bytes, bytearray)):
            field_rows.append(
                {
                    "field": int(field_number),
                    "wire_type": int(wire_type),
                    "byte_length": len(bytes(value)),
                }
            )
            continue

        field_rows.append(
            {
                "field": int(field_number),
                "wire_type": int(wire_type),
                "python_type": type(value).__name__,
            }
        )

    return {"parse_ok": bool(ok), "fields": field_rows}


def _try_infer_ref_guid_from_fields(decoded_fields: List[Tuple[int, int, Any]]) -> Optional[int]:
    for field_number, wire_type, value in decoded_fields:
        if wire_type != 0 or not isinstance(value, int):
            continue
        if int(field_number) != 501:
            continue
        candidate = int(value)
        if 1073000000 <= candidate <= 1075000000:
            return candidate
    return None


def _try_infer_guid_list_from_fields(decoded_fields: List[Tuple[int, int, Any]]) -> List[int]:
    guids: List[int] = []
    for field_number, wire_type, value in decoded_fields:
        if int(field_number) != 501 or wire_type != 2 or not isinstance(value, (bytes, bytearray)):
            continue
        decoded = _try_decode_varint_stream(bytes(value), max_items=256)
        if not decoded:
            continue
        # 只保留“像 GUID 的值”（避免误把小数组当 GUID）
        for v in decoded:
            if 1073000000 <= int(v) <= 1075000000:
                guids.append(int(v))
    return guids


def _try_decode_varint_stream(data: bytes, *, max_items: int) -> Optional[List[int]]:
    values: List[int] = []
    current_offset = 0
    end_offset = len(data)
    while current_offset < end_offset:
        if len(values) >= int(max_items):
            return None
        value, current_offset, ok = _decode_varint(data, current_offset)
        if not ok:
            return None
        values.append(int(value))
    if not values:
        return None
    return values


def _dedupe_int_list(values: List[int]) -> List[int]:
    seen: set[int] = set()
    result: List[int] = []
    for v in values:
        iv = int(v)
        if iv in seen:
            continue
        seen.add(iv)
        result.append(iv)
    return result


def _decode_variable_ref_from_nested_message(nested_message_bytes: Optional[bytes]) -> Optional[Dict[str, Any]]:
    if not isinstance(nested_message_bytes, (bytes, bytearray)):
        return None
    nested_fields, ok = _parse_protobuf_like_fields(bytes(nested_message_bytes))
    if not ok:
        return None
    variable_ref = _extract_variable_ref_from_nested_fields(nested_fields)
    if variable_ref is None:
        return None

    group_id = variable_ref.get("group_id")
    group_name = _resolve_variable_group_name(group_id) if isinstance(group_id, int) else None
    variable_ref["group_name"] = group_name
    name_text = variable_ref.get("name")
    if isinstance(name_text, str) and name_text != "":
        if isinstance(group_name, str) and group_name != "":
            variable_ref["full_name"] = f"{group_name}.{name_text}"
        else:
            variable_ref["full_name"] = name_text
    else:
        variable_ref["full_name"] = None

    return variable_ref


def _resolve_variable_group_name(group_id: int) -> Optional[str]:
    # 目前样本确认：101 对应“关卡”（UI 变量选择器中的分组）
    name_by_id = {
        101: "关卡",
    }
    return name_by_id.get(int(group_id))


def _extract_variable_ref_from_nested_fields(nested_fields: List[Tuple[int, int, Any]]) -> Optional[Dict[str, Any]]:
    group_id: Optional[int] = None
    name_bytes: Optional[bytes] = None

    for field_number, wire_type, value in nested_fields:
        if field_number == 501 and wire_type == 0 and isinstance(value, int):
            group_id = int(value)
        if field_number == 502 and wire_type == 2 and isinstance(value, (bytes, bytearray)):
            name_bytes = bytes(value)

    if group_id is None and name_bytes is None:
        return None

    # observed: unset sentinel in some dumps (uint64 max) -> treat as -1 for readability
    if group_id == 18446744073709551615:
        group_id = -1

    name_text: Optional[str] = None
    name_utf8_hex: Optional[str] = None
    if name_bytes is not None:
        name_text = name_bytes.decode("utf-8", errors="replace")
        name_utf8_hex = name_bytes.hex()

    is_bound = isinstance(name_text, str) and name_text != ""
    return {
        "group_id": group_id,
        "name": name_text,
        "name_utf8_hex": name_utf8_hex,
        "is_bound": bool(is_bound),
    }


def _looks_like_variable_ref_nested_fields(nested_fields: List[Tuple[int, int, Any]]) -> bool:
    """
    变量引用嵌套 message 的宽松判定：
    - 允许缺失变量名（502），只要出现 group_id（501）即可视为“未绑定变量”。
    """
    has_group_id = False
    has_name_bytes = False
    for field_number, wire_type, value in nested_fields:
        if field_number == 501 and wire_type == 0 and isinstance(value, int):
            has_group_id = True
            continue
        if field_number == 502 and wire_type == 2 and isinstance(value, (bytes, bytearray)):
            has_name_bytes = True
            continue
    return bool(has_group_id or has_name_bytes)


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


def _parse_protobuf_like_fields(data: bytes) -> Tuple[List[Tuple[int, int, Any]], bool]:
    """
    将 data 当作 protobuf message 解析，返回 (fields, ok)。

    - fields: list[(field_number, wire_type, value)]
      - wire_type=0: value=int
      - wire_type=2: value=bytes
      - wire_type=1/5: value=bytes（raw）
    - ok=False 表示结构不完整/不合法（不会抛异常）。
    """
    fields: List[Tuple[int, int, Any]] = []
    current_offset = 0
    end_offset = len(data)

    while current_offset < end_offset:
        tag_value, current_offset, ok = _decode_varint(data, current_offset)
        if not ok:
            return fields, False
        if tag_value == 0:
            return fields, False

        field_number = tag_value >> 3
        wire_type = tag_value & 0x07
        if field_number <= 0:
            return fields, False

        if wire_type == 0:
            varint_value, current_offset, ok = _decode_varint(data, current_offset)
            if not ok:
                return fields, False
            fields.append((int(field_number), 0, int(varint_value)))
            continue

        if wire_type == 1:
            if current_offset + 8 > end_offset:
                return fields, False
            fields.append((int(field_number), 1, data[current_offset : current_offset + 8]))
            current_offset += 8
            continue

        if wire_type == 5:
            if current_offset + 4 > end_offset:
                return fields, False
            fields.append((int(field_number), 5, data[current_offset : current_offset + 4]))
            current_offset += 4
            continue

        if wire_type == 2:
            length_value, current_offset, ok = _decode_varint(data, current_offset)
            if not ok:
                return fields, False
            length_int = int(length_value)
            if length_int < 0:
                return fields, False
            if current_offset + length_int > end_offset:
                return fields, False
            value_bytes = data[current_offset : current_offset + length_int]
            current_offset += length_int
            fields.append((int(field_number), 2, value_bytes))
            continue

        return fields, False

    return fields, True


