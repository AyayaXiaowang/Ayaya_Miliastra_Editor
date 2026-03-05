from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, List

from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map, encode_message, parse_binary_data_hex_text
from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import decoded_field_map_to_numeric_message
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.ui.readable_dump import (
    extract_primary_guid as _extract_primary_guid,
    extract_primary_name as _extract_primary_name,
    extract_ui_record_list as _extract_ui_record_list,
)

from ..shared import (
    DEFAULT_LIBRARY_ROOT_GUID,
    CreatedControlGroupTemplate,
    _GROUP_CONTAINER_META0,
    _GROUP_TEMPLATE_META12,
    _allocate_next_guid,
    _append_children_guids_to_parent_record,
    _collect_all_widget_guids,
    _decode_varint_stream,
    _dump_gil_to_raw_json_object,
    _encode_varint_stream,
    _find_record_by_guid,
    _force_record_to_group_container_shape,
    _get_children_guids_from_parent_record,
    _prepend_layout_root_guid_to_layout_registry,
    _replace_children_guids_in_parent_record,
    _set_children_guids_to_parent_record,
    _set_widget_guid,
    _set_widget_name,
    _set_widget_parent_guid_field504,
    _write_back_modified_gil_by_reencoding_payload,
    _build_group_meta13_template_ref,
    _build_meta_self_guid,
    _build_template_root_meta14_group_ref,
    format_binary_data_hex_text,
)
from .helpers import _assert_children_are_custom_placeable_controls, _extract_name_for_debug


