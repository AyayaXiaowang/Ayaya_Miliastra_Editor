from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message, format_binary_data_hex_text
from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import decoded_field_map_to_numeric_message
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.ui_parsers.progress_bars import (
    decode_progressbar_binding_blob as _decode_progressbar_binding_blob,
    find_progressbar_binding_blob as _find_progressbar_binding_blob,
)
from ugc_file_tools.ui.readable_dump import (
    extract_primary_guid as _extract_primary_guid,
    extract_ui_record_list as _extract_ui_record_list,
)

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    find_record_by_guid as _find_record_by_guid,
    write_back_modified_gil_by_reencoding_payload as _write_back_modified_gil_by_reencoding_payload,
)


@dataclass(frozen=True, slots=True)
class ProgressbarVariantPatch:
    guid: int
    # 可选：形状/样式/颜色（见 ui_parsers/progress_bars.py 的 map）
    shape_code: Optional[int] = None
    style_code: Optional[int] = None
    color_code: Optional[int] = None
    # 可选：变量绑定（outer binding blob 的 nested message：field_504/505/506）
    group_id: Optional[int] = None
    current_name: Optional[str] = None
    min_name: Optional[str] = None
    max_name: Optional[str] = None
    # 可选：初始可见性（写回 record['505'][*]['503']['503']）
    visible: Optional[bool] = None


def apply_progressbar_variant_patches_in_gil(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    patches: List[ProgressbarVariantPatch],
    # 仅当 record['504'] == layout_guid 时才会匹配（用于仅改某个布局下的进度条实例）
    restrict_layout_guid: Optional[int] = None,
    verify_with_dll_dump: bool = True,
) -> Dict[str, Any]:
    """
    对指定 GUID 的进度条写回“多字段差异”：
    - binding blob：shape/style/color + current/min/max 绑定变量名（可选）
    - record：初始可见性 flag（可选）

    约束：
    - 不依赖 DLL 的 JsonToGil；基于 dump-json 的 payload_root['4'] 修改后用自研 encoder 重编码写回。
    - 不使用 try/except；结构不一致直接抛错，避免写坏存档。
    """
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    patch_by_guid: Dict[int, ProgressbarVariantPatch] = {}
    for patch in patches:
        g = int(patch.guid)
        if g in patch_by_guid:
            raise ValueError(f"patch guid duplicated: {g}")
        patch_by_guid[g] = patch

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    ui_record_list = _extract_ui_record_list(raw_dump_object)

    changes: List[Dict[str, Any]] = []
    progressbar_hit_total = 0
    patched_total = 0

    for record_list_index, record in enumerate(ui_record_list):
        if not isinstance(record, dict):
            continue

        guid_value = _extract_primary_guid(record)
        if not isinstance(guid_value, int):
            continue

        hit = _find_progressbar_binding_blob(record)
        if hit is None:
            continue

        progressbar_hit_total += 1

        if restrict_layout_guid is not None:
            parent_value = record.get("504")
            if not isinstance(parent_value, int) or int(parent_value) != int(restrict_layout_guid):
                continue

        plan = patch_by_guid.get(int(guid_value))
        if plan is None:
            continue

        binding_path, binding_blob_bytes = hit
        before = _decode_progressbar_binding_blob(binding_blob_bytes)
        if before is None:
            raise RuntimeError(f"无法解析 progressbar binding blob：guid={int(guid_value)} path={binding_path}")

        new_blob_bytes = _patch_binding_blob_bytes(
            blob_bytes=binding_blob_bytes,
            plan=plan,
        )

        _write_binding_blob_back_to_record(record, binding_path=binding_path, new_blob_bytes=new_blob_bytes)

        visibility_changed = _apply_visibility_patch(record, visible=plan.visible)

        after = _decode_progressbar_binding_blob(new_blob_bytes)
        if after is None:
            raise RuntimeError(f"写回后无法解析 progressbar binding blob：guid={int(guid_value)} path={binding_path}")

        patched_total += 1
        changes.append(
            {
                "guid": int(guid_value),
                "record_list_index": int(record_list_index),
                "binding_blob_path": str(binding_path),
                "visibility_changed_total": int(visibility_changed),
                "before": before,
                "after": after,
            }
        )

    if patched_total <= 0:
        raise RuntimeError("未命中任何需要写回的进度条（请检查 guid 列表/布局过滤条件）。")

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_path,
        output_gil_path=output_path,
    )

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "restrict_layout_guid": (int(restrict_layout_guid) if restrict_layout_guid is not None else None),
        "progressbar_hit_total": int(progressbar_hit_total),
        "requested_patch_total": len(patches),
        "patched_total": int(patched_total),
        "changes": changes,
    }

    if verify_with_dll_dump:
        verify_dump = _dump_gil_to_raw_json_object(output_path)
        verify_records = _extract_ui_record_list(verify_dump)
        ok = True
        for change in changes:
            guid_int = int(change.get("guid", 0) or 0)
            if guid_int <= 0:
                ok = False
                break
            if _find_record_by_guid(verify_records, guid_int) is None:
                ok = False
                break
        report["verify"] = {"ok": bool(ok), "patched_guids_exist": bool(ok)}

    return report


