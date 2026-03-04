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
from .web_ui_import_item_display import (
    find_item_display_binding,
    map_item_display_type_to_code,
    patch_item_display_binding,
    write_item_display_binding_back_to_record,
)
from .web_ui_import_constants import (
    DEFAULT_ITEM_DISPLAY_BUTTON_CONFIG_ID_VARIABLE_FULL_NAME,
    DEFAULT_ITEM_DISPLAY_BUTTON_COOLDOWN_SECONDS_VARIABLE_FULL_NAME,
    DEFAULT_ITEM_DISPLAY_BUTTON_QUANTITY_VARIABLE_FULL_NAME,
)
from .web_ui_import_rect import parse_float_pair, write_rect_states_from_web_rect
from .web_ui_import_run_state import WebUiImportRunState
from .web_ui_import_types import ImportedWebItemDisplay
from ugc_file_tools.custom_variables.refs import parse_variable_ref_text
from .web_ui_import_visibility import apply_visibility_patch, parse_initial_visible


def import_item_display_widget(
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
    template_item_display_record: Dict[str, Any],
    pc_canvas_size: Tuple[float, float],
    ui_action_meta_by_ui_key: Dict[str, Dict[str, str]],
) -> None:
    widget_type = str(widget.get("widget_type") or "").strip()
    if widget_type != "道具展示":
        raise ValueError(f"internal error: widget_type mismatch: {widget_type!r}")

    widget_id = str(widget.get("widget_id") or "")
    ui_key = normalize_ui_key(widget.get("ui_key"), fallback=widget_id)
    widget_name_raw = str(widget.get("widget_name") or widget_id or widget_type or "控件")
    widget_name = widget_name_raw
    layer_index = int(widget.get("layer_index") or 0)

    pos = parse_float_pair(widget.get("position"), name="position")
    size = parse_float_pair(widget.get("size"), name="size")
    initial_visible = parse_initial_visible(widget.get("initial_visible"), default_value=True)
    settings = widget.get("settings")
    if not isinstance(settings, dict):
        settings = {}
    display_type = str(settings.get("display_type") or "").strip() or "玩家当前装备"

    can_interact = bool(settings.get("can_interact")) if isinstance(settings, dict) else False
    if can_interact:
        # 约定：可交互按钮锚点道具展示默认视为“模板道具”，并绑定到“关卡实体变量”。
        # 若用户显式提供了变量名，则以用户为准。
        if str(display_type or "").strip() in ("", "玩家当前装备"):
            display_type = "模板道具"
            settings["display_type"] = "模板道具"

        config_var_raw = settings.get("config_id_variable")
        if not isinstance(config_var_raw, str) or str(config_var_raw).strip() in ("", "."):
            settings["config_id_variable"] = str(DEFAULT_ITEM_DISPLAY_BUTTON_CONFIG_ID_VARIABLE_FULL_NAME)

        qty_var_raw = settings.get("quantity_variable")
        if not isinstance(qty_var_raw, str) or str(qty_var_raw).strip() in ("", "."):
            settings["quantity_variable"] = str(DEFAULT_ITEM_DISPLAY_BUTTON_QUANTITY_VARIABLE_FULL_NAME)

        cooldown_var_raw = settings.get("cooldown_seconds_variable")
        if not isinstance(cooldown_var_raw, str) or str(cooldown_var_raw).strip() in ("", "."):
            settings["cooldown_seconds_variable"] = str(DEFAULT_ITEM_DISPLAY_BUTTON_COOLDOWN_SECONDS_VARIABLE_FULL_NAME)

        # 约束（软）：优先保持 1..14 且同页唯一（键鼠/手柄同号）。
        # 重要：即使用户配置/导出端产生了重复，也不应阻断导出；改为记录 warning 并继续。
        def _normalize_code(value: Any) -> int:
            if isinstance(value, bool):
                return 0
            if isinstance(value, int):
                return int(value)
            if isinstance(value, float):
                return int(value)
            if isinstance(value, str) and value.strip().isdigit():
                return int(value.strip())
            return 0

        kbm_code = _normalize_code(settings.get("keybind_kbm_code"))
        pad_code = _normalize_code(settings.get("keybind_gamepad_code"))

        if kbm_code > 0 and pad_code > 0 and kbm_code != pad_code:
            raise ValueError(
                f"可交互道具展示的按键码必须一致（键鼠/手柄必须同号）：ui_key={ui_key!r}, widget_name={widget_name!r}, "
                f"keybind_kbm_code={kbm_code}, keybind_gamepad_code={pad_code}"
            )
        desired_code = kbm_code if kbm_code > 0 else (pad_code if pad_code > 0 else 0)
        explicit_code = bool(desired_code > 0)

        used = run.interactive_item_display_key_codes_used
        if desired_code <= 0:
            # 未显式提供按键码：尽量分配未占用的 1..14；若已满则回退为 1（允许重复，不阻断导出）
            for c in range(1, 15):
                if c not in used:
                    desired_code = c
                    break
            if desired_code <= 0:
                desired_code = 1
                run.interactive_item_display_key_code_warnings.append(
                    {
                        "ui_key": ui_key,
                        "widget_name": widget_name,
                        "warning": "auto_keybind_code_fallback_due_to_no_free_codes",
                        "assigned_code": int(desired_code),
                    }
                )
        if desired_code < 1 or desired_code > 14:
            raise ValueError(
                f"可交互道具展示的按键码仅允许 1..14：ui_key={ui_key!r}, widget_name={widget_name!r}, code={desired_code}"
            )
        if int(desired_code) in used:
            # 重复按键码：不再报错。
            # - 若是自动分配导致的重复，尝试再找一个空闲码（仅当有空闲时）。
            # - 若是显式配置导致的重复，保持原码并写 warning（方便排查“按键漂移/冲突”）。
            if not explicit_code:
                for c in range(1, 15):
                    if c not in used:
                        run.interactive_item_display_key_code_warnings.append(
                            {
                                "ui_key": ui_key,
                                "widget_name": widget_name,
                                "warning": "auto_keybind_code_conflict_resolved",
                                "requested_code": int(desired_code),
                                "assigned_code": int(c),
                            }
                        )
                        desired_code = int(c)
                        break
            if int(desired_code) in used:
                run.interactive_item_display_key_code_warnings.append(
                    {
                        "ui_key": ui_key,
                        "widget_name": widget_name,
                        "warning": "duplicate_keybind_code_allowed",
                        "code": int(desired_code),
                    }
                )
        else:
            used.add(int(desired_code))
        settings["keybind_kbm_code"] = int(desired_code)
        settings["keybind_gamepad_code"] = int(desired_code)

    for variable_key in (
        "config_id_variable",
        "cooldown_seconds_variable",
        "use_count_variable",
        "quantity_variable",
    ):
        value = settings.get(variable_key)
        if not isinstance(value, str):
            continue
        _, _, full_name = parse_variable_ref_text(value, allow_constant_number=False)
        if full_name:
            run.referenced_variable_full_names.add(str(full_name))
            if variable_key == "config_id_variable":
                group_name, var_name = str(full_name).split(".", 1)
                run.item_display_config_id_variable_refs.add((str(group_name), str(var_name)))
            elif variable_key == "cooldown_seconds_variable":
                group_name, var_name = str(full_name).split(".", 1)
                run.item_display_float_variable_refs.add((str(group_name), str(var_name)))
            elif variable_key in ("use_count_variable", "quantity_variable"):
                group_name, var_name = str(full_name).split(".", 1)
                run.item_display_int_variable_refs.add((str(group_name), str(var_name)))

    desired_guid = int(ctx.ui_key_to_guid.get(ui_key) or 0) if ui_key else 0
    if desired_guid > 0:
        prev = ctx.reserved_guid_to_ui_key.get(int(desired_guid))
        if prev is not None and prev != ui_key:
            ctx.guid_collision_avoided.append(
                {
                    "ui_key": ui_key,
                    "expected_widget_type": "道具展示",
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
                from .web_ui_import_rect import try_extract_widget_name

                ctx.guid_collision_avoided.append(
                    {
                        "ui_key": ui_key,
                        "expected_widget_type": "道具展示",
                        "desired_guid": int(desired_guid),
                        "existing_widget_name": (try_extract_widget_name(existing_record) or ""),
                        "reason": "guid_exists_but_not_in_target_parent_children",
                    }
                )
                existing_record = None
        if existing_record is not None and find_item_display_binding(existing_record) is None:
            from .web_ui_import_rect import try_extract_widget_name

            existing_name = try_extract_widget_name(existing_record) or ""
            ctx.guid_collision_avoided.append(
                {
                    "ui_key": ui_key,
                    "expected_widget_type": "道具展示",
                    "desired_guid": int(desired_guid),
                    "existing_widget_name": existing_name,
                    "reason": "guid_record_shape_mismatch_missing_item_display_binding",
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
        record = copy.deepcopy(template_item_display_record)
        _set_widget_guid(record, int(new_guid))
        _set_widget_name(record, widget_name)
        _set_widget_parent_guid_field504(record, int(target_parent_guid))
        created_new_record = True

    # 关键：无论新建还是复用，都要把 ui_key→guid 写回 registry（避免 registry 漏 key）。
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
        raise RuntimeError("internal error: item_display record missing state_index=0 after clone")
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

    hit = find_item_display_binding(record)
    if hit is None:
        raise RuntimeError(f"克隆后的 record 不包含可识别的 道具展示 binding：guid={int(new_guid)}")
    binding_path, binding_kind, binding_value = hit
    patched_kind, patched_value = patch_item_display_binding(
        kind=str(binding_kind),
        binding_value=binding_value,
        display_type=display_type,
        settings=settings,
    )
    write_item_display_binding_back_to_record(
        record,
        binding_path=binding_path,
        kind=str(patched_kind),
        value=patched_value,
    )

    if created_new_record:
        ctx.ui_record_list.append(record)
    run.visibility_changed_total += int(apply_visibility_patch(record, visible=bool(initial_visible)))
    ensure_child_in_parent_children(target_parent_record, int(new_guid))
    run.import_order_by_guid[int(new_guid)] = min(int(widget_index), int(run.import_order_by_guid.get(int(new_guid), widget_index)))
    if target_parent_record is not layout_record:
        remove_child_from_parent_children(layout_record, int(new_guid))
        group_child_entries.setdefault(group_key, []).append((int(layer_index), int(widget_index), int(new_guid)))

    run.imported_item_displays.append(
        ImportedWebItemDisplay(
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
            display_type=display_type,
            raw_codes={
                "display_type_code": map_item_display_type_to_code(display_type),
            },
        )
    )

    # 生成“点击动作映射”：仅对可交互道具展示生效（游戏内只有这类控件能点击触发事件）
    if can_interact:
        meta = ui_action_meta_by_ui_key.get(ui_key) or {}
        run.ui_click_actions.append(
            {
                "guid": int(new_guid),
                "ui_key": str(ui_key),
                "widget_name": str(widget_name),
                "action_key": str(meta.get("action_key") or "").strip(),
                "action_args": str(meta.get("action_args") or "").strip(),
            }
        )

