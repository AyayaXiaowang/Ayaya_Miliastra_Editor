from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple, TypeGuard


@dataclass(frozen=True)
class RectTransformState:
    state_index: int
    scale: Optional[Dict[str, Optional[float]]]
    anchor_min: Optional[Dict[str, Optional[float]]]
    anchor_max: Optional[Dict[str, Optional[float]]]
    pivot: Optional[Dict[str, Optional[float]]]
    anchored_position: Optional[Dict[str, Optional[float]]]
    size: Optional[Dict[str, Optional[float]]]


def build_readable_ui_dump(dll_dump_object: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 dump-json（数值键 JSON）进一步提取为更易读的 UI 信息。

    目前已确认：
    - UI 元素记录列表：dump_object["4"]["9"]["502"] (list[dict])
    - 元素 ID：record["504"] (int)
    - 元素名称候选：任意路径末尾为 "12/501" 的非空字符串
    - 文本内容候选：常见路径 "505/[3]/503/19/505/501"（富文本字符串）
    - RectTransform：在嵌套结构中存在形如 {501..506} 的字典（锚点/位置/大小/轴心/缩放）
    - 初始可见性（对齐真源参考存档）：
      - 表达位于 `component_list[1]['503']['14']['502']`
        - 缺失：可见
        - == 1：隐藏
      - 旧口径 `nested['503']` 在真源样本中恒为 1，不可作为初始隐藏判断依据。
    """
    ui_record_list = _extract_ui_record_list(dll_dump_object)

    readable_instances: List[Dict[str, Any]] = []
    for record_list_index, record in enumerate(ui_record_list):
        if not isinstance(record, dict):
            continue
        index_id = record.get("504")
        if not isinstance(index_id, int):
            continue
        readable_instances.append(_build_readable_instance(record, record_list_index))

    grouped_by_index_id: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for readable_instance in readable_instances:
        grouped_by_index_id[int(readable_instance["index_id"])].append(readable_instance)

    readable_groups: List[Dict[str, Any]] = []
    for index_id, instance_list in sorted(grouped_by_index_id.items(), key=lambda item: item[0]):
        primary_name_set = set()
        name_set = set()
        text_set = set()
        for instance in instance_list:
            primary_name = instance.get("name")
            if isinstance(primary_name, str) and primary_name != "":
                primary_name_set.add(primary_name)
            for name_text in instance.get("name_candidates", []):
                name_set.add(name_text)
            text_value = instance.get("text_content")
            if isinstance(text_value, str) and text_value != "":
                text_set.add(text_value)

        readable_groups.append(
            {
                "index_id": index_id,
                "instance_count": len(instance_list),
                "primary_names": sorted(primary_name_set),
                "name_candidates": sorted(name_set),
                "text_candidates": sorted(text_set),
                "instances": instance_list,
            }
        )

    return {
        "ui_record_total": len(ui_record_list),
        "ui_instance_total": len(readable_instances),
        "ui_unique_index_id_total": len(readable_groups),
        "elements_by_index_id": readable_groups,
    }


def build_textbox_dump(
    dll_dump_object: Dict[str, Any],
    *,
    include_transform: bool = False,
) -> Dict[str, Any]:
    """
    只导出“可回写”的 TextBox 信息（用于配合 `ugc_unified.py ui update-content`）。

    判定规则：能在 record 中提取到 text_content（字符串）即可视为 TextBox。
    输出字段以 guid 为核心（update-content 依赖 guid）。
    """
    ui_record_list = _extract_ui_record_list(dll_dump_object)

    textbox_list: List[Dict[str, Any]] = []
    for record_list_index, record in enumerate(ui_record_list):
        if not isinstance(record, dict):
            continue
        index_id_value = record.get("504")
        if not isinstance(index_id_value, int):
            continue

        guid_value = _extract_primary_guid(record)
        if guid_value is None:
            continue

        text_content = _extract_text_content(record)
        if text_content is None:
            continue

        name_text = _extract_primary_name(record)
        visibility_flag_values = _extract_visibility_flag_values(record)
        is_visible = all(flag_value == 1 for flag_value in visibility_flag_values)

        textbox_object: Dict[str, Any] = {
            "record_list_index": record_list_index,
            "index_id": int(index_id_value),
            "guid": int(guid_value),
            "name": name_text,
            "text": text_content,
            "visible": is_visible,
        }

        if include_transform:
            rect_transform_candidates = _find_rect_transform_state_lists(record)
            chosen_transform_path, chosen_transform_states = _choose_best_rect_transform_states(
                rect_transform_candidates
            )
            chosen_transform = _choose_best_rect_transform_state(chosen_transform_states)
            textbox_object["rect_transform"] = chosen_transform
            textbox_object["rect_transform_source_path"] = chosen_transform_path

        textbox_list.append(textbox_object)

    textbox_list.sort(key=lambda item: item["guid"])

    textbox_by_guid: Dict[int, Any] = {}
    for textbox in textbox_list:
        textbox_by_guid[int(textbox["guid"])] = textbox

    return {
        "textbox_total": len(textbox_list),
        "textboxes": textbox_list,
        "textboxes_by_guid": textbox_by_guid,
    }


def build_control_dump(
    dll_dump_object: Dict[str, Any],
    *,
    include_name_candidates: bool = False,
) -> Dict[str, Any]:
    """
    导出所有 UI 控件记录的 GUID（每条 record 的 501[0]），并附带 index_id(504) 与名称信息。

    备注：
    - `guid` 在样本中对每条 record 都存在且唯一，可视为控件实例 ID。
    - `index_id`（504）在部分 record 中缺失；存在时通常用于表示“同一模板/索引”的复用（例如 1073744004 会出现多次）。 
    - “更上层模板”ID（常见 109xxxxxxx）并不直接出现在 record 内部；目前只能从 `4/15`、`4/16` 表中
      扫描对 index_id 的引用来建立“index_id -> template_asset_ids”的不完全映射。
    """
    ui_record_list = _extract_ui_record_list(dll_dump_object)
    index_id_to_template_asset_ids = _build_index_id_to_template_asset_ids(dll_dump_object)

    control_list: List[Dict[str, Any]] = []
    guid_to_control: Dict[int, Any] = {}

    record_without_index_id_total = 0
    record_with_index_id_total = 0

    for record_list_index, record in enumerate(ui_record_list):
        if not isinstance(record, dict):
            continue

        guid_value = _extract_primary_guid(record)
        if guid_value is None:
            continue

        index_id_value = record.get("504") if isinstance(record.get("504"), int) else None
        if index_id_value is None:
            record_without_index_id_total += 1
        else:
            record_with_index_id_total += 1

        name_text = _extract_primary_name(record)
        visibility_flag_values = _extract_visibility_flag_values(record)
        is_visible = all(flag_value == 1 for flag_value in visibility_flag_values)

        control_object: Dict[str, Any] = {
            "record_list_index": record_list_index,
            "guid": int(guid_value),
            "index_id": int(index_id_value) if index_id_value is not None else None,
            "name": name_text,
            "visible": is_visible,
        }

        if include_name_candidates:
            control_object["name_candidates"] = _extract_name_candidates(record)

        if index_id_value is not None:
            template_asset_ids = sorted(index_id_to_template_asset_ids.get(int(index_id_value), set()))
        else:
            template_asset_ids = []
        control_object["template_asset_ids"] = template_asset_ids

        control_list.append(control_object)
        guid_to_control[int(guid_value)] = control_object

    control_list.sort(key=lambda item: item["guid"])

    return {
        "ui_record_total": len(ui_record_list),
        "control_total": len(control_list),
        "control_with_index_id_total": record_with_index_id_total,
        "control_without_index_id_total": record_without_index_id_total,
        "template_asset_id_total": len(
            {template_id for template_ids in index_id_to_template_asset_ids.values() for template_id in template_ids}
        ),
        "index_id_with_template_asset_ids_total": len(index_id_to_template_asset_ids),
        "controls": control_list,
        "controls_by_guid": guid_to_control,
        "index_id_to_template_asset_ids": {
            str(index_id): sorted(template_ids)
            for index_id, template_ids in sorted(index_id_to_template_asset_ids.items())
        },
    }


def _extract_ui_record_list(dll_dump_object: Dict[str, Any]) -> List[Any]:
    root_data = dll_dump_object.get("4")
    if not isinstance(root_data, dict):
        raise ValueError("DLL dump JSON 缺少根字段 '4'（期望为 dict）。")

    field9 = root_data.get("9")
    if isinstance(field9, str) and field9.startswith("<binary_data>"):
        # 兼容：写回链路的 lossless dump 可能把 length-delimited message 也表示成 "<binary_data> .."，
        # 导致 `4/9` 未展开为 dict。此处强制把其按“嵌套 message”解码回 numeric_message。
        from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import binary_data_text_to_numeric_message

        decoded = binary_data_text_to_numeric_message(field9)
        if not isinstance(decoded, dict):
            raise TypeError(f"DLL dump JSON 字段 '4/9' 解码后不是 dict：type={type(decoded).__name__}")
        root_data["9"] = decoded
        field9 = decoded

    if not isinstance(field9, dict):
        # fail-fast：后续写回流程强依赖 `4/9/501`（布局注册表 varint stream）与 `4/9/502`（UI record 列表）。
        # 如果 `4/9` 不是 message，则说明基底 `.gil` 不是我们期望的 UI layout 结构，或 dump/解码口径异常。
        candidates: List[str] = []
        for path_parts, current_value in _iter_nodes_with_paths(root_data):
            if not isinstance(current_value, list) or not current_value:
                continue
            # UI record 的最小签名：record["505"] 为 component_list(list)，且 record["501"] 含 guid（int 或 list[int]）
            record_like = 0
            for item in current_value:
                if not isinstance(item, dict):
                    continue
                component_list = item.get("505")
                guid_candidates = item.get("501")
                if not isinstance(component_list, list):
                    continue
                if isinstance(guid_candidates, int):
                    record_like += 1
                    continue
                if isinstance(guid_candidates, list) and any(isinstance(x, int) for x in guid_candidates):
                    record_like += 1
                    continue
            if record_like >= 8 and len(current_value) >= 8:
                candidates.append(f"{'/'.join(path_parts)} (record_like={record_like}, len={len(current_value)})")
                if len(candidates) >= 5:
                    break
        hint = f"，可能的 record_list 候选路径: {candidates!r}" if candidates else ""
        raise ValueError(
            f"DLL dump JSON 缺少字段 '4/9'（期望为 dict），实际为 {type(field9).__name__}{hint}。"
        )

    record_list = field9.get("502")
    if not isinstance(record_list, list):
        raise ValueError("DLL dump JSON 缺少字段 '4/9/502'（期望为 list）。")

    # 兼容：写回链路的 lossless dump 可能把 record list 的单条 record 也表示成 "<binary_data> .."。
    # 若不解码，后续 GUID 收集/查找/唯一性校验会漏掉这些 record，进而导致 GUID 复用与串页问题。
    from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import binary_data_text_to_numeric_message

    normalized: List[Any] = []
    for item in list(record_list):
        if isinstance(item, dict):
            normalized.append(item)
            continue
        if isinstance(item, str) and item.startswith("<binary_data>"):
            decoded_item = binary_data_text_to_numeric_message(item)
            if not isinstance(decoded_item, dict):
                raise TypeError(
                    "DLL dump JSON 字段 '4/9/502' 的 record 解码后不是 dict："
                    f"type={type(decoded_item).__name__}"
                )
            normalized.append(decoded_item)
            continue
        raise TypeError(
            "DLL dump JSON 字段 '4/9/502' 的 record 不是 dict 或 '<binary_data>'："
            f"type={type(item).__name__} value={item!r}"
        )

    field9["502"] = normalized
    return normalized


def _build_readable_instance(record: Dict[str, Any], record_list_index: int) -> Dict[str, Any]:
    index_id = int(record["504"])
    guid_candidates = record.get("501")
    if not isinstance(guid_candidates, list):
        guid_candidates = []

    primary_name = _extract_primary_name(record)
    name_candidates = _extract_name_candidates(record)
    text_content = _extract_text_content(record)

    rect_transform_candidates = _find_rect_transform_state_lists(record)
    chosen_transform_path, chosen_transform_states = _choose_best_rect_transform_states(rect_transform_candidates)
    chosen_transform = _choose_best_rect_transform_state(chosen_transform_states)

    visibility_flag_values = _extract_visibility_flag_values(record)
    # 当前样本中该值恒为 1，但仍输出，便于后续确认“隐藏/禁用”是否存在其他值。
    is_visible = all(flag_value == 1 for flag_value in visibility_flag_values)

    return {
        "record_list_index": record_list_index,
        "index_id": index_id,
        "guid_candidates": guid_candidates,
        "name": primary_name,
        "name_candidates": name_candidates,
        "text_content": text_content,
        "visible": is_visible,
        "visibility_flag_values": visibility_flag_values,
        "rect_transform": chosen_transform,
        "rect_transform_states": chosen_transform_states,
        "rect_transform_source_path": chosen_transform_path,
    }


def _extract_name_candidates(record: Dict[str, Any]) -> List[str]:
    name_set = set()
    for path_parts, text in _iter_string_paths(record):
        if not text:
            continue
        if text.startswith("<binary_data>"):
            continue
        if len(path_parts) >= 2 and path_parts[-2:] == ("12", "501"):
            name_set.add(text)
    return sorted(name_set)


def _extract_primary_name(record: Dict[str, Any]) -> Optional[str]:
    component_list = record.get("505")
    if not isinstance(component_list, list):
        return None
    for component in component_list:
        if not isinstance(component, dict):
            continue
        name_container = component.get("12")
        if not isinstance(name_container, dict):
            continue
        name_text = name_container.get("501")
        if isinstance(name_text, str) and name_text != "":
            return name_text
    return None


def _extract_primary_guid(record: Dict[str, Any]) -> Optional[int]:
    guid_candidates = record.get("501")
    # 兼容：部分 dump-json 中该字段可能直接是 int（而非 list[int]）
    if isinstance(guid_candidates, int):
        return int(guid_candidates)
    if not isinstance(guid_candidates, list):
        return None
    for guid_value in guid_candidates:
        if isinstance(guid_value, int):
            return int(guid_value)
    return None


def _build_index_id_to_template_asset_ids(dll_dump_object: Dict[str, Any]) -> Dict[int, set[int]]:
    root_data = dll_dump_object.get("4")
    if not isinstance(root_data, dict):
        return {}

    # heuristics: index_id is around 107374xxxx; template asset ids appear around 1.0~1.3e9 in 4/15 and 4/16
    min_index_id = 1073000000
    max_index_id = 1075000000
    min_template_asset_id = 1000000000
    max_template_asset_id = 1300000000

    def iter_int_values(value: Any) -> Iterable[int]:
        stack = [value]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                stack.extend(current.values())
            elif isinstance(current, list):
                stack.extend(current)
            elif isinstance(current, int):
                yield current

    def extract_template_asset_id(element: Dict[str, Any]) -> Optional[int]:
        candidate_id_from_field2 = element.get("2")
        if (
            isinstance(candidate_id_from_field2, int)
            and min_template_asset_id <= candidate_id_from_field2 <= max_template_asset_id
        ):
            return candidate_id_from_field2

        candidate_id_from_field1 = element.get("1")
        if isinstance(candidate_id_from_field1, list):
            for item in candidate_id_from_field1:
                if isinstance(item, int) and min_template_asset_id <= item <= max_template_asset_id:
                    return item
        return None

    index_id_to_template_ids: Dict[int, set[int]] = defaultdict(set)

    for field_id in ("15", "16"):
        container = root_data.get(field_id)
        if not isinstance(container, dict):
            continue
        element_list = container.get("1")
        if not isinstance(element_list, list):
            continue

        for element in element_list:
            if not isinstance(element, dict):
                continue
            template_asset_id = extract_template_asset_id(element)
            if template_asset_id is None:
                continue
            for integer_value in iter_int_values(element):
                if min_index_id <= integer_value <= max_index_id:
                    index_id_to_template_ids[int(integer_value)].add(int(template_asset_id))

    return index_id_to_template_ids


def _extract_text_content(record: Dict[str, Any]) -> Optional[str]:
    component_list = record.get("505")
    if not isinstance(component_list, list) or len(component_list) <= 3:
        return None
    component_node = component_list[3]
    if not isinstance(component_node, dict):
        return None
    nested_node = component_node.get("503")
    if not isinstance(nested_node, dict):
        return None
    node19 = nested_node.get("19")
    if not isinstance(node19, dict):
        return None
    node505 = node19.get("505")
    if not isinstance(node505, dict):
        return None
    text = node505.get("501")
    if not isinstance(text, str):
        return None
    return text


def _extract_visibility_flag_values(record: Dict[str, Any]) -> List[int]:
    component_list = record.get("505")
    if not isinstance(component_list, list):
        return []
    # 优先：真源初始隐藏口径（node14.502）
    # 备注：并非所有 record 都有该字段（例如布局 root / 特殊节点等）。
    for component in component_list:
        if not isinstance(component, dict):
            continue
        nested = component.get("503")
        if not isinstance(nested, dict):
            continue
        node14 = nested.get("14")
        if not isinstance(node14, dict):
            continue
        if node14.get("501") != 5:
            continue
        # 缺失=可见；=1 隐藏
        hidden = bool(int(node14.get("502", 0)) == 1)
        return [0] if hidden else [1]

    # 兜底：旧字段（仅用于展示/排障；不要用它判断初始隐藏）
    flag_values: List[int] = []
    for component in component_list:
        if not isinstance(component, dict):
            continue
        nested = component.get("503")
        if not isinstance(nested, dict):
            continue
        flag_value = nested.get("503")
        if isinstance(flag_value, int):
            flag_values.append(flag_value)
    return flag_values


def _iter_string_paths(root_value: Any) -> Iterable[Tuple[Tuple[str, ...], str]]:
    stack: List[Tuple[Tuple[str, ...], Any]] = [((), root_value)]
    while stack:
        path_parts, current_value = stack.pop()
        if isinstance(current_value, dict):
            for key, child in current_value.items():
                stack.append((path_parts + (str(key),), child))
        elif isinstance(current_value, list):
            for index, child in enumerate(current_value):
                stack.append((path_parts + (f"[{index}]",), child))
        elif isinstance(current_value, str):
            yield path_parts, current_value


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


def _find_rect_transform_state_lists(record: Dict[str, Any]) -> List[Tuple[str, List[Dict[str, Any]]]]:
    candidates: List[Tuple[str, List[Dict[str, Any]]]] = []
    for path_parts, current_value in _iter_nodes_with_paths(record):
        if not isinstance(current_value, list):
            continue
        state_list = _parse_rect_transform_state_list(current_value)
        if not state_list:
            continue
        candidates.append(("/".join(path_parts), state_list))
    return candidates


def _parse_rect_transform_state_list(candidate_list: List[Any]) -> List[Dict[str, Any]]:
    parsed_states: List[Dict[str, Any]] = []
    for element in candidate_list:
        if not isinstance(element, dict):
            continue
        transform_candidate = element.get("502")
        if not _looks_like_rect_transform_dict(transform_candidate):
            continue

        state_index_value = element.get("501")
        if isinstance(state_index_value, int):
            state_index = state_index_value
        else:
            state_index = 0

        parsed_states.append(
            {
                "state_index": state_index,
                "transform": _parse_rect_transform(transform_candidate),
            }
        )
    return parsed_states


def _looks_like_rect_transform_dict(candidate: Any) -> TypeGuard[Dict[str, Any]]:
    if not isinstance(candidate, dict):
        return False
    required_keys = {"501", "502", "503", "504", "505", "506"}
    if not required_keys.issubset(candidate.keys()):
        return False

    size_node = candidate.get("505")
    if not isinstance(size_node, dict):
        return False
    if not isinstance(size_node.get("501"), (int, float)):
        return False
    if not isinstance(size_node.get("502"), (int, float)):
        return False
    return True


def _parse_rect_transform(transform_dict: Dict[str, Any]) -> Dict[str, Any]:
    scale_node = transform_dict.get("501")
    anchor_min_node = transform_dict.get("502")
    anchor_max_node = transform_dict.get("503")
    position_node = transform_dict.get("504")
    size_node = transform_dict.get("505")
    pivot_node = transform_dict.get("506")

    return {
        "scale": _parse_vec3(scale_node, ("1", "2", "3")),
        # Protobuf 语义：数值字段缺失即为默认 0。
        # 进度条/布局样本中确实存在“只写 x 或只写 y”的情况：例如 (x=1, y=0) 只写 x=1。
        # 因此锚点不要做“y=x”补全，否则会把右下角(1,0)误读为右上角(1,1)。
        "anchor_min": _parse_vec2(anchor_min_node, fill_missing_with_zero=True),
        "anchor_max": _parse_vec2(anchor_max_node, fill_missing_with_zero=True),
        "pivot": _parse_vec2(pivot_node, fill_missing_y_from_x=True),
        "anchored_position": _parse_vec2(position_node, fill_missing_with_zero=True),
        "size": _parse_vec2(size_node),
    }


def _parse_vec2(
    node: Any,
    *,
    fill_missing_y_from_x: bool = False,
    fill_missing_with_zero: bool = False,
) -> Optional[Dict[str, Optional[float]]]:
    if not isinstance(node, dict):
        return None
    x_value = node.get("501")
    y_value = node.get("502")

    x_float = _to_float_or_none(x_value)
    y_float = _to_float_or_none(y_value)

    if fill_missing_y_from_x and x_float is not None and y_float is None:
        y_float = x_float

    if fill_missing_with_zero:
        if x_float is None:
            x_float = 0.0
        if y_float is None:
            y_float = 0.0

    return {"x": x_float, "y": y_float}


def _parse_vec3(node: Any, key_order: Tuple[str, str, str]) -> Optional[Dict[str, Optional[float]]]:
    if not isinstance(node, dict):
        return None
    x_value = node.get(key_order[0])
    y_value = node.get(key_order[1])
    z_value = node.get(key_order[2])
    return {
        "x": _to_float_or_none(x_value),
        "y": _to_float_or_none(y_value),
        "z": _to_float_or_none(z_value),
    }


def _to_float_or_none(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _choose_best_rect_transform_states(
    candidates: List[Tuple[str, List[Dict[str, Any]]]]
) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    if not candidates:
        return None, []

    best_path: Optional[str] = None
    best_states: List[Dict[str, Any]] = []
    best_score = -1

    for path_text, states in candidates:
        score = _score_transform_state_list(states)
        if score > best_score:
            best_score = score
            best_path = path_text
            best_states = states

    return best_path, best_states


def _score_transform_state_list(state_list: List[Dict[str, Any]]) -> int:
    if not state_list:
        return 0
    best_single_state_score = 0
    for state in state_list:
        transform = state.get("transform")
        if not isinstance(transform, dict):
            continue
        state_score = _score_single_transform(transform)
        if state_score > best_single_state_score:
            best_single_state_score = state_score
    return best_single_state_score * 10 + len(state_list)


def _score_single_transform(transform: Dict[str, Any]) -> int:
    score = 0
    score += _score_vec2(transform.get("anchored_position")) * 2
    score += _score_vec2(transform.get("size")) * 2
    score += _score_vec2(transform.get("anchor_min"))
    score += _score_vec2(transform.get("anchor_max"))
    score += _score_vec2(transform.get("pivot"))
    scale_node = transform.get("scale")
    if isinstance(scale_node, dict):
        if scale_node.get("x") is not None:
            score += 1
        if scale_node.get("y") is not None:
            score += 1
        if scale_node.get("z") is not None:
            score += 1
    return score


def _score_vec2(vec2_node: Any) -> int:
    if not isinstance(vec2_node, dict):
        return 0
    score = 0
    if vec2_node.get("x") is not None:
        score += 1
    if vec2_node.get("y") is not None:
        score += 1
    return score


def _choose_best_rect_transform_state(state_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    best_transform: Optional[Dict[str, Any]] = None
    best_score = -1
    for state in state_list:
        transform = state.get("transform")
        if not isinstance(transform, dict):
            continue
        score = _score_single_transform(transform)
        if score > best_score:
            best_score = score
            best_transform = transform
    return best_transform


def _extract_ui_record_list_public_api__duplicate(dll_dump_object: Dict[str, Any]) -> List[Any]:
    """Public API. See `_extract_ui_record_list` for implementation details."""
    return _extract_ui_record_list(dll_dump_object)


def _extract_primary_name_public_api__duplicate(record: Dict[str, Any]) -> Optional[str]:
    """Public API. See `_extract_primary_name` for implementation details."""
    return _extract_primary_name(record)


def _extract_primary_guid_public_api__duplicate(record: Dict[str, Any]) -> Optional[int]:
    """Public API. See `_extract_primary_guid` for implementation details."""
    return _extract_primary_guid(record)


def _extract_visibility_flag_values_public_api__duplicate(record: Dict[str, Any]) -> List[int]:
    """Public API. See `_extract_visibility_flag_values` for implementation details."""
    return _extract_visibility_flag_values(record)


def _find_rect_transform_state_lists_public_api__duplicate(record: Dict[str, Any]) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """Public API. See `_find_rect_transform_state_lists` for implementation details."""
    return _find_rect_transform_state_lists(record)


def _choose_best_rect_transform_states_public_api__duplicate(
    candidates: List[Tuple[str, List[Dict[str, Any]]]],
) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """Public API. See `_choose_best_rect_transform_states` for implementation details."""
    return _choose_best_rect_transform_states(candidates)


def _choose_best_rect_transform_state_public_api__duplicate(state_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Public API. See `_choose_best_rect_transform_state` for implementation details."""
    return _choose_best_rect_transform_state(state_list)

def extract_ui_record_list(dll_dump_object: Dict[str, Any]) -> List[Any]:
    """
    Public API.

    NOTE: `*_dump.py` 等上层模块禁止跨模块导入 `_extract_ui_record_list` 这类私有符号，
    统一通过公开函数访问。
    """
    return _extract_ui_record_list(dll_dump_object)


def extract_primary_name(record: Dict[str, Any]) -> Optional[str]:
    """Public API. See `_extract_primary_name` for implementation details."""
    return _extract_primary_name(record)


def extract_primary_guid(record: Dict[str, Any]) -> Optional[int]:
    """Public API. See `_extract_primary_guid` for implementation details."""
    return _extract_primary_guid(record)


def extract_visibility_flag_values(record: Dict[str, Any]) -> List[int]:
    """Public API. See `_extract_visibility_flag_values` for implementation details."""
    return _extract_visibility_flag_values(record)


def find_rect_transform_state_lists(record: Dict[str, Any]) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """Public API. See `_find_rect_transform_state_lists` for implementation details."""
    return _find_rect_transform_state_lists(record)


def choose_best_rect_transform_states(
    candidates: List[Tuple[str, List[Dict[str, Any]]]],
) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """Public API. See `_choose_best_rect_transform_states` for implementation details."""
    return _choose_best_rect_transform_states(candidates)


def choose_best_rect_transform_state(state_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Public API. See `_choose_best_rect_transform_state` for implementation details."""
    return _choose_best_rect_transform_state(state_list)
