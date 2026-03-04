from __future__ import annotations

import copy
from typing import Any, Dict, Optional, Tuple

from ugc_file_tools.ui_parsers.progress_bars import find_progressbar_binding_blob as _find_progressbar_binding_blob

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    allocate_next_guid as _allocate_next_guid,
    find_record_by_guid as _find_record_by_guid,
    get_children_guids_from_parent_record as _get_children_guids_from_parent_record,
    set_rect_transform_layer as _set_rect_transform_layer,
    set_widget_guid as _set_widget_guid,
    set_widget_name as _set_widget_name,
    set_widget_parent_guid_field504 as _set_widget_parent_guid_field504,
    try_extract_rect_transform_layer as _try_extract_rect_transform_layer,
)
from .web_ui_import_context import WebUiImportContext
from .web_ui_import_grouping import ensure_child_in_parent_children, remove_child_from_parent_children
from .web_ui_import_guid_registry import normalize_ui_key
from .web_ui_import_key_normalization import build_widget_source_meta
from .web_ui_import_layout import find_progressbar_binding_message_node
from .web_ui_import_progressbar import (
    map_progressbar_color_hex_to_code,
    map_progressbar_shape_to_code,
    map_progressbar_style_to_code,
    patch_progressbar_binding_blob_bytes,
    patch_progressbar_binding_message_in_place,
    write_progressbar_binding_blob_back_to_record,
)
from .web_ui_import_rect import parse_float_pair, write_rect_states_from_web_rect
from .web_ui_import_run_state import WebUiImportRunState
from .web_ui_import_types import ImportedWebProgressbar
from ugc_file_tools.custom_variables.refs import parse_variable_ref_text
from ugc_file_tools.custom_variables.web_ui_apply import normalize_progressbar_binding_text
from .web_ui_import_visibility import apply_visibility_patch, parse_initial_visible


