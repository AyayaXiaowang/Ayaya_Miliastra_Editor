from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.ui_parsers.progress_bars import (
    decode_progressbar_binding_blob as _decode_progressbar_binding_blob,
    find_progressbar_binding_blob as _find_progressbar_binding_blob,
)
from ugc_file_tools.ui.readable_dump import (
    extract_primary_guid as _extract_primary_guid,
    extract_ui_record_list as _extract_ui_record_list,
)


@dataclass(frozen=True, slots=True)
class ProgressbarPatchPlan:
    guid: int
    record_list_index: int
    binding_blob_path: str
    blob_offset_in_gil: Optional[int]
    blob_occurrence_count_in_gil: int
    blob_byte_length: int
    old_color_code: int
    new_color_code: int


def patch_progressbars_color_in_gil(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    target_color_code: int,
    allow_multi_occurrence: bool = False,
    verify_with_dll_dump: bool = True,
) -> Dict[str, Any]:
    """
    将 `.gil` 中所有“进度条”控件的颜色改为指定枚举值（target_color_code），并写出新的 `.gil`。

    实现策略：
    - 先用纯 Python dump-json 定位 UI record，并从 record 中提取 progressbar 绑定 blob（<binary_data>）。
    - 对 blob 内 field_503(varint) 做**等长替换**（例如 1→0，2→0），然后在 `.gil` 文件中定位该 blob 原始 bytes 并原地改写。
    - 不进行 JSON→GIL 全量重编码（当前 DLL 的 UGC_JsonToGil 仍为预留接口）。
    """
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    if int(target_color_code) < 0:
        raise ValueError(f"target_color_code must be >= 0, got {target_color_code}")

    file_bytes = input_path.read_bytes()
    file_buffer = bytearray(file_bytes)

    patch_plans, patched_blob_count = _build_patch_plans_and_apply_in_memory(
        file_buffer=file_buffer,
        input_gil_file_path=input_path,
        target_color_code=int(target_color_code),
        allow_multi_occurrence=bool(allow_multi_occurrence),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(bytes(file_buffer))

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "target_color_code": int(target_color_code),
        "allow_multi_occurrence": bool(allow_multi_occurrence),
        "progressbar_total": len(patch_plans),
        "patched_blob_total": int(patched_blob_count),
        "changes": [
            {
                "guid": plan.guid,
                "record_list_index": plan.record_list_index,
                "binding_blob_path": plan.binding_blob_path,
                "blob_offset_in_gil": plan.blob_offset_in_gil,
                "blob_occurrence_count_in_gil": plan.blob_occurrence_count_in_gil,
                "blob_byte_length": plan.blob_byte_length,
                "old_color_code": plan.old_color_code,
                "new_color_code": plan.new_color_code,
            }
            for plan in patch_plans
        ],
    }

    if verify_with_dll_dump:
        verify_result = _verify_progressbar_colors_with_dll_dump(
            output_gil_file_path=output_path,
            expected_color_code=int(target_color_code),
        )
        report["verify"] = verify_result

    return report


