from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .claude_files import _ensure_claude_for_directory
from .file_io import _ensure_directory, _sanitize_filename, _write_json_file


def _is_control_group_template_root(record: Dict[str, Any]) -> bool:
    """
    经验性识别“控件组模板 root”（来自 save-control-group-as-template 的样本）：
    - root record（无 parent=504）
    - meta 列表（502）中包含 meta14（key="14"）
    """
    if not isinstance(record, dict):
        return False
    if "504" in record:
        return False
    meta_list = record.get("502")
    if not isinstance(meta_list, list):
        return False
    for meta in meta_list:
        if isinstance(meta, dict) and "14" in meta:
            return True
    return False


def _extract_children_guid_list_from_record(record: Dict[str, Any]) -> List[int]:
    from ugc_file_tools.gil_dump_codec.protobuf_like import parse_binary_data_hex_text

    field503 = record.get("503")
    if not isinstance(field503, list) or not field503:
        return []
    first = field503[0]
    if not isinstance(first, str) or not first.startswith("<binary_data>"):
        return []
    data = parse_binary_data_hex_text(first)
    return _decode_varint_stream(data)


def _decode_varint(data: bytes, offset: int) -> tuple[int, int, bool]:
    value = 0
    shift_bits = 0
    current_offset = offset
    while True:
        if current_offset >= len(data):
            return 0, current_offset, False
        current_byte = data[current_offset]
        current_offset += 1
        value |= (current_byte & 0x7F) << shift_bits
        if (current_byte & 0x80) == 0:
            return value, current_offset, True
        shift_bits += 7
        if shift_bits >= 64:
            return 0, current_offset, False


def _decode_varint_stream(data: bytes) -> List[int]:
    values: List[int] = []
    offset = 0
    end_offset = len(data)
    while offset < end_offset:
        value, offset, ok = _decode_varint(data, offset)
        if not ok:
            raise ValueError("invalid varint stream")
        values.append(int(value))
    return values


