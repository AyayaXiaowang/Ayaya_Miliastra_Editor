from __future__ import annotations

import copy
from typing import Any, Dict, Optional, Tuple

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    allocate_next_guid as _allocate_next_guid,
    find_record_by_guid as _find_record_by_guid,
    get_children_guids_from_parent_record as _get_children_guids_from_parent_record,
    set_rect_transform_layer as _set_rect_transform_layer,
    set_widget_guid as _set_widget_guid,
    set_widget_name as _set_widget_name,
    set_widget_parent_guid_field504 as _set_widget_parent_guid_field504,
)
from .web_ui_import_context import WebUiImportContext
from .web_ui_import_grouping import ensure_child_in_parent_children, remove_child_from_parent_children
from .web_ui_import_guid_registry import normalize_ui_key
from .web_ui_import_key_normalization import build_widget_source_meta
from .web_ui_import_rect import parse_float_pair, try_extract_textbox_text_node, write_rect_states_from_web_rect
from .web_ui_import_run_state import WebUiImportRunState
from .web_ui_import_textbox import write_textbox_text_and_style
from .web_ui_import_types import ImportedWebTextbox
from ugc_file_tools.custom_variables.refs import extract_variable_refs_from_text_placeholders
from .web_ui_import_visibility import apply_visibility_patch, parse_initial_visible


