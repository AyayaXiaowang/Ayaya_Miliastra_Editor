from __future__ import annotations

import struct
from typing import Any, Dict, List, Optional, Tuple

from ..file_io import _sanitize_filename, _write_json_file
from ..section15_decoders import _try_decode_section15_meta_data
from .context import Section15ExportContext
from .decoded_values import _try_extract_fixed32_float, _try_extract_message, _try_extract_utf8


def _decode_varint_stream(raw_bytes: bytes) -> List[int]:
    """将一段 bytes 尽可能按连续 varint 解析为 int 列表。

    说明：
    - 仅用于把 decode_gil 产物中的 `raw_hex`（多为 protobuf packed repeated）还原为候选 ID 列表；
    - 遇到无法解析的情况会停止（不抛 try/except，不做吞错）。
    """
    values: List[int] = []
    index = 0
    length = len(raw_bytes)
    while index < length:
        shift = 0
        value = 0
        while index < length:
            byte_value = raw_bytes[index]
            index += 1
            value |= (byte_value & 0x7F) << shift
            if (byte_value & 0x80) == 0:
                values.append(int(value))
                break
            shift += 7
            if shift >= 64:
                # 非法 varint：终止解析
                return values
        else:
            # 未完整读出一个 varint：终止解析
            return values
    return values


def _read_varint(raw_bytes: bytes, start_offset: int) -> Tuple[int, int]:
    value = 0
    shift = 0
    offset = int(start_offset)
    length = len(raw_bytes)
    while offset < length:
        byte_value = raw_bytes[offset]
        offset += 1
        value |= (byte_value & 0x7F) << shift
        if (byte_value & 0x80) == 0:
            return int(value), int(offset)
        shift += 7
        if shift >= 64:
            return int(value), int(offset)
    return int(value), int(offset)


def _parse_shield_tag_override_message(raw_bytes: bytes) -> Optional[Dict[str, Any]]:
    """解析护盾 payload 中的单个 tag override 子消息（只抽取 name + float 值）。"""
    tag_name: Optional[str] = None
    tag_value: Optional[float] = None
    offset = 0
    length = len(raw_bytes)
    while offset < length:
        key, offset = _read_varint(raw_bytes, offset)
        field_number = int(key) >> 3
        wire_type = int(key) & 0x07
        if wire_type == 2:
            size, offset = _read_varint(raw_bytes, offset)
            if offset + size > length:
                break
            chunk = raw_bytes[offset : offset + size]
            offset += size
            if field_number == 1:
                decoded_text = chunk.decode("utf-8", errors="ignore").strip()
                if decoded_text != "":
                    tag_name = decoded_text
        elif wire_type == 5:
            if offset + 4 > length:
                break
            float_value = struct.unpack("<f", raw_bytes[offset : offset + 4])[0]
            offset += 4
            if field_number == 2:
                tag_value = float(float_value)
        elif wire_type == 0:
            _, offset = _read_varint(raw_bytes, offset)
        else:
            break

    if isinstance(tag_name, str) and tag_name.strip() != "":
        return {"tag_name": tag_name.strip(), "value": tag_value}
    return None


def _parse_shield_inner_payload_bytes(inner_bytes: bytes) -> Dict[str, Any]:
    result: Dict[str, Any] = {"attack_tag_overrides": [], "attack_tag_id_ints": []}
    overrides: List[Dict[str, Any]] = []
    tag_id_ints: List[int] = []

    offset = 0
    length = len(inner_bytes)
    while offset < length:
        key, offset = _read_varint(inner_bytes, offset)
        field_number = int(key) >> 3
        wire_type = int(key) & 0x07
        if wire_type == 2:
            size, offset = _read_varint(inner_bytes, offset)
            if offset + size > length:
                break
            chunk = inner_bytes[offset : offset + size]
            offset += size

            if field_number in {1, 2, 4}:
                parsed = _parse_shield_tag_override_message(chunk)
                if isinstance(parsed, dict):
                    parsed["source_field_number"] = int(field_number)
                    overrides.append(parsed)
                    continue

            if field_number == 10:
                tag_id_ints = _decode_varint_stream(chunk)
                continue
        elif wire_type == 0:
            _, offset = _read_varint(inner_bytes, offset)
        elif wire_type == 5:
            if offset + 4 > length:
                break
            offset += 4
        else:
            break

    result["attack_tag_overrides"] = overrides
    result["attack_tag_id_ints"] = tag_id_ints
    return result


