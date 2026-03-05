from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from ugc_file_tools.gil_dump_codec.gil_container import (
    build_gil_file_bytes_from_payload,
    read_gil_container_spec,
    read_gil_payload_bytes,
)
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.wire import replace_length_delimited_fields_payload_bytes_in_message_bytes


def write_patched_gil_by_sections_and_return_output_path(
    *,
    effective_base_gil_path: Path,
    output_gil_path: Path,
    payload_root: Dict[str, Any],
    include_section5: bool,
) -> Path:
    # ===== 写盘：wire-level 仅替换必要段（默认仅 field10=NodeGraphs），避免整份 payload 重编码漂移 =====
    section10_obj = payload_root.get("10")
    if not isinstance(section10_obj, dict):
        raise ValueError("payload_root['10'] must be dict after writeback")

    patched_sections: Dict[int, bytes] = {10: encode_message(dict(section10_obj))}
    if bool(include_section5):
        section5_obj = payload_root.get("5")
        if not isinstance(section5_obj, dict):
            raise ValueError("ui_custom_variable_sync applied but payload_root['5'] is not dict")
        patched_sections[5] = encode_message(dict(section5_obj))

    base_payload_bytes = read_gil_payload_bytes(Path(effective_base_gil_path))
    patched_payload_bytes = replace_length_delimited_fields_payload_bytes_in_message_bytes(
        message_bytes=base_payload_bytes,
        payload_bytes_by_field_number=patched_sections,
    )
    container_spec = read_gil_container_spec(Path(effective_base_gil_path))
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=patched_payload_bytes, container_spec=container_spec)
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)
    return Path(output_path)


def maybe_write_missing_enum_constants_report(
    *,
    output_gil_path: Path,
    skipped_enum_constants: Any,
) -> Optional[str]:
    if not skipped_enum_constants:
        return None
    # report 落点与输出 gil 同目录（输出路径会被 resolve_output_file_path_in_out_dir 收口到 out/）
    output_path_for_report = resolve_output_file_path_in_out_dir(Path(output_gil_path))
    report_path = output_path_for_report.parent / f"{output_path_for_report.name}.missing_enum_constants.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(skipped_enum_constants, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(report_path)


__all__ = [
    "write_patched_gil_by_sections_and_return_output_path",
    "maybe_write_missing_enum_constants_report",
]

