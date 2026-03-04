from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.gil_dump_codec.protobuf_like import (
    decode_message_to_field_map,
    encode_message,
    format_binary_data_hex_text,
    parse_binary_data_hex_text,
)
from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import decoded_field_map_to_numeric_message
from ugc_file_tools.ui_schema_library.library import find_schema_ids_by_label, load_schema_record

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    get_children_guids_from_parent_record as _get_children_guids_from_parent_record,
)
from .web_ui_import_constants import UI_SCHEMA_LABEL_ITEM_DISPLAY
from .web_ui_import_rect import has_rect_transform_state, try_extract_widget_name
from ugc_file_tools.custom_variables.refs import parse_variable_ref_text


def choose_item_display_record_template(ui_record_list: List[Any]) -> Optional[Dict[str, Any]]:
    """
    选择一个可作为“克隆模板”的 道具展示 UI record：
    - 必须包含 item_display blob（见 `find_item_display_blob`）
    - 必须包含 RectTransform state0（用于写回坐标）
    - 要求无 children（避免处理子树克隆）

    返回 None 表示未找到。
    """
    best_score: Optional[int] = None
    best_record: Optional[Dict[str, Any]] = None

    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        if not has_rect_transform_state(record, state_index=0):
            continue
        children = _get_children_guids_from_parent_record(record)
        if children:
            continue
        hit = find_item_display_binding(record)
        if hit is None:
            continue

        score = 0
        name = try_extract_widget_name(record)
        if name == "道具展示":
            score += 10

        # 偏好 “玩家当前装备” 的模板（Web 默认导出也是这个）
        _, kind, binding_value = hit
        display_code = try_peek_item_display_type_code(kind=kind, binding_value=binding_value)
        if display_code == 1:
            score += 3

        if best_score is None or score > best_score:
            best_score = score
            best_record = record

    return best_record


def try_load_item_display_record_template_from_ui_schema_library() -> Optional[Dict[str, Any]]:
    """
    优先从 `ui_schema_library` 中读取已标注为 item_display 的模板 record。
    """
    schema_ids = find_schema_ids_by_label(UI_SCHEMA_LABEL_ITEM_DISPLAY)
    if not schema_ids:
        return None
    candidates: List[Dict[str, Any]] = []
    for sid in schema_ids:
        candidates.append(load_schema_record(sid))
    return choose_item_display_record_template(candidates)

