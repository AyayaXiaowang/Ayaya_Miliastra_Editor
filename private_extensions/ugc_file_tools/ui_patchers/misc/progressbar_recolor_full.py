from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map, encode_message, format_binary_data_hex_text
from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import decoded_field_map_to_numeric_message
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
    write_back_modified_gil_by_reencoding_payload as _write_back_modified_gil_by_reencoding_payload,
)


@dataclass(frozen=True, slots=True)
class ProgressbarRecolorChange:
    guid: int
    record_list_index: int
    old_color_code: int
    new_color_code: int


def recolor_progressbars_in_gil_by_reencoding_payload(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    target_color_code: int,
    verify_with_dll_dump: bool = True,
) -> Dict[str, Any]:
    """
    “全量改色”版本：通过修改 dump-json 的 payload 树并自研 encoder 重编码写回。

    与 `progress_bars.patch_progressbars_color_in_gil`（二进制等长补丁）不同：
    - 本实现允许插入缺失字段（例如 blob 内原本缺少 field_503 时也能写入 color_code）。
    - 代价是需要对整个 payload 重新编码写回。
    """
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    if int(target_color_code) < 0:
        raise ValueError(f"target_color_code must be >= 0, got {target_color_code}")

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    ui_record_list = _extract_ui_record_list(raw_dump_object)

    changes: List[ProgressbarRecolorChange] = []
    progressbar_total = 0

    for record_list_index, record in enumerate(ui_record_list):
        if not isinstance(record, dict):
            continue
        hit = _find_progressbar_binding_blob(record)
        if hit is None:
            continue
        binding_path, blob_bytes = hit
        parsed = _decode_progressbar_binding_blob(blob_bytes)
        if parsed is None:
            continue

        guid_value = _extract_primary_guid(record)
        if not isinstance(guid_value, int):
            continue

        progressbar_total += 1
        old_color_code = int(parsed.get("raw_codes", {}).get("color_code", 0) or 0)

        new_blob_bytes = _set_color_code_in_binding_blob(blob_bytes=blob_bytes, color_code=int(target_color_code))
        _write_binding_blob_back_to_record(record, binding_path=binding_path, new_blob_bytes=new_blob_bytes)

        changes.append(
            ProgressbarRecolorChange(
                guid=int(guid_value),
                record_list_index=int(record_list_index),
                old_color_code=int(old_color_code),
                new_color_code=int(target_color_code),
            )
        )

    if progressbar_total <= 0:
        raise RuntimeError("未在该 .gil 中定位到任何进度条控件（无法改色）。")

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_path,
        output_gil_path=output_path,
    )

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "target_color_code": int(target_color_code),
        "progressbar_total": int(progressbar_total),
        "changes_total": len(changes),
        "changes": [
            {
                "guid": c.guid,
                "record_list_index": c.record_list_index,
                "old_color_code": c.old_color_code,
                "new_color_code": c.new_color_code,
            }
            for c in changes
        ],
    }

    if verify_with_dll_dump:
        verify_dump = _dump_gil_to_raw_json_object(output_path)
        verify_records = _extract_ui_record_list(verify_dump)
        mismatch_total = 0
        mismatches: List[Dict[str, Any]] = []
        for record_list_index, record in enumerate(verify_records):
            if not isinstance(record, dict):
                continue
            hit = _find_progressbar_binding_blob(record)
            if hit is None:
                continue
            _path, blob_bytes = hit
            parsed = _decode_progressbar_binding_blob(blob_bytes)
            if parsed is None:
                continue
            guid_value = _extract_primary_guid(record)
            guid_int = int(guid_value) if isinstance(guid_value, int) else None
            color_code = int(parsed.get("raw_codes", {}).get("color_code", 0) or 0)
            if color_code != int(target_color_code):
                mismatch_total += 1
                mismatches.append(
                    {
                        "guid": guid_int,
                        "record_list_index": int(record_list_index),
                        "color_code": int(color_code),
                    }
                )
        report["verify"] = {
            "expected_color_code": int(target_color_code),
            "mismatch_total": int(mismatch_total),
            "mismatches": mismatches,
        }

    return report


def _set_color_code_in_binding_blob(*, blob_bytes: bytes, color_code: int) -> bytes:
    decoded, consumed = decode_message_to_field_map(
        data_bytes=bytes(blob_bytes),
        start_offset=0,
        end_offset=len(blob_bytes),
        remaining_depth=16,
    )
    if consumed != len(blob_bytes):
        raise ValueError("binding blob 未能完整解码为单个 message（存在 trailing bytes）")
    message = decoded_field_map_to_numeric_message(decoded)
    message["503"] = int(color_code)
    return encode_message(dict(message))


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
    "recolor_progressbars_in_gil_by_reencoding_payload",
]


