from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.ui_schema_library.library import find_schema_ids_by_label, load_schema_record

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    DEFAULT_CANVAS_SIZE_BY_STATE_INDEX,
    allocate_next_guid as _allocate_next_guid,
    append_children_guids_to_parent_record as _append_children_guids_to_parent_record,
    collect_all_widget_guids as _collect_all_widget_guids,
    dump_gil_to_raw_json_object as _dump_gil_to_raw_json_object,
    find_record_by_guid as _find_record_by_guid,
    get_children_guids_from_parent_record as _get_children_guids_from_parent_record,
    set_rect_state_canvas_position_and_size as _set_rect_state_canvas_position_and_size,
    set_widget_guid as _set_widget_guid,
    set_widget_name as _set_widget_name,
    set_widget_parent_guid_field504 as _set_widget_parent_guid_field504,
    write_back_modified_gil_by_reencoding_payload as _write_back_modified_gil_by_reencoding_payload,
)


_UI_SCHEMA_LABEL_TEXTBOX = "textbox"


def _try_extract_textbox_text_node(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    尝试从一个 UI record 中提取 TextBox 的“文本配置节点”（node19）。

    约定样本结构（不硬编码 component index）：
    - record['505'][?]['503']['19'] 为 TextBox 相关节点 dict
    - node19['505']['501'] 为文本内容（string）
    """
    component_list = record.get("505")
    if not isinstance(component_list, list):
        return None
    for component in component_list:
        if not isinstance(component, dict):
            continue
        nested = component.get("503")
        if not isinstance(nested, dict):
            continue
        node19 = nested.get("19")
        if not isinstance(node19, dict):
            continue
        return node19
    return None


def _has_rect_transform_state(record: Dict[str, Any], *, state_index: int) -> bool:
    component_list = record.get("505")
    if not isinstance(component_list, list) or len(component_list) < 3:
        return False
    rect_component = component_list[2]
    if not isinstance(rect_component, dict):
        return False
    node503 = rect_component.get("503")
    if not isinstance(node503, dict):
        return False
    node13 = node503.get("13")
    if not isinstance(node13, dict):
        return False
    node12 = node13.get("12")
    if not isinstance(node12, dict):
        return False
    state_list = node12.get("501")
    if not isinstance(state_list, list) or not state_list:
        return False
    for state in state_list:
        if not isinstance(state, dict):
            continue
        idx_value = state.get("501")
        idx = int(idx_value) if isinstance(idx_value, int) else 0
        if idx == int(state_index):
            transform = state.get("502")
            return isinstance(transform, dict)
    return False


def _choose_textbox_record_template(ui_record_list: List[Any]) -> Optional[Dict[str, Any]]:
    """
    选择一个可作为“克隆模板”的 TextBox UI record：
    - 必须能定位到 text_node（见 `_try_extract_textbox_text_node`）
    - 必须包含 RectTransform state0（用于写回坐标）
    - 要求无 children（避免处理子树克隆）
    """
    best_score: Optional[int] = None
    best_record: Optional[Dict[str, Any]] = None

    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        if _try_extract_textbox_text_node(record) is None:
            continue
        if not _has_rect_transform_state(record, state_index=0):
            continue
        if _get_children_guids_from_parent_record(record):
            continue

        score = 0
        component_list = record.get("505")
        if isinstance(component_list, list) and component_list:
            name_component = component_list[0]
            if isinstance(name_component, dict):
                node12 = name_component.get("12")
                if isinstance(node12, dict) and node12.get("501") == "文本框":
                    score += 10

        if best_score is None or score > best_score:
            best_score = score
            best_record = record

    return best_record


def _load_textbox_template_record_from_schema_library() -> Optional[Dict[str, Any]]:
    schema_ids = find_schema_ids_by_label(_UI_SCHEMA_LABEL_TEXTBOX)
    if not schema_ids:
        return None
    candidates: List[Dict[str, Any]] = []
    for sid in schema_ids:
        candidates.append(load_schema_record(sid))
    return _choose_textbox_record_template(candidates)


def _set_textbox_content(record: Dict[str, Any], *, content: str) -> None:
    node19 = _try_extract_textbox_text_node(record)
    if node19 is None:
        raise RuntimeError("record 不包含可识别的 TextBox 文本节点（node19）")
    node505 = node19.get("505")
    if not isinstance(node505, dict):
        node505 = {}
        node19["505"] = node505
    node505["501"] = str(content or "")


def _extract_rect_pivot_from_state0(record: Dict[str, Any]) -> Tuple[float, float]:
    component_list = record.get("505")
    if not isinstance(component_list, list) or len(component_list) < 3:
        return 0.5, 0.5
    rect_component = component_list[2]
    if not isinstance(rect_component, dict):
        return 0.5, 0.5
    node503 = rect_component.get("503")
    if not isinstance(node503, dict):
        return 0.5, 0.5
    node13 = node503.get("13")
    if not isinstance(node13, dict):
        return 0.5, 0.5
    node12 = node13.get("12")
    if not isinstance(node12, dict):
        return 0.5, 0.5
    state_list = node12.get("501")
    if not isinstance(state_list, list):
        return 0.5, 0.5
    for state in state_list:
        if not isinstance(state, dict):
            continue
        if int(state.get("501") or 0) != 0:
            continue
        transform = state.get("502")
        if not isinstance(transform, dict):
            continue
        pivot_node = transform.get("506")
        if not isinstance(pivot_node, dict):
            return 0.5, 0.5
        px = pivot_node.get("501")
        py = pivot_node.get("502")
        pivot_x = float(px) if isinstance(px, (int, float)) else 0.5
        pivot_y = float(py) if isinstance(py, (int, float)) else 0.5
        return pivot_x, pivot_y
    return 0.5, 0.5


def _top_left_to_canvas_position(
    *,
    left: float,
    top: float,
    width: float,
    height: float,
    pivot: Tuple[float, float],
    canvas_height: float,
) -> Tuple[float, float]:
    """
    输入：top-left 原点坐标系（y 向下）
    输出：canvas 坐标系（left-bottom 原点，写回的是 pivot 的 canvas 坐标）
    """
    pivot_x, pivot_y = float(pivot[0]), float(pivot[1])
    x_top_left = float(left) + pivot_x * float(width)
    y_top_left = float(top) + (1.0 - pivot_y) * float(height)
    return float(x_top_left), float(canvas_height) - float(y_top_left)


def add_textbox_to_gil(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    parent_guid: int,
    name: str,
    content: str,
    canvas_position: Tuple[float, float],
    size: Tuple[float, float],
    verify_new_guid_exists: bool = True,
) -> Dict[str, Any]:
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    payload_root = raw_dump_object.get("4")
    if not isinstance(payload_root, dict):
        raise ValueError("dump-json 缺少根字段 '4'（期望为 dict）。")
    node9 = payload_root.get("9")
    if not isinstance(node9, dict):
        raise ValueError("dump-json 缺少字段 '4/9'（期望为 dict）。")
    ui_record_list = node9.get("502")
    if not isinstance(ui_record_list, list):
        raise ValueError("dump-json 缺少字段 '4/9/502'（期望为 list）。")

    existing_guids = _collect_all_widget_guids(ui_record_list)
    if not existing_guids:
        raise RuntimeError("无法收集现有 GUID（疑似 dump 结构异常）。")

    parent_record = _find_record_by_guid(ui_record_list, int(parent_guid))
    if parent_record is None:
        raise RuntimeError(f"未找到 parent_guid={int(parent_guid)} 对应的 UI record。")

    template_record = _choose_textbox_record_template(ui_record_list)
    if template_record is None:
        template_record = _load_textbox_template_record_from_schema_library()
    if template_record is None:
        raise RuntimeError(
            "未找到任何可克隆的 TextBox record（输入 .gil 不含文本框且 schema library 未沉淀 textbox 模板）。"
        )

    reserved = set(existing_guids)
    allocated_guid = _allocate_next_guid(reserved, start=max(reserved) + 1)
    reserved.add(int(allocated_guid))

    cloned = copy.deepcopy(template_record)
    _set_widget_guid(cloned, int(allocated_guid))
    _set_widget_parent_guid_field504(cloned, int(parent_guid))
    _set_widget_name(cloned, str(name))
    _set_textbox_content(cloned, content=str(content))

    _set_rect_state_canvas_position_and_size(
        record=cloned,
        state_index=0,
        canvas_position=(float(canvas_position[0]), float(canvas_position[1])),
        size=(float(size[0]), float(size[1])),
        canvas_size_by_state_index=dict(DEFAULT_CANVAS_SIZE_BY_STATE_INDEX),
    )

    ui_record_list.append(cloned)
    _append_children_guids_to_parent_record(parent_record, [int(allocated_guid)])

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_path,
        output_gil_path=output_path,
    )

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "parent_guid": int(parent_guid),
        "created_guid": int(allocated_guid),
        "name": str(name),
        "size": {"x": float(size[0]), "y": float(size[1])},
        "canvas_position": {"x": float(canvas_position[0]), "y": float(canvas_position[1])},
    }

    if verify_new_guid_exists:
        verify_dump = _dump_gil_to_raw_json_object(output_path)
        verify_root = verify_dump.get("4")
        verify_node9 = verify_root.get("9") if isinstance(verify_root, dict) else None
        verify_records = verify_node9.get("502") if isinstance(verify_node9, dict) else None
        ok = False
        if isinstance(verify_records, list):
            ok = _find_record_by_guid(verify_records, int(allocated_guid)) is not None
        report["verify"] = {"ok": bool(ok)}

    return report


def update_textbox_content_in_gil(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    guid: int,
    content: str,
    verify_guid_exists: bool = True,
) -> Dict[str, Any]:
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    payload_root = raw_dump_object.get("4")
    if not isinstance(payload_root, dict):
        raise ValueError("dump-json 缺少根字段 '4'（期望为 dict）。")
    node9 = payload_root.get("9")
    if not isinstance(node9, dict):
        raise ValueError("dump-json 缺少字段 '4/9'（期望为 dict）。")
    ui_record_list = node9.get("502")
    if not isinstance(ui_record_list, list):
        raise ValueError("dump-json 缺少字段 '4/9/502'（期望为 list）。")

    record = _find_record_by_guid(ui_record_list, int(guid))
    if record is None:
        raise RuntimeError(f"未找到 guid={int(guid)} 对应的 UI record。")

    _set_textbox_content(record, content=str(content))

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_path,
        output_gil_path=output_path,
    )

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "guid": int(guid),
    }

    if verify_guid_exists:
        verify_dump = _dump_gil_to_raw_json_object(output_path)
        verify_root = verify_dump.get("4")
        verify_node9 = verify_root.get("9") if isinstance(verify_root, dict) else None
        verify_records = verify_node9.get("502") if isinstance(verify_node9, dict) else None
        ok = False
        if isinstance(verify_records, list):
            ok = _find_record_by_guid(verify_records, int(guid)) is not None
        report["verify"] = {"ok": bool(ok)}

    return report


def _build_rich_text_rows_from_image(
    *,
    image_file_path: Path,
    resolution: Tuple[int, int],
    grain_size: int,
) -> List[str]:
    from PIL import Image

    image_path = Path(image_file_path).resolve()
    if not image_path.is_file():
        raise FileNotFoundError(str(image_path))

    w, h = int(resolution[0]), int(resolution[1])
    if w <= 0 or h <= 0:
        raise ValueError(f"invalid resolution: {resolution!r}")
    g = int(grain_size)
    if g <= 0:
        raise ValueError(f"grain_size must be positive, got {g}")

    img = Image.open(str(image_path)).convert("RGB").resize((w, h))
    px = img.load()
    if px is None:
        raise RuntimeError("failed to load image pixels")

    cols = max(1, w // g)
    rows = max(1, h // g)

    out_rows: List[str] = []
    for row in range(rows):
        y0 = row * g
        parts: List[str] = []
        current_hex: Optional[str] = None
        current_run = 0

        def flush_run() -> None:
            nonlocal current_hex, current_run
            if current_hex is None or current_run <= 0:
                current_hex = None
                current_run = 0
                return
            parts.append(f"<color=#{current_hex}>" + ("█" * current_run) + "</color>")
            current_hex = None
            current_run = 0

        for col in range(cols):
            x0 = col * g
            # block average
            r_sum = 0
            g_sum = 0
            b_sum = 0
            count = 0
            for dy in range(g):
                yy = y0 + dy
                if yy >= h:
                    break
                for dx in range(g):
                    xx = x0 + dx
                    if xx >= w:
                        break
                    r, gg, b = px[xx, yy]
                    r_sum += int(r)
                    g_sum += int(gg)
                    b_sum += int(b)
                    count += 1
            if count <= 0:
                block_hex = "000000"
            else:
                rr = int(r_sum / count)
                gg2 = int(g_sum / count)
                bb = int(b_sum / count)
                block_hex = f"{rr:02X}{gg2:02X}{bb:02X}"

            if current_hex is None:
                current_hex = block_hex
                current_run = 1
            elif current_hex == block_hex:
                current_run += 1
            else:
                flush_run()
                current_hex = block_hex
                current_run = 1

        flush_run()
        out_rows.append("".join(parts))

    return out_rows


def write_image_as_textboxes_in_gil(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    parent_guid: int,
    image_file_path: Path,
    resolution: Tuple[int, int],
    position_top_left: Tuple[float, float],
    text_box_height: float,
    grain_size: int,
    name_prefix: str = "image_row",
    verify_new_guids_exist: bool = True,
) -> Dict[str, Any]:
    """
    纯 Python 版本：图片 → 富文本 TextBox 网格。

    坐标约定（对齐 `web_ui_import`）：
    - position_top_left: (left, top)，原点在画布左上角，y 向下。
    - 写回 RectTransform 时，会转换为“画布左下角原点”的 pivot canvas 坐标。
    """
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    w, h = int(resolution[0]), int(resolution[1])
    if w <= 0 or h <= 0:
        raise ValueError(f"invalid resolution: {resolution!r}")
    row_h = float(text_box_height)
    if row_h <= 0:
        raise ValueError(f"text_box_height must be > 0, got {row_h}")

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    payload_root = raw_dump_object.get("4")
    if not isinstance(payload_root, dict):
        raise ValueError("dump-json 缺少根字段 '4'（期望为 dict）。")
    node9 = payload_root.get("9")
    if not isinstance(node9, dict):
        raise ValueError("dump-json 缺少字段 '4/9'（期望为 dict）。")
    ui_record_list = node9.get("502")
    if not isinstance(ui_record_list, list):
        raise ValueError("dump-json 缺少字段 '4/9/502'（期望为 list）。")

    existing_guids = _collect_all_widget_guids(ui_record_list)
    if not existing_guids:
        raise RuntimeError("无法收集现有 GUID（疑似 dump 结构异常）。")

    parent_record = _find_record_by_guid(ui_record_list, int(parent_guid))
    if parent_record is None:
        raise RuntimeError(f"未找到 parent_guid={int(parent_guid)} 对应的 UI record。")

    template_record = _choose_textbox_record_template(ui_record_list)
    if template_record is None:
        template_record = _load_textbox_template_record_from_schema_library()
    if template_record is None:
        raise RuntimeError(
            "未找到任何可克隆的 TextBox record（输入 .gil 不含文本框且 schema library 未沉淀 textbox 模板）。"
        )

    pivot = _extract_rect_pivot_from_state0(template_record)
    canvas_h = float(DEFAULT_CANVAS_SIZE_BY_STATE_INDEX[0][1])

    rows = _build_rich_text_rows_from_image(
        image_file_path=Path(image_file_path),
        resolution=(int(w), int(h)),
        grain_size=int(grain_size),
    )
    if not rows:
        raise RuntimeError("image produced no rows")

    left0, top0 = float(position_top_left[0]), float(position_top_left[1])

    reserved = set(existing_guids)
    created_guids: List[int] = []

    for row_index, row_text in enumerate(rows):
        allocated_guid = _allocate_next_guid(reserved, start=max(reserved) + 1)
        reserved.add(int(allocated_guid))

        cloned = copy.deepcopy(template_record)
        _set_widget_guid(cloned, int(allocated_guid))
        _set_widget_parent_guid_field504(cloned, int(parent_guid))
        _set_widget_name(cloned, f"{str(name_prefix)}_{row_index:03d}")
        _set_textbox_content(cloned, content=row_text)

        top = float(top0) + float(row_index) * float(row_h)
        canvas_pos = _top_left_to_canvas_position(
            left=float(left0),
            top=float(top),
            width=float(w),
            height=float(row_h),
            pivot=pivot,
            canvas_height=float(canvas_h),
        )
        _set_rect_state_canvas_position_and_size(
            record=cloned,
            state_index=0,
            canvas_position=(float(canvas_pos[0]), float(canvas_pos[1])),
            size=(float(w), float(row_h)),
            canvas_size_by_state_index=dict(DEFAULT_CANVAS_SIZE_BY_STATE_INDEX),
        )

        ui_record_list.append(cloned)
        created_guids.append(int(allocated_guid))

    _append_children_guids_to_parent_record(parent_record, [int(g) for g in created_guids])

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_path,
        output_gil_path=output_path,
    )

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "parent_guid": int(parent_guid),
        "image_file": str(Path(image_file_path).resolve()),
        "resolution": {"x": int(w), "y": int(h)},
        "position_top_left": {"x": float(left0), "y": float(top0)},
        "text_box_height": float(row_h),
        "grain_size": int(grain_size),
        "created_total": int(len(created_guids)),
        "created_guids": created_guids,
    }

    if verify_new_guids_exist:
        verify_dump = _dump_gil_to_raw_json_object(output_path)
        verify_root = verify_dump.get("4")
        verify_node9 = verify_root.get("9") if isinstance(verify_root, dict) else None
        verify_records = verify_node9.get("502") if isinstance(verify_node9, dict) else None
        ok = False
        if isinstance(verify_records, list):
            ok = all(_find_record_by_guid(verify_records, int(g)) is not None for g in created_guids)
        report["verify"] = {"ok": bool(ok)}

    return report


__all__ = [
    "add_textbox_to_gil",
    "update_textbox_content_in_gil",
    "write_image_as_textboxes_in_gil",
]

