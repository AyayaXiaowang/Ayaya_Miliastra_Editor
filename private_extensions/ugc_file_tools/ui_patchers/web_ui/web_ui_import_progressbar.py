from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from engine.configs.specialized.ui_widget_configs import PROGRESSBAR_COLOR_CODE_BY_HEX
from ugc_file_tools.gil_dump_codec.protobuf_like import (
    decode_message_to_field_map,
    encode_message,
    format_binary_data_hex_text,
    parse_binary_data_hex_text,
)
from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import decoded_field_map_to_numeric_message
from ugc_file_tools.ui_parsers.progress_bars import find_progressbar_binding_blob as _find_progressbar_binding_blob
from ugc_file_tools.ui_schema_library.library import find_schema_ids_by_label, load_schema_record

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    decode_varint_stream as _decode_varint_stream,
    get_children_guids_from_parent_record as _get_children_guids_from_parent_record,
)
from .web_ui_import_constants import UI_SCHEMA_LABEL_PROGRESSBAR
from .web_ui_import_layout import find_progressbar_binding_message_node, looks_like_template_library_entry, prefer_center_pivot_and_fixed_anchor_score
from .web_ui_import_rect import has_rect_transform_state, try_extract_rect_transform_from_state, try_extract_widget_name
from ugc_file_tools.custom_variables.refs import parse_variable_ref_text


def choose_progressbar_record_template(ui_record_list: List[Any]) -> Optional[Dict[str, Any]]:
    """
    选择一个可作为“克隆模板”的进度条 UI record：
    - 必须包含 binding blob（505/[3]/503/20）或 message 形态 binding
    - 必须包含 RectTransform state0（用于写回坐标）
    - 优先选择无 children 的 record（避免处理子树克隆）

    返回 None 表示未找到。
    """

    def try_extract_guid(record: Dict[str, Any]) -> Optional[int]:
        # 兼容：field_501 既可能是 int，也可能是 list[int]
        raw = record.get("501")
        if isinstance(raw, int):
            return int(raw)
        if isinstance(raw, list) and raw and isinstance(raw[0], int):
            return int(raw[0])
        return None

    # 更可靠地选择“可克隆的进度条实例 record”：
    # - Web UI 导入期望克隆“布局里的可放置控件实例”，而不是“模板库条目/模板 root”；
    # - 否则会导致导入时把每个进度条都变成模板，污染模板库（用户观感：所有进度条都成了模板）。
    def _try_get_children_guids_for_scanning(parent_record: Dict[str, Any]) -> List[int]:
        """
        扫描阶段：用于统计 all_child_guids（判断“是否为布局实例”）。

        约束：
        - 不应因为某个非布局/污染 record 的 children 字段异常而中断整个导入；
        - 仅当字段形态明确可解析时才解析，否则视为“无 children”。
        """
        field503 = parent_record.get("503")
        if field503 is None:
            return []
        if isinstance(field503, str):
            if field503 == "":
                return []
            if not field503.startswith("<binary_data>"):
                return []
            return _decode_varint_stream(parse_binary_data_hex_text(field503))
        if isinstance(field503, list):
            if not field503:
                return []
            first = field503[0]
            if not isinstance(first, str):
                return []
            if first == "":
                return []
            if not first.startswith("<binary_data>"):
                return []
            return _decode_varint_stream(parse_binary_data_hex_text(first))
        return []

    all_child_guids: set[int] = set()
    for parent in ui_record_list:
        if not isinstance(parent, dict):
            continue
        for g in _try_get_children_guids_for_scanning(parent):
            all_child_guids.add(int(g))

    best_score: Optional[int] = None
    best_record: Optional[Dict[str, Any]] = None

    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        # 关键：跳过“模板库条目 record”，避免 clone 后把控件写成模板
        if looks_like_template_library_entry(record):
            continue
        if _find_progressbar_binding_blob(record) is None and find_progressbar_binding_message_node(record) is None:
            continue
        if not has_rect_transform_state(record, state_index=0):
            continue

        # 评分阶段：若 children 字段结构异常，视为“无 children”（避免非关键字段阻断模板选择）
        children = _try_get_children_guids_for_scanning(record)
        has_children = bool(children)

        score = 0
        name = try_extract_widget_name(record)
        if name == "进度条":
            score += 10
        if not has_children:
            score += 5

        # 强化：优先选择“确实作为某个 parent.children 出现”的 record（更像布局实例）
        guid = try_extract_guid(record)
        if guid is not None:
            if int(guid) in all_child_guids:
                score += 8
            else:
                score -= 2

        score += prefer_center_pivot_and_fixed_anchor_score(record)

        if best_score is None or score > best_score:
            best_score = score
            best_record = record

    return best_record


def try_load_progressbar_record_template_from_ui_schema_library() -> Optional[Dict[str, Any]]:
    """
    优先从 `ui_schema_library` 中读取已标注为 progressbar 的模板 record。
    这允许“只依赖一次样本存档做沉淀”，后续在任意 base `.gil` 中复用该结构。
    """
    schema_ids = find_schema_ids_by_label(UI_SCHEMA_LABEL_PROGRESSBAR)
    if not schema_ids:
        return None
    candidates: List[Dict[str, Any]] = []
    for sid in schema_ids:
        candidates.append(load_schema_record(sid))
    return choose_progressbar_record_template(candidates)


