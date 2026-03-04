from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.ui_parsers.item_displays import build_item_display_dump
from ugc_file_tools.ui.readable_dump import extract_ui_record_list as _extract_ui_record_list

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    dump_gil_to_raw_json_object as _dump_gil_to_raw_json_object,
    find_record_by_guid as _find_record_by_guid,
    write_back_modified_gil_by_reencoding_payload as _write_back_modified_gil_by_reencoding_payload,
)
from .web_ui_import import (
    _find_item_display_blob,
    _parse_variable_ref_text,
    _patch_item_display_blob_bytes,
    _write_item_display_blob_back_to_record,
)


@dataclass(frozen=True, slots=True)
class ItemDisplayVariantPatch:
    """对单个“道具展示”控件的 patch（按 guid 定位）。"""

    guid: int
    display_type: Optional[str] = None
    can_interact: Optional[bool] = None
    keybind_kbm_code: Optional[int] = None
    keybind_gamepad_code: Optional[int] = None
    config_id_variable: Optional[str] = None
    cooldown_seconds_variable: Optional[str] = None
    use_count_enabled: Optional[bool] = None
    hide_when_empty_count: Optional[bool] = None
    use_count_variable: Optional[str] = None
    quantity_variable: Optional[str] = None
    show_quantity: Optional[bool] = None
    hide_when_zero: Optional[bool] = None
    no_equipment_behavior_code: Optional[int] = None