def import_textbox_widget(
    ctx: WebUiImportContext,
    run: WebUiImportRunState,
    *,
    widget_index: int,
    widget: Dict[str, Any],
    target_parent_record: Dict[str, Any],
    target_parent_guid: int,
    layout_record: Dict[str, Any],
    group_key: str,
    group_child_entries: Dict[str, list[tuple[int, int, int]]],
    template_textbox_record: Dict[str, Any],
    pc_canvas_size: Tuple[float, float],
) -> None:
    widget_type = str(widget.get("widget_type") or "").strip()
    if widget_type != "文本框":
        raise ValueError(f"internal error: widget_type mismatch: {widget_type!r}")

    widget_id = str(widget.get("widget_id") or "")
    ui_key = normalize_ui_key(widget.get("ui_key"), fallback=widget_id)
    widget_name_raw = str(widget.get("widget_name") or widget_id or widget_type or "控件")
    widget_name = widget_name_raw
    layer_index = int(widget.get("layer_index") or 0)

    pos = parse_float_pair(widget.get("position"), name="position")
    size = parse_float_pair(widget.get("size"), name="size")
    settings = widget.get("settings")
    if not isinstance(settings, dict):
        settings = {}
    initial_visible = parse_initial_visible(widget.get("initial_visible"), default_value=True)
    text_content = str(settings.get("text_content") or "")
    background_color = str(settings.get("background_color") or "")
    for group_name, var_name, field_path in extract_variable_refs_from_text_placeholders(text_content):
        g = str(group_name)
        n = str(var_name)
        fp = tuple(str(x) for x in (field_path or ()))
        run.text_placeholder_variable_refs.add((g, n, fp))
        # referenced_variable_full_names 仅记录“根变量名”，避免把 dict 字段路径当作多个变量
        run.referenced_variable_full_names.add(f"{g}.{n}")
    font_size_value = settings.get("font_size")
    font_size_int = int(font_size_value) if isinstance(font_size_value, int) else 16
    alignment_h = str(settings.get("alignment_h") or "").strip()
    alignment_v = str(settings.get("alignment_v") or "").strip()

    desired_guid = int(ctx.ui_key_to_guid.get(ui_key) or 0) if ui_key else 0
    if desired_guid > 0:
        prev = ctx.reserved_guid_to_ui_key.get(int(desired_guid))
        if prev is not None and prev != ui_key:
            ctx.guid_collision_avoided.append(
                {
                    "ui_key": ui_key,
                    "expected_widget_type": "文本框",
                    "desired_guid": int(desired_guid),
                    "existing_widget_name": "",
                    "reason": f"guid_already_reserved_by_other_ui_key:{prev}",
                }
            )
            desired_guid = 0

    existing_record: Optional[Dict[str, Any]] = None
    if desired_guid > 0:
        existing_record = _find_record_by_guid(ctx.ui_record_list, int(desired_guid))
        if existing_record is not None:
            children_now = _get_children_guids_from_parent_record(target_parent_record)
            if (int(desired_guid) not in children_now) and (target_parent_record is not layout_record):
                layout_children_now = _get_children_guids_from_parent_record(layout_record)
                if int(desired_guid) in layout_children_now:
                    children_now = layout_children_now
            if int(desired_guid) not in children_now:
                ctx.guid_collision_avoided.append(
                    {
                        "ui_key": ui_key,
                        "expected_widget_type": "文本框",
                        "desired_guid": int(desired_guid),
                        "existing_widget_name": "",
                        "reason": "guid_exists_but_not_in_target_parent_children",
                    }
                )
                existing_record = None
        if existing_record is not None and try_extract_textbox_text_node(existing_record) is None:
            from .web_ui_import_rect import try_extract_widget_name

            existing_name = try_extract_widget_name(existing_record) or ""
            ctx.guid_collision_avoided.append(
                {
                    "ui_key": ui_key,
                    "expected_widget_type": "文本框",
                    "desired_guid": int(desired_guid),
                    "existing_widget_name": existing_name,
                    "reason": "guid_record_shape_mismatch_missing_textbox_node19",
                }
            )
            existing_record = None

    record: Dict[str, Any]
    new_guid: int
    created_new_record = False

    if existing_record is not None:
        record = existing_record
        new_guid = int(desired_guid)
        _set_widget_name(record, widget_name)
        _set_widget_parent_guid_field504(record, int(target_parent_guid))
    else:
        new_guid = _allocate_next_guid(ctx.existing_guids, start=max(ctx.existing_guids) + 1)
        ctx.existing_guids.add(int(new_guid))
        ctx.ui_key_to_guid[ui_key] = int(new_guid)
        record = copy.deepcopy(template_textbox_record)
        _set_widget_guid(record, int(new_guid))
        _set_widget_name(record, widget_name)
        _set_widget_parent_guid_field504(record, int(target_parent_guid))
        created_new_record = True

    # 关键：复用时也必须写回 ui_key→guid（否则 registry 可能长期缺 key，导致节点图占位符无法稳定解析）。
    ctx.ui_key_to_guid[str(ui_key)] = int(new_guid)

    ctx.reserved_guid_to_ui_key[int(new_guid)] = str(ui_key)
    run.widget_sources_by_guid[int(new_guid)] = build_widget_source_meta(
        widget,
        ui_key=str(ui_key),
        widget_id=str(widget_id),
        widget_name=str(widget_name),
        widget_type=str(widget_type),
        widget_index=int(widget_index),
        group_key=str(group_key),
    )

    states_written = write_rect_states_from_web_rect(
        record,
        web_left=float(pos[0]),
        web_top=float(pos[1]),
        web_width=float(size[0]),
        web_height=float(size[1]),
        reference_pc_canvas_size=ctx.reference_pc_canvas_size,
        canvas_size_by_state_index=ctx.canvas_size_by_state_index,
    )

    pc_state = states_written.get(0)
    if pc_state is None:
        raise RuntimeError("internal error: textbox record missing state_index=0 after clone")
    pc_canvas_pos = pc_state["canvas_position"]

    mobile_state = states_written.get(1)
    mobile_canvas_pos: Optional[Tuple[float, float]] = mobile_state["canvas_position"] if mobile_state else None
    mobile_size_value: Optional[Tuple[float, float]] = mobile_state["size"] if mobile_state else None

    console_state = states_written.get(2)
    console_canvas_pos: Optional[Tuple[float, float]] = console_state["canvas_position"] if console_state else None
    console_size_value: Optional[Tuple[float, float]] = console_state["size"] if console_state else None

    gamepad_state = states_written.get(3)
    gamepad_canvas_pos: Optional[Tuple[float, float]] = gamepad_state["canvas_position"] if gamepad_state else None
    gamepad_size_value: Optional[Tuple[float, float]] = gamepad_state["size"] if gamepad_state else None

    _set_rect_transform_layer(record, int(layer_index))
    raw_text_codes = write_textbox_text_and_style(
        record,
        text_content=text_content,
        background_color=background_color,
        font_size=int(font_size_int),
        alignment_h=alignment_h,
        alignment_v=alignment_v,
    )
    run.visibility_changed_total += int(apply_visibility_patch(record, visible=bool(initial_visible)))

    if created_new_record:
        ctx.ui_record_list.append(record)
    ensure_child_in_parent_children(target_parent_record, int(new_guid))
    run.import_order_by_guid[int(new_guid)] = min(int(widget_index), int(run.import_order_by_guid.get(int(new_guid), widget_index)))
    if target_parent_record is not layout_record:
        remove_child_from_parent_children(layout_record, int(new_guid))
        group_child_entries.setdefault(group_key, []).append((int(layer_index), int(widget_index), int(new_guid)))

    run.imported_textboxes.append(
        ImportedWebTextbox(
            ui_key=ui_key,
            widget_id=widget_id,
            widget_name=widget_name,
            guid=int(new_guid),
            layer=int(layer_index),
            initial_visible=bool(initial_visible),
            pc_canvas_position=(float(pc_canvas_pos[0]), float(pc_canvas_pos[1])),
            pc_size=(float(pc_state["size"][0]), float(pc_state["size"][1])),
            mobile_canvas_position=mobile_canvas_pos,
            mobile_size=mobile_size_value,
            console_canvas_position=console_canvas_pos,
            console_size=console_size_value,
            gamepad_canvas_position=gamepad_canvas_pos,
            gamepad_size=gamepad_size_value,
            text_content=text_content,
            font_size=int(font_size_int),
            raw_codes=dict(raw_text_codes),
        )
    )