def find_item_display_binding(record: Dict[str, Any]) -> Optional[Tuple[str, str, Any]]:
    """
    在 record 中寻找“道具展示”控件的 binding：
    - blob 形态：nested['28'] 为 '<binary_data> ...' 字符串
    - dict 形态：nested['28'] 为 dict message（典型字段：node['501']=display_type_code）

    返回：
    - (binding_path, kind, value)
      - kind: 'blob' / 'dict'
      - value: bytes（blob）/ dict（dict message）
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
        value = nested.get("28")
        if isinstance(value, str) and value.startswith("<binary_data>"):
            blob_bytes = parse_binary_data_hex_text(value)
            display_type_code = try_peek_item_display_type_code(kind="blob", binding_value=blob_bytes)
            if display_type_code in (1, 2, 3):
                return f"505/[{i}]/503/28", "blob", blob_bytes
            continue
        if isinstance(value, dict):
            display_type_code = try_peek_item_display_type_code(kind="dict", binding_value=value)
            if display_type_code in (1, 2, 3):
                return f"505/[{i}]/503/28", "dict", value
            continue
    return None


def find_item_display_blob(record: Dict[str, Any]) -> Optional[Tuple[str, bytes]]:
    """
    在 record 中寻找“道具展示”控件的 blob（样本常见路径：505/[3]/503/28）。
    """
    hit = find_item_display_binding(record)
    if hit is None:
        return None
    binding_path, kind, value = hit
    if kind != "blob":
        return None
    if not isinstance(value, (bytes, bytearray)):
        return None
    return binding_path, bytes(value)


def find_item_display_binding_message_node(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    兼容“道具展示 binding 已被展开为 dict message”的形态（非 <binary_data> blob）。

    目标：用于控件类型判定（例如组件组内排序/层级修正），避免仅靠 blob 形态导致漏判。
    典型字段：
    - node['501'] = display_type_code（1/2/3）
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
        node = nested.get("28")
        if not isinstance(node, dict):
            continue
        code = node.get("501")
        if isinstance(code, int) and int(code) in (1, 2, 3):
            return node
    return None


def try_peek_item_display_type_code(*, kind: str, binding_value: Any) -> Optional[int]:
    if kind == "dict":
        node = binding_value
        if not isinstance(node, dict):
            return None
        code = node.get("501")
        return int(code) if isinstance(code, int) else None
    if kind == "blob":
        blob_bytes = binding_value
        if not isinstance(blob_bytes, (bytes, bytearray)):
            return None
        decoded, consumed = decode_message_to_field_map(
            data_bytes=bytes(blob_bytes),
            start_offset=0,
            end_offset=len(blob_bytes),
            remaining_depth=8,
        )
        if consumed != len(blob_bytes):
            return None
        message = decoded_field_map_to_numeric_message(decoded)
        if not isinstance(message, dict):
            return None
        code = message.get("501")
        return int(code) if isinstance(code, int) else None
    return None


def write_item_display_binding_back_to_record(record: Dict[str, Any], *, binding_path: str, kind: str, value: Any) -> None:
    component_list = record.get("505")
    if not isinstance(component_list, list):
        raise ValueError("record missing component list at field 505")
    for component in component_list:
        if not isinstance(component, dict):
            continue
        nested = component.get("503")
        if not isinstance(nested, dict):
            continue
        current = nested.get("28")
        if kind == "blob":
            if not isinstance(value, (bytes, bytearray)):
                raise TypeError("binding kind=blob expects bytes")
            if isinstance(current, str) and current.startswith("<binary_data>"):
                nested["28"] = format_binary_data_hex_text(bytes(value))
                return
            if isinstance(current, dict):
                # 允许从 dict 形态写回为 blob 形态（兜底；一般不走这个分支）
                nested["28"] = format_binary_data_hex_text(bytes(value))
                return
        if kind == "dict":
            if not isinstance(value, dict):
                raise TypeError("binding kind=dict expects dict")
            if isinstance(current, dict) or (isinstance(current, str) and current.startswith("<binary_data>")):
                nested["28"] = dict(value)
                return
    raise ValueError(f"record missing item_display binding at {binding_path}")


def patch_item_display_binding_message_node(*, node: Dict[str, Any], display_type: str, settings: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(node, dict):
        raise TypeError("node must be dict")
    message: Dict[str, Any] = dict(node)

    # display type
    message["501"] = int(map_item_display_type_to_code(str(display_type)))
    display_type_code = int(message.get("501") or 0)

    # can_interact: false 表现为“删除 502”
    if "can_interact" in settings:
        can_interact = settings.get("can_interact")
        if isinstance(can_interact, bool):
            if bool(can_interact):
                message["502"] = 1
            else:
                if "502" in message:
                    del message["502"]
        elif isinstance(can_interact, (int, float, str)):
            if int(float(can_interact)) != 0:
                message["502"] = 1
            else:
                if "502" in message:
                    del message["502"]

    # keybinds
    if "keybind_kbm_code" in settings:
        kbm_code = settings.get("keybind_kbm_code")
        if isinstance(kbm_code, (int, float, str)):
            message["503"] = int(float(kbm_code))
    if "keybind_gamepad_code" in settings:
        pad_code = settings.get("keybind_gamepad_code")
        if isinstance(pad_code, (int, float, str)):
            message["504"] = int(float(pad_code))

    # config_id variable
    config_var_text = settings.get("config_id_variable")
    if isinstance(config_var_text, str):
        config_ref = build_item_display_variable_ref_message(config_var_text)
        if display_type_code == 2:
            node511 = message.get("511")
            if not isinstance(node511, dict):
                node511 = {}
            node511["501"] = int(config_ref["501"])
            if "502" in config_ref:
                node511["502"] = str(config_ref["502"])
            else:
                if "502" in node511:
                    del node511["502"]
            message["511"] = node511
        elif display_type_code == 3:
            message["516"] = dict(config_ref)
        else:
            message["505"] = dict(config_ref)

    # no equipment behavior
    if "no_equipment_behavior_code" in settings:
        code_value = settings.get("no_equipment_behavior_code")
        if isinstance(code_value, (int, float, str)):
            message["506"] = int(float(code_value))

    # template item toggles (type=2)
    if display_type_code == 2:
        if "show_quantity" in settings and isinstance(settings.get("show_quantity"), bool):
            if bool(settings.get("show_quantity")):
                message["512"] = 1
            else:
                if "512" in message:
                    del message["512"]
        if "hide_when_zero" in settings and isinstance(settings.get("hide_when_zero"), bool):
            if bool(settings.get("hide_when_zero")):
                message["513"] = 1
            else:
                if "513" in message:
                    del message["513"]

    # cooldown var
    cooldown_text = settings.get("cooldown_seconds_variable")
    if isinstance(cooldown_text, str):
        message["507"] = dict(build_item_display_variable_ref_message(cooldown_text))

    # use count switches
    if "use_count_enabled" in settings and isinstance(settings.get("use_count_enabled"), bool):
        if bool(settings.get("use_count_enabled")):
            message["509"] = 1
        else:
            if "509" in message:
                del message["509"]
    if "hide_when_empty_count" in settings and isinstance(settings.get("hide_when_empty_count"), bool):
        if bool(settings.get("hide_when_empty_count")):
            message["508"] = 1
        else:
            if "508" in message:
                del message["508"]
    use_count_var_text = settings.get("use_count_variable")
    if isinstance(use_count_var_text, str):
        message["510"] = dict(build_item_display_variable_ref_message(use_count_var_text))

    # quantity var
    quantity_var_text = settings.get("quantity_variable")
    if isinstance(quantity_var_text, str):
        message["514"] = dict(build_item_display_variable_ref_message(quantity_var_text))

    return message


def patch_item_display_binding(
    *,
    kind: str,
    binding_value: Any,
    display_type: str,
    settings: Dict[str, Any],
) -> Tuple[str, Any]:
    if kind == "dict":
        if not isinstance(binding_value, dict):
            raise TypeError("binding_value must be dict when kind='dict'")
        return "dict", patch_item_display_binding_message_node(node=binding_value, display_type=display_type, settings=settings)
    if kind == "blob":
        if not isinstance(binding_value, (bytes, bytearray)):
            raise TypeError("binding_value must be bytes when kind='blob'")
        return "blob", patch_item_display_blob_bytes(blob_bytes=bytes(binding_value), display_type=display_type, settings=settings)
    raise ValueError(f"unknown binding kind: {kind!r}")


def write_item_display_blob_back_to_record(record: Dict[str, Any], *, binding_path: str, new_blob_bytes: bytes) -> None:
    # 兼容旧入口：默认按 blob 形态写回
    write_item_display_binding_back_to_record(record, binding_path=binding_path, kind="blob", value=bytes(new_blob_bytes))


def patch_item_display_blob_bytes(*, blob_bytes: bytes, display_type: str, settings: Dict[str, Any]) -> bytes:
    """
    道具展示 blob 写回（基于样本逆向出来的字段）。

    已确认字段（道具展示.gil）：
    - field_501(varint)：display_type_code（1/2/3）
    - field_502(varint)：can_interact（样本：缺失=不可交互；1=可交互）
    - field_503(varint)：keybind_kbm_code
    - field_504(varint)：keybind_gamepad_code
    - field_505(message)：config_id_variable（玩家当前装备，group_id + name）
    - field_506(varint)：无装备时表现（样本：2=默认；3=变体）
    - field_507(message)：cooldown_seconds_variable（group_id + name）
    - field_509(varint)：use_count_enabled
    - field_508(varint)：hide_when_empty_count
    - field_510(message)：use_count_variable（group_id + name）
    - field_511(message)：模板道具相关块（样本内包含 config_id_variable + 额外开关字段 512/513）
    - field_514(message)：quantity_variable（group_id + name）
    - field_516(message)：config_id_variable（背包内道具，group_id + name）
    """
    decoded, consumed = decode_message_to_field_map(
        data_bytes=bytes(blob_bytes),
        start_offset=0,
        end_offset=len(blob_bytes),
        remaining_depth=16,
    )
    if consumed != len(blob_bytes):
        raise ValueError("item_display blob 未能完整解码为单个 message（存在 trailing bytes）")
    message = decoded_field_map_to_numeric_message(decoded)
    if not isinstance(message, dict):
        raise ValueError("item_display blob 解码结果不是 dict message")

    # display type
    message["501"] = int(map_item_display_type_to_code(str(display_type)))
    display_type_code = int(message.get("501") or 0)

    # can_interact（可选；样本中 false 表现为“删除 field_502”）
    if "can_interact" in settings:
        can_interact = settings.get("can_interact")
        if isinstance(can_interact, bool):
            if bool(can_interact):
                message["502"] = 1
            else:
                if "502" in message:
                    del message["502"]
        elif isinstance(can_interact, (int, float, str)):
            if int(float(can_interact)) != 0:
                message["502"] = 1
            else:
                if "502" in message:
                    del message["502"]

    # keybinds（可选）
    if "keybind_kbm_code" in settings:
        kbm_code = settings.get("keybind_kbm_code")
        if isinstance(kbm_code, (int, float, str)):
            message["503"] = int(float(kbm_code))
    if "keybind_gamepad_code" in settings:
        pad_code = settings.get("keybind_gamepad_code")
        if isinstance(pad_code, (int, float, str)):
            message["504"] = int(float(pad_code))

    # config_id variable（可选）
    config_var_text = settings.get("config_id_variable")
    if isinstance(config_var_text, str):
        config_ref = build_item_display_variable_ref_message(config_var_text)
        if display_type_code == 2:
            node511 = message.get("511")
            if not isinstance(node511, dict):
                node511 = {}
            node511["501"] = int(config_ref["501"])
            if "502" in config_ref:
                node511["502"] = str(config_ref["502"])
            else:
                if "502" in node511:
                    del node511["502"]
            message["511"] = node511
        elif display_type_code == 3:
            message["516"] = dict(config_ref)
        else:
            message["505"] = dict(config_ref)

    # 无装备时表现（可选，样本为 field_506）
    if "no_equipment_behavior_code" in settings:
        code_value = settings.get("no_equipment_behavior_code")
        if isinstance(code_value, (int, float, str)):
            message["506"] = int(float(code_value))

    # 模板道具额外开关（样本：field_512/513 为顶层 varint）
    if display_type_code == 2:
        if "show_quantity" in settings and isinstance(settings.get("show_quantity"), bool):
            if bool(settings.get("show_quantity")):
                message["512"] = 1
            else:
                if "512" in message:
                    del message["512"]
        if "hide_when_zero" in settings and isinstance(settings.get("hide_when_zero"), bool):
            if bool(settings.get("hide_when_zero")):
                message["513"] = 1
            else:
                if "513" in message:
                    del message["513"]

    # cooldown var（可选）
    cooldown_text = settings.get("cooldown_seconds_variable")
    if isinstance(cooldown_text, str):
        message["507"] = dict(build_item_display_variable_ref_message(cooldown_text))

    # use count switches（可选）
    if "use_count_enabled" in settings and isinstance(settings.get("use_count_enabled"), bool):
        if bool(settings.get("use_count_enabled")):
            message["509"] = 1
        else:
            if "509" in message:
                del message["509"]
    if "hide_when_empty_count" in settings and isinstance(settings.get("hide_when_empty_count"), bool):
        if bool(settings.get("hide_when_empty_count")):
            message["508"] = 1
        else:
            if "508" in message:
                del message["508"]

    use_count_var_text = settings.get("use_count_variable")
    if isinstance(use_count_var_text, str):
        message["510"] = dict(build_item_display_variable_ref_message(use_count_var_text))

    # quantity var（可选；样本为 field_514 message）
    quantity_var_text = settings.get("quantity_variable")
    if isinstance(quantity_var_text, str):
        message["514"] = dict(build_item_display_variable_ref_message(quantity_var_text))

    return encode_message(dict(message))


def map_item_display_type_to_code(display_type: str) -> int:
    name = str(display_type or "").strip()
    mapping = {
        "玩家当前装备": 1,
        "背包内道具": 3,
        "模板道具": 2,
    }
    return int(mapping.get(name, 1))


def build_item_display_variable_ref_message(full_name: str) -> Dict[str, Any]:
    """
    将“玩家自身.新增变量1”这类可读形式转换为 item_display blob 内部的 variable_ref message：
    - 501: group_id（未绑定用 sentinel）
    - 502: name（仅变量名部分；未绑定尽量删除 502）
    """
    group_id, name, _ = parse_variable_ref_text(str(full_name or ""), allow_constant_number=False)
    out: Dict[str, Any] = {"501": int(group_id)}
    if name is not None and str(name) != "":
        out["502"] = str(name)
    return out