def save_component_groups_as_custom_templates(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    component_group_guids: List[int],
    template_names: List[str],
    library_root_guid: int = DEFAULT_LIBRARY_ROOT_GUID,
    verify_with_dll_dump: bool = True,
) -> Dict[str, Any]:
    """
    一次性将“布局内组件组容器（纯组容器）”保存为“自定义模板”：

    - 读取每个 component_group_guid 的 children（必须为可放置控件：包含 RectTransform）
    - 将 children 克隆到控件组库根（library_root_guid）下，并打组为一个库内组容器
    - 将该库内组容器保存为模板（生成 template_root + template children，并写入双向 meta blob）

    用途：
    - Web UI 导出 `.gil` 时，用户可按需选择“同时沉淀按钮为自定义模板”。
    """
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    if not isinstance(component_group_guids, list) or not component_group_guids:
        raise ValueError("component_group_guids 不能为空")
    if not isinstance(template_names, list) or not template_names:
        raise ValueError("template_names 不能为空")
    if len(component_group_guids) != len(template_names):
        raise ValueError("component_group_guids 与 template_names 长度必须一致")

    normalized_group_guids = [int(g) for g in component_group_guids]
    if len(set(normalized_group_guids)) != len(normalized_group_guids):
        raise ValueError("component_group_guids 存在重复值")

    normalized_template_names: List[str] = []
    for name in template_names:
        n = str(name or "").strip()
        if n == "":
            raise ValueError("template_names 存在空名称")
        normalized_template_names.append(n)

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    ui_record_list = _extract_ui_record_list(raw_dump_object)
    existing_guids = _collect_all_widget_guids(ui_record_list)
    if not existing_guids:
        raise RuntimeError("无法收集现有 GUID（疑似 dump 结构异常）。")

    library_root_guid = int(library_root_guid)
    library_root_record = _find_record_by_guid(ui_record_list, int(library_root_guid))
    if library_root_record is None:
        raise RuntimeError(f"未找到 library_root_guid={int(library_root_guid)} 对应的 UI record。")

    reserved = set(int(g) for g in existing_guids)
    next_start = int(max(reserved)) + 1

    created: List[Dict[str, Any]] = []
    reused_existing: List[Dict[str, Any]] = []
    skipped_duplicate_request: List[Dict[str, Any]] = []
    repaired_invalid_existing: List[Dict[str, Any]] = []

    # 复用策略：
    # - 若 base `.gil` 中已存在同名“控件组模板 root”，则视为已沉淀，跳过创建（避免模板库膨胀与同名重复）。
    # - 同一次调用中若重复请求同名 template_name，仅处理第一次，其余记为 skipped（避免重复工作）。
    wanted_names = set(str(n or "").strip() for n in normalized_template_names if str(n or "").strip() != "")
    existing_template_root_guid_by_name: Dict[str, int] = {}
    if wanted_names:
        for rec in ui_record_list:
            if not isinstance(rec, dict):
                continue
            if "504" in rec:
                continue
            name_text = _extract_primary_name(rec)
            if not isinstance(name_text, str) or name_text.strip() == "":
                continue
            name_text = str(name_text).strip()
            if name_text not in wanted_names:
                continue
            meta_list = rec.get("502")
            if not isinstance(meta_list, list):
                continue
            has_template_marker = any(
                isinstance(m, dict)
                and m.get("12") == _GROUP_TEMPLATE_META12.get("12")
                and m.get("501") == _GROUP_TEMPLATE_META12.get("501")
                and m.get("502") == _GROUP_TEMPLATE_META12.get("502")
                for m in meta_list
            )
            if not has_template_marker:
                continue
            guid0 = _extract_primary_guid(rec)
            if guid0 is None or int(guid0) <= 0:
                continue
            existing_template_root_guid_by_name.setdefault(str(name_text), int(guid0))

    processed_names: set[str] = set()

    def _try_extract_template_root_group_guids(template_root_record: Dict[str, Any]) -> List[int]:
        meta_list = template_root_record.get("502")
        if not isinstance(meta_list, list):
            return []
        for m in meta_list:
            if not isinstance(m, dict):
                continue
            if m.get("501") == 4 and m.get("502") == 4:
                node14 = m.get("14")
                # 兼容：不同 dump 口径下，meta14 可能是：
                # - str: outer message bytes（样本写法：见 shared._build_template_root_meta14_group_ref）
                # - dict: 已展开/被转换过的形态（历史/第三方工具）
                if isinstance(node14, str):
                    if node14 != "" and not node14.startswith("<binary_data>"):
                        continue
                    outer_bytes = parse_binary_data_hex_text(node14) if node14 != "" else b""
                    field_map, consumed = decode_message_to_field_map(
                        data_bytes=outer_bytes,
                        start_offset=0,
                        end_offset=len(outer_bytes),
                        remaining_depth=8,
                    )
                    if consumed != len(outer_bytes):
                        continue
                    numeric = decoded_field_map_to_numeric_message(field_map)
                    inner = numeric.get("501")
                    if isinstance(inner, list):
                        inner = inner[0] if inner else ""
                    if not isinstance(inner, str) or (inner != "" and not inner.startswith("<binary_data>")):
                        continue
                    data_bytes = parse_binary_data_hex_text(inner) if inner != "" else b""
                    return [int(x) for x in _decode_varint_stream(data_bytes)]
                if isinstance(node14, dict):
                    raw = node14.get("501")
                    if not isinstance(raw, str) or (raw != "" and not raw.startswith("<binary_data>")):
                        continue
                    data_bytes = parse_binary_data_hex_text(raw) if raw != "" else b""
                    return [int(x) for x in _decode_varint_stream(data_bytes)]
        return []

    def _set_template_root_group_guids(template_root_record: Dict[str, Any], group_guids: List[int]) -> None:
        meta_list = template_root_record.get("502")
        if not isinstance(meta_list, list):
            raise ValueError("template_root_record 缺少 meta list(502)")

        # meta14 的 payload：outer message bytes，其中 field_501(wire_type=2) 存放 varint stream(group_guids)
        inner_stream_bytes = _encode_varint_stream([int(x) for x in group_guids])
        outer_bytes = encode_message({"501": format_binary_data_hex_text(inner_stream_bytes)})
        meta14_blob = format_binary_data_hex_text(outer_bytes)

        for m in meta_list:
            if not isinstance(m, dict):
                continue
            if m.get("501") == 4 and m.get("502") == 4:
                # 兼容：历史数据里 m['14'] 可能不是 str（甚至不是合法的 <binary_data>），
                # 这里直接规范化为样本一致的 blob 形态，避免“可见但使用为空白/乱码”。
                m["14"] = meta14_blob
                return
        # 兼容：少数存档可能缺失 meta14，直接补齐为样本形态
        meta_list.append({"14": meta14_blob, "501": 4, "502": 4})

    def _ensure_template_root_has_library_group(
        *,
        template_root_guid: int,
        template_name: str,
    ) -> Dict[str, Any]:
        """
        关键修复：
        - 真源样本中，template_root meta14 的 group_ref 必须至少包含一个“控件组库内的组容器 guid”（parent=library_root_guid）。
        - 若 meta14 仅指向布局内实例（parent=layout_guid），编辑器侧会出现“模板可见但使用为空白/乱码”的情况。
        - 本函数会在检测到“缺少库内 group”时自动修复：创建一个库内 group（克隆 template_root children）并写回 meta14。
        """
        nonlocal next_start

        tpl_root = _find_record_by_guid(ui_record_list, int(template_root_guid))
        if tpl_root is None:
            raise RuntimeError(f"未找到 template_root_guid={int(template_root_guid)} 对应的 UI record。")
        if "504" in tpl_root:
            raise ValueError("template_root_record 不应包含 parent(504)")

        group_guids = _try_extract_template_root_group_guids(tpl_root)
        # 判断是否已有“库内 group”
        has_library_group = False
        for gg in group_guids:
            gr = _find_record_by_guid(ui_record_list, int(gg))
            if gr is None:
                continue
            parent = gr.get("504")
            if isinstance(parent, int) and int(parent) == int(library_root_guid):
                has_library_group = True
                break
        if has_library_group:
            return {"repaired": False, "reason": "ok_already_has_library_group"}

        # 读取 template_root children，并克隆到库内 group 下
        tpl_child_guids = _get_children_guids_from_parent_record(tpl_root)
        if not tpl_child_guids:
            raise ValueError("template_root children 为空，无法修复为可用模板。")
        tpl_child_records: List[Dict[str, Any]] = []
        for cg in tpl_child_guids:
            rec = _find_record_by_guid(ui_record_list, int(cg))
            if rec is None:
                raise RuntimeError(f"template_root child guid={int(cg)} 未找到对应 record。")
            tpl_child_records.append(rec)
        _assert_children_are_custom_placeable_controls(
            child_records=tpl_child_records,
            context="repair_template_root_library_group",
        )
        for rec in tpl_child_records:
            if _get_children_guids_from_parent_record(rec):
                raise ValueError(
                    "当前不支持修复“template_root children 带 children 的控件 record”（需要克隆整棵子树并重写引用）；"
                    f"record_name={_extract_name_for_debug(rec)!r}"
                )

        new_library_group_guid = _allocate_next_guid(reserved, start=next_start)
        reserved.add(int(new_library_group_guid))
        local_next_start = int(new_library_group_guid) + 1

        cloned_child_records: List[Dict[str, Any]] = []
        cloned_child_guids: List[int] = []
        for src in tpl_child_records:
            new_child_guid = _allocate_next_guid(reserved, start=local_next_start)
            reserved.add(int(new_child_guid))
            local_next_start = int(new_child_guid) + 1
            cloned = copy.deepcopy(src)
            _set_widget_guid(cloned, int(new_child_guid))
            _set_widget_parent_guid_field504(cloned, int(new_library_group_guid))
            cloned_child_records.append(cloned)
            cloned_child_guids.append(int(new_child_guid))

        # 新建库内 group record（强制为组容器形态）
        new_group_record = copy.deepcopy(library_root_record)
        _set_widget_guid(new_group_record, int(new_library_group_guid))
        _set_widget_parent_guid_field504(new_group_record, int(library_root_guid))
        component_list = new_group_record.get("505")
        if not isinstance(component_list, list) or not component_list:
            raise ValueError("record missing component list at field 505")
        name_component = component_list[0]
        if not isinstance(name_component, dict):
            raise ValueError("record field 505[0] must be dict")
        name_component["12"] = {"501": str(template_name)}
        _set_children_guids_to_parent_record(new_group_record, [int(g) for g in cloned_child_guids])
        _force_record_to_group_container_shape(new_group_record)
        # 写入模板指针（meta13）+ marker（meta12），确保编辑器识别为模板关联组
        new_group_record["502"] = [
            copy.deepcopy(_GROUP_CONTAINER_META0),
            _build_meta_self_guid(int(new_library_group_guid)),
            dict(_GROUP_TEMPLATE_META12),
            _build_group_meta13_template_ref(int(template_root_guid)),
        ]

        # 写回到 record list + library_root children
        ui_record_list.extend(cloned_child_records)
        ui_record_list.append(new_group_record)
        _append_children_guids_to_parent_record(library_root_record, [int(new_library_group_guid)])

        # 更新 template_root meta14：确保包含库内 group（放在列表头部，保持顺序稳定）
        new_group_guids = [int(new_library_group_guid)] + [
            int(x) for x in group_guids if int(x) != int(new_library_group_guid)
        ]
        _set_template_root_group_guids(tpl_root, new_group_guids)
        _prepend_layout_root_guid_to_layout_registry(raw_dump_object, int(template_root_guid))

        # 让 next_start 向前推进，避免后续分配撞上我们新建的 guid
        next_start = max(next_start, local_next_start)

        return {
            "repaired": True,
            "reason": "fixed_missing_library_group_ref_in_template_root_meta14",
            "template_root_guid": int(template_root_guid),
            "created_library_group_guid": int(new_library_group_guid),
            "created_library_group_children_total": int(len(cloned_child_guids)),
        }

    for source_group_guid, template_name in zip(normalized_group_guids, normalized_template_names, strict=True):
        if template_name in processed_names:
            skipped_duplicate_request.append(
                {
                    "source_component_group_guid": int(source_group_guid),
                    "template_name": str(template_name),
                    "reason": "duplicate_template_name_in_same_request",
                }
            )
            continue
        processed_names.add(str(template_name))

        existing_tpl_root = existing_template_root_guid_by_name.get(str(template_name))
        if isinstance(existing_tpl_root, int) and int(existing_tpl_root) > 0:
            repair_report = _ensure_template_root_has_library_group(
                template_root_guid=int(existing_tpl_root),
                template_name=str(template_name),
            )
            if bool(repair_report.get("repaired")):
                repaired_invalid_existing.append(
                    {
                        "source_component_group_guid": int(source_group_guid),
                        "template_name": str(template_name),
                        "template_root_guid": int(existing_tpl_root),
                        "reason": "base_gil_has_same_name_template_root_but_invalid_repaired",
                        "repair": dict(repair_report),
                    }
                )
            else:
                reused_existing.append(
                    {
                        "source_component_group_guid": int(source_group_guid),
                        "template_name": str(template_name),
                        "template_root_guid": int(existing_tpl_root),
                        "reason": "base_gil_already_has_same_name_template_root",
                    }
                )
            continue

        # 1) 从布局内组件组读取 children（必须为可放置控件）
        source_group_record = _find_record_by_guid(ui_record_list, int(source_group_guid))
        if source_group_record is None:
            raise RuntimeError(f"未找到 component_group_guid={int(source_group_guid)} 对应的 UI record。")
        source_child_guids = _get_children_guids_from_parent_record(source_group_record)
        if not source_child_guids:
            raise ValueError(f"component_group_guid={int(source_group_guid)} 的 children 为空，无法保存为模板。")

        source_child_records: List[Dict[str, Any]] = []
        for child_guid in source_child_guids:
            rec = _find_record_by_guid(ui_record_list, int(child_guid))
            if rec is None:
                raise RuntimeError(f"component_group child guid={int(child_guid)} 未找到对应 record。")
            source_child_records.append(rec)

        _assert_children_are_custom_placeable_controls(
            child_records=source_child_records,
            context="save_component_groups_as_custom_templates",
        )

        # 2) clone children 到控件组库根下
        cloned_child_guids: List[int] = []
        cloned_child_records: List[Dict[str, Any]] = []
        for src in source_child_records:
            if _get_children_guids_from_parent_record(src):
                raise ValueError(
                    "当前不支持克隆“带 children 的控件 record”（需要克隆整棵子树并重写引用）；"
                    f"请先确保组件组 children 均为叶子控件。record_name={_extract_name_for_debug(src)!r}"
                )
            new_guid = _allocate_next_guid(reserved, start=next_start)
            reserved.add(int(new_guid))
            next_start = int(new_guid) + 1

            cloned = copy.deepcopy(src)
            _set_widget_guid(cloned, int(new_guid))
            _set_widget_parent_guid_field504(cloned, int(library_root_guid))
            cloned_child_guids.append(int(new_guid))
            cloned_child_records.append(cloned)

        ui_record_list.extend(cloned_child_records)
        _append_children_guids_to_parent_record(library_root_record, [int(g) for g in cloned_child_guids])

        # 3) 在控件组库根下打组（库内组容器）
        library_group_guid = _allocate_next_guid(reserved, start=next_start)
        reserved.add(int(library_group_guid))
        next_start = int(library_group_guid) + 1

        library_group_record = copy.deepcopy(library_root_record)
        _set_widget_guid(library_group_record, int(library_group_guid))
        _set_widget_parent_guid_field504(library_group_record, int(library_root_guid))
        # 兼容：库根/根容器可能是 binary name；这里确保写入 dict 名称
        component_list = library_group_record.get("505")
        if not isinstance(component_list, list) or not component_list:
            raise ValueError("record missing component list at field 505")
        name_component = component_list[0]
        if not isinstance(name_component, dict):
            raise ValueError("record field 505[0] must be dict")
        name_component["12"] = {"501": str(template_name)}
        _set_children_guids_to_parent_record(library_group_record, [int(g) for g in cloned_child_guids])
        _force_record_to_group_container_shape(library_group_record)

        _replace_children_guids_in_parent_record(
            library_root_record,
            remove_child_guids=[int(g) for g in cloned_child_guids],
            insert_child_guids=[int(library_group_guid)],
        )
        for child_record in cloned_child_records:
            _set_widget_parent_guid_field504(child_record, int(library_group_guid))

        ui_record_list.append(library_group_record)

        # 4) 将库内组容器保存为模板（生成 template_root + template children，并写入双向引用）
        group_record = library_group_record
        group_children = _get_children_guids_from_parent_record(group_record)
        if not group_children:
            raise RuntimeError("internal error: library group children is empty")

        group_child_records: List[Dict[str, Any]] = []
        for g in group_children:
            rec = _find_record_by_guid(ui_record_list, int(g))
            if rec is None:
                raise RuntimeError(f"group child guid={int(g)} 未找到对应 record。")
            group_child_records.append(rec)

        _assert_children_are_custom_placeable_controls(
            child_records=group_child_records,
            context="save_component_groups_as_custom_templates(save_control_group_as_template)",
        )

        template_root_guid = _allocate_next_guid(reserved, start=next_start)
        reserved.add(int(template_root_guid))
        next_start = int(template_root_guid) + 1

        template_child_guids: List[int] = []
        for _ in group_children:
            new_child_guid = _allocate_next_guid(reserved, start=next_start)
            reserved.add(int(new_child_guid))
            next_start = int(new_child_guid) + 1
            template_child_guids.append(int(new_child_guid))

        template_root_record = copy.deepcopy(group_record)
        _set_widget_guid(template_root_record, int(template_root_guid))
        # 模板 root：无 parent
        if "504" in template_root_record:
            del template_root_record["504"]
        _set_children_guids_to_parent_record(template_root_record, [int(g) for g in template_child_guids])
        _force_record_to_group_container_shape(template_root_record)
        template_root_record["502"] = [
            _build_meta_self_guid(int(template_root_guid)),
            dict(_GROUP_TEMPLATE_META12),
            _build_template_root_meta14_group_ref(int(library_group_guid)),
            copy.deepcopy(_GROUP_CONTAINER_META0),
        ]

        template_child_records: List[Dict[str, Any]] = []
        for src_child_record, new_child_guid in zip(group_child_records, template_child_guids, strict=True):
            cloned = copy.deepcopy(src_child_record)
            _set_widget_guid(cloned, int(new_child_guid))
            _set_widget_parent_guid_field504(cloned, int(template_root_guid))
            template_child_records.append(cloned)

        # group_record 写入模板指针（meta13）并同步名称
        _force_record_to_group_container_shape(group_record)
        group_record["502"] = [
            copy.deepcopy(_GROUP_CONTAINER_META0),
            _build_meta_self_guid(int(library_group_guid)),
            dict(_GROUP_TEMPLATE_META12),
            _build_group_meta13_template_ref(int(template_root_guid)),
        ]

        _prepend_layout_root_guid_to_layout_registry(raw_dump_object, int(template_root_guid))

        # 样本中模板 root 位于 record_list 开头：保持一致
        ui_record_list[:0] = [template_root_record, *template_child_records]

        created.append(
            {
                "source_component_group_guid": int(source_group_guid),
                "created_library_group_guid": int(library_group_guid),
                "template_root_guid": int(template_root_guid),
                "template_name": str(template_name),
                "template_children_guids_total": int(len(template_child_guids)),
            }
        )
        # 创建后立刻做一次“库内 group ref”一致性校验与修复（应当是 noop，但可兜底避免异常基底导致不可用模板）
        repair_report = _ensure_template_root_has_library_group(
            template_root_guid=int(template_root_guid),
            template_name=str(template_name),
        )
        if bool(repair_report.get("repaired")):
            repaired_invalid_existing.append(
                {
                    "source_component_group_guid": int(source_group_guid),
                    "template_name": str(template_name),
                    "template_root_guid": int(template_root_guid),
                    "reason": "new_template_root_missing_library_group_ref_repaired",
                    "repair": dict(repair_report),
                }
            )

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_path,
        output_gil_path=output_path,
    )

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "library_root_guid": int(library_root_guid),
        "created_total": int(len(created)),
        "created": created,
        "reused_existing_total": int(len(reused_existing)),
        "reused_existing": reused_existing,
        "skipped_duplicate_request_total": int(len(skipped_duplicate_request)),
        "skipped_duplicate_request": skipped_duplicate_request,
        "repaired_invalid_existing_total": int(len(repaired_invalid_existing)),
        "repaired_invalid_existing": repaired_invalid_existing,
    }

    if verify_with_dll_dump:
        verify_dump = _dump_gil_to_raw_json_object(output_path)
        verify_ui_records = _extract_ui_record_list(verify_dump)
        ok = True
        for item in created:
            tpl_guid = int(item.get("template_root_guid") or 0)
            lib_group_guid = int(item.get("created_library_group_guid") or 0)
            if tpl_guid <= 0 or lib_group_guid <= 0:
                ok = False
                continue
            if _find_record_by_guid(verify_ui_records, int(tpl_guid)) is None:
                ok = False
            if _find_record_by_guid(verify_ui_records, int(lib_group_guid)) is None:
                ok = False
        for item in reused_existing:
            tpl_guid = int(item.get("template_root_guid") or 0)
            if tpl_guid <= 0:
                ok = False
                continue
            if _find_record_by_guid(verify_ui_records, int(tpl_guid)) is None:
                ok = False
        report["verify"] = {"ok": bool(ok), "ui_record_total": int(len(verify_ui_records))}

    return report