def _export_ui_widget_templates_from_dll_dump(
    dll_dump_object: Dict[str, Any],
    output_package_root: Path,
) -> List[Dict[str, Any]]:
    """
    从 DLL dump-json（数值键结构）中提取“控件组模板 root + children”，导出为项目存档资源：
    - 管理配置/UI控件模板/*.json（ResourceType.UI_WIDGET_TEMPLATE）
    - 管理配置/UI控件模板/原始解析/*.raw.json（用于写回/追溯）

    注意：当前只覆盖“保存控件组为模板”的模板 root 形态（meta14），不尝试穷举所有 UI 控件。
    """
    from ugc_file_tools.ui_parsers.item_displays import build_item_display_dump
    from ugc_file_tools.ui_parsers.layouts import build_layout_dump
    from ugc_file_tools.ui.readable_dump import (
        extract_primary_guid as _extract_primary_guid,
        extract_primary_name as _extract_primary_name,
        extract_ui_record_list as _extract_ui_record_list,
    )

    ui_record_list = _extract_ui_record_list(dll_dump_object)
    guid_to_record: Dict[int, Dict[str, Any]] = {}
    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        guid_value = _extract_primary_guid(record)
        if isinstance(guid_value, int):
            guid_to_record[int(guid_value)] = record

    # 先解析一次“道具展示”控件，供后续按 template children guid 关联到 widgets 列表。
    item_display_dump = build_item_display_dump(
        dll_dump_object,
        canvas_size=(1600.0, 900.0),
        include_raw_binding_blob_hex=False,
    )
    item_displays_by_guid_obj = item_display_dump.get("item_displays_by_guid")
    item_displays_by_guid: Dict[int, Any] = (
        {int(k): v for k, v in item_displays_by_guid_obj.items() if isinstance(k, int)}
        if isinstance(item_displays_by_guid_obj, dict)
        else {}
    )

    layout_dump = build_layout_dump(dll_dump_object)
    registry_guids = layout_dump.get("layout_registry_guids", [])
    library_root_guid = layout_dump.get("library_root_guid")

    normalized_registry: List[int] = []
    if isinstance(registry_guids, list):
        normalized_registry = [int(v) for v in registry_guids if isinstance(v, int)]

    excluded: set[int] = set()
    if isinstance(library_root_guid, int):
        excluded.add(int(library_root_guid))

    template_root_guids: List[int] = []
    for guid in normalized_registry:
        if int(guid) in excluded:
            continue
        record = guid_to_record.get(int(guid))
        if record is None:
            continue
        if _is_control_group_template_root(record):
            template_root_guids.append(int(guid))

    template_directory = output_package_root / "管理配置" / "UI控件模板"
    template_raw_directory = template_directory / "原始解析"
    _ensure_directory(template_raw_directory)
    _ensure_claude_for_directory(
        template_raw_directory,
        purpose="存放从 DLL dump-json 中提取的 UI 控件模板原始结构（template root + children records），用于写回与追溯。",
    )

    exported: List[Dict[str, Any]] = []

    def _normalize_variable_full_name(variable_obj: Any) -> str:
        if isinstance(variable_obj, dict):
            full_name = variable_obj.get("full_name")
            if isinstance(full_name, str) and full_name.strip() != "":
                return str(full_name).strip()
        return "."

    def _build_item_display_widget_payload(*, widget_index: int, item_display_obj: Dict[str, Any]) -> Dict[str, Any]:
        item_display = item_display_obj.get("item_display")
        if not isinstance(item_display, dict):
            raise ValueError("invalid item_display obj: missing item_display")

        display_type = item_display.get("display_type")
        display_type_name = display_type.get("name") if isinstance(display_type, dict) else None
        display_type_name = str(display_type_name or "").strip() or "玩家当前装备"

        kbm = item_display.get("keybind_kbm")
        pad = item_display.get("keybind_gamepad")
        kbm_code = kbm.get("code") if isinstance(kbm, dict) else None
        pad_code = pad.get("code") if isinstance(pad, dict) else None

        no_equipment_behavior = item_display.get("no_equipment_behavior")
        no_equipment_behavior_code = no_equipment_behavior.get("code") if isinstance(no_equipment_behavior, dict) else None

        show_quantity = item_display.get("show_quantity")
        hide_when_zero = item_display.get("hide_when_zero")

        # 位置/尺寸：用于主程序预览；缺失则填 0。
        canvas_pos = item_display_obj.get("canvas_position")
        x = float(canvas_pos.get("x")) if isinstance(canvas_pos, dict) and isinstance(canvas_pos.get("x"), (int, float)) else 0.0
        y = float(canvas_pos.get("y")) if isinstance(canvas_pos, dict) and isinstance(canvas_pos.get("y"), (int, float)) else 0.0
        rect_transform = item_display_obj.get("rect_transform")
        size = rect_transform.get("size") if isinstance(rect_transform, dict) else None
        w = float(size.get("x")) if isinstance(size, dict) and isinstance(size.get("x"), (int, float)) else 0.0
        h = float(size.get("y")) if isinstance(size, dict) and isinstance(size.get("y"), (int, float)) else 0.0

        guid_value = item_display_obj.get("guid")
        if not isinstance(guid_value, int):
            raise ValueError("invalid item_display obj: missing guid")
        guid_int = int(guid_value)

        settings: Dict[str, Any] = {
            "display_type": display_type_name,
            "can_interact": bool(item_display.get("can_interact")),
            "config_id_variable": _normalize_variable_full_name(item_display.get("config_id_variable")),
            "cooldown_seconds_variable": _normalize_variable_full_name(item_display.get("cooldown_seconds_variable")),
            "use_count_enabled": bool(item_display.get("use_count_enabled")),
            "hide_when_empty_count": bool(item_display.get("hide_when_empty_count")),
            "use_count_variable": _normalize_variable_full_name(item_display.get("use_count_variable")),
            "quantity_variable": _normalize_variable_full_name(item_display.get("quantity_variable")),
        }
        if isinstance(kbm_code, int):
            settings["keybind_kbm_code"] = int(kbm_code)
        if isinstance(pad_code, int):
            settings["keybind_gamepad_code"] = int(pad_code)
        if isinstance(no_equipment_behavior_code, int):
            settings["no_equipment_behavior_code"] = int(no_equipment_behavior_code)
        if isinstance(show_quantity, bool):
            settings["show_quantity"] = bool(show_quantity)
        if isinstance(hide_when_zero, bool):
            settings["hide_when_zero"] = bool(hide_when_zero)

        return {
            "__ugc_guid_int": int(guid_int),
            "widget_id": f"ugc_ui_{guid_int}",
            "widget_type": "道具展示",
            "widget_name": str(item_display_obj.get("name") or "道具展示"),
            "position": [float(x), float(y)],
            "size": [float(w), float(h)],
            "initial_visible": bool(item_display_obj.get("visible", True)),
            "layer_index": int(widget_index),
            "is_builtin": False,
            "settings": settings,
        }

    for template_root_guid in template_root_guids:
        root_record = guid_to_record.get(int(template_root_guid))
        if root_record is None:
            continue

        template_name = _extract_primary_name(root_record)
        if not isinstance(template_name, str) or template_name.strip() == "":
            template_name = f"ui_widget_template_{int(template_root_guid)}"
        template_name = str(template_name).strip()

        child_guids = _extract_children_guid_list_from_record(root_record)
        child_records: List[Dict[str, Any]] = []
        for child_guid in child_guids:
            rec = guid_to_record.get(int(child_guid))
            if isinstance(rec, dict):
                child_records.append(rec)

        raw_object: Dict[str, Any] = {
            "template_root_guid": int(template_root_guid),
            "template_name": template_name,
            "children_guids": [int(g) for g in child_guids],
            "template_root_record": root_record,
            "child_records": child_records,
            "assumptions": {
                "layout_registry_path": "4/9/501[0]",
                "ui_record_list_path": "4/9/502",
                "template_root_detection": "root record + meta contains key '14'",
                "template_children_path": "record/503[0]",
            },
        }

        raw_file_path = template_raw_directory / f"ugc_ui_widget_template_{int(template_root_guid)}.raw.json"
        _write_json_file(raw_file_path, raw_object)

        template_id_text = str(int(template_root_guid))

        # 将可识别的控件（当前覆盖：道具展示）写入 widgets，供主程序 UI 面板直接编辑 settings。
        widgets: List[Dict[str, Any]] = []
        for idx, child_guid in enumerate(child_guids):
            item = item_displays_by_guid.get(int(child_guid))
            if not isinstance(item, dict):
                continue
            widgets.append(_build_item_display_widget_payload(widget_index=int(idx), item_display_obj=item))

        template_object: Dict[str, Any] = {
            "template_id": template_id_text,
            "template_name": template_name,
            "is_combination": True if len(child_guids) > 1 else False,
            "widgets": widgets,
            "group_position": [0.0, 0.0],
            "group_size": [100.0, 100.0],
            "supports_layout_visibility_override": True,
            "description": "",
            "created_at": "",
            "updated_at": "",
            "metadata": {
                "ugc": {
                    "ui_widget_template": {
                        "source": "dll_dump",
                        "raw_dll_dump": "原始解析/dll/dump.json",
                        "template_root_guid": int(template_root_guid),
                        "raw_template": str(raw_file_path.relative_to(output_package_root)).replace("\\", "/"),
                    }
                }
            },
        }

        output_file_name = _sanitize_filename(f"{template_name}_{template_id_text}") + ".json"
        output_path = template_directory / output_file_name
        _write_json_file(output_path, template_object)

        exported.append(
            {
                "template_id": template_id_text,
                "template_name": template_name,
                "output": str(output_path.relative_to(output_package_root)).replace("\\", "/"),
            }
        )

    exported_sorted = sorted(exported, key=lambda item: str(item.get("template_id", "")))
    _write_json_file(template_directory / "ui_widget_templates_index.json", exported_sorted)
    return exported_sorted


__all__ = ["_export_ui_widget_templates_from_dll_dump"]


