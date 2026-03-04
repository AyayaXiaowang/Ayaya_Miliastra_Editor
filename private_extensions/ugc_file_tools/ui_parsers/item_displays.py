from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map, encode_message, parse_binary_data_hex_text
from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import decoded_field_map_to_numeric_message
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

# observed sentinel in some dumps: uint64 max (varint 10 bytes) means "unset / unbound"
_UNBOUND_GROUP_ID_SENTINEL_UINT64_MAX = 18446744073709551615

# 当前样本（道具展示.gil）可确认的 group_id：用于把 “group_id+name” 拼回可读 full_name
_KNOWN_GROUP_NAME_BY_ID: Dict[int, str] = {
    100: "玩家自身",
    101: "关卡",
}

_RE_KBM_KEY_LABEL = re.compile(r"^\s*按键(.+?)键鼠\s*$")
_RE_GAMEPAD_KEY_LABEL = re.compile(r"^\s*手柄按键(.+?)道具展示\s*$")


def _build_canvas_size_by_state_index(
    pc_canvas_size: Optional[Tuple[float, float]],
) -> Dict[int, Tuple[float, float]]:
    if pc_canvas_size is None:
        return {}
    pc_w, pc_h = float(pc_canvas_size[0]), float(pc_canvas_size[1])
    return {
        0: (pc_w, pc_h),
        1: (1280.0, 720.0),
        2: (1920.0, 1080.0),
        3: (1280.0, 720.0),
    }


def build_item_display_dump(
    dll_dump_object: Dict[str, Any],
    *,
    canvas_size: Optional[Tuple[float, float]] = (1600.0, 900.0),
    include_raw_binding_blob_hex: bool = False,
) -> Dict[str, Any]:
    """
    从 raw dump-json（数值键结构）中解析“道具展示”控件。

    当前样本验证：道具展示 record 内存在一个 <binary_data> blob（常见路径 505/[3]/503/28），
    blob 为 protobuf-like message（字段号以 501+ 为主），包含：
    - field_501(varint)：展示类型（样本：1=玩家当前装备，2=模板道具，3=背包内道具）
    - field_502(varint)：是否可交互（样本：缺失=不可交互；1=可交互）
    - field_503(varint)：按键映射-键鼠（样本：1/2/3/9/11...）
    - field_504(varint)：按键映射-手柄（样本：1/4/5/9...）
    - field_505(message)：配置ID变量（嵌套 message：field_501=group_id, field_502=name）
    - field_506(varint)：无装备时表现（样本：2=默认；3=“无装备时表现”变体）
    - field_507(message)：冷却时间变量（同上；可为未绑定）
    - field_509(varint)：栏位使用次数（样本：1=开启）
    - field_508(varint)：无次数时隐藏（样本：1=开启）
    - field_510(message)：次数变量（同上；可为未绑定）
    - field_514(message)：道具数量变量（样本：field_501=group_id, field_502=name；可为未绑定）

    注意：部分字段仍在逆向中（例如 field_517 等），会保留 raw_codes 便于继续对照。
    """
    ui_record_list = _extract_ui_record_list(dll_dump_object)
    canvas_size_by_state_index = _build_canvas_size_by_state_index(canvas_size)

    items: List[Dict[str, Any]] = []
    for record_list_index, record in enumerate(ui_record_list):
        if not isinstance(record, dict):
            continue
        parsed = _try_parse_item_display_record(
            record,
            record_list_index=record_list_index,
            canvas_size_by_state_index=canvas_size_by_state_index,
            include_raw_binding_blob_hex=include_raw_binding_blob_hex,
        )
        if parsed is None:
            continue
        items.append(parsed)

    items.sort(key=lambda item: int(item.get("guid", 0) or 0))
    items_by_guid: Dict[int, Any] = {}
    for item in items:
        guid_value = item.get("guid")
        if isinstance(guid_value, int):
            items_by_guid[int(guid_value)] = item

    # 额外输出：按键码 → 名称 hint（从“控件名”中提取，便于建立对照表）
    kbm_key_code_to_label_hint: Dict[str, str] = {}
    gamepad_key_code_to_label_hint: Dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        display = item.get("item_display")
        if not isinstance(display, dict):
            continue
        kbm = display.get("keybind_kbm")
        if isinstance(kbm, dict) and isinstance(kbm.get("code"), int) and isinstance(kbm.get("label_hint"), str):
            code = int(kbm["code"])
            label = str(kbm.get("label_hint") or "").strip()
            if label:
                kbm_key_code_to_label_hint[str(code)] = label
        pad = display.get("keybind_gamepad")
        if isinstance(pad, dict) and isinstance(pad.get("code"), int) and isinstance(pad.get("label_hint"), str):
            code = int(pad["code"])
            label = str(pad.get("label_hint") or "").strip()
            if label:
                gamepad_key_code_to_label_hint[str(code)] = label

    return {
        "ui_record_total": len(ui_record_list),
        "item_display_total": len(items),
        "item_displays": items,
        "item_displays_by_guid": items_by_guid,
        "assumptions": {
            "canvas_size": {"x": canvas_size[0], "y": canvas_size[1]} if canvas_size is not None else None,
            "device_template_by_state_index": {
                str(state_index): name for state_index, name in DEFAULT_DEVICE_TEMPLATE_BY_STATE_INDEX.items()
            },
            "canvas_position_formula": (
                "if anchor_min==anchor_max: canvas_pos = anchored_position + (anchor_min.x*canvas_size.x, anchor_min.y*canvas_size.y)"
                if canvas_size is not None
                else None
            ),
            "keybind_kbm_code_to_label_hint": kbm_key_code_to_label_hint,
            "keybind_gamepad_code_to_label_hint": gamepad_key_code_to_label_hint,
        },
    }