def apply_item_display_variant_patches_in_gil(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    patches: List[ItemDisplayVariantPatch],
    verify_with_dll_dump: bool = True,
    verify_canvas_size: tuple[float, float] = (1600.0, 900.0),
) -> Dict[str, Any]:
    """
    对 `.gil` 内指定 GUID 的“道具展示”控件进行 blob 写回，并输出新的 `.gil`。

    约束：
    - 使用 dump-json（数值键结构）作为结构真源，再用自研 encoder 重编码 payload 写回。
    - 不使用 try/except；结构不一致直接抛错。
    """
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    if not patches:
        raise ValueError("patches 不能为空")

    patch_by_guid: Dict[int, ItemDisplayVariantPatch] = {}
    for patch in patches:
        guid_int = int(patch.guid)
        if guid_int in patch_by_guid:
            raise ValueError(f"patch guid duplicated: {guid_int}")
        patch_by_guid[guid_int] = patch

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    ui_record_list = _extract_ui_record_list(raw_dump_object)

    current_item_dump = build_item_display_dump(
        raw_dump_object,
        canvas_size=verify_canvas_size,
        include_raw_binding_blob_hex=False,
    )
    current_by_guid = current_item_dump.get("item_displays_by_guid")
    if not isinstance(current_by_guid, dict):
        raise TypeError("internal error: item_displays_by_guid 不是 dict")

    patched_total = 0
    changes: List[Dict[str, Any]] = []

    for guid_int, patch in patch_by_guid.items():
        record = _find_record_by_guid(ui_record_list, int(guid_int))
        if record is None:
            raise RuntimeError(f"未找到 guid={int(guid_int)} 对应的 UI record")

        hit = _find_item_display_blob(record)
        if hit is None:
            raise RuntimeError(f"guid={int(guid_int)} 对应 record 不包含可识别的 道具展示 blob")
        binding_path, blob_bytes = hit

        effective_display_type = str(patch.display_type or "").strip()
        if effective_display_type == "":
            # 未提供时：保持原 display_type（通过现有解析输出推断，避免误改模板道具/背包道具的类型）
            if int(guid_int) not in current_by_guid:
                raise RuntimeError(f"internal error: 未能从解析结果中定位 guid={int(guid_int)} 的道具展示")
            current_item = current_by_guid[int(guid_int)]
            current_display = (
                current_item.get("item_display", {}).get("display_type", {}).get("name")
                if isinstance(current_item, dict)
                else None
            )
            effective_display_type = str(current_display or "").strip()
            if effective_display_type == "":
                raise RuntimeError(f"无法推断 guid={int(guid_int)} 的 display_type（请在 patch 中显式提供 display_type）")

        settings: Dict[str, Any] = {}
        if patch.can_interact is not None:
            settings["can_interact"] = bool(patch.can_interact)
        if patch.keybind_kbm_code is not None:
            settings["keybind_kbm_code"] = int(patch.keybind_kbm_code)
        if patch.keybind_gamepad_code is not None:
            settings["keybind_gamepad_code"] = int(patch.keybind_gamepad_code)
        if patch.config_id_variable is not None:
            settings["config_id_variable"] = str(patch.config_id_variable)
        if patch.cooldown_seconds_variable is not None:
            settings["cooldown_seconds_variable"] = str(patch.cooldown_seconds_variable)
        if patch.use_count_enabled is not None:
            settings["use_count_enabled"] = bool(patch.use_count_enabled)
        if patch.hide_when_empty_count is not None:
            settings["hide_when_empty_count"] = bool(patch.hide_when_empty_count)
        if patch.use_count_variable is not None:
            settings["use_count_variable"] = str(patch.use_count_variable)
        if patch.quantity_variable is not None:
            settings["quantity_variable"] = str(patch.quantity_variable)
        if patch.show_quantity is not None:
            settings["show_quantity"] = bool(patch.show_quantity)
        if patch.hide_when_zero is not None:
            settings["hide_when_zero"] = bool(patch.hide_when_zero)
        if patch.no_equipment_behavior_code is not None:
            settings["no_equipment_behavior_code"] = int(patch.no_equipment_behavior_code)

        patched_blob = _patch_item_display_blob_bytes(
            blob_bytes=bytes(blob_bytes),
            display_type=str(effective_display_type),
            settings=settings,
        )
        # 写回到 record
        _write_item_display_blob_back_to_record(record, binding_path=binding_path, new_blob_bytes=patched_blob)

        patched_total += 1
        changes.append(
            {
                "guid": int(guid_int),
                "display_type": str(effective_display_type),
                "settings": dict(settings),
                "binding_blob_path": str(binding_path),
                "binding_blob_byte_length_before": int(len(blob_bytes)),
                "binding_blob_byte_length_after": int(len(patched_blob)),
            }
        )

    if patched_total <= 0:
        raise RuntimeError("未应用任何 patch（patches 为空）")

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_path,
        output_gil_path=output_path,
    )

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "requested_patch_total": int(len(patches)),
        "patched_total": int(patched_total),
        "changes": changes,
    }

    if verify_with_dll_dump:
        verify_dump_object = _dump_gil_to_raw_json_object(output_path)
        verify_item_dump = build_item_display_dump(
            verify_dump_object,
            canvas_size=verify_canvas_size,
            include_raw_binding_blob_hex=False,
        )
        verify_by_guid = verify_item_dump.get("item_displays_by_guid")
        if not isinstance(verify_by_guid, dict):
            raise TypeError("verify: item_displays_by_guid 不是 dict")

        def _normalize_full_name(text: str) -> Optional[str]:
            raw = str(text or "").strip()
            if raw in {"", "."}:
                return None
            _, _, full_name = _parse_variable_ref_text(raw, allow_constant_number=False)
            return str(full_name) if full_name else None

        mismatches: List[Dict[str, Any]] = []
        for patch in patches:
            guid_int = int(patch.guid)
            item = verify_by_guid.get(int(guid_int))
            if not isinstance(item, dict):
                mismatches.append({"guid": int(guid_int), "reason": "not_found"})
                continue
            parsed = item.get("item_display")
            if not isinstance(parsed, dict):
                mismatches.append({"guid": int(guid_int), "reason": "missing_item_display"})
                continue

            # 简单字段对比（仅对 patch 显式提供的字段做断言）
            if patch.display_type is not None:
                parsed_type = parsed.get("display_type")
                parsed_name = parsed_type.get("name") if isinstance(parsed_type, dict) else None
                if str(parsed_name or "") != str(patch.display_type):
                    mismatches.append(
                        {
                            "guid": int(guid_int),
                            "field": "display_type",
                            "expected": str(patch.display_type),
                            "actual": str(parsed_name or ""),
                        }
                    )

            if patch.can_interact is not None and bool(parsed.get("can_interact")) != bool(patch.can_interact):
                mismatches.append(
                    {
                        "guid": int(guid_int),
                        "field": "can_interact",
                        "expected": bool(patch.can_interact),
                        "actual": bool(parsed.get("can_interact")),
                    }
                )

            if patch.no_equipment_behavior_code is not None:
                ne = parsed.get("no_equipment_behavior")
                ne_code = ne.get("code") if isinstance(ne, dict) else None
                if int(ne_code or 0) != int(patch.no_equipment_behavior_code):
                    mismatches.append(
                        {
                            "guid": int(guid_int),
                            "field": "no_equipment_behavior_code",
                            "expected": int(patch.no_equipment_behavior_code),
                            "actual": ne_code,
                        }
                    )

            if patch.keybind_kbm_code is not None:
                kb = parsed.get("keybind_kbm")
                code = kb.get("code") if isinstance(kb, dict) else None
                if int(code or 0) != int(patch.keybind_kbm_code):
                    mismatches.append(
                        {
                            "guid": int(guid_int),
                            "field": "keybind_kbm_code",
                            "expected": int(patch.keybind_kbm_code),
                            "actual": code,
                        }
                    )

            if patch.keybind_gamepad_code is not None:
                kb = parsed.get("keybind_gamepad")
                code = kb.get("code") if isinstance(kb, dict) else None
                if int(code or 0) != int(patch.keybind_gamepad_code):
                    mismatches.append(
                        {
                            "guid": int(guid_int),
                            "field": "keybind_gamepad_code",
                            "expected": int(patch.keybind_gamepad_code),
                            "actual": code,
                        }
                    )

            if patch.use_count_enabled is not None and bool(parsed.get("use_count_enabled")) != bool(patch.use_count_enabled):
                mismatches.append(
                    {
                        "guid": int(guid_int),
                        "field": "use_count_enabled",
                        "expected": bool(patch.use_count_enabled),
                        "actual": bool(parsed.get("use_count_enabled")),
                    }
                )
            if patch.hide_when_empty_count is not None and bool(parsed.get("hide_when_empty_count")) != bool(patch.hide_when_empty_count):
                mismatches.append(
                    {
                        "guid": int(guid_int),
                        "field": "hide_when_empty_count",
                        "expected": bool(patch.hide_when_empty_count),
                        "actual": bool(parsed.get("hide_when_empty_count")),
                    }
                )

            if patch.show_quantity is not None and bool(parsed.get("show_quantity")) != bool(patch.show_quantity):
                mismatches.append(
                    {
                        "guid": int(guid_int),
                        "field": "show_quantity",
                        "expected": bool(patch.show_quantity),
                        "actual": bool(parsed.get("show_quantity")),
                    }
                )
            if patch.hide_when_zero is not None and bool(parsed.get("hide_when_zero")) != bool(patch.hide_when_zero):
                mismatches.append(
                    {
                        "guid": int(guid_int),
                        "field": "hide_when_zero",
                        "expected": bool(patch.hide_when_zero),
                        "actual": bool(parsed.get("hide_when_zero")),
                    }
                )

            def _check_var(field_name: str, expected_text: Optional[str]) -> None:
                if expected_text is None:
                    return
                normalized = _normalize_full_name(str(expected_text))
                var_obj = parsed.get(field_name)
                actual = var_obj.get("full_name") if isinstance(var_obj, dict) else None
                if str(actual or "") != str(normalized or ""):
                    mismatches.append(
                        {
                            "guid": int(guid_int),
                            "field": field_name,
                            "expected": normalized,
                            "actual": actual,
                        }
                    )

            _check_var("config_id_variable", patch.config_id_variable)
            _check_var("cooldown_seconds_variable", patch.cooldown_seconds_variable)
            _check_var("use_count_variable", patch.use_count_variable)
            _check_var("quantity_variable", patch.quantity_variable)

        report["verify"] = {
            "ok": bool(len(mismatches) == 0),
            "mismatch_total": int(len(mismatches)),
            "mismatches": mismatches,
        }

    return report


__all__ = [
    "ItemDisplayVariantPatch",
    "apply_item_display_variant_patches_in_gil",
]


