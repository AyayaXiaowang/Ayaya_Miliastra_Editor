from __future__ import annotations

from typing import Any, Dict, Optional

from ugc_file_tools.gil_dump_codec.protobuf_like import format_binary_data_hex_text, parse_binary_data_hex_text
from ugc_file_tools.ui.readable_dump import extract_primary_guid as _extract_primary_guid

from .guid_and_find import _find_record_by_guid
from .models import DEFAULT_LIBRARY_ROOT_GUID
from .varint_stream import _decode_varint_stream, _encode_varint_stream


def _append_layout_root_guid_to_layout_registry(raw_dump_object: Dict[str, Any], layout_guid: int) -> None:
    """
    将新布局 GUID 注册到 `4/9/501[0]` 的 varint stream 中，否则编辑器不会显示该布局。

    样本（测试新建布局2.gil）中该列表形如：
      [默认布局, 自定义布局1, 自定义布局2, 自定义布局3, ..., 1073741838]

    其中末尾的 1073741838（控件组库根）需要保持在最后，因此新增布局会插入到“倒数第 1 个”之前。
    """
    payload_root = raw_dump_object.get("4")
    if not isinstance(payload_root, dict):
        raise ValueError("DLL dump-json 缺少根字段 '4'（期望为 dict）。")
    node9 = payload_root.get("9")
    if not isinstance(node9, dict):
        raise ValueError("DLL dump-json 缺少字段 '4/9'（期望为 dict）。")
    list501 = node9.get("501")
    # 兼容：repeated 字段在“只有 1 个元素”时可能被 dump 为标量（str）而非 list[str]
    if isinstance(list501, str):
        list501 = [list501]
        node9["501"] = list501
    if not isinstance(list501, list) or not list501:
        raise ValueError("dump-json 缺少字段 '4/9/501'（期望为非空 list 或 str）。")
    first = list501[0]
    if not isinstance(first, str) or (first != "" and not first.startswith("<binary_data>")):
        raise ValueError("字段 '4/9/501[0]' 期望为 '<binary_data>' 字符串或空字符串。")

    existing_bytes = parse_binary_data_hex_text(first) if first != "" else b""
    existing_ids = _decode_varint_stream(existing_bytes)

    target_layout_guid = int(layout_guid)
    if target_layout_guid in existing_ids:
        return

    # 末尾固定为库根 GUID（样本中为 1073741838），新增布局插在它前面。
    insert_index = len(existing_ids)
    if existing_ids and int(existing_ids[-1]) == int(DEFAULT_LIBRARY_ROOT_GUID):
        insert_index = len(existing_ids) - 1

    new_ids = list(existing_ids)
    new_ids.insert(int(insert_index), target_layout_guid)
    list501[0] = format_binary_data_hex_text(_encode_varint_stream(new_ids))


def try_infer_layout_index_from_layout_registry(
    raw_dump_object: Dict[str, Any],
    *,
    layout_guid: int,
) -> Optional[int]:
    """
    反查“布局索引”（供节点 `切换当前界面布局` 使用）：
    - 从 `4/9/501[0]` 解出 layout registry varint stream（内容为 layout root GUID 列表）
    - 去掉末尾的控件组库根 guid（默认 1073741838）
    - 跳过“模板 root”（template roots）条目（它们也会被注册到 4/9/501，但不是可切换的界面布局）
    - 返回“布局索引”的整数值：**布局 root GUID 本身**（不是 1-based 序号）

    依据（真源图验证）：
    - `Switch Current Interface Layout(382)` 的第二个输入端口类型为 `Int`，但其值通常为 107374xxxx
      的 layout root GUID（例如默认布局 guid=1073741825），而不是 1..N 的序号。
    """
    payload_root = raw_dump_object.get("4")
    if not isinstance(payload_root, dict):
        raise ValueError("DLL dump-json 缺少根字段 '4'（期望为 dict）。")
    node9 = payload_root.get("9")
    if not isinstance(node9, dict):
        raise ValueError("DLL dump-json 缺少字段 '4/9'（期望为 dict）。")

    list501 = node9.get("501")
    # repeated 兼容：单元素可能被 dump 为 str
    if isinstance(list501, str):
        list501 = [list501]
    if not isinstance(list501, list) or not list501:
        return None
    first = list501[0]
    if not isinstance(first, str) or (first != "" and not first.startswith("<binary_data>")):
        return None

    existing_bytes = parse_binary_data_hex_text(first) if first != "" else b""
    existing_ids = _decode_varint_stream(existing_bytes)
    if not existing_ids:
        return None

    # drop library root
    ids2 = list(existing_ids)
    if ids2 and int(ids2[-1]) == int(DEFAULT_LIBRARY_ROOT_GUID):
        ids2 = ids2[:-1]

    ui_record_list = node9.get("502")
    if isinstance(ui_record_list, dict):
        ui_record_list = [ui_record_list]
    if not isinstance(ui_record_list, list):
        ui_record_list = []

    def _is_template_root_record(record: Any) -> bool:
        if not isinstance(record, dict):
            return False
        # template root：无 parent(504)，并且 meta 中包含 14(group_ref) 与 16(group_container_meta0)
        if "504" in record:
            return False
        meta = record.get("502")
        if not isinstance(meta, list):
            return False
        has14 = False
        has16 = False
        for m in meta:
            if not isinstance(m, dict):
                continue
            if m.get("501") == 4 and m.get("502") == 4:
                has14 = True
            if m.get("501") == 6 and m.get("502") == 13:
                has16 = True
        return bool(has14 and has16)

    layout_roots: list[int] = []
    for gid in ids2:
        g = int(gid)
        rec = _find_record_by_guid(ui_record_list, g)
        if rec is not None and _is_template_root_record(rec):
            continue
        layout_roots.append(g)

    target = int(layout_guid)
    if target not in layout_roots:
        return None
    return int(target)