def import_progressbar_widget(
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
    template_progressbar_record: Dict[str, Any],
    pc_canvas_size: Tuple[float, float],
) -> None:
    widget_type = str(widget.get("widget_type") or "").strip()
    if widget_type != "进度条":
        raise ValueError(f"internal error: widget_type mismatch: {widget_type!r}")

    widget_id = str(widget.get("widget_id") or "")
    ui_key = normalize_ui_key(widget.get("ui_key"), fallback=widget_id)
    widget_name_raw = str(widget.get("widget_name") or widget_id or widget_type or "控件")
    widget_name = widget_name_raw
    layer_index = int(widget.get("layer_index") or 0)

    pos = parse_float_pair(widget.get("position"), name="position")
    size = parse_float_pair(widget.get("size"), name="size")
    initial_visible = parse_initial_visible(widget.get("initial_visible"), default_value=True)

    desired_guid = int(ctx.ui_key_to_guid.get(ui_key) or 0) if ui_key else 0
    if desired_guid > 0:
        prev = ctx.reserved_guid_to_ui_key.get(int(desired_guid))
        if prev is not None and prev != ui_key:
            ctx.guid_collision_avoided.append(
                {
                    "ui_key": ui_key,
                    "expected_widget_type": "进度条",
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
            # 兼容：历史产物可能尚未启用“组件打组”，当本次启用了打组时允许把 record 从 layout 迁移到组容器下。
            if (int(desired_guid) not in children_now) and (target_parent_record is not layout_record):
                layout_children_now = _get_children_guids_from_parent_record(layout_record)
                if int(desired_guid) in layout_children_now:
                    children_now = layout_children_now
            if int(desired_guid) not in children_now:
                ctx.guid_collision_avoided.append(
                    {
                        "ui_key": ui_key,
                        "expected_widget_type": "进度条",
                        "desired_guid": int(desired_guid),
                        "existing_widget_name": "",
                        "reason": "guid_exists_but_not_in_target_parent_children",
                    }
                )
                existing_record = None
        if existing_record is not None:
            has_binding = _find_progressbar_binding_blob(existing_record) is not None
            has_message = find_progressbar_binding_message_node(existing_record) is not None
            if not has_binding and not has_message:
                from .web_ui_import_rect import try_extract_widget_name

                existing_name = try_extract_widget_name(existing_record) or ""
                ctx.guid_collision_avoided.append(
                    {
                        "ui_key": ui_key,
                        "expected_widget_type": "进度条",
                        "desired_guid": int(desired_guid),
                        "existing_widget_name": existing_name,
                        "reason": "guid_record_shape_mismatch_missing_progressbar_binding",
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
        record = copy.deepcopy(template_progressbar_record)
        _set_widget_guid(record, int(new_guid))
        _set_widget_name(record, widget_name)
        _set_widget_parent_guid_field504(record, int(target_parent_guid))
        created_new_record = True

    # 关键：无论是“新建”还是“复用已有 record”，都要把 ui_key→guid 写回 registry（避免 registry 漏 key）。
    #
    # 背景：registry 只在“写回 UI”时更新；若复用时不回写映射，且旧 registry 里恰好缺该 key，
    # 则会出现“UI+节点图同次写回时，节点图阶段解析 ui_key 占位符失败”的问题。
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
        raise RuntimeError("internal error: progressbar record missing state_index=0 after clone")
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

    settings = widget.get("settings")
    if not isinstance(settings, dict):
        settings = {}
    shape_code = map_progressbar_shape_to_code(str(settings.get("shape") or "").strip())
    style_code = map_progressbar_style_to_code(str(settings.get("style") or "").strip())
    color_code = map_progressbar_color_hex_to_code(str(settings.get("color") or "").strip())

    current_var = settings.get("current_var")
    min_var = settings.get("min_var")
    max_var = settings.get("max_var")

    current_text = str(current_var) if current_var is not None else ""
    min_text = str(min_var) if min_var is not None else ""
    max_text = str(max_var) if max_var is not None else ""

    before_current = str(current_text)
    before_min = str(min_text)
    before_max = str(max_text)
    current_text = normalize_progressbar_binding_text(role="current", text=current_text)
    min_text = normalize_progressbar_binding_text(role="min", text=min_text)
    max_text = normalize_progressbar_binding_text(role="max", text=max_text)
    if (current_text != before_current) or (min_text != before_min) or (max_text != before_max):
        run.progressbar_binding_auto_filled_total += 1

    # 约定（对齐 UI源码 目录规则）：
    # - current：必须为变量引用（或 '.' / '' 触发自动补齐）
    # - min/max：允许数字常量（例如 0/100）
    current_group_id, current_var_name, current_full = parse_variable_ref_text(current_text, allow_constant_number=False)
    min_group_id, min_var_name, min_full = parse_variable_ref_text(min_text, allow_constant_number=True)
    max_group_id, max_var_name, max_full = parse_variable_ref_text(max_text, allow_constant_number=True)

    if current_full:
        run.referenced_variable_full_names.add(str(current_full))
    if min_full:
        run.referenced_variable_full_names.add(str(min_full))
    if max_full:
        run.referenced_variable_full_names.add(str(max_full))

    def record_progressbar_var(role: str, var_name: Optional[str], full_name: Optional[str]) -> None:
        if not full_name or not var_name:
            return
        if "." not in str(full_name):
            return
        group_name = str(full_name).split(".", 1)[0]
        key = (group_name, str(var_name))
        run.progressbar_variable_roles.setdefault(key, set()).add(str(role))

    record_progressbar_var("current", current_var_name, current_full)
    record_progressbar_var("min", min_var_name, min_full)
    record_progressbar_var("max", max_var_name, max_full)

    hit = _find_progressbar_binding_blob(record)
    if hit is not None:
        binding_path, binding_blob = hit
        patched_blob = patch_progressbar_binding_blob_bytes(
            blob_bytes=binding_blob,
            shape_code=shape_code,
            style_code=style_code,
            color_code=color_code,
            current_text=current_text,
            min_text=min_text,
            max_text=max_text,
        )
        write_progressbar_binding_blob_back_to_record(
            record,
            binding_path=binding_path,
            new_blob_bytes=patched_blob,
        )
    else:
        msg_hit = find_progressbar_binding_message_node(record)
        if msg_hit is None:
            raise RuntimeError(f"克隆后的 record 不包含可识别的进度条 binding（blob/message 均未命中）：guid={int(new_guid)}")
        _, binding_message = msg_hit
        patch_progressbar_binding_message_in_place(
            binding_message,
            shape_code=shape_code,
            style_code=style_code,
            color_code=color_code,
            current_text=current_text,
            min_text=min_text,
            max_text=max_text,
        )

    if created_new_record:
        ctx.ui_record_list.append(record)
    run.visibility_changed_total += int(apply_visibility_patch(record, visible=bool(initial_visible)))

    ensure_child_in_parent_children(target_parent_record, int(new_guid))
    run.import_order_by_guid[int(new_guid)] = min(int(widget_index), int(run.import_order_by_guid.get(int(new_guid), widget_index)))
    if target_parent_record is not layout_record:
        remove_child_from_parent_children(layout_record, int(new_guid))
        group_child_entries.setdefault(group_key, []).append((int(layer_index), int(widget_index), int(new_guid)))

    run.imported_progressbars.append(
        ImportedWebProgressbar(
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
            raw_codes={
                "shape_code": int(shape_code),
                "style_code": int(style_code),
                "color_code": int(color_code),
            },
        )
    )