def _build_patch_plans_and_apply_in_memory(
    *,
    file_buffer: bytearray,
    input_gil_file_path: Path,
    target_color_code: int,
    allow_multi_occurrence: bool,
) -> Tuple[List[ProgressbarPatchPlan], int]:
    """
    返回:
    - patch_plans: 每条进度条的变更计划（含 blob offset）
    - patched_blob_count: 实际执行了字节替换的 blob 数
    """
    raw_dump_object = _dump_gil_to_raw_json_object(input_gil_file_path)
    ui_record_list = _extract_ui_record_list(raw_dump_object)

    patch_plans: List[ProgressbarPatchPlan] = []
    patched_blob_count = 0

    # 备注：progressbar binding blob 可能被多个 record 共享（bytes 完全一致）。
    # 当我们允许 multi-occurrence 时，首次命中会对所有出现位置做等长替换；后续同 bytes 的 record
    # 不应再次尝试定位 old bytes（否则会 count==0），因此需要去重。
    original_haystack = bytes(file_buffer)
    already_patched_blob_bytes: set[bytes] = set()

    for record_list_index, record in enumerate(ui_record_list):
        if not isinstance(record, dict):
            continue

        hit = _find_progressbar_binding_blob(record)
        if hit is None:
            continue
        binding_blob_path, blob_bytes = hit

        parsed_config = _decode_progressbar_binding_blob(blob_bytes)
        if parsed_config is None:
            continue

        guid_value = _extract_primary_guid(record)
        if guid_value is None:
            continue

        old_color_code = int(parsed_config.get("raw_codes", {}).get("color_code", 0) or 0)

        patched_blob_bytes, did_patch = _patch_color_code_in_progressbar_blob(
            blob_bytes=blob_bytes,
            new_color_code=int(target_color_code),
        )

        blob_occurrence_count = int(original_haystack.count(blob_bytes))
        blob_offset: Optional[int] = None
        if did_patch:
            if blob_occurrence_count <= 0:
                raise RuntimeError("无法在 .gil 二进制中定位 progressbar blob（bytes 序列未出现）。")

            # 同 bytes 的 blob 已经在前一条记录中被写回过：跳过实际改写，但仍记录计划。
            if blob_bytes in already_patched_blob_bytes:
                blob_offset = int(original_haystack.find(blob_bytes))
                patched_blob_bytes = bytes(patched_blob_bytes)

                patch_plans.append(
                    ProgressbarPatchPlan(
                        guid=int(guid_value),
                        record_list_index=int(record_list_index),
                        binding_blob_path=str(binding_blob_path),
                        blob_offset_in_gil=blob_offset if blob_offset >= 0 else None,
                        blob_occurrence_count_in_gil=int(blob_occurrence_count),
                        blob_byte_length=int(len(blob_bytes)),
                        old_color_code=int(old_color_code),
                        new_color_code=int(target_color_code),
                    )
                )
                continue

            if blob_occurrence_count == 1:
                haystack = bytes(file_buffer)
                blob_offset = int(haystack.find(blob_bytes))
                if blob_offset < 0:
                    raise RuntimeError("无法在 .gil 二进制中定位 progressbar blob（bytes 序列未出现）。")
                file_buffer[blob_offset : blob_offset + len(blob_bytes)] = patched_blob_bytes
                patched_blob_count += 1
            else:
                if not bool(allow_multi_occurrence):
                    raise RuntimeError(
                        "progressbar blob 在 .gil 中出现了多次，无法安全写回（需要更强的定位规则）。"
                    )

                # 允许“多处出现”：对所有出现位置做等长替换。
                # 备注：这会把共享同一 binding blob bytes 的多个进度条一起改色；最终以 verify dump 为准。
                haystack = bytes(file_buffer)
                current_offset = 0
                first_offset: Optional[int] = None
                patched_occurrence = 0
                while True:
                    found = haystack.find(blob_bytes, current_offset)
                    if found < 0:
                        break
                    if first_offset is None:
                        first_offset = int(found)
                    file_buffer[int(found) : int(found) + len(blob_bytes)] = patched_blob_bytes
                    patched_occurrence += 1
                    current_offset = int(found) + len(blob_bytes)
                if patched_occurrence != int(blob_occurrence_count):
                    raise RuntimeError(
                        f"progressbar blob 多处替换次数不一致：expected={blob_occurrence_count}, patched={patched_occurrence}"
                    )
                blob_offset = int(first_offset) if first_offset is not None else None
                patched_blob_count += int(patched_occurrence)

            already_patched_blob_bytes.add(bytes(blob_bytes))

        patch_plans.append(
            ProgressbarPatchPlan(
                guid=int(guid_value),
                record_list_index=int(record_list_index),
                binding_blob_path=str(binding_blob_path),
                blob_offset_in_gil=blob_offset,
                blob_occurrence_count_in_gil=int(blob_occurrence_count),
                blob_byte_length=int(len(blob_bytes)),
                old_color_code=int(old_color_code),
                new_color_code=int(target_color_code),
            )
        )

    if not patch_plans:
        raise RuntimeError("未在该 .gil 中定位到任何进度条控件（无法写回颜色）。")

    return patch_plans, patched_blob_count


def _dump_gil_to_raw_json_object(input_gil_file_path: Path) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as temporary_directory:
        raw_json_path = Path(temporary_directory) / "ui.raw.json"
        dump_gil_to_json(str(input_gil_file_path), str(raw_json_path))
        raw_text = raw_json_path.read_text(encoding="utf-8")
    payload = json.loads(raw_text)
    if not isinstance(payload, dict):
        raise TypeError("DLL dump-json 输出格式错误：期望为 dict")
    return payload


