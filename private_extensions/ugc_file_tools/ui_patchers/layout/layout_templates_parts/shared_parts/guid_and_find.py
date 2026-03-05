from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.gil_dump_codec.protobuf_like import parse_binary_data_hex_text
from ugc_file_tools.ui.readable_dump import extract_primary_guid as _extract_primary_guid
from ugc_file_tools.ui.readable_dump import extract_primary_name as _extract_primary_name
from ugc_file_tools.ui_parsers.progress_bars import find_progressbar_binding_blob as _find_progressbar_binding_blob

from .models import DEFAULT_LIBRARY_ROOT_GUID
from .varint_stream import _decode_varint_stream


def _collect_all_widget_guids(ui_record_list: List[Any]) -> set[int]:
    guids: set[int] = set()
    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        guid_value = _extract_primary_guid(record)
        if isinstance(guid_value, int):
            guids.add(int(guid_value))
    return guids


def _allocate_next_guid(existing_ids: set[int], start: int) -> int:
    candidate = int(start)
    while candidate in existing_ids:
        candidate += 1
    return candidate


def _find_record_by_guid(ui_record_list: List[Any], guid: int) -> Optional[Dict[str, Any]]:
    target = int(guid)
    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        if _extract_primary_guid(record) == target:
            return record
    return None


def _infer_base_layout_guid(ui_record_list: List[Any]) -> int:
    """
    找一个适合作为“复制模板”的布局 root。
    优先选择“有 children 的布局 root”，避免从空布局继续复制空布局导致危险产物。

    优先级：
    - 名字包含“自定义布局”且 children 非空的 root record（优先选择序号较小的自定义布局：自定义布局_1/2/3...，避免误选带演示控件的高序号布局）
    - 名字包含“默认布局”且 children 非空的 root record
    - 任意 children 非空的 root record
    - 退化：名字包含“自定义布局”的 root record
    - 再退化：任意 root record
    """

    def _extract_custom_layout_suffix_number(name_text: str) -> Optional[int]:
        """
        尝试从布局名中解析 `自定义布局[_]N` 的 N（例如：自定义布局_1 / 自定义布局2）。
        解析失败返回 None。
        """
        raw = str(name_text or "")
        key = "自定义布局"
        idx = raw.find(key)
        if idx < 0:
            return None
        rest = raw[idx + len(key) :].strip()
        if rest.startswith("_"):
            rest = rest[1:].strip()
        digits: List[str] = []
        for ch in rest:
            if ch.isdigit():
                digits.append(ch)
            else:
                break
        if not digits:
            return None
        return int("".join(digits))

    # (suffix_rank, children_total, guid)
    candidates_custom_non_empty: List[Tuple[int, int, int]] = []
    # (suffix_rank, guid)
    candidates_custom_any: List[Tuple[int, int]] = []
    candidates_default_non_empty: List[int] = []
    fallback_non_empty: List[int] = []
    fallback_any: List[int] = []

    def _try_extract_children_guids_for_layout_inference(record: Dict[str, Any]) -> Optional[List[int]]:
        """
        在“推断 base_layout_guid”的场景中，允许跳过结构异常的 root record：
        - 不是所有 root record 都是布局；有些 record 可能缺少/污染 children(503)
        - 推断逻辑应尽量“跳过不符合形态的候选”，而不是直接崩溃

        返回：
        - list[int]：成功解析到 children（可能为空）
        - None：结构不符合预期（跳过该 record）
        """
        field503 = record.get("503")
        if field503 is None:
            return []
        if isinstance(field503, str):
            if field503 == "":
                return []
            if not field503.startswith("<binary_data>"):
                return None
            data = parse_binary_data_hex_text(field503)
            return _decode_varint_stream(data)
        if isinstance(field503, list):
            if not field503:
                return []
            first = field503[0]
            if not isinstance(first, str):
                return None
            if first == "":
                return []
            if not first.startswith("<binary_data>"):
                return None
            data = parse_binary_data_hex_text(first)
            return _decode_varint_stream(data)
        return None

    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        guid_value = _extract_primary_guid(record)
        if not isinstance(guid_value, int):
            continue
        # root record：没有 parent（504）
        if "504" in record:
            continue
        if int(guid_value) == int(DEFAULT_LIBRARY_ROOT_GUID):
            # 控件组库根不是布局模板
            continue
        name_text = _extract_primary_name(record)
        children = _try_extract_children_guids_for_layout_inference(record)
        if children is None:
            continue
        has_children = bool(children)

        if isinstance(name_text, str) and "自定义布局" in name_text:
            if has_children:
                suffix = _extract_custom_layout_suffix_number(name_text)
                suffix_rank = int(suffix) if suffix is not None else 9999
                candidates_custom_non_empty.append((suffix_rank, int(len(children)), int(guid_value)))
            else:
                suffix = _extract_custom_layout_suffix_number(name_text)
                suffix_rank = int(suffix) if suffix is not None else 9999
                candidates_custom_any.append((suffix_rank, int(guid_value)))
            continue

        if isinstance(name_text, str) and "默认布局" in name_text and has_children:
            candidates_default_non_empty.append(int(guid_value))
            continue

        if has_children:
            fallback_non_empty.append(int(guid_value))
        else:
            fallback_any.append(int(guid_value))

    if candidates_custom_non_empty:
        # suffix 小的更靠前；同 suffix 时 children 少的更优先（更像“纯固有内容”）；再按 guid 稳定。
        candidates_custom_non_empty.sort()
        return int(candidates_custom_non_empty[0][2])
    if candidates_default_non_empty:
        return min(candidates_default_non_empty)
    if fallback_non_empty:
        return min(fallback_non_empty)
    if candidates_custom_any:
        candidates_custom_any.sort()
        return int(candidates_custom_any[0][1])
    if fallback_any:
        return min(fallback_any)
    raise RuntimeError("无法推断 base_layout_guid（未找到任何 root record）。")


def _find_any_progressbar_record_with_parent(
    ui_record_list: List[Any],
    *,
    parent_guid: int,
) -> Optional[Dict[str, Any]]:
    parent_guid = int(parent_guid)
    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        if record.get("504") != parent_guid:
            continue
        if _find_progressbar_binding_blob(record) is not None:
            return record
    return None


def _find_any_progressbar_record_with_template_id_blob(ui_record_list: List[Any]) -> Optional[Dict[str, Any]]:
    """
    兼容旧名字：历史上用 `502/*/13` 的存在来“猜测进度条 record”，但该字段语义并不稳定，
    且控件组子控件也会出现该 blob。

    现在该函数改为：返回任意能识别为“进度条”（存在绑定 blob）的 record。
    """
    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        if _find_progressbar_binding_blob(record) is not None:
            return record
    return None


__all__ = [
    "_collect_all_widget_guids",
    "_allocate_next_guid",
    "_find_record_by_guid",
    "_infer_base_layout_guid",
    "_find_any_progressbar_record_with_parent",
    "_find_any_progressbar_record_with_template_id_blob",
]