def _apply_visibility_patch(record: Dict[str, Any], visible: Optional[bool]) -> int:
    if visible is None:
        return 0
    component_list = record.get("505")
    if not isinstance(component_list, list):
        return 0
    new_flag_value = 1 if bool(visible) else 0
    changed = 0
    for component in component_list:
        if not isinstance(component, dict):
            continue
        nested = component.get("503")
        if not isinstance(nested, dict):
            continue
        old_flag = nested.get("503")
        if not isinstance(old_flag, int):
            continue
        if int(old_flag) == int(new_flag_value):
            continue
        nested["503"] = int(new_flag_value)
        changed += 1
    return int(changed)


def _patch_binding_blob_bytes(*, blob_bytes: bytes, plan: ProgressbarVariantPatch) -> bytes:
    decoded, consumed = decode_message_to_field_map(
        data_bytes=bytes(blob_bytes),
        start_offset=0,
        end_offset=len(blob_bytes),
        remaining_depth=16,
    )
    if consumed != len(blob_bytes):
        raise ValueError("binding blob 未能完整解码为单个 message（存在 trailing bytes）")
    message = decoded_field_map_to_numeric_message(decoded)

    if plan.shape_code is not None:
        message["501"] = int(plan.shape_code)
    if plan.style_code is not None:
        message["502"] = int(plan.style_code)
    if plan.color_code is not None:
        message["503"] = int(plan.color_code)

    message = _patch_variable_ref_in_message(message, field_number=504, group_id=plan.group_id, name=plan.current_name)
    message = _patch_variable_ref_in_message(message, field_number=505, group_id=plan.group_id, name=plan.min_name)
    message = _patch_variable_ref_in_message(message, field_number=506, group_id=plan.group_id, name=plan.max_name)

    return encode_message(dict(message))


def _patch_variable_ref_in_message(
    message: Dict[str, Any],
    *,
    field_number: int,
    group_id: Optional[int],
    name: Optional[str],
) -> Dict[str, Any]:
    key = str(int(field_number))
    nested = message.get(key)
    if nested is None:
        return message
    if not isinstance(nested, dict):
        return message

    if group_id is not None:
        nested["501"] = int(group_id)
    if name is not None:
        nested["502"] = str(name)

    message[key] = nested
    return message


def _write_binding_blob_back_to_record(record: Dict[str, Any], *, binding_path: str, new_blob_bytes: bytes) -> None:
    # 当前样本/识别规则：进度条 binding blob 固定在 505/[3]/503/20
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


def _dump_gil_to_raw_json_object(input_gil_file_path: Path) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as temporary_directory:
        raw_json_path = Path(temporary_directory) / "ui.raw.json"
        dump_gil_to_json(str(input_gil_file_path), str(raw_json_path))
        raw_text = raw_json_path.read_text(encoding="utf-8")
    payload = json.loads(raw_text)
    if not isinstance(payload, dict):
        raise TypeError("DLL dump-json 输出格式错误：期望为 dict")
    return payload


__all__ = [
    "ProgressbarVariantPatch",
    "apply_progressbar_variant_patches_in_gil",
]


