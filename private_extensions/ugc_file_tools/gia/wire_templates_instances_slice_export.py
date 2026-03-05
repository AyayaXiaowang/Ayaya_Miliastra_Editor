from __future__ import annotations

"""
wire_templates_instances_slice_export.py

目标：
- 从一个“元件模板+实体摆放(实例)” bundle.gia（Root.field_1 templates / Root.field_2 instances）
  中按 template_root_id_int 做切片导出：仅保留指定 template GraphUnit 与引用它的 instance GraphUnit。

设计动机：
- 项目存档中的 TemplateConfig JSON（由 .gia 导入）通常携带 `metadata.ugc.source_gia_file` 与
  `source_template_root_id_int`。当用户希望“导出回游戏可识别的 .gia 并保留装饰物”时，
  最可靠的方式是 **wire-level 保真切片**，而不是从 JSON 语义重建完整 GraphUnit payload。

注意：
- 该模块只做 wire-level 切片与 Root.filePath 的文件名对齐（其余 bytes 保持来源 bundle 的原样）。
- 输入必须是 bundle.gia 形态；若输入不是该形态会 fail-fast 抛错。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ugc_file_tools.gia.container import unwrap_gia_container, validate_gia_container_file, wrap_gia_container
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_wire_chunks, encode_tag, encode_varint, encode_wire_chunks
from ugc_file_tools.wire.patch import build_length_delimited_value_raw, parse_tag_raw, split_length_delimited_value_raw


@dataclass(frozen=True, slots=True)
class _GraphUnitId:
    class_int: int
    type_int: int
    id_int: int


def _decode_varint_bytes(value_raw: bytes) -> int:
    val = 0
    shift = 0
    for b in bytes(value_raw):
        val |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            break
        shift += 7
    return int(val)


def _try_parse_unit_id(unit_bytes: bytes) -> Optional[_GraphUnitId]:
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=unit_bytes, start_offset=0, end_offset=len(unit_bytes))
    if consumed != len(unit_bytes):
        return None
    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.field_number != 1 or tag.wire_type != 2:
            continue
        _lr, id_payload = split_length_delimited_value_raw(value_raw)
        id_chunks_raw, consumed2 = decode_message_to_wire_chunks(data_bytes=id_payload, start_offset=0, end_offset=len(id_payload))
        if consumed2 != len(id_payload):
            return None
        class_int: Optional[int] = None
        type_int: Optional[int] = None
        id_int: Optional[int] = None
        for t_raw, v_raw in id_chunks_raw:
            t = parse_tag_raw(t_raw)
            if t.wire_type != 0:
                continue
            if t.field_number == 2:
                class_int = int(_decode_varint_bytes(v_raw))
            elif t.field_number == 3:
                type_int = int(_decode_varint_bytes(v_raw))
            elif t.field_number == 4:
                id_int = int(_decode_varint_bytes(v_raw))
        if not (isinstance(class_int, int) and isinstance(type_int, int) and isinstance(id_int, int)):
            return None
        return _GraphUnitId(class_int=int(class_int), type_int=int(type_int), id_int=int(id_int))
    return None


def _try_parse_unit_which(unit_bytes: bytes) -> Optional[int]:
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=unit_bytes, start_offset=0, end_offset=len(unit_bytes))
    if consumed != len(unit_bytes):
        return None
    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.field_number == 5 and tag.wire_type == 0:
            return int(_decode_varint_bytes(value_raw))
    return None


def _is_template_unit(unit_bytes: bytes) -> bool:
    uid = _try_parse_unit_id(unit_bytes)
    which = _try_parse_unit_which(unit_bytes)
    return bool(uid is not None and uid.class_int == 1 and uid.type_int == 1 and which == 1)


def _is_instance_unit(unit_bytes: bytes) -> bool:
    uid = _try_parse_unit_id(unit_bytes)
    which = _try_parse_unit_which(unit_bytes)
    return bool(uid is not None and uid.class_int == 1 and uid.type_int == 14 and which == 28)


def _derive_file_path_from_base(*, base_file_path: str, output_file_name: str) -> str:
    base = str(base_file_path or "").strip()
    out_name = str(output_file_name or "").strip()
    if out_name == "":
        return base
    if base == "":
        return out_name
    marker = "\\"
    last = base.rfind(marker)
    if last < 0:
        return base + marker + out_name
    return base[: last + 1] + out_name


def _find_instance_payload_bytes(instance_unit_bytes: bytes) -> Optional[bytes]:
    """
    经验：instances 使用 GraphUnit.field_21 作为 wrapper，wrapper.field_1 为 payload(message)。
    """
    chunks_raw, consumed = decode_message_to_wire_chunks(
        data_bytes=instance_unit_bytes, start_offset=0, end_offset=len(instance_unit_bytes)
    )
    if consumed != len(instance_unit_bytes):
        return None
    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.field_number != 21 or tag.wire_type != 2:
            continue
        _lr, wrapper_bytes = split_length_delimited_value_raw(value_raw)
        wrapper_chunks_raw, consumed2 = decode_message_to_wire_chunks(
            data_bytes=wrapper_bytes, start_offset=0, end_offset=len(wrapper_bytes)
        )
        if consumed2 != len(wrapper_bytes):
            continue
        for wtag_raw, wvalue_raw in wrapper_chunks_raw:
            wtag = parse_tag_raw(wtag_raw)
            if wtag.field_number == 1 and wtag.wire_type == 2:
                _lr2, payload_bytes = split_length_delimited_value_raw(wvalue_raw)
                return bytes(payload_bytes)
    return None


def _extract_template_root_id_from_instance_payload(payload_bytes: bytes) -> Optional[int]:
    """
    经验路径（已用真源样本验证）：
    - payload.field_4[*].field_50.message.field_502 -> template_root_id_int
    """
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=payload_bytes, start_offset=0, end_offset=len(payload_bytes))
    if consumed != len(payload_bytes):
        return None
    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.field_number != 4 or tag.wire_type != 2:
            continue
        _lr, entry_payload = split_length_delimited_value_raw(value_raw)
        entry_chunks_raw, consumed2 = decode_message_to_wire_chunks(data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload))
        if consumed2 != len(entry_payload):
            continue
        for etag_raw, evalue_raw in entry_chunks_raw:
            etag = parse_tag_raw(etag_raw)
            if etag.field_number != 50 or etag.wire_type != 2:
                continue
            _lr2, nested_payload = split_length_delimited_value_raw(evalue_raw)
            nested_chunks_raw, consumed3 = decode_message_to_wire_chunks(
                data_bytes=nested_payload, start_offset=0, end_offset=len(nested_payload)
            )
            if consumed3 != len(nested_payload):
                continue
            for ntag_raw, nvalue_raw in nested_chunks_raw:
                ntag = parse_tag_raw(ntag_raw)
                if ntag.field_number == 502 and ntag.wire_type == 0:
                    return int(_decode_varint_bytes(nvalue_raw))
    return None


def slice_templates_instances_bundle_gia_wire(
    *,
    input_bundle_gia: Path,
    output_bundle_gia: Path,
    template_root_id_int: int,
    check_header: bool,
) -> Dict[str, Any]:
    input_bundle_gia = Path(input_bundle_gia).resolve()
    if check_header:
        validate_gia_container_file(input_bundle_gia)

    proto_bytes = unwrap_gia_container(input_bundle_gia, check_header=False)
    root_chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=proto_bytes, start_offset=0, end_offset=len(proto_bytes))
    if consumed != len(proto_bytes):
        raise ValueError("root wire decode not fully consumed")

    base_file_path_text = ""
    templates_units: List[bytes] = []
    instances_units: List[bytes] = []
    used_ids: Set[int] = set()

    for tag_raw, value_raw in root_chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.field_number == 3 and tag.wire_type == 2 and base_file_path_text == "":
            _lr, payload = split_length_delimited_value_raw(value_raw)
            base_file_path_text = payload.decode("utf-8", errors="replace")
        if tag.field_number == 1 and tag.wire_type == 2:
            _lr, payload = split_length_delimited_value_raw(value_raw)
            b = bytes(payload)
            templates_units.append(b)
            uid = _try_parse_unit_id(b)
            if uid is not None:
                used_ids.add(int(uid.id_int))
        elif tag.field_number == 2 and tag.wire_type == 2:
            _lr, payload = split_length_delimited_value_raw(value_raw)
            b = bytes(payload)
            instances_units.append(b)
            uid = _try_parse_unit_id(b)
            if uid is not None:
                used_ids.add(int(uid.id_int))

    templates_only = [u for u in templates_units if _is_template_unit(u)]
    instances_only = [u for u in instances_units if _is_instance_unit(u)]
    if not templates_only:
        raise ValueError("输入 .gia 不包含 templates（Root.field_1, class=1,type=1,which=1）")

    selected_templates: List[bytes] = []
    for u in list(templates_only):
        uid = _try_parse_unit_id(u)
        if uid is not None and int(uid.id_int) == int(template_root_id_int):
            selected_templates.append(u)
    if not selected_templates:
        raise ValueError(f"未在输入 .gia 中找到 template_root_id_int={int(template_root_id_int)} 的模板 GraphUnit")

    selected_instances: List[bytes] = []
    selected_instance_ids: Set[int] = set()
    for inst in instances_only:
        uid = _try_parse_unit_id(inst)
        if uid is None:
            continue
        payload = _find_instance_payload_bytes(inst)
        if payload is None:
            continue
        tid = _extract_template_root_id_from_instance_payload(payload)
        if isinstance(tid, int) and int(tid) == int(template_root_id_int):
            selected_instances.append(inst)
            selected_instance_ids.add(int(uid.id_int))

    output_name = str(Path(output_bundle_gia).name)
    new_file_path = _derive_file_path_from_base(base_file_path=base_file_path_text, output_file_name=output_name)
    new_file_path_value_raw = build_length_delimited_value_raw(new_file_path.encode("utf-8"))

    # rebuild root: keep all non-unit chunks; patch filePath; keep only selected template+instances chunks in place.
    out_root_chunks: List[Tuple[bytes, bytes]] = []
    file_path_written = False
    kept_templates_count = 0
    kept_instances_count = 0
    for tag_raw, value_raw in root_chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.field_number == 3 and tag.wire_type == 2 and (not file_path_written):
            out_root_chunks.append((bytes(tag_raw), bytes(new_file_path_value_raw)))
            file_path_written = True
            continue
        if tag.field_number == 1 and tag.wire_type == 2:
            _lr, payload = split_length_delimited_value_raw(value_raw)
            unit_bytes = bytes(payload)
            uid = _try_parse_unit_id(unit_bytes)
            if uid is None:
                continue
            if int(uid.id_int) != int(template_root_id_int):
                continue
            if not _is_template_unit(unit_bytes):
                continue
            out_root_chunks.append((bytes(tag_raw), bytes(value_raw)))
            kept_templates_count += 1
            continue
        if tag.field_number == 2 and tag.wire_type == 2:
            _lr, payload = split_length_delimited_value_raw(value_raw)
            unit_bytes = bytes(payload)
            uid = _try_parse_unit_id(unit_bytes)
            if uid is None:
                continue
            if int(uid.id_int) not in selected_instance_ids:
                continue
            if not _is_instance_unit(unit_bytes):
                continue
            out_root_chunks.append((bytes(tag_raw), bytes(value_raw)))
            kept_instances_count += 1
            continue
        out_root_chunks.append((bytes(tag_raw), bytes(value_raw)))

    if not file_path_written:
        out_root_chunks.append((encode_tag(3, 2), new_file_path_value_raw))

    out_proto = encode_wire_chunks(out_root_chunks)
    output_bundle_gia = Path(output_bundle_gia).resolve()
    output_bundle_gia.parent.mkdir(parents=True, exist_ok=True)
    output_bundle_gia.write_bytes(wrap_gia_container(out_proto))

    return {
        "input_bundle_gia": str(input_bundle_gia),
        "output_bundle_gia": str(output_bundle_gia),
        "template_root_id_int": int(template_root_id_int),
        "selected_templates_count": int(len(selected_templates)),
        "selected_instances_count": int(len(selected_instances)),
        "kept_templates_count": int(kept_templates_count),
        "kept_instances_count": int(kept_instances_count),
        "file_path": str(new_file_path),
        "used_unit_ids_total_in_source": int(len(used_ids)),
    }