def map_progressbar_shape_to_code(shape_name: str) -> int:
    name = str(shape_name or "").strip()
    mapping = {
        "横向": 0,
        "纵向": 1,
        "竖向": 1,
        "圆形": 2,
        "圆环": 2,
        "菱形": 3,
    }
    return int(mapping.get(name, 0))


def map_progressbar_style_to_code(style_name: str) -> int:
    name = str(style_name or "").strip()
    mapping = {
        "百分比": 0,
        "不显示": 1,
        "当前值": 2,
        "真实比例": 3,
    }
    return int(mapping.get(name, 1))


def map_progressbar_color_hex_to_code(color_hex: str) -> int:
    raw = str(color_hex or "").strip().upper()
    if raw == "":
        return 0
    code = PROGRESSBAR_COLOR_CODE_BY_HEX.get(str(raw))
    if code is None:
        raise ValueError(f"不支持的进度条颜色 hex: {raw!r}（仅允许: {sorted(PROGRESSBAR_COLOR_CODE_BY_HEX.keys())}）")
    return int(code)


def patch_progressbar_binding_blob_bytes(
    *,
    blob_bytes: bytes,
    shape_code: int,
    style_code: int,
    color_code: int,
    current_text: str,
    min_text: str,
    max_text: str,
) -> bytes:
    decoded, consumed = decode_message_to_field_map(
        data_bytes=bytes(blob_bytes),
        start_offset=0,
        end_offset=len(blob_bytes),
        remaining_depth=16,
    )
    if consumed != len(blob_bytes):
        raise ValueError("binding blob 未能完整解码为单个 message（存在 trailing bytes）")
    message = decoded_field_map_to_numeric_message(decoded)

    message["501"] = int(shape_code)
    message["502"] = int(style_code)
    message["503"] = int(color_code)

    # 约定（对齐 UI源码 目录规则）：
    # - current：必须为变量引用（或 '.' / '' 触发自动补齐）
    # - min/max：允许数字常量（例如 0/100）
    current_gid, current_name, _ = parse_variable_ref_text(current_text, allow_constant_number=False)
    min_gid, min_name, _ = parse_variable_ref_text(min_text, allow_constant_number=True)
    max_gid, max_name, _ = parse_variable_ref_text(max_text, allow_constant_number=True)

    message = set_variable_ref_in_progressbar_message(message, field_number=504, group_id=current_gid, name=current_name)
    message = set_variable_ref_in_progressbar_message(message, field_number=505, group_id=min_gid, name=min_name)
    message = set_variable_ref_in_progressbar_message(message, field_number=506, group_id=max_gid, name=max_name)

    return encode_message(dict(message))


def patch_progressbar_binding_message_in_place(
    message: Dict[str, Any],
    *,
    shape_code: int,
    style_code: int,
    color_code: int,
    current_text: str,
    min_text: str,
    max_text: str,
) -> None:
    """
    兼容“已展开为 dict 的 progressbar binding message”写回：
    - 501/502/503：形状/样式/颜色（与 blob 版口径一致）
    - 504/505/506：变量引用（group_id + name，可选）
    """
    message["501"] = int(shape_code)
    message["502"] = int(style_code)
    message["503"] = int(color_code)

    current_gid, current_name, _ = parse_variable_ref_text(current_text, allow_constant_number=False)
    min_gid, min_name, _ = parse_variable_ref_text(min_text, allow_constant_number=True)
    max_gid, max_name, _ = parse_variable_ref_text(max_text, allow_constant_number=True)

    def set_ref(field_key: str, group_id: int, name: Optional[str]) -> None:
        nested = message.get(field_key)
        if not isinstance(nested, dict):
            nested = {}
        nested["501"] = int(group_id)
        if name is not None and str(name) != "":
            nested["502"] = str(name)
        else:
            if "502" in nested:
                del nested["502"]
        message[field_key] = nested

    set_ref("504", int(current_gid), current_name)
    set_ref("505", int(min_gid), min_name)
    set_ref("506", int(max_gid), max_name)


def set_variable_ref_in_progressbar_message(
    message: Dict[str, Any],
    *,
    field_number: int,
    group_id: int,
    name: Optional[str],
) -> Dict[str, Any]:
    key = str(int(field_number))
    nested = message.get(key)
    if not isinstance(nested, dict):
        nested = {}

    nested["501"] = int(group_id)
    if name is not None and str(name) != "":
        nested["502"] = str(name)
    else:
        # 为空时尽量删除 502（更贴近样本：只有 group_id，没有 name）
        if "502" in nested:
            del nested["502"]

    message[key] = nested
    return message


def write_progressbar_binding_blob_back_to_record(
    record: Dict[str, Any],
    *,
    binding_path: str,
    new_blob_bytes: bytes,
) -> None:
    if str(binding_path) != "505/[3]/503/20":
        raise ValueError(f"暂不支持的 binding_blob_path：{binding_path!r}（期望 505/[3]/503/20）")

    component_list = record.get("505")
    if not isinstance(component_list, list) or len(component_list) <= 3:
        raise ValueError("record missing component list at field 505 (expected len>3)")
    component = component_list[3]
    if not isinstance(component, dict):
        raise ValueError("record field 505[3] must be dict")
    nested = component.get("503")
    if not isinstance(nested, dict):
        raise ValueError("record field 505[3]/503 must be dict")

    nested["20"] = format_binary_data_hex_text(bytes(new_blob_bytes))

