from __future__ import annotations

from typing import Any, Dict, List, Optional

from ugc_file_tools.ui.readable_dump import extract_ui_record_list as _extract_ui_record_list

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    dump_gil_to_raw_json_object as _dump_gil_to_raw_json_object,
    find_record_by_guid as _find_record_by_guid,
    get_children_guids_from_parent_record as _get_children_guids_from_parent_record,
)
from .web_ui_import_types import ImportedWebItemDisplay, ImportedWebProgressbar, ImportedWebTextbox
from ugc_file_tools.custom_variables.apply import find_root4_5_1_entry_by_name
from .web_ui_import_visibility import try_get_record_visibility_flag


def verify_import_result_with_dll_dump(
    *,
    output_gil_path,
    layout_guid: int,
    imported_progressbars: List[ImportedWebProgressbar],
    imported_textboxes: List[ImportedWebTextbox],
    imported_item_displays: List[ImportedWebItemDisplay],
    created_custom_variables_report: Dict[str, Any],
) -> Dict[str, Any]:
    verify_dump = _dump_gil_to_raw_json_object(output_gil_path)
    verify_ui_records = _extract_ui_record_list(verify_dump)
    created_ok = True
    for item in imported_progressbars:
        if _find_record_by_guid(verify_ui_records, int(item.guid)) is None:
            created_ok = False
            break
    for item in imported_textboxes:
        if _find_record_by_guid(verify_ui_records, int(item.guid)) is None:
            created_ok = False
            break
    for item in imported_item_displays:
        if _find_record_by_guid(verify_ui_records, int(item.guid)) is None:
            created_ok = False
            break

    out: Dict[str, Any] = {
        "ui_record_total": int(len(verify_ui_records)),
        "imported_progressbar_guids_exist": bool(created_ok),
        "imported_textbox_guids_exist": bool(created_ok),
        "imported_item_display_guids_exist": bool(created_ok),
    }

    # --- 可见性校验：检查 record 的可见性标志是否符合输入 JSON 的 initial_visible
    visibility_ok = True
    visibility_mismatches: List[Dict[str, Any]] = []

    def _check_one(guid: int, ui_key: str, expected_visible: bool) -> None:
        nonlocal visibility_ok
        rec = _find_record_by_guid(verify_ui_records, int(guid))
        if not isinstance(rec, dict):
            visibility_ok = False
            visibility_mismatches.append(
                {"guid": int(guid), "ui_key": str(ui_key), "expected_visible": bool(expected_visible), "reason": "record_not_found"}
            )
            return
        flag = try_get_record_visibility_flag(rec)
        if flag is None:
            # 组容器等“非控件 record”可能没有该字段；此处仅记录为 info，不判失败。
            visibility_mismatches.append(
                {
                    "guid": int(guid),
                    "ui_key": str(ui_key),
                    "expected_visible": bool(expected_visible),
                    "actual_flag": None,
                    "reason": "visibility_flag_not_found",
                }
            )
            return
        expected_flag = 1 if bool(expected_visible) else 0
        if int(flag) != int(expected_flag):
            visibility_ok = False
            visibility_mismatches.append(
                {
                    "guid": int(guid),
                    "ui_key": str(ui_key),
                    "expected_visible": bool(expected_visible),
                    "expected_flag": int(expected_flag),
                    "actual_flag": int(flag),
                    "reason": "visibility_flag_mismatch",
                }
            )

    for item in imported_progressbars:
        _check_one(int(item.guid), str(item.ui_key), bool(item.initial_visible))
    for item in imported_textboxes:
        _check_one(int(item.guid), str(item.ui_key), bool(item.initial_visible))
    for item in imported_item_displays:
        _check_one(int(item.guid), str(item.ui_key), bool(item.initial_visible))

    out["visibility"] = {
        "ok": bool(visibility_ok),
        "mismatches_total": int(len([m for m in visibility_mismatches if m.get("reason") != "visibility_flag_not_found"])),
        "samples": visibility_mismatches[:80],
        "note": "visible flag 口径（对齐真源）：component_list[*]['503']['14']['502'] 缺失=可见；=1 表示隐藏（因此 visible_flag: visible=1/hidden=0）。",
    }

    # --- 结构校验：确保导入的控件“挂在树上”（避免写入成功但运行时不展示）
    if isinstance(verify_ui_records, list):
        record_by_guid_verify: Dict[int, Dict[str, Any]] = {}
        for rec in verify_ui_records:
            if not isinstance(rec, dict):
                continue
            guid_value = rec.get("501")
            if isinstance(guid_value, int):
                record_by_guid_verify[int(guid_value)] = rec

        def safe_children_guids(rec: Dict[str, Any]) -> List[int]:
            field503 = rec.get("503")
            # None 表示无 children
            if field503 is None:
                return []
            # 兼容：repeated 字段可能是 str 或 list[str]
            if isinstance(field503, str):
                return _get_children_guids_from_parent_record(rec)
            if isinstance(field503, list) and field503:
                first = field503[0]
                if isinstance(first, str):
                    return _get_children_guids_from_parent_record(rec)
            return []

        reachable: set[int] = set()
        parent_mismatch_edges: List[Dict[str, Any]] = []
        stack: List[int] = [int(layout_guid)]
        while stack:
            current = int(stack.pop())
            if current in reachable:
                continue
            reachable.add(current)
            rec = record_by_guid_verify.get(current)
            if not isinstance(rec, dict):
                continue
            for child_guid in safe_children_guids(rec):
                child_guid_int = int(child_guid)
                child_rec = record_by_guid_verify.get(child_guid_int)
                if isinstance(child_rec, dict):
                    parent_value = child_rec.get("504")
                    if isinstance(parent_value, int) and int(parent_value) != current:
                        parent_mismatch_edges.append(
                            {"parent_guid": current, "child_guid": child_guid_int, "child_parent_field504": int(parent_value)}
                        )
                stack.append(child_guid_int)

        imported_widget_guid_to_keys: Dict[int, List[str]] = {}
        imported_widget_guids: List[int] = []
        for item in imported_progressbars:
            imported_widget_guids.append(int(item.guid))
            imported_widget_guid_to_keys.setdefault(int(item.guid), []).append(str(item.ui_key))
        for item in imported_textboxes:
            imported_widget_guids.append(int(item.guid))
            imported_widget_guid_to_keys.setdefault(int(item.guid), []).append(str(item.ui_key))
        for item in imported_item_displays:
            imported_widget_guids.append(int(item.guid))
            imported_widget_guid_to_keys.setdefault(int(item.guid), []).append(str(item.ui_key))

        duplicated_imported_guids = [
            {"guid": int(g), "ui_keys": sorted(set(keys))}
            for g, keys in imported_widget_guid_to_keys.items()
            if len(set(keys)) >= 2
        ]

        unreachable_imported = [int(g) for g in sorted(set(imported_widget_guids)) if int(g) not in reachable]
        unreachable_samples: List[Dict[str, Any]] = []
        for g in unreachable_imported[:50]:
            rec = record_by_guid_verify.get(int(g))
            parent_field504: Optional[int] = None
            if isinstance(rec, dict):
                parent_raw = rec.get("504")
                if isinstance(parent_raw, int):
                    parent_field504 = int(parent_raw)
            unreachable_samples.append(
                {
                    "guid": int(g),
                    "ui_keys": sorted(set(imported_widget_guid_to_keys.get(int(g), []))),
                    "has_record": bool(isinstance(rec, dict)),
                    "parent_field504": parent_field504,
                }
            )

        out["tree"] = {
            "reachable_total": int(len(reachable)),
            "imported_widgets_total": int(len(set(imported_widget_guids))),
            "unreachable_imported_total": int(len(unreachable_imported)),
            "unreachable_imported_samples": unreachable_samples,
            "parent_mismatch_edges_total": int(len(parent_mismatch_edges)),
            "parent_mismatch_edges_samples": parent_mismatch_edges[:50],
            "duplicate_guid_across_widgets_total": int(len(duplicated_imported_guids)),
            "duplicate_guid_across_widgets_samples": duplicated_imported_guids[:50],
        }

    # 额外校验：若本次导入创建了“进度条变量”，确保目标实体条目里确实出现对应变量名
    try_verify_vars = created_custom_variables_report.get("variables") if isinstance(created_custom_variables_report, dict) else None
    if isinstance(try_verify_vars, list) and try_verify_vars:
        root4_verify = verify_dump.get("4")
        section5_verify = root4_verify.get("5") if isinstance(root4_verify, dict) else None
        entry_list_verify = section5_verify.get("1") if isinstance(section5_verify, dict) else None

        vars_ok = True
        missing_vars: List[Dict[str, Any]] = []
        if isinstance(entry_list_verify, list):
            for var_item in try_verify_vars:
                if not isinstance(var_item, dict):
                    continue
                target_entity_name = str(var_item.get("target_entity_name") or "").strip()
                var_name = str(var_item.get("variable_name") or "").strip()
                group_name = str(var_item.get("group") or "").strip()
                if target_entity_name == "" or var_name == "":
                    continue

                target_entry = find_root4_5_1_entry_by_name(entry_list_verify, target_entity_name)
                if target_entry is None:
                    vars_ok = False
                    missing_vars.append(
                        {
                            "group": group_name,
                            "target_entity_name": target_entity_name,
                            "variable_name": var_name,
                            "reason": "target_entity_not_found",
                        }
                    )
                    continue

                found = False
                group_list = target_entry.get("7")
                if isinstance(group_list, list):
                    for group_item in group_list:
                        if not isinstance(group_item, dict):
                            continue
                        if group_item.get("1") != 1 or group_item.get("2") != 1:
                            continue
                        container = group_item.get("11")
                        if not isinstance(container, dict):
                            continue
                        items = container.get("1")
                        if isinstance(items, dict):
                            items = [items]
                        if not isinstance(items, list):
                            continue
                        for v in items:
                            if not isinstance(v, dict):
                                continue
                            if str(v.get("2") or "").strip() == var_name:
                                found = True
                                break
                        if found:
                            break

                if not found:
                    vars_ok = False
                    missing_vars.append(
                        {
                            "group": group_name,
                            "target_entity_name": target_entity_name,
                            "variable_name": var_name,
                            "reason": "variable_not_found",
                        }
                    )

        out["progressbar_custom_variables_exist"] = bool(vars_ok)
        out["missing_progressbar_custom_variables"] = missing_vars

    return out