def _verify_progressbar_colors_with_dll_dump(
    *,
    output_gil_file_path: Path,
    expected_color_code: int,
) -> Dict[str, Any]:
    raw_dump_object = _dump_gil_to_raw_json_object(output_gil_file_path)
    ui_record_list = _extract_ui_record_list(raw_dump_object)

    progressbar_total = 0
    mismatch_total = 0
    mismatches: List[Dict[str, Any]] = []

    for record_list_index, record in enumerate(ui_record_list):
        if not isinstance(record, dict):
            continue
        hit = _find_progressbar_binding_blob(record)
        if hit is None:
            continue
        _binding_blob_path, blob_bytes = hit
        parsed_config = _decode_progressbar_binding_blob(blob_bytes)
        if parsed_config is None:
            continue

        progressbar_total += 1

        guid_value = _extract_primary_guid(record)
        guid_int = int(guid_value) if isinstance(guid_value, int) else None

        color_code = int(parsed_config.get("raw_codes", {}).get("color_code", 0) or 0)
        if color_code != int(expected_color_code):
            mismatch_total += 1
            mismatches.append(
                {
                    "guid": guid_int,
                    "record_list_index": int(record_list_index),
                    "color_code": int(color_code),
                }
            )

    if progressbar_total <= 0:
        raise RuntimeError("verify: 未在输出 .gil 中找到任何进度条（可能写坏或 DLL 解析失败）。")

    return {
        "progressbar_total": int(progressbar_total),
        "expected_color_code": int(expected_color_code),
        "mismatch_total": int(mismatch_total),
        "mismatches": mismatches,
    }


@dataclass(frozen=True, slots=True)
class _ProtobufFieldSpan:
    field_number: int
    wire_type: int
    value_start: int
    value_end: int
    value_int: Optional[int]


def _patch_color_code_in_progressbar_blob(*, blob_bytes: bytes, new_color_code: int) -> Tuple[bytes, bool]:
    """
    仅修改 progressbar blob 的 field_503(varint) 值。
    - 若 blob 内缺失 field_503，则视为默认色：不插入字段（保持等长）。
    """
    spans, ok = _parse_protobuf_like_varint_field_spans(blob_bytes)
    if not ok:
        raise ValueError("progressbar blob protobuf-like 结构不合法，无法写回。")

    did_patch = False
    patched = bytearray(blob_bytes)

    for span in spans:
        if span.field_number != 503 or span.wire_type != 0:
            continue
        if span.value_int is None:
            continue

        old_value = int(span.value_int)
        if old_value == int(new_color_code):
            continue

        old_len = int(span.value_end - span.value_start)
        new_encoded = _encode_varint(int(new_color_code))
        if len(new_encoded) != old_len:
            raise ValueError(
                "color_code 变更将导致 varint 字节长度变化，当前补丁器只支持等长替换；"
                f"old={old_value} (bytes={old_len}), new={new_color_code} (bytes={len(new_encoded)})"
            )

        patched[span.value_start : span.value_end] = new_encoded
        did_patch = True

    return bytes(patched), did_patch


def _parse_protobuf_like_varint_field_spans(data: bytes) -> Tuple[List[_ProtobufFieldSpan], bool]:
    """
    只关心 wire_type=0 的 value span（用于原地改 varint）。
    返回 (spans, ok)；ok=False 表示结构不合法。
    """
    spans: List[_ProtobufFieldSpan] = []
    current_offset = 0
    end_offset = len(data)

    while current_offset < end_offset:
        tag_value, current_offset, ok = _decode_varint(data, current_offset)
        if not ok or tag_value == 0:
            return spans, False

        field_number = tag_value >> 3
        wire_type = tag_value & 0x07
        if field_number <= 0:
            return spans, False

        if wire_type == 0:
            value_start = current_offset
            value_int, current_offset, ok = _decode_varint(data, current_offset)
            if not ok:
                return spans, False
            value_end = current_offset
            spans.append(
                _ProtobufFieldSpan(
                    field_number=int(field_number),
                    wire_type=0,
                    value_start=int(value_start),
                    value_end=int(value_end),
                    value_int=int(value_int),
                )
            )
            continue

        if wire_type == 1:
            if current_offset + 8 > end_offset:
                return spans, False
            current_offset += 8
            continue

        if wire_type == 5:
            if current_offset + 4 > end_offset:
                return spans, False
            current_offset += 4
            continue

        if wire_type == 2:
            length_value, current_offset, ok = _decode_varint(data, current_offset)
            if not ok:
                return spans, False
            length_int = int(length_value)
            if length_int < 0:
                return spans, False
            if current_offset + length_int > end_offset:
                return spans, False
            current_offset += length_int
            continue

        return spans, False

    return spans, True


def _decode_varint(data: bytes, offset: int) -> Tuple[int, int, bool]:
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


def _encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError(f"varint value must be >= 0, got {value}")
    parts: List[int] = []
    remaining = int(value)
    while True:
        byte_value = remaining & 0x7F
        remaining >>= 7
        if remaining:
            parts.append(byte_value | 0x80)
        else:
            parts.append(byte_value)
            break
    return bytes(parts)