def save_control_group_as_template(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    library_root_guid: int = DEFAULT_LIBRARY_ROOT_GUID,
    group_guid: int,
    template_name: str,
    verify_with_dll_dump: bool = True,
) -> Dict[str, Any]:
    """
    将控件组库内的某个“组容器”保存为模板：
    - 在 layout registry（`4/9/501[0]`）新增一个“模板 root”（无 parent，含 children）
    - 组容器 record 写入 template 指针（meta 13: field_501=template_root_guid）
    - 模板 root record 写入 group 反向指针（meta 14: field_501(bytes)=group_guid_varint）
    """
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    template_name = str(template_name or "").strip()
    if template_name == "":
        raise ValueError("template_name 不能为空")

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    ui_record_list = _extract_ui_record_list(raw_dump_object)

    existing_guids = _collect_all_widget_guids(ui_record_list)
    if not existing_guids:
        raise RuntimeError("无法收集现有 GUID（疑似 dump 结构异常）。")

    library_root_guid = int(library_root_guid)
    library_root_record = _find_record_by_guid(ui_record_list, int(library_root_guid))
    if library_root_record is None:
        raise RuntimeError(f"未找到 library_root_guid={int(library_root_guid)} 对应的 UI record。")

    group_guid = int(group_guid)
    group_record = _find_record_by_guid(ui_record_list, int(group_guid))
    if group_record is None:
        raise RuntimeError(f"未找到 group_guid={int(group_guid)} 对应的 UI record。")
    if int(group_record.get("504") or 0) != int(library_root_guid):
        raise ValueError("group_record 的 parent(504) 不是 library_root_guid，当前实现仅支持库内组保存为模板。")

    group_children = _get_children_guids_from_parent_record(group_record)
    if not group_children:
        raise ValueError("group_record 的 children 为空，无法保存为模板。")

    group_child_records: List[Dict[str, Any]] = []
    for src_child_guid in group_children:
        src_child_record = _find_record_by_guid(ui_record_list, int(src_child_guid))
        if src_child_record is None:
            raise RuntimeError(f"group child guid={int(src_child_guid)} 未找到对应 record。")
        group_child_records.append(src_child_record)

    _assert_children_are_custom_placeable_controls(
        child_records=group_child_records,
        context="save_control_group_as_template",
    )

    reserved = set(existing_guids)
    template_root_guid = _allocate_next_guid(reserved, start=max(reserved) + 1)
    reserved.add(int(template_root_guid))

    cloned_child_guids: List[int] = []
    next_start = int(template_root_guid) + 1
    for _ in group_children:
        new_guid = _allocate_next_guid(reserved, start=next_start)
        reserved.add(int(new_guid))
        next_start = int(new_guid) + 1
        cloned_child_guids.append(int(new_guid))

    # 1) 生成模板 root：clone group_record，但移除 parent；children 指向 cloned_child_guids；meta 改为模板 root 形态
    template_root_record = copy.deepcopy(group_record)
    _set_widget_guid(template_root_record, int(template_root_guid))
    _set_widget_name(template_root_record, template_name)
    if "504" in template_root_record:
        del template_root_record["504"]
    _set_children_guids_to_parent_record(template_root_record, [int(g) for g in cloned_child_guids])
    _force_record_to_group_container_shape(template_root_record)
    template_root_record["502"] = [
        _build_meta_self_guid(int(template_root_guid)),
        dict(_GROUP_TEMPLATE_META12),
        _build_template_root_meta14_group_ref(int(group_guid)),
        copy.deepcopy(_GROUP_CONTAINER_META0),
    ]

    # 2) 克隆 children 到模板 root 下（保持原 name/配置；只改 guid/parent）
    cloned_child_records: List[Dict[str, Any]] = []
    for src_child_record, new_child_guid in zip(group_child_records, cloned_child_guids, strict=True):
        cloned = copy.deepcopy(src_child_record)
        _set_widget_guid(cloned, int(new_child_guid))
        _set_widget_parent_guid_field504(cloned, int(template_root_guid))
        cloned_child_records.append(cloned)

    # 3) 更新 group_record：名称改为 template_name；meta 写入模板指针（13）与 marker（12）
    _set_widget_name(group_record, template_name)
    _force_record_to_group_container_shape(group_record)
    group_record["502"] = [
        copy.deepcopy(_GROUP_CONTAINER_META0),
        _build_meta_self_guid(int(group_guid)),
        dict(_GROUP_TEMPLATE_META12),
        _build_group_meta13_template_ref(int(template_root_guid)),
    ]

    # 4) 将模板 root 注册到 layout registry（插到开头；末尾的 library_root_guid 保持在最后）
    _prepend_layout_root_guid_to_layout_registry(raw_dump_object, int(template_root_guid))

    # 5) 写回 record_list：样本中模板 root 位于 record_list 开头，这里也保持一致（先插入 root 与 children，再保留原列表顺序）
    ui_record_list[:0] = [template_root_record, *cloned_child_records]

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_path,
        output_gil_path=output_path,
    )

    created_template = CreatedControlGroupTemplate(
        group_guid=int(group_guid),
        template_root_guid=int(template_root_guid),
        name=template_name,
        cloned_child_guids=tuple(int(g) for g in cloned_child_guids),
    )

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "group_guid": created_template.group_guid,
        "template_root_guid": created_template.template_root_guid,
        "template_name": created_template.name,
        "template_children_guids": list(created_template.cloned_child_guids),
    }

    if verify_with_dll_dump:
        verify_dump = _dump_gil_to_raw_json_object(output_path)
        verify_ui_records = _extract_ui_record_list(verify_dump)
        verify_group = _find_record_by_guid(verify_ui_records, int(group_guid))
        verify_template_root = _find_record_by_guid(verify_ui_records, int(template_root_guid))
        report["verify"] = {
            "ui_record_total": len(verify_ui_records),
            "group_exists": verify_group is not None,
            "template_root_exists": verify_template_root is not None,
            "template_root_children": (
                _get_children_guids_from_parent_record(verify_template_root) if verify_template_root is not None else None
            ),
            "template_children_parent_ok": all(
                (_find_record_by_guid(verify_ui_records, int(g)) or {}).get("504") == int(template_root_guid)
                for g in cloned_child_guids
            ),
        }

    return report


__all__ = [
    "save_component_groups_as_custom_templates",
    "save_control_group_as_template",
]