def _try_parse_item_display_record(
    record: Dict[str, Any],
    *,
    record_list_index: int,
    canvas_size_by_state_index: Dict[int, Tuple[float, float]],
    include_raw_binding_blob_hex: bool,
) -> Optional[Dict[str, Any]]:
    guid_value = _extract_primary_guid(record)
    if guid_value is None:
        return None

    hit = _find_item_display_blob(record)
    if hit is None:
        return None
    binding_blob_path, binding_blob_bytes = hit

    decoded, consumed = decode_message_to_field_map(
        data_bytes=bytes(binding_blob_bytes),
        start_offset=0,
        end_offset=len(binding_blob_bytes),
        remaining_depth=16,
    )
    if consumed != len(binding_blob_bytes):
        return None
    message = decoded_field_map_to_numeric_message(decoded)
    if not isinstance(message, dict):
        return None

    # 样本固定：display_type_code 存在
    display_type_code_value = message.get("501")
    if not isinstance(display_type_code_value, int):
        return None
    display_type_code = int(display_type_code_value)

    display_type_name = _map_display_type_code(display_type_code)

    index_id_value = record.get("504")
    index_id_int = int(index_id_value) if isinstance(index_id_value, int) else None

    name_text = _extract_primary_name(record)
    visibility_flag_values = _extract_visibility_flag_values(record)
    is_visible = all(flag_value == 1 for flag_value in visibility_flag_values) if visibility_flag_values else True

    rect_transform_candidates = _find_rect_transform_state_lists(record)
    chosen_transform_path, chosen_transform_states = _choose_best_rect_transform_states(rect_transform_candidates)
    chosen_transform = _choose_best_rect_transform_state(chosen_transform_states)

    anchored_position: Optional[Dict[str, Any]] = None
    anchor_min: Optional[Dict[str, Any]] = None
    anchor_max: Optional[Dict[str, Any]] = None
    size: Optional[Dict[str, Any]] = None
    canvas_position: Optional[Dict[str, Any]] = None
    anchor_preset: Optional[str] = None

    if isinstance(chosen_transform, dict):
        anchored_position = chosen_transform.get("anchored_position")
        anchor_min = chosen_transform.get("anchor_min")
        anchor_max = chosen_transform.get("anchor_max")
        size = chosen_transform.get("size")

        anchor_preset = _infer_anchor_preset_name(anchor_min, anchor_max)

    pc_canvas_size = canvas_size_by_state_index.get(0)
    if (
        pc_canvas_size is not None
        and isinstance(anchored_position, dict)
        and isinstance(anchored_position.get("x"), (int, float))
        and isinstance(anchored_position.get("y"), (int, float))
    ):
        resolved = _resolve_canvas_position_from_rect_transform(
            anchored_position=anchored_position,
            anchor_min=anchor_min,
            anchor_max=anchor_max,
            canvas_size=(float(pc_canvas_size[0]), float(pc_canvas_size[1])),
        )
        if resolved is not None:
            canvas_position = resolved

    # 解析关键字段
    # 是否可交互：样本中“不可交互”会直接缺失 field_502（而不是显式写 0）
    can_interact = bool(int(message.get("502") or 0) != 0) if isinstance(message.get("502"), int) else False

    keybind_kbm_code = message.get("503") if isinstance(message.get("503"), int) else None
    keybind_gamepad_code = message.get("504") if isinstance(message.get("504"), int) else None

    config_var_field505 = _decode_variable_ref_from_nested_message(message.get("505"))
    # 背包内道具（display_type_code=3）样本中，道具配置ID变量位于 field_516（message：group_id + name）
    config_var_field516 = _decode_variable_ref_from_nested_message(message.get("516"))
    no_equipment_behavior_code = message.get("506") if isinstance(message.get("506"), int) else None
    cooldown_var = _decode_variable_ref_from_nested_message(message.get("507"))
    use_count_var = _decode_variable_ref_from_nested_message(message.get("510"))
    quantity_var = _decode_variable_ref_from_nested_message(message.get("514"))

    # 模板道具（display_type_code=2）样本中，config_id_variable 位于 field_511；数量显示开关位于 field_512/513
    template_item_block: Optional[Dict[str, Any]] = None
    if int(display_type_code) == 2 and isinstance(message.get("511"), dict):
        template_item_block = _decode_template_item_block(message.get("511"))

    effective_config_var: Optional[Dict[str, Any]] = None
    if int(display_type_code) == 2:
        effective_config_var = (
            template_item_block.get("config_id_variable") if isinstance(template_item_block, dict) else None
        )
        if effective_config_var is None:
            effective_config_var = config_var_field505
    elif int(display_type_code) == 3:
        effective_config_var = config_var_field516 if config_var_field516 is not None else config_var_field505
    else:
        effective_config_var = config_var_field505

    show_quantity: Optional[bool] = None
    hide_when_zero: Optional[bool] = None
    if int(display_type_code) == 2:
        show_quantity = bool(int(message.get("512") or 0) != 0) if isinstance(message.get("512"), int) else False
        hide_when_zero = bool(int(message.get("513") or 0) != 0) if isinstance(message.get("513"), int) else False

    # 统计 raw_codes，便于继续 reverse
    raw_codes: Dict[str, Any] = {}
    known_keys = {
        # 已语义化/已解析字段
        "501",  # display_type
        "502",  # can_interact
        "503",  # keybind_kbm
        "504",  # keybind_gamepad
        "505",  # config_id_variable
        "506",  # no_equipment_behavior_code
        "507",  # cooldown_seconds_variable
        "508",  # hide_when_empty_count
        "509",  # use_count_enabled
        "510",  # use_count_variable
        "511",  # template item block (type=2)
        "512",  # show_quantity (type=2)
        "513",  # hide_when_zero (type=2)
        "514",  # quantity variable
        # 背包内道具（type=3）样本中的配置ID变量：516
        "515",
        "516",
    }
    for key, value in message.items():
        if key in known_keys:
            continue
        if isinstance(value, (int, float, str)):
            raw_codes[str(key)] = value

    out: Dict[str, Any] = {
        "record_list_index": int(record_list_index),
        "guid": int(guid_value),
        "index_id": index_id_int,
        "name": name_text,
        "visible": bool(is_visible),
        "visibility_flag_values": list(visibility_flag_values),
        "rect_transform": chosen_transform,
        "rect_transform_source_path": chosen_transform_path,
        "canvas_position": canvas_position,
        "anchor_preset": anchor_preset,
        "item_display": {
            "display_type": {"code": int(display_type_code), "name": display_type_name},
            "can_interact": bool(can_interact),
            "keybind_kbm": (
                {
                    "code": int(keybind_kbm_code),
                    "label_hint": _infer_keybind_label_hint_from_record_name(
                        name_text, kind="kbm"
                    ),
                }
                if isinstance(keybind_kbm_code, int)
                else None
            ),
            "keybind_gamepad": (
                {
                    "code": int(keybind_gamepad_code),
                    "label_hint": _infer_keybind_label_hint_from_record_name(
                        name_text, kind="gamepad"
                    ),
                }
                if isinstance(keybind_gamepad_code, int)
                else None
            ),
            "config_id_variable": effective_config_var,
            "config_id_variable_field505": config_var_field505,
            "config_id_variable_field516": config_var_field516,
            "no_equipment_behavior": (
                {"code": int(no_equipment_behavior_code)} if isinstance(no_equipment_behavior_code, int) else None
            ),
            "cooldown_seconds_variable": cooldown_var,
            "use_count_enabled": bool(int(message.get("509") or 0) != 0) if isinstance(message.get("509"), int) else False,
            "hide_when_empty_count": bool(int(message.get("508") or 0) != 0) if isinstance(message.get("508"), int) else False,
            "use_count_variable": use_count_var,
            "quantity_variable": quantity_var,
            "show_quantity": show_quantity,
            "hide_when_zero": hide_when_zero,
            "template_item_block": template_item_block,
            "raw_codes": raw_codes,
        },
        "source": {
            "binding_blob_path": str(binding_blob_path),
            "binding_blob_byte_length": int(len(binding_blob_bytes)),
            "raw_binding_blob_hex": (binding_blob_bytes.hex() if include_raw_binding_blob_hex else None),
        },
    }

    return out


