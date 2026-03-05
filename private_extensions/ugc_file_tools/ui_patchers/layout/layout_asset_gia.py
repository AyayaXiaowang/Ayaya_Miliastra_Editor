from __future__ import annotations

import copy
import time
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.gia.container import wrap_gia_container
from ugc_file_tools.gil_dump_codec.protobuf_like import (
    encode_message,
    format_binary_data_hex_text,
    parse_binary_data_hex_text,
)
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.ui.readable_dump import (
    extract_primary_name as _extract_primary_name,
    extract_ui_record_list as _extract_ui_record_list,
)

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    decode_varint_stream as _decode_varint_stream,
    dump_gil_to_raw_json_object as _dump_gil_to_raw_json_object,
    encode_varint_stream as _encode_varint_stream,
    find_record_by_guid as _find_record_by_guid,
)
from ugc_file_tools.gia.container import unwrap_gia_container
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map
from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import decoded_field_map_to_numeric_message
from ugc_file_tools.ui_patchers.web_ui.web_ui_import_rect import (
    has_rect_transform_state,
    try_extract_textbox_text_node,
    write_rect_states_from_web_rect,
)
from ugc_file_tools.ui_patchers.misc.add_progress_bars import set_widget_name as _set_widget_name
from ugc_file_tools.ui_patchers.misc.add_progress_bars import (
    set_widget_parent_guid_field504 as _set_widget_parent_guid_field504,
)


def _make_layout_asset_entry_id(guid: int) -> Dict[str, Any]:
    """
    `.gia`(布局资产)中“条目 ID”的固定形态（从样本反推）：
      - 2: 1
      - 3: 8
      - 4: <guid>

    这不是 `.gil` 的 UI record（UI record 的 guid 位于 record["501"]），而是布局资产容器条目的 ID。
    """
    g = int(guid)
    return {"2": 1, "3": 8, "4": g}


def _iter_record_children_guids(record: Dict[str, Any]) -> List[int]:
    """
    UI record children（安全模式）：
    - 只有当 record["503"] 形态为 `["<binary_data> ..."]`（或标量 str）时，才视为 children varint stream；
    - 其它形态（例如 dict / list[dict] / int / 非 <binary_data> 的字符串）一律视为“无 children”，避免误判导致崩溃。
    """
    field503 = record.get("503")
    if field503 is None:
        return []
    if isinstance(field503, str):
        items = [field503]
    elif isinstance(field503, list):
        items = field503
    else:
        return []
    if not items:
        return []
    first = items[0]
    if not isinstance(first, str):
        return []
    if first == "":
        return []
    if not first.startswith("<binary_data>"):
        return []
    raw = parse_binary_data_hex_text(first)
    children = _decode_varint_stream(raw)
    return [int(x) for x in children]


def _append_child_guid_to_record(
    *,
    parent_record: Dict[str, Any],
    child_guid: int,
) -> None:
    """
    将 child_guid 追加到 parent_record 的 children varint stream（record["503"]）中。

    注意：
    - 这里修改的是 UI record 自身的 children（编辑器/游戏渲染层级通常以它为准）；
    - 仅修改条目 entry.field_2（布局资产层的 children id 列表）不足以保证可见。
    """
    parent_children = list(_iter_record_children_guids(parent_record))
    g = int(child_guid)
    if g <= 0:
        raise ValueError("child_guid 必须为正整数")
    if g not in parent_children:
        parent_children.append(g)
    parent_record["503"] = [format_binary_data_hex_text(_encode_varint_stream([int(x) for x in parent_children]))]