def _extract_shield_semantics_from_decoded(decoded_wrapper: Dict[str, Any]) -> Dict[str, Any]:
    """从 type_code=22（护盾）解码结果中抽取可稳定语义化的信息。"""
    result: Dict[str, Any] = {"attack_tag_overrides": [], "attack_tag_id_ints": []}
    decoded_root = decoded_wrapper.get("decoded")
    if not isinstance(decoded_root, dict):
        return result

    root_message = _try_extract_message(decoded_root.get("field_1"))
    if root_message is None:
        # decode_gil 可能把 inner payload 当作文本：此时 field_1 为 {raw_hex, utf8}
        field_1_node = decoded_root.get("field_1")
        if isinstance(field_1_node, dict):
            raw_hex = field_1_node.get("raw_hex")
            if isinstance(raw_hex, str) and raw_hex:
                return _parse_shield_inner_payload_bytes(bytes.fromhex(raw_hex))
        return result

    # 经验：field_1/field_2/field_4 多为 “标签名 + 数值” 对
    overrides: List[Dict[str, Any]] = []
    for field_key in ("field_1", "field_2", "field_4"):
        item_message = _try_extract_message(root_message.get(field_key))
        if item_message is None:
            continue
        tag_name = _try_extract_utf8(item_message.get("field_1"))
        tag_value = _try_extract_fixed32_float(item_message.get("field_2"))
        if isinstance(tag_name, str) and tag_name.strip() != "":
            overrides.append(
                {
                    "tag_name": tag_name,
                    "value": tag_value,
                    "source_field": field_key,
                }
            )
    result["attack_tag_overrides"] = overrides

    # packed ids：root_message.field_10.raw_hex
    field_10_obj = root_message.get("field_10")
    if isinstance(field_10_obj, dict):
        raw_hex = field_10_obj.get("raw_hex")
        if isinstance(raw_hex, str) and raw_hex:
            raw_bytes = bytes.fromhex(raw_hex)
            result["attack_tag_id_ints"] = _decode_varint_stream(raw_bytes)

    return result


def export_shield_entry(
    *,
    section15_entry: Dict[str, Any],
    entry_id_int: int,
    type_code_int: int,
    entry_name: str,
    source_path_text: str,
    context: Section15ExportContext,
    result: Dict[str, Any],
) -> None:
    shield_id = f"shield_{entry_id_int}__{context.package_namespace}"
    raw_file_name = f"ugc_shield_{entry_id_int}.pyugc.json"
    raw_file_path = context.shield_raw_directory / raw_file_name
    _write_json_file(raw_file_path, section15_entry)

    decoded_shield = _try_decode_section15_meta_data(section15_entry, 51, "61@data")
    decoded_shield_rel_path: Optional[str] = None
    shield_semantics: Dict[str, Any] = {}
    if decoded_shield is not None:
        decoded_file_path = context.shield_raw_directory / f"ugc_shield_{entry_id_int}.decoded.json"
        _write_json_file(decoded_file_path, decoded_shield)
        decoded_shield_rel_path = str(decoded_file_path.relative_to(context.output_package_root)).replace("\\", "/")
        shield_semantics = _extract_shield_semantics_from_decoded(decoded_shield)

    attack_tag_overrides = (
        shield_semantics.get("attack_tag_overrides")
        if isinstance(shield_semantics.get("attack_tag_overrides"), list)
        else []
    )
    attack_tags = [
        item.get("tag_name")
        for item in attack_tag_overrides
        if isinstance(item, dict) and isinstance(item.get("tag_name"), str) and item.get("tag_name").strip()
    ]
    attack_tag_id_ints = (
        shield_semantics.get("attack_tag_id_ints") if isinstance(shield_semantics.get("attack_tag_id_ints"), list) else []
    )

    shield_object: Dict[str, Any] = {
        "shield_id": shield_id,
        "shield_name": entry_name,
        "absorbable_damage_types": [],
        "remove_when_depleted": True,
        "show_ui": True,
        "ui_color": "#00FFFF",
        "damage_ratio": 1.0,
        "shield_value": 0.0,
        "ignore_shield_amplification": False,
        "infinite_absorption": False,
        "absorption_ratio": 1.0,
        "settlement_priority": 0,
        "layer_based_effect": False,
        "nullify_overflow_damage": False,
        "attack_tags": list(attack_tags),
        "description": "",
        "shield_type": "absorb",
        "duration": 0.0,
        "absorb_types": [],
        "visual_effect": "",
        "metadata": {
            "ugc": {
                "source_entry_id_int": entry_id_int,
                "source_type_code": type_code_int,
                "source_pyugc_path": source_path_text,
                "raw_pyugc_entry": str(raw_file_path.relative_to(context.output_package_root)).replace("\\", "/"),
                "decoded": decoded_shield_rel_path,
                "attack_tag_overrides": attack_tag_overrides,
                "attack_tag_id_ints": attack_tag_id_ints,
            }
        },
        "updated_at": "",
        "name": entry_name,
    }
    output_file_name = _sanitize_filename(f"{entry_name}_{entry_id_int}") + ".json"
    output_path = context.shield_directory / output_file_name
    _write_json_file(output_path, shield_object)
    result["shields"].append(
        {
            "shield_id": shield_id,
            "shield_name": entry_name,
            "output": str(output_path.relative_to(context.output_package_root)).replace("\\", "/"),
        }
    )