def _prepend_layout_root_guid_to_layout_registry(raw_dump_object: Dict[str, Any], layout_guid: int) -> None:
    """
    将一个“模板 root / 布局 root”的 GUID 注册到 `4/9/501[0]` 的 varint stream 中。

    重要（模板相关）：
    - 某些真源存档中，`4/9/501[0]` 的第一个 GUID 是“模板索引根”（template root），其顺序具有语义；
      若把新模板 root 插到最开头，会把原本的 template root 顶下去，导致编辑器侧“模板看似存在但使用异常/乱码”。
    - 因此本函数对“模板 root”采用 **插入到现有 template roots 之后** 的策略，以保持现有模板根顺序稳定。

    样本（仅详情两个，打组了，而且保存成模板了.gil）：
      [模板组合1, 默认布局, 1073741838]
    """
    payload_root = raw_dump_object.get("4")
    if not isinstance(payload_root, dict):
        raise ValueError("DLL dump-json 缺少根字段 '4'（期望为 dict）。")
    node9 = payload_root.get("9")
    if not isinstance(node9, dict):
        raise ValueError("DLL dump-json 缺少字段 '4/9'（期望为 dict）。")
    list501 = node9.get("501")
    # 兼容：repeated 字段在“只有 1 个元素”时可能被 dump 为标量（str）而非 list[str]
    if isinstance(list501, str):
        list501 = [list501]
        node9["501"] = list501
    if not isinstance(list501, list) or not list501:
        raise ValueError("dump-json 缺少字段 '4/9/501'（期望为非空 list 或 str）。")
    first = list501[0]
    if not isinstance(first, str) or (first != "" and not first.startswith("<binary_data>")):
        raise ValueError("字段 '4/9/501[0]' 期望为 '<binary_data>' 字符串或空字符串。")

    existing_bytes = parse_binary_data_hex_text(first) if first != "" else b""
    existing_ids = _decode_varint_stream(existing_bytes)

    target_layout_guid = int(layout_guid)
    if target_layout_guid in existing_ids:
        return

    new_ids = list(existing_ids)
    # 约定：将新模板 root 插入到“现有模板 roots 列表”之后；若无法判定，则退回插到开头。
    insert_index = 0

    node9 = payload_root.get("9")
    ui_record_list = node9.get("502") if isinstance(node9, dict) else None
    if isinstance(ui_record_list, dict):
        ui_record_list = [ui_record_list]
    if not isinstance(ui_record_list, list):
        ui_record_list = []

    def _is_template_root_guid(guid: int) -> bool:
        target = int(guid)
        for rec in ui_record_list:
            if not isinstance(rec, dict):
                continue
            if _extract_primary_guid(rec) != target:
                continue
            # template root：无 parent(504)，并且 meta 中包含 14(group_ref) 与 16(group_container_meta0)
            if "504" in rec:
                return False
            meta = rec.get("502")
            if not isinstance(meta, list):
                return False
            has14 = False
            has16 = False
            for m in meta:
                if not isinstance(m, dict):
                    continue
                if m.get("501") == 4 and m.get("502") == 4:
                    has14 = True
                if m.get("501") == 6 and m.get("502") == 13:
                    has16 = True
            if not (has14 and has16):
                return False
            return True
        return False

    idx = 0
    while idx < len(new_ids) and _is_template_root_guid(int(new_ids[idx])):
        idx += 1
    insert_index = int(idx)

    new_ids.insert(int(insert_index), target_layout_guid)
    list501[0] = format_binary_data_hex_text(_encode_varint_stream(new_ids))


__all__ = [
    "_append_layout_root_guid_to_layout_registry",
    "try_infer_layout_index_from_layout_registry",
    "_prepend_layout_root_guid_to_layout_registry",
]