def _collect_reachable_ui_record_tree(
    *,
    ui_record_list: List[Any],
    root_guid: int,
    extra_children_by_guid: Dict[int, List[int]] | None = None,
) -> Tuple[List[int], Dict[int, Dict[str, Any]]]:
    """
    从 layout_root_guid 出发，沿 UI record 的 children 关系，收集整棵可达树。

    返回：
    - ordered_guids：按 DFS（按 children 顺序）首次到达顺序展开的 guid 列表（包含 root_guid）
    - record_by_guid：guid -> record dict
    """
    record_by_guid: Dict[int, Dict[str, Any]] = {}
    for r in ui_record_list:
        if not isinstance(r, dict):
            continue
        guid_value = r.get("501")
        if not isinstance(guid_value, int):
            continue
        record_by_guid[int(guid_value)] = r

    root = int(root_guid)
    if root not in record_by_guid:
        raise KeyError(f"在 .gil 中未找到 layout_root_guid 对应的 UI record：{root}")

    ordered: List[int] = []
    visited: set[int] = set()

    extra = dict(extra_children_by_guid or {})

    stack: List[int] = [root]
    while stack:
        guid = int(stack.pop())
        if guid in visited:
            continue
        visited.add(guid)
        ordered.append(guid)

        record = record_by_guid.get(guid)
        if record is None:
            raise KeyError(f"在 .gil 中未找到 UI record（树引用缺失）：{guid}")
        children = list(_iter_record_children_guids(record))
        extra_children = extra.get(int(guid)) or []
        if extra_children:
            # extra children 排在后面（保留 record children 的相对顺序）
            children.extend([int(x) for x in extra_children if int(x) > 0])
        # DFS：保持 children 的顺序（父->子），因此入栈需要反序
        for child_guid in reversed(children):
            if child_guid <= 0:
                continue
            stack.append(int(child_guid))

    return ordered, record_by_guid


def _allocate_layout_asset_file_guid(*, file_name: str, used_guids: set[int]) -> int:
    """
    生成 root_message.field_3 中使用的“文件 GUID”段（样本中为 1073742011/1073742031）：
    - 它不会出现在条目 ID 列表中（样本中也没有作为 int 出现，仅存在于字符串）；
    - 不能与任何条目 guid 冲突（尤其不能等于 layout_root_guid）。

    这里采用稳定策略：对 file_name 做 CRC32，映射到 0x40000000 段内的一个小范围（~1073742000 起），
    并在冲突时顺延，直到找到未占用 guid。
    """
    name = str(file_name or "").strip() or "layout_asset.gia"
    crc32 = zlib.crc32(name.encode("utf-8")) & 0xFFFFFFFF

    # 0x40000000 = 1073741824
    base = 1073742000  # 贴近样本：2011/2031 等
    span = 4096  # 留足空间做避让
    candidate = int(base + (crc32 % span))
    if candidate < 1073741824:
        candidate = 1073741824

    # 避让冲突
    for _ in range(span + 16):
        if candidate not in used_guids:
            return int(candidate)
        candidate += 1
        if candidate >= base + span:
            candidate = int(base)
    raise RuntimeError("无法分配 layout asset file guid（冲突过多）")


