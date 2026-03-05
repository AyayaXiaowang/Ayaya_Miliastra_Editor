from __future__ import annotations

"""
merge_signal_entries.py

wire-level 合并 `.gil` 内两条 signal entry，并重绑 NodeGraph 内信号节点引用。

典型用途：
- 官方编辑器导入节点图时，因信号名冲突/缺失导致自动新建占位符信号（例如 `信号_3`），与目标正式信号重复；
- 需要将两条 entry 合并为 1 条，并确保所有节点图内的发送/监听/向服务器发送信号节点都绑定到同一套 node_def/端口索引。

设计原则：
- 最小改动：以 wire chunks 为单位 patch，避免整包 decode→re-encode 带来的字段漂移；
- fail-fast：结构不符合预期直接抛错，不猜测、不吞异常；
- 显式指定：调用方必须明确给出 keep/remove 信号名（可选将 keep entry 重命名为新名字）。
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gil.signal_scanner import summarize_signal_entries
from ugc_file_tools.gil_dump_codec.dump_json_tree import load_gil_payload_as_numeric_message
from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_varint, encode_tag, encode_varint
from ugc_file_tools.gil_package_exporter.gil_reader import read_gil_header
from ugc_file_tools.wire.codec import decode_message_to_wire_chunks, encode_wire_chunks
from ugc_file_tools.wire.patch import build_length_delimited_value_raw, parse_tag_raw, split_length_delimited_value_raw


@dataclass(frozen=True, slots=True)
class _SignalSummary:
    signal_name: str
    param_count: int
    signal_index_int: int | None
    send_id_int: int
    listen_id_int: int
    server_id_int: int
    send_signal_name_port_index_int: int | None
    listen_signal_name_port_index_int: int | None
    server_signal_name_port_index_int: int | None
    send_param_port_indices_int: list[int]
    listen_param_port_indices_int: list[int]
    server_param_port_indices_int: list[int]


def _as_int_list(value: Any) -> list[int]:
    if value is None:
        return []
    if isinstance(value, list):
        return [int(x) for x in value if isinstance(x, int)]
    return [int(value)] if isinstance(value, int) else []


def _coerce_signal_summary(raw: Mapping[str, Any]) -> _SignalSummary:
    name = str(raw.get("signal_name") or "").strip()
    if name == "":
        raise ValueError("invalid signal summary: empty signal_name")
    param_count = raw.get("param_count")
    if not isinstance(param_count, int):
        raise ValueError(f"invalid signal summary: param_count not int for {name!r}")

    send_id = raw.get("send_id_int")
    listen_id = raw.get("listen_id_int")
    server_id = raw.get("server_id_int")
    if not (isinstance(send_id, int) and isinstance(listen_id, int) and isinstance(server_id, int)):
        raise ValueError(f"invalid signal summary: missing node_def ids for {name!r}")

    return _SignalSummary(
        signal_name=name,
        param_count=int(param_count),
        signal_index_int=(int(raw.get("signal_index_int")) if isinstance(raw.get("signal_index_int"), int) else None),
        send_id_int=int(send_id),
        listen_id_int=int(listen_id),
        server_id_int=int(server_id),
        send_signal_name_port_index_int=(
            int(raw.get("send_signal_name_port_index_int"))
            if isinstance(raw.get("send_signal_name_port_index_int"), int)
            else None
        ),
        listen_signal_name_port_index_int=(
            int(raw.get("listen_signal_name_port_index_int"))
            if isinstance(raw.get("listen_signal_name_port_index_int"), int)
            else None
        ),
        server_signal_name_port_index_int=(
            int(raw.get("server_signal_name_port_index_int"))
            if isinstance(raw.get("server_signal_name_port_index_int"), int)
            else None
        ),
        send_param_port_indices_int=_as_int_list(raw.get("send_param_port_indices_int")),
        listen_param_port_indices_int=_as_int_list(raw.get("listen_param_port_indices_int")),
        server_param_port_indices_int=_as_int_list(raw.get("server_param_port_indices_int")),
    )


def _decode_chunks(payload_bytes: bytes) -> list[tuple[bytes, bytes]]:
    chunks, consumed = decode_message_to_wire_chunks(
        data_bytes=payload_bytes,
        start_offset=0,
        end_offset=len(payload_bytes),
    )
    if consumed != len(payload_bytes):
        raise ValueError(f"wire decode consumed mismatch: consumed={consumed}, total={len(payload_bytes)}")
    return list(chunks)


def _decode_varint_value(value_raw: bytes) -> int:
    value, offset, ok = decode_varint(value_raw, 0, len(value_raw))
    if not ok or offset != len(value_raw):
        raise ValueError("invalid varint value_raw")
    return int(value)


def _get_first_varint_field(message_payload: bytes, field_number: int) -> int | None:
    for tag_raw, value_raw in _decode_chunks(message_payload):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number == int(field_number) and parsed.wire_type == 0:
            return _decode_varint_value(value_raw)
    return None


def _set_first_varint_field(message_payload: bytes, field_number: int, new_value: int) -> tuple[bytes, bool]:
    changed = False
    out: list[tuple[bytes, bytes]] = []
    for tag_raw, value_raw in _decode_chunks(message_payload):
        parsed = parse_tag_raw(tag_raw)
        if (not changed) and parsed.field_number == int(field_number) and parsed.wire_type == 0:
            old_value = _decode_varint_value(value_raw)
            if int(old_value) != int(new_value):
                changed = True
            out.append((tag_raw, encode_varint(int(new_value))))
            continue
        out.append((tag_raw, value_raw))
    return encode_wire_chunks(out), bool(changed)


def _decode_utf8_or_none(text_bytes: bytes) -> str | None:
    try:
        return text_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _get_first_string_field(message_payload: bytes, field_number: int) -> str | None:
    for tag_raw, value_raw in _decode_chunks(message_payload):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number == int(field_number) and parsed.wire_type == 2:
            _, text_payload = split_length_delimited_value_raw(value_raw)
            return _decode_utf8_or_none(text_payload)
    return None


def _set_first_string_field(message_payload: bytes, field_number: int, new_text: str) -> tuple[bytes, bool]:
    changed = False
    out: list[tuple[bytes, bytes]] = []
    for tag_raw, value_raw in _decode_chunks(message_payload):
        parsed = parse_tag_raw(tag_raw)
        if (not changed) and parsed.field_number == int(field_number) and parsed.wire_type == 2:
            _, old_payload = split_length_delimited_value_raw(value_raw)
            old_text = _decode_utf8_or_none(old_payload)
            target = str(new_text)
            if old_text != target:
                changed = True
            out.append((tag_raw, build_length_delimited_value_raw(target.encode("utf-8"))))
            continue
        out.append((tag_raw, value_raw))
    return encode_wire_chunks(out), bool(changed)


def _find_first_ld_field(chunks: Sequence[tuple[bytes, bytes]], field_number: int) -> tuple[int, bytes]:
    for idx, (tag_raw, value_raw) in enumerate(list(chunks)):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number == int(field_number) and parsed.wire_type == 2:
            _, payload = split_length_delimited_value_raw(value_raw)
            return int(idx), payload
    raise ValueError(f"missing length-delimited field: {field_number}")


def _iter_signal_entry_chunk_indices_by_name(
    *, section5_chunks: Sequence[tuple[bytes, bytes]]
) -> dict[str, list[int]]:
    mapping: dict[str, list[int]] = {}
    for chunk_index, (tag_raw, value_raw) in enumerate(list(section5_chunks)):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number != 3 or parsed.wire_type != 2:
            continue
        _, entry_payload = split_length_delimited_value_raw(value_raw)
        name = str(_get_first_string_field(entry_payload, 3) or "").strip()
        if name == "":
            continue
        mapping.setdefault(name, []).append(int(chunk_index))
    return mapping


def _extract_pin_kind_and_index(pin_payload: bytes) -> tuple[int, int]:
    """
    读取 pin.field_1(i1) 的 (kind,index)。

    注意：index==0 在部分编码中会省略 field_2，因此缺失时按 0 处理，
    避免无法命中 “第 0 个参数 pin” 的补丁。
    """
    kind_int = 0
    index_int = 0
    for tag_raw, value_raw in _decode_chunks(pin_payload):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number != 1 or parsed.wire_type != 2:
            continue
        _, i1_payload = split_length_delimited_value_raw(value_raw)
        kind = _get_first_varint_field(i1_payload, 1)
        idx = _get_first_varint_field(i1_payload, 2)
        kind_int = int(kind) if isinstance(kind, int) else 0
        index_int = int(idx) if isinstance(idx, int) else 0
        return int(kind_int), int(index_int)
    return int(kind_int), int(index_int)


def _patch_pin_field7_composite_index(pin_payload: bytes, *, new_cpi: int) -> tuple[bytes, bool]:
    changed = False
    has_field7 = False
    out: list[tuple[bytes, bytes]] = []
    for tag_raw, value_raw in _decode_chunks(pin_payload):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number == 7 and parsed.wire_type == 0:
            has_field7 = True
            old_value = _decode_varint_value(value_raw)
            if int(old_value) != int(new_cpi):
                changed = True
            out.append((tag_raw, encode_varint(int(new_cpi))))
            continue
        out.append((tag_raw, value_raw))
    if not has_field7:
        out.append((encode_tag(7, 0), encode_varint(int(new_cpi))))
        changed = True
    if not changed:
        return pin_payload, False
    return encode_wire_chunks(out), True


def _patch_varbase_string_value(varbase_payload: bytes, *, new_text: str) -> tuple[bytes, int]:
    """
    仅修补 VarBase(StringBase) 的实际字符串值（field_105.StringBaseValue.field_1）。

    兼容 ConcreteBase(10000) 包裹：递归 patch inner VarBase。
    """
    cls = _get_first_varint_field(varbase_payload, 1)

    # ConcreteBase: unwrap inner value (field_110.concrete.field_2)
    if isinstance(cls, int) and int(cls) == 10000:
        out_chunks: list[tuple[bytes, bytes]] = []
        changed_count = 0
        for tag_raw, value_raw in _decode_chunks(varbase_payload):
            parsed = parse_tag_raw(tag_raw)
            if parsed.field_number == 110 and parsed.wire_type == 2:
                _, concrete_payload = split_length_delimited_value_raw(value_raw)
                concrete_out: list[tuple[bytes, bytes]] = []
                concrete_changed = 0
                for c_tag_raw, c_value_raw in _decode_chunks(concrete_payload):
                    c_parsed = parse_tag_raw(c_tag_raw)
                    if c_parsed.field_number == 2 and c_parsed.wire_type == 2:
                        _, inner_payload = split_length_delimited_value_raw(c_value_raw)
                        patched_inner, delta = _patch_varbase_string_value(inner_payload, new_text=str(new_text))
                        if delta > 0:
                            concrete_changed += int(delta)
                            concrete_out.append((c_tag_raw, build_length_delimited_value_raw(patched_inner)))
                            continue
                    concrete_out.append((c_tag_raw, c_value_raw))
                if concrete_changed > 0:
                    changed_count += int(concrete_changed)
                    out_chunks.append((tag_raw, build_length_delimited_value_raw(encode_wire_chunks(concrete_out))))
                else:
                    out_chunks.append((tag_raw, value_raw))
                continue
            out_chunks.append((tag_raw, value_raw))
        if changed_count > 0:
            return encode_wire_chunks(out_chunks), int(changed_count)
        return varbase_payload, 0

    # 非 StringBase：不做任何修改（避免误伤其它 VarBase）
    if not (isinstance(cls, int) and int(cls) == 5):
        return varbase_payload, 0

    out_chunks: list[tuple[bytes, bytes]] = []
    changed_count = 0
    for tag_raw, value_raw in _decode_chunks(varbase_payload):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number == 105 and parsed.wire_type == 2:
            _, string_base_payload = split_length_delimited_value_raw(value_raw)
            patched_string_base_payload, changed = _set_first_string_field(string_base_payload, 1, str(new_text))
            if changed:
                changed_count += 1
                out_chunks.append((tag_raw, build_length_delimited_value_raw(patched_string_base_payload)))
            else:
                out_chunks.append((tag_raw, value_raw))
            continue
        out_chunks.append((tag_raw, value_raw))
    if changed_count > 0:
        return encode_wire_chunks(out_chunks), int(changed_count)
    return varbase_payload, 0


def _patch_meta_pin_payload(pin_payload: bytes, *, new_name: str, new_cpi: Optional[int]) -> tuple[bytes, int]:
    """
    修补 META pin(kind=5)：更新信号名字符串；若 new_cpi 不为空则写入/覆盖 field_7(compositePinIndex)。
    """
    changed_count = 0
    out: list[tuple[bytes, bytes]] = []
    has_field7 = False
    for tag_raw, value_raw in _decode_chunks(pin_payload):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number == 3 and parsed.wire_type == 2:
            _, varbase_payload = split_length_delimited_value_raw(value_raw)
            patched_vb, delta = _patch_varbase_string_value(varbase_payload, new_text=str(new_name))
            if delta > 0:
                changed_count += int(delta)
                out.append((tag_raw, build_length_delimited_value_raw(patched_vb)))
            else:
                out.append((tag_raw, value_raw))
            continue
        if (new_cpi is not None) and parsed.field_number == 7 and parsed.wire_type == 0:
            has_field7 = True
            old_value = _decode_varint_value(value_raw)
            if int(old_value) != int(new_cpi):
                changed_count += 1
            out.append((tag_raw, encode_varint(int(new_cpi))))
            continue
        out.append((tag_raw, value_raw))
    if new_cpi is not None and (not has_field7):
        out.append((encode_tag(7, 0), encode_varint(int(new_cpi))))
        changed_count += 1
    if changed_count == 0:
        return pin_payload, 0
    return encode_wire_chunks(out), int(changed_count)


def _extract_node_def_id_from_node_instance(node_payload: bytes) -> int | None:
    for tag_raw, value_raw in _decode_chunks(node_payload):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number == 2 and parsed.wire_type == 2:
            _, meta_payload = split_length_delimited_value_raw(value_raw)
            return _get_first_varint_field(meta_payload, 5)
    return None


def _patch_node_instance_ids(node_payload: bytes, *, id_remap: Mapping[int, int]) -> tuple[bytes, int]:
    out_chunks: list[tuple[bytes, bytes]] = []
    changed_count = 0
    for tag_raw, value_raw in _decode_chunks(node_payload):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number in (2, 3) and parsed.wire_type == 2:
            _, meta_payload = split_length_delimited_value_raw(value_raw)
            old_id = _get_first_varint_field(meta_payload, 5)
            if isinstance(old_id, int) and int(old_id) in id_remap:
                new_id = int(id_remap[int(old_id)])
                patched_meta, changed = _set_first_varint_field(meta_payload, 5, new_id)
                if changed:
                    changed_count += 1
                out_chunks.append((tag_raw, build_length_delimited_value_raw(patched_meta)))
                continue
        out_chunks.append((tag_raw, value_raw))
    if changed_count == 0:
        return node_payload, 0
    return encode_wire_chunks(out_chunks), int(changed_count)


def _patch_node_def_signal_name(node_def_payload: bytes, *, signal_name: str) -> tuple[bytes, int]:
    """
    node_def.field_107.*.field_1（嵌套 message）写入新的 signal_name。
    """
    changed_count = 0
    out_chunks: list[tuple[bytes, bytes]] = []
    for tag_raw, value_raw in _decode_chunks(node_def_payload):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number == 107 and parsed.wire_type == 2:
            _, signal_payload = split_length_delimited_value_raw(value_raw)
            signal_out: list[tuple[bytes, bytes]] = []
            for signal_tag_raw, signal_value_raw in _decode_chunks(signal_payload):
                signal_parsed = parse_tag_raw(signal_tag_raw)
                if signal_parsed.wire_type == 2 and signal_parsed.field_number in (101, 102):
                    _, inner_payload = split_length_delimited_value_raw(signal_value_raw)
                    patched_inner_payload, changed = _set_first_string_field(inner_payload, 1, str(signal_name))
                    if changed:
                        changed_count += 1
                    signal_out.append((signal_tag_raw, build_length_delimited_value_raw(patched_inner_payload)))
                    continue
                signal_out.append((signal_tag_raw, signal_value_raw))
            out_chunks.append((tag_raw, build_length_delimited_value_raw(encode_wire_chunks(signal_out))))
            continue
        out_chunks.append((tag_raw, value_raw))
    if changed_count == 0:
        return node_def_payload, 0
    return encode_wire_chunks(out_chunks), int(changed_count)


def _extract_node_def_id_from_node_def_payload(node_def_payload: bytes) -> int | None:
    for tag_raw, value_raw in _decode_chunks(node_def_payload):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number != 4 or parsed.wire_type != 2:
            continue
        _, meta_payload = split_length_delimited_value_raw(value_raw)
        for meta_tag_raw, meta_value_raw in _decode_chunks(meta_payload):
            meta_parsed = parse_tag_raw(meta_tag_raw)
            if meta_parsed.field_number == 1 and meta_parsed.wire_type == 2:
                _, inner_meta = split_length_delimited_value_raw(meta_value_raw)
                return _get_first_varint_field(inner_meta, 5)
    return None


def _extract_node_def_id_from_wrapper_payload(wrapper_payload: bytes) -> int | None:
    for tag_raw, value_raw in _decode_chunks(wrapper_payload):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number != 1 or parsed.wire_type != 2:
            continue
        _, node_def_payload = split_length_delimited_value_raw(value_raw)
        return _extract_node_def_id_from_node_def_payload(node_def_payload)
    return None


def merge_gil_signal_entries(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    keep_signal_name: str,
    remove_signal_name: str,
    rename_keep_to: str = "",
    patch_composite_pin_index: bool = True,
) -> dict:
    input_path = Path(input_gil_file_path).resolve()
    output_path = Path(output_gil_file_path).resolve()
    keep_name = str(keep_signal_name or "").strip()
    remove_name = str(remove_signal_name or "").strip()
    rename_to = str(rename_keep_to or "").strip()
    if keep_name == "" or remove_name == "":
        raise ValueError("keep/remove signal_name cannot be empty")
    if keep_name == remove_name:
        raise ValueError("keep_signal_name and remove_signal_name must differ")
    if rename_to == "":
        rename_to = keep_name

    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))
    if output_path == input_path:
        raise ValueError("output path cannot be the same as input path")
    if output_path.suffix.lower() != ".gil":
        raise ValueError(f"output file must be .gil: {str(output_path)}")

    # Read-only summaries (best-effort) to resolve node_def ids + port indices for the kept entry.
    payload_root = load_gil_payload_as_numeric_message(input_path)
    summaries_raw = summarize_signal_entries(payload_root)

    def _find_unique_summary(name: str) -> _SignalSummary:
        candidates = [s for s in summaries_raw if str(s.get("signal_name") or "").strip() == str(name).strip()]
        if len(candidates) != 1:
            brief = [
                {
                    "signal_name": str(s.get("signal_name") or ""),
                    "param_count": s.get("param_count"),
                    "signal_index_int": s.get("signal_index_int"),
                    "send_id_int": s.get("send_id_int"),
                }
                for s in candidates[:10]
            ]
            raise ValueError(
                f"expected exactly 1 signal entry for {name!r}, got {len(candidates)}. "
                f"candidates(head)={json.dumps(brief, ensure_ascii=False)}"
            )
        return _coerce_signal_summary(candidates[0])

    keep_summary = _find_unique_summary(keep_name)
    remove_summary = _find_unique_summary(remove_name)

    canonical_send_id = int(keep_summary.send_id_int)
    canonical_listen_id = int(keep_summary.listen_id_int)
    canonical_server_id = int(keep_summary.server_id_int)

    removed_node_def_ids = {int(remove_summary.send_id_int), int(remove_summary.listen_id_int), int(remove_summary.server_id_int)}

    id_remap: dict[int, int] = {
        int(remove_summary.send_id_int): canonical_send_id,
        int(remove_summary.listen_id_int): canonical_listen_id,
        int(remove_summary.server_id_int): canonical_server_id,
    }

    # Port indices for compositePinIndex patching (derived from kept entry).
    ports_by_role: dict[str, dict[str, Any]] = {
        "send": {
            "meta": keep_summary.send_signal_name_port_index_int,
            "params": list(keep_summary.send_param_port_indices_int),
        },
        "listen": {
            "meta": keep_summary.listen_signal_name_port_index_int,
            "params": list(keep_summary.listen_param_port_indices_int),
        },
        "server": {
            "meta": keep_summary.server_signal_name_port_index_int,
            "params": list(keep_summary.server_param_port_indices_int),
        },
    }

    if patch_composite_pin_index:
        for role, spec in ports_by_role.items():
            meta_idx = spec.get("meta")
            params = spec.get("params")
            if keep_summary.param_count > 0 and not isinstance(meta_idx, int):
                raise ValueError(
                    f"kept entry {keep_name!r} missing {role}.signal_name_port_index_int; cannot patch compositePinIndex safely"
                )
            if keep_summary.param_count > 0 and isinstance(params, list) and len(params) < int(keep_summary.param_count):
                raise ValueError(
                    f"kept entry {keep_name!r} missing {role}.param_port_indices (have {len(params)} < expected {keep_summary.param_count})"
                )

    # --- Read raw bytes and locate section10/section5 ---
    file_bytes = input_path.read_bytes()
    header = read_gil_header(file_bytes)
    payload_bytes = file_bytes[20 : 20 + int(header.body_size)]
    if len(payload_bytes) != int(header.body_size):
        raise ValueError(
            f"gil payload size mismatch: expected={int(header.body_size)} got={len(payload_bytes)} path={str(input_path)!r}"
        )

    root_chunks = _decode_chunks(payload_bytes)
    section10_index, section10_payload = _find_first_ld_field(root_chunks, 10)
    section10_chunks = _decode_chunks(section10_payload)

    section5_index, section5_payload = _find_first_ld_field(section10_chunks, 5)
    section5_chunks = _decode_chunks(section5_payload)

    # Locate entry chunk indices by name (wire-level ground truth; used for removal/rename).
    entry_chunk_indices_by_name = _iter_signal_entry_chunk_indices_by_name(section5_chunks=section5_chunks)
    keep_entry_chunks = entry_chunk_indices_by_name.get(keep_name, [])
    remove_entry_chunks = entry_chunk_indices_by_name.get(remove_name, [])
    if len(keep_entry_chunks) != 1:
        raise ValueError(f"expected exactly 1 section5 entry chunk for keep={keep_name!r}, got {keep_entry_chunks}")
    if len(remove_entry_chunks) != 1:
        raise ValueError(f"expected exactly 1 section5 entry chunk for remove={remove_name!r}, got {remove_entry_chunks}")

    keep_entry_chunk_index = int(keep_entry_chunks[0])
    remove_entry_chunk_index = int(remove_entry_chunks[0])

    # --- Patch section5: remove entry + meta ids; rename kept entry ---
    removed_signal_entries = 0
    removed_meta_entries = 0
    entry_name_changes = 0

    patched_section5_chunks: list[tuple[bytes, bytes]] = []
    for chunk_index, (tag_raw, value_raw) in enumerate(list(section5_chunks)):
        parsed = parse_tag_raw(tag_raw)

        # signal entry
        if parsed.field_number == 3 and parsed.wire_type == 2:
            if int(chunk_index) == int(remove_entry_chunk_index):
                removed_signal_entries += 1
                continue

            if int(chunk_index) == int(keep_entry_chunk_index):
                _, entry_payload = split_length_delimited_value_raw(value_raw)
                patched_entry_payload, changed = _set_first_string_field(entry_payload, 3, str(rename_to))
                if changed:
                    entry_name_changes += 1
                patched_section5_chunks.append((tag_raw, build_length_delimited_value_raw(patched_entry_payload)))
                continue

            patched_section5_chunks.append((tag_raw, value_raw))
            continue

        # meta index entry (prune removed node_defs)
        if parsed.field_number == 2 and parsed.wire_type == 2:
            _, meta_payload = split_length_delimited_value_raw(value_raw)
            node_def_id = _get_first_varint_field(meta_payload, 5)
            if isinstance(node_def_id, int) and int(node_def_id) in removed_node_def_ids:
                removed_meta_entries += 1
                continue
            patched_section5_chunks.append((tag_raw, value_raw))
            continue

        patched_section5_chunks.append((tag_raw, value_raw))

    patched_section5_payload = encode_wire_chunks(patched_section5_chunks)
    section5_tag_raw, _section5_value_raw = section10_chunks[section5_index]
    section10_chunks[section5_index] = (section5_tag_raw, build_length_delimited_value_raw(patched_section5_payload))

    # --- Patch graphs: remap ids + patch pins for canonical node_defs ---
    node_instance_id_changes = 0
    node_pin_patches = 0

    def _patch_node_payload(node_payload: bytes) -> tuple[bytes, int, int]:
        """
        Return (patched_payload, id_change_count, pin_patch_count).
        """
        patched, id_delta = _patch_node_instance_ids(node_payload, id_remap=id_remap)
        node_def_id = _extract_node_def_id_from_node_instance(patched)
        if not isinstance(node_def_id, int):
            return patched, int(id_delta), 0

        role: str | None = None
        if int(node_def_id) == int(canonical_send_id):
            role = "send"
        elif int(node_def_id) == int(canonical_listen_id):
            role = "listen"
        elif int(node_def_id) == int(canonical_server_id):
            role = "server"

        if role is None:
            return patched, int(id_delta), 0

        spec = ports_by_role[str(role)]
        meta_cpi = spec.get("meta") if patch_composite_pin_index else None
        param_cpis: list[int] = [int(x) for x in list(spec.get("params") or []) if isinstance(x, int)] if patch_composite_pin_index else []

        changed_pin_count = 0
        node_out: list[tuple[bytes, bytes]] = []
        for tag_raw, value_raw in _decode_chunks(patched):
            parsed = parse_tag_raw(tag_raw)
            if parsed.field_number == 4 and parsed.wire_type == 2:
                _, pin_payload = split_length_delimited_value_raw(value_raw)
                kind, idx = _extract_pin_kind_and_index(pin_payload)

                if kind == 5:
                    patched_pin, delta = _patch_meta_pin_payload(
                        pin_payload,
                        new_name=str(rename_to),
                        new_cpi=(int(meta_cpi) if isinstance(meta_cpi, int) else None),
                    )
                    if delta > 0:
                        changed_pin_count += int(delta)
                        node_out.append((tag_raw, build_length_delimited_value_raw(patched_pin)))
                        continue

                # send/server: param pins are InParam(kind=3)
                if role in ("send", "server") and kind == 3 and isinstance(idx, int) and 0 <= int(idx) < len(param_cpis):
                    patched_pin, changed = _patch_pin_field7_composite_index(pin_payload, new_cpi=int(param_cpis[int(idx)]))
                    if changed:
                        changed_pin_count += 1
                        node_out.append((tag_raw, build_length_delimited_value_raw(patched_pin)))
                        continue

                # listen: param pins are OutParam(kind=4)
                if role == "listen" and kind == 4 and isinstance(idx, int) and 0 <= int(idx) < len(param_cpis):
                    patched_pin, changed = _patch_pin_field7_composite_index(pin_payload, new_cpi=int(param_cpis[int(idx)]))
                    if changed:
                        changed_pin_count += 1
                        node_out.append((tag_raw, build_length_delimited_value_raw(patched_pin)))
                        continue

                node_out.append((tag_raw, value_raw))
                continue

            node_out.append((tag_raw, value_raw))

        if changed_pin_count == 0:
            return patched, int(id_delta), 0
        return encode_wire_chunks(node_out), int(id_delta), int(changed_pin_count)

    patched_section10_after_graphs: list[tuple[bytes, bytes]] = []
    for tag_raw, value_raw in list(section10_chunks):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number != 1 or parsed.wire_type != 2:
            patched_section10_after_graphs.append((tag_raw, value_raw))
            continue

        _, group_payload = split_length_delimited_value_raw(value_raw)
        group_chunks = _decode_chunks(group_payload)

        group_changed = False
        group_out: list[tuple[bytes, bytes]] = []
        for group_tag_raw, group_value_raw in list(group_chunks):
            group_parsed = parse_tag_raw(group_tag_raw)
            if group_parsed.field_number != 1 or group_parsed.wire_type != 2:
                group_out.append((group_tag_raw, group_value_raw))
                continue

            _, graph_entry_payload = split_length_delimited_value_raw(group_value_raw)
            graph_entry_chunks = _decode_chunks(graph_entry_payload)

            graph_changed = False
            graph_out: list[tuple[bytes, bytes]] = []
            for entry_tag_raw, entry_value_raw in list(graph_entry_chunks):
                entry_parsed = parse_tag_raw(entry_tag_raw)
                if entry_parsed.field_number != 3 or entry_parsed.wire_type != 2:
                    graph_out.append((entry_tag_raw, entry_value_raw))
                    continue

                _, node_payload = split_length_delimited_value_raw(entry_value_raw)
                patched_node_payload, id_delta, pin_delta = _patch_node_payload(node_payload)
                if id_delta > 0 or pin_delta > 0:
                    graph_changed = True
                    node_instance_id_changes += int(id_delta)
                    node_pin_patches += int(pin_delta)
                    graph_out.append((entry_tag_raw, build_length_delimited_value_raw(patched_node_payload)))
                else:
                    graph_out.append((entry_tag_raw, entry_value_raw))

            if graph_changed:
                group_changed = True
                group_out.append((group_tag_raw, build_length_delimited_value_raw(encode_wire_chunks(graph_out))))
            else:
                group_out.append((group_tag_raw, group_value_raw))

        if group_changed:
            patched_section10_after_graphs.append((tag_raw, build_length_delimited_value_raw(encode_wire_chunks(group_out))))
        else:
            patched_section10_after_graphs.append((tag_raw, value_raw))

    # --- Patch node_defs: rename canonical defs; remove removed defs ---
    node_def_name_changes = 0
    removed_node_def_wrappers = 0

    section10_after_node_defs: list[tuple[bytes, bytes]] = []
    for tag_raw, value_raw in list(patched_section10_after_graphs):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number != 2 or parsed.wire_type != 2:
            section10_after_node_defs.append((tag_raw, value_raw))
            continue

        _, wrapper_payload = split_length_delimited_value_raw(value_raw)
        node_def_id = _extract_node_def_id_from_wrapper_payload(wrapper_payload)
        if isinstance(node_def_id, int) and int(node_def_id) in removed_node_def_ids:
            removed_node_def_wrappers += 1
            continue

        wrapper_chunks = _decode_chunks(wrapper_payload)
        wrapper_changed = False
        wrapper_out: list[tuple[bytes, bytes]] = []
        for w_tag_raw, w_value_raw in list(wrapper_chunks):
            w_parsed = parse_tag_raw(w_tag_raw)
            if w_parsed.field_number == 1 and w_parsed.wire_type == 2:
                _, node_def_payload = split_length_delimited_value_raw(w_value_raw)
                this_id = _extract_node_def_id_from_node_def_payload(node_def_payload)
                if isinstance(this_id, int) and int(this_id) in {
                    int(canonical_send_id),
                    int(canonical_listen_id),
                    int(canonical_server_id),
                }:
                    patched_node_def_payload, delta = _patch_node_def_signal_name(node_def_payload, signal_name=str(rename_to))
                    if delta > 0:
                        node_def_name_changes += int(delta)
                        wrapper_changed = True
                        wrapper_out.append((w_tag_raw, build_length_delimited_value_raw(patched_node_def_payload)))
                        continue
            wrapper_out.append((w_tag_raw, w_value_raw))

        if wrapper_changed:
            section10_after_node_defs.append((tag_raw, build_length_delimited_value_raw(encode_wire_chunks(wrapper_out))))
        else:
            section10_after_node_defs.append((tag_raw, value_raw))

    patched_section10_payload = encode_wire_chunks(section10_after_node_defs)
    section10_tag_raw, _section10_value_raw = root_chunks[section10_index]
    root_chunks[section10_index] = (section10_tag_raw, build_length_delimited_value_raw(patched_section10_payload))

    output_payload_bytes = encode_wire_chunks(root_chunks)
    container_spec = read_gil_container_spec(input_path)
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=output_payload_bytes, container_spec=container_spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)

    return {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "keep_signal_name": str(keep_name),
        "remove_signal_name": str(remove_name),
        "rename_keep_to": str(rename_to),
        "kept_entry": {
            "signal_name": keep_summary.signal_name,
            "param_count": int(keep_summary.param_count),
            "signal_index_int": keep_summary.signal_index_int,
            "send_id_int": int(keep_summary.send_id_int),
            "listen_id_int": int(keep_summary.listen_id_int),
            "server_id_int": int(keep_summary.server_id_int),
        },
        "removed_entry": {
            "signal_name": remove_summary.signal_name,
            "param_count": int(remove_summary.param_count),
            "signal_index_int": remove_summary.signal_index_int,
            "send_id_int": int(remove_summary.send_id_int),
            "listen_id_int": int(remove_summary.listen_id_int),
            "server_id_int": int(remove_summary.server_id_int),
        },
        "id_remap": {str(k): int(v) for k, v in sorted(id_remap.items(), key=lambda kv: int(kv[0]))},
        "removed_signal_entries": int(removed_signal_entries),
        "removed_meta_entries": int(removed_meta_entries),
        "entry_name_changes": int(entry_name_changes),
        "node_instance_id_changes": int(node_instance_id_changes),
        "node_pin_patches": int(node_pin_patches),
        "node_def_name_changes": int(node_def_name_changes),
        "removed_node_def_wrappers": int(removed_node_def_wrappers),
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description=(
            "wire-level 合并 .gil 内两条 signal entry，并重绑节点图内信号节点引用（删除 remove entry/node_defs，保留 keep entry/node_defs；可选重命名 keep）。"
        )
    )
    parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    parser.add_argument("output_gil_file", help="输出 .gil 文件路径（不能与输入相同）")
    parser.add_argument("--keep-signal-name", dest="keep_signal_name", required=True, help="要保留的 signal entry 名字（按当前 .gil 内名字匹配）")
    parser.add_argument(
        "--remove-signal-name", dest="remove_signal_name", required=True, help="要移除的 signal entry 名字（按当前 .gil 内名字匹配）"
    )
    parser.add_argument(
        "--rename-keep-to",
        dest="rename_keep_to",
        default="",
        help="可选：将 keep entry 重命名为该名字（常用于 keep=占位符，rename_to=正式名）。不传则保持 keep 名字不变。",
    )
    parser.add_argument(
        "--no-patch-composite-pin-index",
        dest="no_patch_cpi",
        action="store_true",
        help="禁用 compositePinIndex(field_7) 补丁（仍会 remap node_def ids + patch META pin 信号名字符串）。",
    )
    parser.add_argument(
        "--report",
        dest="report_json_file",
        default="",
        help="可选：输出修复报告 JSON 文件路径",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    report = merge_gil_signal_entries(
        input_gil_file_path=Path(str(args.input_gil_file)),
        output_gil_file_path=Path(str(args.output_gil_file)),
        keep_signal_name=str(args.keep_signal_name),
        remove_signal_name=str(args.remove_signal_name),
        rename_keep_to=str(args.rename_keep_to),
        patch_composite_pin_index=(not bool(args.no_patch_cpi)),
    )

    report_path_text = str(args.report_json_file or "").strip()
    if report_path_text:
        report_path = Path(report_path_text).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))


__all__ = [
    "merge_gil_signal_entries",
    "main",
]


if __name__ == "__main__":
    main()