def _infer_keybind_label_hint_from_record_name(name_text: Optional[str], *, kind: str) -> Optional[str]:
    """
    从控件名推断按键标签（仅作为 hint）。

    约定（来自示例存档命名习惯）：
    - 键鼠：按键<标签>键鼠，例如 "按键U键鼠" / "按键2键鼠"
    - 手柄：手柄按键<标签>道具展示，例如 "手柄按键9道具展示"
    """
    text = str(name_text or "").strip()
    if not text:
        return None
    if kind == "kbm":
        m = _RE_KBM_KEY_LABEL.match(text)
        if not m:
            return None
        label = str(m.group(1) or "").strip()
        return label if label else None
    if kind == "gamepad":
        m = _RE_GAMEPAD_KEY_LABEL.match(text)
        if not m:
            return None
        label = str(m.group(1) or "").strip()
        return label if label else None
    return None


def _find_item_display_blob(record: Dict[str, Any]) -> Optional[Tuple[str, bytes]]:
    """
    在 record 中寻找道具展示控件的 blob（样本常见路径：505/[3]/503/28）。
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
        blob_value = nested.get("28")
        blob_bytes: Optional[bytes] = None
        if isinstance(blob_value, str) and blob_value.startswith("<binary_data>"):
            blob_bytes = parse_binary_data_hex_text(blob_value)
        elif isinstance(blob_value, dict):
            # 兼容：binding 已展开为 dict message（与写回端一致）
            # 这里统一编码回 bytes，再走相同的 decode 路径，保证输出口径一致。
            code = blob_value.get("501")
            if isinstance(code, int) and int(code) in (1, 2, 3):
                blob_bytes = encode_message(dict(blob_value))
        if blob_bytes is None:
            continue
        # 粗略签名：必须能解码出 field_501(varint)
        decoded, consumed = decode_message_to_field_map(
            data_bytes=bytes(blob_bytes),
            start_offset=0,
            end_offset=len(blob_bytes),
            remaining_depth=16,
        )
        if consumed != len(blob_bytes):
            continue
        message = decoded_field_map_to_numeric_message(decoded)
        if isinstance(message, dict) and isinstance(message.get("501"), int):
            return f"505/[{i}]/503/28", blob_bytes
    return None


def _map_display_type_code(code: int) -> Optional[str]:
    mapping = {
        1: "玩家当前装备",
        2: "模板道具",
        3: "背包内道具",
    }
    return mapping.get(int(code))


def _decode_variable_ref_from_nested_message(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    group_id_value = value.get("501")
    name_value = value.get("502")

    group_id: Optional[int] = int(group_id_value) if isinstance(group_id_value, int) else None
    if group_id == _UNBOUND_GROUP_ID_SENTINEL_UINT64_MAX:
        group_id = -1

    name_text: Optional[str] = str(name_value) if isinstance(name_value, str) else None
    is_bound = bool(isinstance(name_text, str) and name_text != "")

    group_name = _KNOWN_GROUP_NAME_BY_ID.get(int(group_id)) if isinstance(group_id, int) and group_id >= 0 else None
    full_name = f"{group_name}.{name_text}" if group_name and name_text else None

    return {
        "group_id": group_id,
        "name": name_text,
        "is_bound": bool(is_bound),
        "group_name": group_name,
        "full_name": full_name,
    }


def _decode_template_item_block(value: Dict[str, Any]) -> Dict[str, Any]:
    # 基于样本推断：field_501/502 仍是 group_id/name（模板道具的 config_id_variable）
    base = _decode_variable_ref_from_nested_message(value) or {}
    return {
        "config_id_variable": base,
        "raw_codes": {k: v for k, v in value.items() if k not in ("501", "502") and isinstance(v, (int, float, str))},
    }


def _infer_anchor_preset_name(
    anchor_min: Optional[Dict[str, Any]],
    anchor_max: Optional[Dict[str, Any]],
) -> Optional[str]:
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


def _resolve_canvas_position_from_rect_transform(
    *,
    anchored_position: Dict[str, Any],
    anchor_min: Optional[Dict[str, Any]],
    anchor_max: Optional[Dict[str, Any]],
    canvas_size: Tuple[float, float],
) -> Optional[Dict[str, Any]]:
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

    px = anchored_position.get("x")
    py = anchored_position.get("y")
    if not isinstance(px, (int, float)) or not isinstance(py, (int, float)):
        return None
    canvas_w, canvas_h = float(canvas_size[0]), float(canvas_size[1])
    return {"x": float(px) + float(ax) * canvas_w, "y": float(py) + float(ay) * canvas_h}