def create_layout_asset_gia_from_gil(
    *,
    input_gil_file_path: Path,
    layout_root_guid: int,
    output_gia_path: Path,
    output_file_name: str,
    game_version: str = "6.3.0",
    export_uid: int = 0,
    sort_entries_by_guid: bool = True,
    sort_children_by_guid: bool = False,
    extra_entry_children_by_guid: Dict[int, List[int]] | None = None,
) -> Dict[str, Any]:
    """
    从 `.gil` 中提取“界面布局 root + children（控件组/模板实例等）”的 UI records，
    打包成“布局资产 `.gia`”（结构以 `builtin_resources/gia_templates/layout_asset_template.gia` 为内置模板反推）。

    设计目标：
    - 不依赖节点图 GIA 口径（该类 `.gia` graphs_count=0，不可用 graph_ir 写回）。
    - 复用 `.gil` 写回链路已生成的真实 UI record 结构（field_19 承载 record 的 message）。
    - 输出文件落盘到 `ugc_file_tools/out/`（通过 `resolve_output_file_path_in_out_dir`）。
    """
    gil_path = Path(input_gil_file_path).resolve()
    if not gil_path.is_file():
        raise FileNotFoundError(str(gil_path))

    root_guid = int(layout_root_guid)
    if root_guid <= 0:
        raise ValueError("layout_root_guid 必须为正整数")

    raw_dump_object = _dump_gil_to_raw_json_object(gil_path)
    ui_record_list = _extract_ui_record_list(raw_dump_object)

    ordered_guids, record_by_guid = _collect_reachable_ui_record_tree(
        ui_record_list=ui_record_list,
        root_guid=root_guid,
        extra_children_by_guid=extra_entry_children_by_guid,
    )
    layout_root_record = record_by_guid.get(root_guid)
    if layout_root_record is None:
        raise KeyError(f"在 .gil 中未找到 layout_root_guid 对应的 UI record：{root_guid}")

    root_children_guids = _iter_record_children_guids(layout_root_record)
    if not root_children_guids:
        raise ValueError(f"layout_root_guid 的 children 为空（无法导出布局资产）：{root_guid}")

    # layout_asset 根条目（field_1）
    layout_name = _extract_primary_name(layout_root_record) or ""
    root_children_ordered = list(root_children_guids)
    if bool(sort_children_by_guid):
        root_children_ordered = sorted([int(x) for x in root_children_ordered])

    root_entry: Dict[str, Any] = {
        "1": _make_layout_asset_entry_id(root_guid),
        "2": [_make_layout_asset_entry_id(int(g)) for g in root_children_ordered],
        "3": layout_name,
        "5": 20,  # 样本：root=20
        "19": {"1": layout_root_record},
    }

    # layout_asset 子条目列表（field_2）：包含 root 下所有可达 record（不含 root 本身）
    child_entries: List[Dict[str, Any]] = []
    candidate_entry_guids = [int(x) for x in ordered_guids if int(x) != int(root_guid)]
    if bool(sort_entries_by_guid):
        candidate_entry_guids = sorted(candidate_entry_guids)
    for guid in candidate_entry_guids:
        record = record_by_guid.get(int(guid))
        if record is None:
            raise KeyError(f"在 .gil 中未找到 child guid 对应的 UI record：{guid}")
        name = _extract_primary_name(record) or ""

        entry: Dict[str, Any] = {
            "1": _make_layout_asset_entry_id(int(guid)),
            "3": name,
            "5": 15,  # 样本：entries=15
            "19": {"1": record},
        }
        children = list(_iter_record_children_guids(record))
        extra_children = (extra_entry_children_by_guid or {}).get(int(guid)) or []
        if extra_children:
            # 与 traversal 一致：extra children 追加在后
            children.extend([int(x) for x in extra_children if int(x) > 0])
        if children:
            children_ordered = list(children)
            if bool(sort_children_by_guid):
                children_ordered = sorted([int(x) for x in children_ordered])
            entry["2"] = [_make_layout_asset_entry_id(int(c)) for c in children_ordered]
        child_entries.append(entry)

    safe_file_name = str(output_file_name or "").strip() or "layout_asset.gia"
    if not safe_file_name.lower().endswith(".gia"):
        safe_file_name = safe_file_name + ".gia"

    # 样本 field_3 形如：`341416358-<timestamp>-<guid>-\\<file_name>`
    # - 第一段在多个样本中保持不变（341416358），因此对齐为常量；
    # - 第二段为时间戳；
    # - 第三段为“文件 GUID”，样本中与 layout_root_guid 不同，且不出现在条目 ID 列表中；
    #   若误写成 layout_root_guid（或与条目 guid 冲突），游戏可能直接拒绝解析。
    # 注意：样本中该分隔符为单个反斜杠 `\`，不是 `\\`。
    used = set(int(x) for x in ordered_guids)
    used.add(int(root_guid))
    file_guid = _allocate_layout_asset_file_guid(file_name=str(safe_file_name), used_guids=used)
    file_path_field = f"341416358-{int(time.time())}-{int(file_guid)}-\\{safe_file_name}"

    root_message: Dict[str, Any] = {
        "1": root_entry,
        "2": child_entries,
        "3": file_path_field,
        "5": str(game_version or "6.3.0"),
    }

    encoded_proto_bytes = encode_message(root_message)
    gia_bytes = wrap_gia_container(encoded_proto_bytes)

    output_path = resolve_output_file_path_in_out_dir(Path(output_gia_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(gia_bytes)

    return {
        "output_gia_file": str(output_path),
        "output_file_name": safe_file_name,
        "layout_root_guid": int(root_guid),
        "layout_name": str(layout_name),
        "children_total": len(root_children_guids),
        "child_guids": [int(x) for x in root_children_guids],
        "reachable_records_total": len(ordered_guids),
        "source_gil_file": str(gil_path),
    }


def create_layout_asset_gia_from_gil_by_patching_base_gia(
    *,
    input_gil_file_path: Path,
    layout_root_guid: int,
    base_gia_file_path: Path,
    output_gia_path: Path,
    output_file_name: str,
    game_version: str = "6.3.0",
    sort_entries_by_guid: bool = True,
    sort_children_by_guid: bool = False,
    extra_entry_children_by_guid: Dict[int, List[int]] | None = None,
) -> Dict[str, Any]:
    """
    “最保守”导出策略：在一个已确认可被游戏解析的“布局资产 .gia 样本”基础上做最小改写。

    改写范围（其余字段完全保留）：
    - root_message["1"]：布局 root 条目（guid/name/children + record）
    - root_message["2"]：条目列表（按 guid 升序）
    - root_message["3"]：路径字符串（保留样本的“文件 GUID”段，只更新时间戳与文件名）
    - root_message["5"]：版本字符串
    """
    base_gia = Path(base_gia_file_path).resolve()
    if not base_gia.is_file():
        raise FileNotFoundError(str(base_gia))

    # 先用“纯构造器”把 root/entries 算出来（但不直接输出文件）
    tmp = create_layout_asset_gia_from_gil(
        input_gil_file_path=Path(input_gil_file_path),
        layout_root_guid=int(layout_root_guid),
        output_gia_path=Path("_ignore.gia"),
        output_file_name=str(output_file_name),
        game_version=str(game_version or "6.3.0"),
        export_uid=0,
        sort_entries_by_guid=bool(sort_entries_by_guid),
        sort_children_by_guid=bool(sort_children_by_guid),
        extra_entry_children_by_guid=extra_entry_children_by_guid,
    )

    # 读取刚刚构造的 message（避免重复实现构造逻辑）：直接从 tmp 输出文件中解码回 message
    # 注意：tmp 输出文件在 out/ 下，我们读取后立刻删除它，避免污染。
    tmp_gia_path = Path(tmp["output_gia_file"]).resolve()
    tmp_proto = unwrap_gia_container(tmp_gia_path, check_header=True)
    tmp_fields, consumed = decode_message_to_field_map(
        data_bytes=tmp_proto,
        start_offset=0,
        end_offset=len(tmp_proto),
        remaining_depth=24,
    )
    if consumed != len(tmp_proto):
        raise ValueError("tmp gia proto decode did not consume full bytes")
    tmp_msg = decoded_field_map_to_numeric_message(tmp_fields)
    if not isinstance(tmp_msg, dict):
        raise TypeError("tmp decoded root_message must be dict")

    # 解码 base message
    base_proto = unwrap_gia_container(base_gia, check_header=True)
    base_fields, consumed2 = decode_message_to_field_map(
        data_bytes=base_proto,
        start_offset=0,
        end_offset=len(base_proto),
        remaining_depth=24,
    )
    if consumed2 != len(base_proto):
        raise ValueError("base gia proto decode did not consume full bytes")
    base_msg = decoded_field_map_to_numeric_message(base_fields)
    if not isinstance(base_msg, dict):
        raise TypeError("base decoded root_message must be dict")

    # patch 1/2/5
    base_msg["1"] = tmp_msg.get("1")
    base_msg["2"] = tmp_msg.get("2")
    base_msg["5"] = str(game_version or base_msg.get("5") or "6.3.0")

    # patch 3：保留样本第三段 guid（file guid），只更新 timestamp + file name
    base_path_value = base_msg.get("3")
    # 兼容：若 base_msg["3"] 以 `<binary_data>` 形态存在（lossless），先解码为 UTF-8 文本再处理
    if isinstance(base_path_value, str) and base_path_value.startswith("<binary_data>"):
        base_path = parse_binary_data_hex_text(base_path_value).decode("utf-8")
    else:
        base_path = str(base_path_value or "")
    safe_name = str(output_file_name or "").strip() or "layout_asset.gia"
    if not safe_name.lower().endswith(".gia"):
        safe_name = safe_name + ".gia"

    # base_path 形如：341416358-<ts>-<file_guid>-\xxx.gia
    # 若解析失败，则回退使用 tmp_msg["3"]（至少保证形态正确）。
    if base_path.count("-") >= 3 and "\\\\" not in base_path:
        parts = base_path.split("-", 3)
        if len(parts) == 4:
            prefix = parts[0]
            file_guid_and_tail = parts[2]
            # parts[3] 包含 "\xxx.gia" 或其它
            # 这里重建：prefix-<now>-<file_guid>-\<safe_name>
            file_guid = str(file_guid_and_tail).strip()
            base_msg["3"] = f"{prefix}-{int(time.time())}-{file_guid}-\\{safe_name}"
        else:
            base_msg["3"] = str(tmp_msg.get("3") or "")
    else:
        base_msg["3"] = str(tmp_msg.get("3") or "")

    # 编码并封装（使用 base 容器格式）
    encoded_proto_bytes = encode_message(base_msg)
    gia_bytes = wrap_gia_container(encoded_proto_bytes)

    output_path = resolve_output_file_path_in_out_dir(Path(output_gia_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(gia_bytes)

    # 清理 tmp 产物
    if tmp_gia_path.is_file():
        tmp_gia_path.unlink()

    return {
        "output_gia_file": str(output_path),
        "base_gia_file": str(base_gia),
        "source_gil_file": str(Path(input_gil_file_path).resolve()),
        "layout_root_guid": int(layout_root_guid),
        "output_file_name": safe_name,
    }


def create_layout_asset_gia_by_patching_base_gia_and_adding_test_progressbar(
    *,
    base_gia_file_path: Path,
    output_gia_path: Path,
    output_file_name: str,
    layout_name: str = "测试布局",
    progressbar_name: str = "进度条_测试",
    template_entry_name_candidates: Tuple[str, ...] = ("文本框", "道具展示"),
    web_left: float = 100.0,
    web_top: float = 100.0,
    web_width: float = 300.0,
    web_height: float = 24.0,
    reference_pc_canvas_size: Tuple[float, float] = (1600.0, 900.0),
    game_version: str = "6.3.0",
    decode_depth: int = 24,
) -> Dict[str, Any]:
    """
    纯 GIA 补丁实验：在一个“已验证可解析的布局资产 .gia 样本”基础上，追加一个“进度条控件”条目。

    目的：
    - 验证“在正确 GIA 上新增控件条目 + 写入 RectTransform”是否被游戏接受；
    - 为后续 HTML→GIA 的最小可行链路提供可控的增量实验基线。

    注意：
    - 优先从 base 样本中克隆“真实进度条 record”（component 中包含 node20 + 绑定配置）；
    - 若 base 中不存在进度条（例如极简样本），则兜底克隆一个可渲染 TextBox（用于验证“新增条目是否可见”）。
    """
    base_gia = Path(base_gia_file_path).resolve()
    if not base_gia.is_file():
        raise FileNotFoundError(str(base_gia))

    proto = unwrap_gia_container(base_gia, check_header=True)
    fields, consumed = decode_message_to_field_map(
        data_bytes=proto,
        start_offset=0,
        end_offset=len(proto),
        remaining_depth=int(decode_depth),
    )
    if consumed != len(proto):
        raise ValueError("base gia proto decode did not consume full bytes")
    msg = decoded_field_map_to_numeric_message(fields, prefer_raw_hex_for_utf8=True)
    if not isinstance(msg, dict):
        raise TypeError("base decoded root_message must be dict")

    root_entry = msg.get("1")
    if not isinstance(root_entry, dict):
        raise ValueError("base gia missing root_entry at field 1")
    layout_root_guid = root_entry.get("1", {}).get("4") if isinstance(root_entry.get("1"), dict) else None
    if not isinstance(layout_root_guid, int) or int(layout_root_guid) <= 0:
        raise ValueError("base gia root_entry missing guid at field 1/1/4")
    layout_root_record = root_entry.get("19", {}).get("1") if isinstance(root_entry.get("19"), dict) else None
    if not isinstance(layout_root_record, dict):
        raise ValueError("base gia root_entry missing ui_record at field 1/19/1")

    def decode_entry_name(value: Any) -> str:
        if isinstance(value, str) and value.startswith("<binary_data>"):
            raw = parse_binary_data_hex_text(value)
            text = raw.decode("utf-8")
            return str(text)
        if isinstance(value, str):
            return str(value)
        return ""

    def try_extract_progressbar_config_dict(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        component_list = record.get("505")
        if not isinstance(component_list, list) or len(component_list) <= 3:
            return None
        component = component_list[3]
        if not isinstance(component, dict):
            return None
        nested = component.get("503")
        if not isinstance(nested, dict):
            return None
        config = nested.get("20")
        if not isinstance(config, dict):
            return None
        if not all(key in config for key in ("504", "505", "506")):
            return None

        def _looks_like_variable_ref(node: Any) -> bool:
            if not isinstance(node, dict):
                return False
            group_id = node.get("501")
            if not isinstance(group_id, int):
                return False
            name_value = node.get("502")
            if name_value is None:
                return True
            if isinstance(name_value, str):
                return True
            return False

        if not (
            _looks_like_variable_ref(config.get("504"))
            and _looks_like_variable_ref(config.get("505"))
            and _looks_like_variable_ref(config.get("506"))
        ):
            return None
        return config

    def set_gia_record_guid(record: Dict[str, Any], new_guid: int) -> None:
        old_guid = record.get("501")
        if not isinstance(old_guid, int):
            raise ValueError("record missing guid int at field 501")
        record["501"] = int(new_guid)
        meta_list = record.get("502")
        if not isinstance(meta_list, list) or not meta_list:
            return
        for meta in meta_list:
            if not isinstance(meta, dict):
                continue
            node11 = meta.get("11")
            if not isinstance(node11, dict):
                continue
            if node11.get("501") == int(old_guid):
                node11["501"] = int(new_guid)

    # 找一个可克隆的模板：
    # - 优先：进度条 record（带 component node20 + 变量绑定配置）；
    # - 兜底：TextBox（可写入可见文本，用于验证“新增条目可见”）。
    entries = msg.get("2")
    if not isinstance(entries, list) or not entries:
        raise ValueError("base gia missing entries at field 2")

    template_entry: Dict[str, Any] | None = None
    progressbar_candidates: List[Dict[str, Any]] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        rec = e.get("19", {}).get("1") if isinstance(e.get("19"), dict) else None
        if not isinstance(rec, dict):
            continue
        if not isinstance(rec.get("501"), int):
            continue
        if not has_rect_transform_state(rec, state_index=0):
            continue
        if try_extract_progressbar_config_dict(rec) is None:
            continue
        progressbar_candidates.append(e)

    if progressbar_candidates:
        # 稳定偏好：优先挑“红色方块/黄色方块/蓝色方块”（更像“条形进度”）
        preferred_names = ("红色方块", "黄色方块", "蓝色方块")
        picked: Dict[str, Any] | None = None
        for preferred in preferred_names:
            for e in progressbar_candidates:
                if decode_entry_name(e.get("3")) == preferred:
                    picked = e
                    break
            if picked is not None:
                break
        template_entry = picked or progressbar_candidates[0]

    if template_entry is None:
        name_candidates = tuple(str(x) for x in (template_entry_name_candidates or ()))
        for candidate_name in name_candidates:
            for e in entries:
                if not isinstance(e, dict):
                    continue
                if decode_entry_name(e.get("3")) != candidate_name:
                    continue
                rec = e.get("19", {}).get("1") if isinstance(e.get("19"), dict) else None
                if not isinstance(rec, dict):
                    continue
                if not isinstance(rec.get("501"), int):
                    continue
                if not has_rect_transform_state(rec, state_index=0):
                    continue
                if not isinstance(try_extract_textbox_text_node(rec), dict):
                    continue
                template_entry = e
                break
            if template_entry is not None:
                break

    if template_entry is None:
        for e in entries:
            if not isinstance(e, dict):
                continue
            rec = e.get("19", {}).get("1") if isinstance(e.get("19"), dict) else None
            if not isinstance(rec, dict):
                continue
            if not isinstance(rec.get("501"), int):
                continue
            if not has_rect_transform_state(rec, state_index=0):
                continue
            if not isinstance(try_extract_textbox_text_node(rec), dict):
                continue
            template_entry = e
            break

    if template_entry is None:
        raise RuntimeError("未找到可作为模板的条目（需要 RectTransform state0；优先 ProgressBar，其次 TextBox）。")

    # 分配新 guid（追加到 entries）
    used_ids: set[int] = set()
    used_ids.add(int(layout_root_guid))
    for e in entries:
        if not isinstance(e, dict):
            continue
        id_node = e.get("1")
        if isinstance(id_node, dict):
            entry_guid_value = id_node.get("4")
            if isinstance(entry_guid_value, int):
                used_ids.add(int(entry_guid_value))

    new_guid = max(used_ids) + 1
    while new_guid in used_ids:
        new_guid += 1

    new_entry = copy.deepcopy(template_entry)
    # patch entry id + name
    if not isinstance(new_entry.get("1"), dict):
        new_entry["1"] = _make_layout_asset_entry_id(int(new_guid))
    else:
        new_entry["1"]["4"] = int(new_guid)
        new_entry["1"]["2"] = 1
        new_entry["1"]["3"] = 8
    new_entry["3"] = str(progressbar_name)

    # patch record
    rec = new_entry.get("19", {}).get("1") if isinstance(new_entry.get("19"), dict) else None
    if not isinstance(rec, dict):
        raise RuntimeError("模板条目缺少 record（field_19/1）")
    # GIA 口径：record["501"] 为 int guid（同时 meta[?]/11/501 也要同步）
    set_gia_record_guid(rec, int(new_guid))
    _set_widget_name(rec, str(progressbar_name))
    _set_widget_parent_guid_field504(rec, int(layout_root_guid))

    # 写 RectTransform
    write_rect_states_from_web_rect(
        rec,
        web_left=float(web_left),
        web_top=float(web_top),
        web_width=float(web_width),
        web_height=float(web_height),
        reference_pc_canvas_size=(float(reference_pc_canvas_size[0]), float(reference_pc_canvas_size[1])),
        canvas_size_by_state_index={
            0: (float(reference_pc_canvas_size[0]), float(reference_pc_canvas_size[1])),
            1: (1280.0, 720.0),
            2: (1920.0, 1080.0),
            3: (1280.0, 720.0),
        },
    )

    # 若兜底选择的是 TextBox：写入可见文本，确保“新增控件”肉眼可见
    node19 = try_extract_textbox_text_node(rec)
    if isinstance(node19, dict):
        node505 = node19.get("505")
        if not isinstance(node505, dict):
            node505 = {}
            node19["505"] = node505
        node505["501"] = "████████████████████"
        # 字号稍大，避免被误判为空
        node19["502"] = 28

    # patch root display name
    msg["1"]["3"] = str(layout_name)

    # attach to root children list and entries list
    if "2" not in root_entry or not isinstance(root_entry.get("2"), list):
        root_entry["2"] = []
    root_entry["2"].append(_make_layout_asset_entry_id(int(new_guid)))
    _append_child_guid_to_record(parent_record=layout_root_record, child_guid=int(new_guid))
    entries.append(new_entry)

    # patch root path/version (保持 file_guid 段不动：若缺失则不改)
    msg["5"] = str(game_version or msg.get("5") or "6.3.0")

    safe_name = str(output_file_name or "").strip() or "layout_asset_test.gia"
    if not safe_name.lower().endswith(".gia"):
        safe_name = safe_name + ".gia"
    # 注意：若 msg["3"] 以 `<binary_data>` 形态保留（lossless），则字符串中不会包含 `-`，
    # 需要先解码为 UTF-8 文本再解析。
    path3_value = msg.get("3")
    path3_text = decode_entry_name(path3_value)
    if path3_text.count("-") >= 3:
        parts = path3_text.split("-", 3)
        if len(parts) == 4:
            prefix = parts[0]
            file_guid = parts[2]
            msg["3"] = f"{prefix}-{int(time.time())}-{file_guid}-\\{safe_name}"

    encoded = encode_message(msg)
    out_bytes = wrap_gia_container(encoded)
    output_path = resolve_output_file_path_in_out_dir(Path(output_gia_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(out_bytes)

    return {
        "output_gia_file": str(output_path),
        "base_gia_file": str(base_gia),
        "layout_root_guid": int(layout_root_guid),
        "added_guid": int(new_guid),
    }

