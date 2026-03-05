from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gia.container import unwrap_gia_container
from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map, decode_varint, encode_tag, encode_varint
from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import decoded_field_map_to_numeric_message
from ugc_file_tools.gil_package_exporter.gil_reader import read_gil_header
from ugc_file_tools.wire.codec import decode_message_to_wire_chunks, encode_wire_chunks
from ugc_file_tools.wire.patch import build_length_delimited_value_raw, parse_tag_raw, split_length_delimited_value_raw

_PLACEHOLDER_SIGNAL_NAME_RE = re.compile(r"^信号(?:[_\s\-].*|\d+.*)$")

# ---------------------------------------------------------------------------
# Public API (no leading underscores)
#
# Import policy: cross-module imports must not import underscored private names.
# Keep underscored implementations for internal structure, but expose stable
# public symbols for wrappers (commands/) and other subdomains.

def plan_dedupe_by_signal_index(
    entries: Sequence[SignalEntryInfo],
    *,
    target_signal_names: set[str],
) -> tuple[set[int], dict[int, int], dict[int, str], list[str], list[str]]:
    return _plan_dedupe_by_signal_index(
        entries=entries,
        target_signal_names=target_signal_names,
    )


def repair_gil_signals_from_imported_gia(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    imported_gia_files: Sequence[Path],
    prune_placeholder_orphans: bool,
) -> dict:
    return _repair_gil_signals_from_imported_gia(
        input_gil_file_path=input_gil_file_path,
        output_gil_file_path=output_gil_file_path,
        imported_gia_files=imported_gia_files,
        prune_placeholder_orphans=prune_placeholder_orphans,
    )


@dataclass(frozen=True, slots=True)
class _SignalEntryInfo:
    chunk_index: int
    signal_index: int | None
    signal_name: str
    send_id: int | None
    listen_id: int | None
    server_id: int | None
    param_count: int
    param_field6_varint_count: int
    param_field6_non_varint_count: int


# Type alias: expose the entry model publicly without duplicating the dataclass.
SignalEntryInfo = _SignalEntryInfo


def _is_placeholder_signal_name(value: str) -> bool:
    return bool(_PLACEHOLDER_SIGNAL_NAME_RE.match(str(value or "").strip()))


def _decode_chunks(payload_bytes: bytes) -> List[Tuple[bytes, bytes]]:
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


def _decode_utf8_or_none(text_bytes: bytes) -> str | None:
    try:
        return text_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _get_first_varint_field(message_payload: bytes, field_number: int) -> int | None:
    for tag_raw, value_raw in _decode_chunks(message_payload):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number == int(field_number) and parsed.wire_type == 0:
            return _decode_varint_value(value_raw)
    return None


def _get_first_string_field(message_payload: bytes, field_number: int) -> str | None:
    for tag_raw, value_raw in _decode_chunks(message_payload):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number == int(field_number) and parsed.wire_type == 2:
            _, string_payload = split_length_delimited_value_raw(value_raw)
            return _decode_utf8_or_none(string_payload)
    return None


def _set_first_string_field(message_payload: bytes, field_number: int, new_text: str) -> tuple[bytes, bool]:
    changed = False
    out_chunks: list[tuple[bytes, bytes]] = []
    for tag_raw, value_raw in _decode_chunks(message_payload):
        parsed = parse_tag_raw(tag_raw)
        if (not changed) and parsed.field_number == int(field_number) and parsed.wire_type == 2:
            _, old_payload = split_length_delimited_value_raw(value_raw)
            old_name = _decode_utf8_or_none(old_payload)
            target_name = str(new_text)
            if old_name != target_name:
                changed = True
            out_chunks.append((tag_raw, build_length_delimited_value_raw(target_name.encode("utf-8"))))
            continue
        out_chunks.append((tag_raw, value_raw))
    return encode_wire_chunks(out_chunks), bool(changed)


def _set_first_varint_field(message_payload: bytes, field_number: int, new_value: int) -> tuple[bytes, bool]:
    changed = False
    out_chunks: list[tuple[bytes, bytes]] = []
    for tag_raw, value_raw in _decode_chunks(message_payload):
        parsed = parse_tag_raw(tag_raw)
        if (not changed) and parsed.field_number == int(field_number) and parsed.wire_type == 0:
            old_value = _decode_varint_value(value_raw)
            if int(old_value) != int(new_value):
                changed = True
            out_chunks.append((tag_raw, encode_varint(int(new_value))))
            continue
        out_chunks.append((tag_raw, value_raw))
    return encode_wire_chunks(out_chunks), bool(changed)


def _find_first_ld_field(chunks: Sequence[tuple[bytes, bytes]], field_number: int) -> tuple[int, bytes]:
    for idx, (tag_raw, value_raw) in enumerate(chunks):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number == int(field_number) and parsed.wire_type == 2:
            _, payload = split_length_delimited_value_raw(value_raw)
            return int(idx), payload
    raise ValueError(f"missing length-delimited field: {int(field_number)}")


def _extract_signal_names_and_param_counts_from_gia_file(
    gia_file_path: Path,
    *,
    max_depth: int = 24,
) -> tuple[set[str], dict[str, int]]:
    gia_path = Path(gia_file_path).resolve()
    if not gia_path.is_file():
        raise FileNotFoundError(str(gia_path))

    proto_bytes = unwrap_gia_container(gia_path, check_header=False)
    field_map, consumed = decode_message_to_field_map(
        data_bytes=proto_bytes,
        start_offset=0,
        end_offset=len(proto_bytes),
        remaining_depth=int(max_depth),
    )
    if consumed != len(proto_bytes):
        raise ValueError(
            f"gia protobuf decode consumed mismatch: consumed={consumed}, total={len(proto_bytes)}, file={str(gia_path)!r}"
        )
    root_message = decoded_field_map_to_numeric_message(field_map)
    if not isinstance(root_message, dict):
        return set(), {}

    names: set[str] = set()
    param_counts: dict[str, int] = {}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            signal_meta = value.get("107")
            if isinstance(signal_meta, dict):
                for key in ("101", "102"):
                    node = signal_meta.get(key)
                    if isinstance(node, dict):
                        signal_name = node.get("1")
                        if isinstance(signal_name, str) and signal_name.strip() != "":
                            sig = str(signal_name).strip()
                            names.add(str(sig))

                            # 尝试提取 param_count（仅从信号 node_def 的 send/server 节点读取 102 列表）
                            node_def_name = str(value.get("200") or "").strip()
                            if node_def_name in {"发送信号", "向服务器节点图发送信号"}:
                                params_value = value.get("102")
                                if params_value is None:
                                    param_count = 0
                                elif isinstance(params_value, list):
                                    param_count = len([x for x in params_value if isinstance(x, dict)])
                                elif isinstance(params_value, dict):
                                    param_count = 1
                                else:
                                    param_count = 0

                                prev = param_counts.get(str(sig))
                                if prev is None:
                                    param_counts[str(sig)] = int(param_count)
                                elif int(prev) != int(param_count):
                                    raise ValueError(
                                        "signal param_count mismatch in .gia extractor:\n"
                                        f"- signal_name: {sig!r}\n"
                                        f"- prev: {int(prev)}\n"
                                        f"- new: {int(param_count)}\n"
                                        f"- gia_file: {str(gia_path)!r}"
                                    )
            for child in value.values():
                walk(child)
            return
        if isinstance(value, list):
            for item in value:
                walk(item)

    walk(root_message)
    return names, param_counts


def _extract_signal_names_from_gias(gia_files: Sequence[Path]) -> tuple[set[str], dict[str, list[str]], dict[str, int]]:
    merged: set[str] = set()
    by_file: dict[str, list[str]] = {}
    merged_param_counts: dict[str, int] = {}
    for gia_path in gia_files:
        names_set, param_counts = _extract_signal_names_and_param_counts_from_gia_file(Path(gia_path))
        names = sorted(names_set)
        merged.update(names)
        by_file[str(Path(gia_path).resolve())] = list(names)

        for k, v in dict(param_counts).items():
            sig = str(k).strip()
            if sig == "":
                continue
            if not isinstance(v, int):
                continue
            prev = merged_param_counts.get(sig)
            if prev is None:
                merged_param_counts[str(sig)] = int(v)
            elif int(prev) != int(v):
                raise ValueError(
                    "signal param_count mismatch across .gia files:\n"
                    f"- signal_name: {sig!r}\n"
                    f"- prev: {int(prev)}\n"
                    f"- new: {int(v)}\n"
                    f"- gia_file: {str(Path(gia_path).resolve())!r}"
                )
    return merged, by_file, merged_param_counts


def _parse_signal_entries(section5_chunks: Sequence[tuple[bytes, bytes]]) -> list[_SignalEntryInfo]:
    entries: list[_SignalEntryInfo] = []
    for chunk_index, (tag_raw, value_raw) in enumerate(section5_chunks):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number != 3 or parsed.wire_type != 2:
            continue
        _, entry_payload = split_length_delimited_value_raw(value_raw)

        signal_index: int | None = None
        signal_name = ""
        send_id: int | None = None
        listen_id: int | None = None
        server_id: int | None = None
        param_count = 0
        param_field6_varint_count = 0
        param_field6_non_varint_count = 0

        for entry_tag_raw, entry_value_raw in _decode_chunks(entry_payload):
            entry_parsed = parse_tag_raw(entry_tag_raw)
            if entry_parsed.field_number == 6 and entry_parsed.wire_type == 0:
                signal_index = _decode_varint_value(entry_value_raw)
            elif entry_parsed.field_number == 3 and entry_parsed.wire_type == 2:
                _, name_payload = split_length_delimited_value_raw(entry_value_raw)
                signal_name = _decode_utf8_or_none(name_payload) or ""
            elif entry_parsed.field_number == 1 and entry_parsed.wire_type == 2:
                _, meta_payload = split_length_delimited_value_raw(entry_value_raw)
                send_id = _get_first_varint_field(meta_payload, 5)
            elif entry_parsed.field_number == 2 and entry_parsed.wire_type == 2:
                _, meta_payload = split_length_delimited_value_raw(entry_value_raw)
                listen_id = _get_first_varint_field(meta_payload, 5)
            elif entry_parsed.field_number == 7 and entry_parsed.wire_type == 2:
                _, meta_payload = split_length_delimited_value_raw(entry_value_raw)
                server_id = _get_first_varint_field(meta_payload, 5)
            elif entry_parsed.field_number == 4 and entry_parsed.wire_type == 2:
                param_count += 1
                _, param_payload = split_length_delimited_value_raw(entry_value_raw)
                for param_tag_raw, _param_value_raw in _decode_chunks(param_payload):
                    param_parsed = parse_tag_raw(param_tag_raw)
                    if param_parsed.field_number != 6:
                        continue
                    if param_parsed.wire_type == 0:
                        param_field6_varint_count += 1
                    else:
                        param_field6_non_varint_count += 1

        entries.append(
            _SignalEntryInfo(
                chunk_index=int(chunk_index),
                signal_index=(int(signal_index) if isinstance(signal_index, int) else None),
                signal_name=str(signal_name),
                send_id=(int(send_id) if isinstance(send_id, int) else None),
                listen_id=(int(listen_id) if isinstance(listen_id, int) else None),
                server_id=(int(server_id) if isinstance(server_id, int) else None),
                param_count=int(param_count),
                param_field6_varint_count=int(param_field6_varint_count),
                param_field6_non_varint_count=int(param_field6_non_varint_count),
            )
        )
    return entries


def _signal_entry_quality_key(entry: _SignalEntryInfo) -> tuple[int, int, int]:
    # Prefer schema-healthier entries first:
    # 1) fewer malformed field_6 (non-varint) values
    # 2) fewer missing varint field_6 values across params
    # 3) stable tie-break by earlier chunk
    malformed = int(entry.param_field6_non_varint_count)
    missing = max(int(entry.param_count) - int(entry.param_field6_varint_count), 0)
    return int(malformed), int(missing), int(entry.chunk_index)


def _choose_canonical_entry(
    group: Sequence[_SignalEntryInfo],
    *,
    target_signal_names: set[str],
) -> tuple[_SignalEntryInfo, str]:
    ordered = sorted(group, key=lambda x: int(x.chunk_index))
    expected = [x for x in ordered if str(x.signal_name).strip() in target_signal_names]
    expected_non_placeholder = [x for x in expected if not _is_placeholder_signal_name(x.signal_name)]
    non_placeholder = [x for x in ordered if str(x.signal_name).strip() and (not _is_placeholder_signal_name(x.signal_name))]

    selected = min(ordered, key=_signal_entry_quality_key)
    selected_quality = _signal_entry_quality_key(selected)

    def _pick_preferred_same_quality(candidates: Sequence[_SignalEntryInfo]) -> _SignalEntryInfo | None:
        same_quality = [x for x in candidates if _signal_entry_quality_key(x) == selected_quality]
        if not same_quality:
            return None
        return sorted(same_quality, key=lambda x: int(x.chunk_index))[0]

    preferred_same_quality = (
        _pick_preferred_same_quality(expected_non_placeholder)
        or _pick_preferred_same_quality(expected)
        or _pick_preferred_same_quality(non_placeholder)
    )
    if preferred_same_quality is not None:
        selected = preferred_same_quality

    canonical_name = str(selected.signal_name).strip()
    if _is_placeholder_signal_name(canonical_name):
        if expected_non_placeholder:
            canonical_name = str(expected_non_placeholder[0].signal_name).strip()
        elif expected:
            canonical_name = str(expected[0].signal_name).strip()
        elif non_placeholder:
            canonical_name = str(non_placeholder[0].signal_name).strip()
    return selected, canonical_name


def _append_id_remap(
    remap: dict[int, int],
    *,
    source_id: int | None,
    target_id: int | None,
    conflicts: list[str],
) -> None:
    if not isinstance(source_id, int) or not isinstance(target_id, int):
        return
    src = int(source_id)
    dst = int(target_id)
    if src == dst:
        return
    old_target = remap.get(src)
    if old_target is not None and int(old_target) != int(dst):
        conflicts.append(f"id remap conflict: {src} -> {old_target} vs {dst}")
    remap[src] = dst


def _plan_dedupe_by_signal_index(
    entries: Sequence[_SignalEntryInfo],
    *,
    target_signal_names: set[str],
) -> tuple[set[int], dict[int, int], dict[int, str], list[str], list[str]]:
    removed_entry_chunks: set[int] = set()
    id_remap: dict[int, int] = {}
    rename_target_by_chunk: dict[int, str] = {}
    remap_conflicts: list[str] = []
    skipped_conflicts: list[str] = []

    target_names = {str(x).strip() for x in (target_signal_names or set()) if str(x).strip() != ""}
    if not target_names:
        return removed_entry_chunks, id_remap, rename_target_by_chunk, remap_conflicts, skipped_conflicts

    groups: dict[int, list[_SignalEntryInfo]] = {}
    for entry in entries:
        if not isinstance(entry.signal_index, int):
            continue
        groups.setdefault(int(entry.signal_index), []).append(entry)

    for signal_index, group in sorted(groups.items(), key=lambda kv: int(kv[0])):
        if len(group) <= 1:
            continue

        group_names = {str(x.signal_name or "").strip() for x in group} - {""}
        group_target_names = {n for n in group_names if n in target_names}
        if not group_target_names:
            continue

        non_placeholder_names = {n for n in group_names if not _is_placeholder_signal_name(n)}
        if len(non_placeholder_names) > 1:
            skipped_conflicts.append(
                f"skip index merge for same-index entries with different non-placeholder names: "
                f"signal_index={int(signal_index)}, names={sorted(non_placeholder_names)}"
            )
            continue

        canonical_entry, canonical_name = _choose_canonical_entry(group, target_signal_names=target_signal_names)
        if canonical_name and canonical_entry.signal_name.strip() != canonical_name:
            rename_target_by_chunk[int(canonical_entry.chunk_index)] = str(canonical_name)

        for entry in sorted(group, key=lambda x: int(x.chunk_index)):
            if int(entry.chunk_index) == int(canonical_entry.chunk_index):
                continue
            removed_entry_chunks.add(int(entry.chunk_index))
            _append_id_remap(
                id_remap,
                source_id=entry.send_id,
                target_id=canonical_entry.send_id,
                conflicts=remap_conflicts,
            )
            _append_id_remap(
                id_remap,
                source_id=entry.listen_id,
                target_id=canonical_entry.listen_id,
                conflicts=remap_conflicts,
            )
            _append_id_remap(
                id_remap,
                source_id=entry.server_id,
                target_id=canonical_entry.server_id,
                conflicts=remap_conflicts,
            )

    return removed_entry_chunks, id_remap, rename_target_by_chunk, remap_conflicts, skipped_conflicts


def _plan_dedupe_by_signal_name(
    entries: Sequence[_SignalEntryInfo],
    *,
    already_removed_chunks: set[int],
    target_signal_names: set[str],
) -> tuple[set[int], dict[int, int], list[str], list[str]]:
    removed_entry_chunks: set[int] = set()
    id_remap: dict[int, int] = {}
    remap_conflicts: list[str] = []
    skipped_conflicts: list[str] = []

    target_names = {str(x).strip() for x in (target_signal_names or set()) if str(x).strip() != ""}
    if not target_names:
        return removed_entry_chunks, id_remap, remap_conflicts, skipped_conflicts

    groups: dict[str, list[_SignalEntryInfo]] = {}
    for entry in entries:
        if int(entry.chunk_index) in already_removed_chunks:
            continue
        signal_name = str(entry.signal_name or "").strip()
        if signal_name == "":
            continue
        if signal_name not in target_names:
            continue
        groups.setdefault(signal_name, []).append(entry)

    for signal_name, group in sorted(groups.items(), key=lambda kv: str(kv[0]).casefold()):
        if len(group) <= 1:
            continue

        # Keep behavior conservative for conflicting schema candidates.
        param_counts = {int(x.param_count) for x in group}
        if len(param_counts) > 1:
            skipped_conflicts.append(
                f"skip merge for same-name entries with different param_count: {signal_name!r}, counts={sorted(param_counts)}"
            )
            continue

        canonical_candidates = [
            x for x in sorted(group, key=lambda e: int(e.chunk_index)) if not _is_placeholder_signal_name(x.signal_name)
        ]
        canonical_entry = canonical_candidates[0] if canonical_candidates else sorted(group, key=lambda e: int(e.chunk_index))[0]

        for entry in sorted(group, key=lambda x: int(x.chunk_index)):
            if int(entry.chunk_index) == int(canonical_entry.chunk_index):
                continue
            removed_entry_chunks.add(int(entry.chunk_index))
            _append_id_remap(
                id_remap,
                source_id=entry.send_id,
                target_id=canonical_entry.send_id,
                conflicts=remap_conflicts,
            )
            _append_id_remap(
                id_remap,
                source_id=entry.listen_id,
                target_id=canonical_entry.listen_id,
                conflicts=remap_conflicts,
            )
            _append_id_remap(
                id_remap,
                source_id=entry.server_id,
                target_id=canonical_entry.server_id,
                conflicts=remap_conflicts,
            )

    return removed_entry_chunks, id_remap, remap_conflicts, skipped_conflicts


def _patch_param_definition_field6(param_payload: bytes) -> tuple[bytes, bool]:
    chunks = _decode_chunks(param_payload)
    has_field6 = False
    field5_value: Optional[int] = None
    for tag_raw, value_raw in chunks:
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number == 6 and parsed.wire_type == 0:
            has_field6 = True
        elif parsed.field_number == 5 and parsed.wire_type == 0:
            field5_value = _decode_varint_value(value_raw)

    if has_field6:
        return param_payload, False
    if not isinstance(field5_value, int):
        return param_payload, False

    inferred = int(field5_value) + 1
    chunks.append((encode_tag(6, 0), encode_varint(inferred)))
    return encode_wire_chunks(chunks), True


def _patch_signal_entry_payload(
    entry_payload: bytes,
    *,
    rename_to: str | None,
) -> tuple[bytes, int, int]:
    out_chunks: list[tuple[bytes, bytes]] = []
    entry_name_change_count = 0
    param_field6_patch_count = 0

    for tag_raw, value_raw in _decode_chunks(entry_payload):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number == 3 and parsed.wire_type == 2 and isinstance(rename_to, str) and rename_to.strip() != "":
            patched_name_payload, name_changed = _set_first_string_field(entry_payload, 3, str(rename_to).strip())
            # _set_first_string_field patches the first field only in whole message; once done we can return fast.
            # Keep param patches by continuing on patched chunks instead of early return.
            if name_changed:
                entry_name_change_count += 1
            # Re-parse from patched message and continue param fixes.
            reparsed = _decode_chunks(patched_name_payload)
            out_chunks = []
            for rep_tag_raw, rep_value_raw in reparsed:
                rep_parsed = parse_tag_raw(rep_tag_raw)
                if rep_parsed.field_number == 4 and rep_parsed.wire_type == 2:
                    _, param_payload = split_length_delimited_value_raw(rep_value_raw)
                    patched_param_payload, changed = _patch_param_definition_field6(param_payload)
                    if changed:
                        param_field6_patch_count += 1
                    out_chunks.append((rep_tag_raw, build_length_delimited_value_raw(patched_param_payload)))
                else:
                    out_chunks.append((rep_tag_raw, rep_value_raw))
            return encode_wire_chunks(out_chunks), int(entry_name_change_count), int(param_field6_patch_count)

        if parsed.field_number == 4 and parsed.wire_type == 2:
            _, param_payload = split_length_delimited_value_raw(value_raw)
            patched_param_payload, changed = _patch_param_definition_field6(param_payload)
            if changed:
                param_field6_patch_count += 1
            out_chunks.append((tag_raw, build_length_delimited_value_raw(patched_param_payload)))
            continue

        out_chunks.append((tag_raw, value_raw))

    return encode_wire_chunks(out_chunks), int(entry_name_change_count), int(param_field6_patch_count)


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


def _extract_signal_name_from_node_def_payload(node_def_payload: bytes) -> str | None:
    for tag_raw, value_raw in _decode_chunks(node_def_payload):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number != 107 or parsed.wire_type != 2:
            continue
        _, signal_payload = split_length_delimited_value_raw(value_raw)
        for signal_tag_raw, signal_value_raw in _decode_chunks(signal_payload):
            signal_parsed = parse_tag_raw(signal_tag_raw)
            if signal_parsed.wire_type != 2 or signal_parsed.field_number not in (101, 102):
                continue
            _, inner_payload = split_length_delimited_value_raw(signal_value_raw)
            signal_name = _get_first_string_field(inner_payload, 1)
            if isinstance(signal_name, str) and signal_name.strip() != "":
                return str(signal_name).strip()
    return None


def _patch_node_def_signal_name(node_def_payload: bytes, *, signal_name: str) -> tuple[bytes, int]:
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

    return encode_wire_chunks(out_chunks), int(changed_count)


def _patch_node_instance_ids(node_payload: bytes, *, id_remap: dict[int, int]) -> tuple[bytes, int]:
    out_chunks: list[tuple[bytes, bytes]] = []
    id_change_count = 0
    for tag_raw, value_raw in _decode_chunks(node_payload):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number in (2, 3) and parsed.wire_type == 2:
            _, meta_payload = split_length_delimited_value_raw(value_raw)
            old_id = _get_first_varint_field(meta_payload, 5)
            if isinstance(old_id, int) and int(old_id) in id_remap:
                new_id = int(id_remap[int(old_id)])
                patched_meta_payload, changed = _set_first_varint_field(meta_payload, 5, new_id)
                if changed:
                    id_change_count += 1
                out_chunks.append((tag_raw, build_length_delimited_value_raw(patched_meta_payload)))
                continue
        out_chunks.append((tag_raw, value_raw))
    return encode_wire_chunks(out_chunks), int(id_change_count)


def _extract_node_def_id_from_node_instance(node_payload: bytes) -> int | None:
    for tag_raw, value_raw in _decode_chunks(node_payload):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number == 2 and parsed.wire_type == 2:
            _, meta_payload = split_length_delimited_value_raw(value_raw)
            return _get_first_varint_field(meta_payload, 5)
    return None


def _extract_pin_kind_from_pin_payload(pin_payload: bytes) -> int | None:
    """从 pin message 中读取 i1.kind_int（对齐 `node_graph_ir_parser.parse_node_pin_index`）。"""
    for tag_raw, value_raw in _decode_chunks(pin_payload):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number != 1 or parsed.wire_type != 2:
            continue
        _, i1_payload = split_length_delimited_value_raw(value_raw)
        return _get_first_varint_field(i1_payload, 1)
    return None


def _patch_varbase_string_value(varbase_payload: bytes, *, new_text: str) -> tuple[bytes, int]:
    """仅修补 VarBase(StringBase) 的实际字符串值（field_105.StringBaseValue.field_1）。"""
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


def _patch_node_runtime_signal_name(node_payload: bytes, *, signal_name: str) -> tuple[bytes, int]:
    """仅修补信号节点的 META pin(kind=5) 上的信号名，不触碰任何参数 pin(kind=3) 的常量值。"""
    out_chunks: list[tuple[bytes, bytes]] = []
    changed_count = 0

    for tag_raw, value_raw in _decode_chunks(node_payload):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number != 4 or parsed.wire_type != 2:
            out_chunks.append((tag_raw, value_raw))
            continue

        _, pin_payload = split_length_delimited_value_raw(value_raw)
        pin_kind = _extract_pin_kind_from_pin_payload(pin_payload)
        if not (isinstance(pin_kind, int) and int(pin_kind) == 5):
            out_chunks.append((tag_raw, value_raw))
            continue

        pin_chunks = _decode_chunks(pin_payload)
        pin_out: list[tuple[bytes, bytes]] = []
        pin_changed = 0
        for p_tag_raw, p_value_raw in pin_chunks:
            p_parsed = parse_tag_raw(p_tag_raw)
            if p_parsed.field_number == 3 and p_parsed.wire_type == 2:
                _, varbase_payload = split_length_delimited_value_raw(p_value_raw)
                patched_varbase, delta = _patch_varbase_string_value(varbase_payload, new_text=str(signal_name))
                if delta > 0:
                    pin_changed += int(delta)
                    pin_out.append((p_tag_raw, build_length_delimited_value_raw(patched_varbase)))
                    continue
            pin_out.append((p_tag_raw, p_value_raw))

        if pin_changed > 0:
            changed_count += int(pin_changed)
            out_chunks.append((tag_raw, build_length_delimited_value_raw(encode_wire_chunks(pin_out))))
        else:
            out_chunks.append((tag_raw, value_raw))

    if changed_count > 0:
        return encode_wire_chunks(out_chunks), int(changed_count)
    return node_payload, 0


def _collect_used_node_def_ids_from_graphs(section10_chunks: Sequence[tuple[bytes, bytes]]) -> set[int]:
    used: set[int] = set()
    for tag_raw, value_raw in section10_chunks:
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number != 1 or parsed.wire_type != 2:
            continue
        _, group_payload = split_length_delimited_value_raw(value_raw)
        for group_tag_raw, group_value_raw in _decode_chunks(group_payload):
            group_parsed = parse_tag_raw(group_tag_raw)
            if group_parsed.field_number != 1 or group_parsed.wire_type != 2:
                continue
            _, graph_entry_payload = split_length_delimited_value_raw(group_value_raw)
            for entry_tag_raw, entry_value_raw in _decode_chunks(graph_entry_payload):
                entry_parsed = parse_tag_raw(entry_tag_raw)
                if entry_parsed.field_number != 3 or entry_parsed.wire_type != 2:
                    continue
                _, node_payload = split_length_delimited_value_raw(entry_value_raw)
                node_def_id = _extract_node_def_id_from_node_instance(node_payload)
                if isinstance(node_def_id, int):
                    used.add(int(node_def_id))
    return used


def _collect_signal_ref_node_def_ids_from_entries(entries: Sequence[_SignalEntryInfo]) -> set[int]:
    ref_ids: set[int] = set()
    for entry in entries:
        for node_def_id in (entry.send_id, entry.listen_id, entry.server_id):
            if isinstance(node_def_id, int):
                ref_ids.add(int(node_def_id))
    return ref_ids


def _plan_placeholder_signal_entry_renames(
    *,
    initial_entries: Sequence[_SignalEntryInfo],
    missing_expected_signal_names: Sequence[str],
    expected_param_count_by_signal_name: Dict[str, int],
) -> tuple[dict[int, str], list[str]]:
    """
    规划“占位符信号名 → 缺失的期望信号名”的重命名。

    目标：在 scoped repair 下，允许把极少量占位符（例如 `信号_1`）重命名为 `.gia` 导出的期望信号名，
    以补齐“本地节点图用到但目标 .gil 中缺失”的信号名，且保持策略保守（避免猜错导致绑错信号）。

    当前策略（保守）：
    - 优先按 “expected param_count（来自 `.gia` 的 send/server node_def['102']）” 做匹配；
    - 仅当能 **唯一定位** 某条占位符 entry 对应某个缺失的期望信号名时才会重命名；
    - 若无法唯一映射则不做重命名，并在 report 中写入 conflicts（不猜测）。
    """
    missing = [str(x).strip() for x in list(missing_expected_signal_names or []) if str(x).strip() != ""]
    if not missing:
        return {}, []

    placeholder_entries = [e for e in list(initial_entries or []) if _is_placeholder_signal_name(str(e.signal_name).strip())]
    if not placeholder_entries:
        return {}, [f"missing_expected_signal_names={missing} but no placeholder entries found in target .gil"]

    used_chunks: set[int] = set()
    renames_by_chunk: dict[int, str] = {}
    conflicts: list[str] = []

    # Pass 1: param_count 匹配（仅在 expected_param_count 已知时）
    for name in list(missing):
        expected_pc = expected_param_count_by_signal_name.get(str(name))
        if not isinstance(expected_pc, int):
            continue
        candidates = [
            e for e in placeholder_entries if int(e.chunk_index) not in used_chunks and int(e.param_count) == int(expected_pc)
        ]
        if len(candidates) == 1:
            renames_by_chunk[int(candidates[0].chunk_index)] = str(name)
            used_chunks.add(int(candidates[0].chunk_index))
            continue
        if len(candidates) > 1:
            details = [
                f"chunk={int(e.chunk_index)} index={e.signal_index} name={str(e.signal_name).strip()!r} params={int(e.param_count)}"
                for e in candidates[:12]
            ]
            conflicts.append(
                "ambiguous placeholder mapping by param_count:\n"
                f"- missing_expected_signal_name: {str(name)!r}\n"
                f"- expected_param_count: {int(expected_pc)}\n"
                f"- candidates: {details}"
            )

    # Pass 2: 1-to-1 fallback（剩余各 1 时允许）
    remaining_missing = [n for n in missing if str(n) not in set(renames_by_chunk.values())]
    remaining_placeholders = [e for e in placeholder_entries if int(e.chunk_index) not in used_chunks]
    if len(remaining_missing) == 1 and len(remaining_placeholders) == 1:
        renames_by_chunk[int(remaining_placeholders[0].chunk_index)] = str(remaining_missing[0])
        used_chunks.add(int(remaining_placeholders[0].chunk_index))
        remaining_missing = []
        remaining_placeholders = []

    # still missing -> summary conflict (keep conservative)
    if remaining_missing:
        details_all = [
            f"chunk={int(e.chunk_index)} index={e.signal_index} name={str(e.signal_name).strip()!r} params={int(e.param_count)}"
            for e in remaining_placeholders
        ]
        conflicts.append("cannot uniquely map placeholder signals to missing expected signal names; refuse to guess.")
        conflicts.append(f"- missing_expected_signal_names: {remaining_missing}")
        conflicts.append(f"- placeholder_entries_total: {int(len(remaining_placeholders))}")
        conflicts.append(f"- placeholder_entries: {details_all[:12]}")

    return dict(renames_by_chunk), list(conflicts)


def _repair_gil_signals_from_imported_gia(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    imported_gia_files: Sequence[Path],
    prune_placeholder_orphans: bool,
) -> dict:
    input_path = Path(input_gil_file_path).resolve()
    output_path = Path(output_gil_file_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))
    if output_path == input_path:
        raise ValueError("output path cannot be the same as input path")
    if output_path.suffix.lower() != ".gil":
        raise ValueError(f"output file must be .gil: {str(output_path)}")

    gia_paths = [Path(x).resolve() for x in list(imported_gia_files or [])]
    if not gia_paths:
        raise ValueError("at least one --imported-gia is required")
    for gia_path in gia_paths:
        if not gia_path.is_file() or gia_path.suffix.lower() != ".gia":
            raise FileNotFoundError(str(gia_path))

    (
        target_signal_names_from_gia,
        gia_signal_names_by_file,
        expected_param_count_by_signal_name,
    ) = _extract_signal_names_from_gias(gia_paths)
    scope_signal_names_from_gia = {str(x).strip() for x in target_signal_names_from_gia if str(x).strip() != ""}
    if not scope_signal_names_from_gia:
        raise ValueError(
            "no signal names extracted from imported .gia files; "
            "repair requires at least one constant signal name in selected graphs"
        )

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

    initial_entries = _parse_signal_entries(section5_chunks)
    gil_signal_name_set = {str(x.signal_name).strip() for x in initial_entries if str(x.signal_name).strip() != ""}

    # scope：以 `.gia` 提取到的信号名为准（选中节点图的“本地真相”）
    target_signal_names_in_gil = {str(x) for x in scope_signal_names_from_gia if str(x) in gil_signal_name_set}
    missing_expected_signal_names = sorted([str(x) for x in scope_signal_names_from_gia if str(x) not in gil_signal_name_set])

    # 兜底：若存在“缺失的期望信号名”，且目标 .gil 中存在唯一占位符 entry，则允许把该占位符重命名为缺失项（不做猜测映射）。
    placeholder_entry_renames_by_chunk, placeholder_rename_conflicts = _plan_placeholder_signal_entry_renames(
        initial_entries=initial_entries,
        missing_expected_signal_names=missing_expected_signal_names,
        expected_param_count_by_signal_name=dict(expected_param_count_by_signal_name),
    )

    target_signal_names_effective = set(target_signal_names_in_gil) | {str(v) for v in placeholder_entry_renames_by_chunk.values()}
    if not target_signal_names_effective:
        examples = sorted(scope_signal_names_from_gia)[:12]
        raise ValueError(
            "none of the signal names extracted from imported .gia files exist in target .gil, "
            "and no safe placeholder rename plan could be determined; refuse to run unscoped repair.\n"
            f"- signals_from_gia_total: {int(len(scope_signal_names_from_gia))}\n"
            f"- example_signals_from_gia: {examples}\n"
            f"- target_gil: {str(input_path)}"
        )

    # planning 视图：把“将被重命名的占位符 entry”以新名字参与 dedupe planning，避免后续去重/引用修复遗漏。
    entries_for_planning: list[_SignalEntryInfo] = []
    for e in list(initial_entries):
        renamed = placeholder_entry_renames_by_chunk.get(int(e.chunk_index))
        if isinstance(renamed, str) and renamed.strip() != "":
            entries_for_planning.append(
                _SignalEntryInfo(
                    chunk_index=int(e.chunk_index),
                    signal_index=(int(e.signal_index) if isinstance(e.signal_index, int) else None),
                    signal_name=str(renamed).strip(),
                    send_id=(int(e.send_id) if isinstance(e.send_id, int) else None),
                    listen_id=(int(e.listen_id) if isinstance(e.listen_id, int) else None),
                    server_id=(int(e.server_id) if isinstance(e.server_id, int) else None),
                    param_count=int(e.param_count),
                    param_field6_varint_count=int(e.param_field6_varint_count),
                    param_field6_non_varint_count=int(e.param_field6_non_varint_count),
                )
            )
        else:
            entries_for_planning.append(e)

    removed_by_index, id_remap_by_index, rename_by_index, remap_conflicts_index, skipped_index_conflicts = (
        _plan_dedupe_by_signal_index(
            entries_for_planning,
            target_signal_names=target_signal_names_effective,
        )
    )
    removed_by_name, id_remap_by_name, remap_conflicts_name, skipped_name_conflicts = _plan_dedupe_by_signal_name(
        entries_for_planning,
        already_removed_chunks=set(removed_by_index),
        target_signal_names=target_signal_names_effective,
    )

    removed_entry_chunks = set(removed_by_index) | set(removed_by_name)
    id_remap: dict[int, int] = dict(id_remap_by_index)
    remap_conflicts = list(remap_conflicts_index) + list(remap_conflicts_name)
    for src_id, dst_id in id_remap_by_name.items():
        _append_id_remap(id_remap, source_id=src_id, target_id=dst_id, conflicts=remap_conflicts)

    patched_section5_chunks: list[tuple[bytes, bytes]] = []
    removed_entry_count = 0
    entry_name_change_count = 0
    param_field6_patch_count = 0
    entry_info_by_chunk_index = {int(x.chunk_index): x for x in initial_entries}
    for chunk_index, (tag_raw, value_raw) in enumerate(section5_chunks):
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number != 3 or parsed.wire_type != 2:
            patched_section5_chunks.append((tag_raw, value_raw))
            continue
        if int(chunk_index) in removed_entry_chunks:
            removed_entry_count += 1
            continue

        _, entry_payload = split_length_delimited_value_raw(value_raw)
        rename_target = rename_by_index.get(int(chunk_index)) or placeholder_entry_renames_by_chunk.get(int(chunk_index))
        entry_info = entry_info_by_chunk_index.get(int(chunk_index))
        entry_name = str(getattr(entry_info, "signal_name", "") or "").strip()
        should_patch = bool(rename_target) or (entry_name in target_signal_names_effective)
        if should_patch:
            patched_entry_payload, entry_name_delta, field6_delta = _patch_signal_entry_payload(
                entry_payload,
                rename_to=rename_target,
            )
            entry_name_change_count += int(entry_name_delta)
            param_field6_patch_count += int(field6_delta)
            patched_section5_chunks.append((tag_raw, build_length_delimited_value_raw(patched_entry_payload)))
        else:
            patched_section5_chunks.append((tag_raw, value_raw))

    patched_section5_payload = encode_wire_chunks(patched_section5_chunks)
    section5_tag_raw, _section5_value_raw = section10_chunks[section5_index]
    section10_chunks[section5_index] = (section5_tag_raw, build_length_delimited_value_raw(patched_section5_payload))

    entries_after_section5_patch = _parse_signal_entries(patched_section5_chunks)
    node_def_name_by_id: dict[int, str] = {}
    for entry in entries_after_section5_patch:
        signal_name = str(entry.signal_name or "").strip()
        if signal_name == "":
            continue
        if signal_name not in target_signal_names_effective:
            continue
        for node_def_id in (entry.send_id, entry.listen_id, entry.server_id):
            if isinstance(node_def_id, int):
                node_def_name_by_id[int(node_def_id)] = str(signal_name)

    node_instance_id_change_count = 0
    graph_runtime_name_change_count = 0
    patched_section10_after_graphs: list[tuple[bytes, bytes]] = []
    for tag_raw, value_raw in section10_chunks:
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number != 1 or parsed.wire_type != 2:
            patched_section10_after_graphs.append((tag_raw, value_raw))
            continue

        _, group_payload = split_length_delimited_value_raw(value_raw)
        group_chunks = _decode_chunks(group_payload)
        group_changed = False
        group_out: list[tuple[bytes, bytes]] = []
        for group_tag_raw, group_value_raw in group_chunks:
            group_parsed = parse_tag_raw(group_tag_raw)
            if group_parsed.field_number != 1 or group_parsed.wire_type != 2:
                group_out.append((group_tag_raw, group_value_raw))
                continue

            _, graph_entry_payload = split_length_delimited_value_raw(group_value_raw)
            graph_entry_chunks = _decode_chunks(graph_entry_payload)
            graph_entry_changed = False
            graph_entry_out: list[tuple[bytes, bytes]] = []
            for entry_tag_raw, entry_value_raw in graph_entry_chunks:
                entry_parsed = parse_tag_raw(entry_tag_raw)
                if entry_parsed.field_number != 3 or entry_parsed.wire_type != 2:
                    graph_entry_out.append((entry_tag_raw, entry_value_raw))
                    continue

                _, node_payload = split_length_delimited_value_raw(entry_value_raw)
                patched_node_payload, id_delta = _patch_node_instance_ids(node_payload, id_remap=id_remap)
                node_instance_id_change_count += int(id_delta)
                node_def_id = _extract_node_def_id_from_node_instance(patched_node_payload)
                runtime_name_delta = 0
                if isinstance(node_def_id, int) and int(node_def_id) in node_def_name_by_id:
                    patched_node_payload, runtime_name_delta = _patch_node_runtime_signal_name(
                        patched_node_payload,
                        signal_name=node_def_name_by_id[int(node_def_id)],
                    )
                graph_runtime_name_change_count += int(runtime_name_delta)
                if id_delta > 0 or runtime_name_delta > 0:
                    graph_entry_changed = True
                    graph_entry_out.append((entry_tag_raw, build_length_delimited_value_raw(patched_node_payload)))
                    continue

                graph_entry_out.append((entry_tag_raw, entry_value_raw))

            if graph_entry_changed:
                group_changed = True
                patched_graph_entry_payload = encode_wire_chunks(graph_entry_out)
                group_out.append((group_tag_raw, build_length_delimited_value_raw(patched_graph_entry_payload)))
            else:
                group_out.append((group_tag_raw, group_value_raw))

        if group_changed:
            patched_group_payload = encode_wire_chunks(group_out)
            patched_section10_after_graphs.append((tag_raw, build_length_delimited_value_raw(patched_group_payload)))
        else:
            patched_section10_after_graphs.append((tag_raw, value_raw))

    node_def_name_change_count = 0
    section10_after_node_defs: list[tuple[bytes, bytes]] = []
    for tag_raw, value_raw in patched_section10_after_graphs:
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number != 2 or parsed.wire_type != 2:
            section10_after_node_defs.append((tag_raw, value_raw))
            continue

        _, wrapper_payload = split_length_delimited_value_raw(value_raw)
        wrapper_chunks = _decode_chunks(wrapper_payload)
        wrapper_changed = False
        wrapper_out: list[tuple[bytes, bytes]] = []
        for wrapper_tag_raw, wrapper_value_raw in wrapper_chunks:
            wrapper_parsed = parse_tag_raw(wrapper_tag_raw)
            if wrapper_parsed.field_number == 1 and wrapper_parsed.wire_type == 2:
                _, node_def_payload = split_length_delimited_value_raw(wrapper_value_raw)
                node_def_id = _extract_node_def_id_from_node_def_payload(node_def_payload)
                if isinstance(node_def_id, int) and int(node_def_id) in node_def_name_by_id:
                    patched_node_def_payload, delta = _patch_node_def_signal_name(
                        node_def_payload,
                        signal_name=node_def_name_by_id[int(node_def_id)],
                    )
                    if delta > 0:
                        node_def_name_change_count += int(delta)
                        wrapper_changed = True
                        wrapper_out.append((wrapper_tag_raw, build_length_delimited_value_raw(patched_node_def_payload)))
                        continue
            wrapper_out.append((wrapper_tag_raw, wrapper_value_raw))

        if wrapper_changed:
            patched_wrapper_payload = encode_wire_chunks(wrapper_out)
            section10_after_node_defs.append((tag_raw, build_length_delimited_value_raw(patched_wrapper_payload)))
        else:
            section10_after_node_defs.append((tag_raw, value_raw))

    entries_after_graph_patch = _parse_signal_entries(
        _decode_chunks(
            split_length_delimited_value_raw(section10_after_node_defs[section5_index][1])[1]
        )
    )
    used_node_def_ids = _collect_used_node_def_ids_from_graphs(section10_after_node_defs)
    signal_ref_node_def_ids = _collect_signal_ref_node_def_ids_from_entries(entries_after_graph_patch)

    removable_node_def_ids: set[int] = {
        int(src_id)
        for src_id in id_remap.keys()
        if int(src_id) not in used_node_def_ids and int(src_id) not in signal_ref_node_def_ids
    }

    # 仅当本次修复范围覆盖目标 .gil 内所有“非占位符信号名”时，才允许执行全局 placeholder orphan 清理：
    # - scoped 修复场景下，避免误删“与本次选择无关”的残留。
    non_placeholder_gil_signal_names = {n for n in gil_signal_name_set if not _is_placeholder_signal_name(n)}
    if bool(prune_placeholder_orphans) and (non_placeholder_gil_signal_names <= set(target_signal_names_in_gil)):
        for tag_raw, value_raw in section10_after_node_defs:
            parsed = parse_tag_raw(tag_raw)
            if parsed.field_number != 2 or parsed.wire_type != 2:
                continue
            _, wrapper_payload = split_length_delimited_value_raw(value_raw)
            node_def_id = _extract_node_def_id_from_wrapper_payload(wrapper_payload)
            if not isinstance(node_def_id, int):
                continue
            if int(node_def_id) in used_node_def_ids or int(node_def_id) in signal_ref_node_def_ids:
                continue
            for wrapper_tag_raw, wrapper_value_raw in _decode_chunks(wrapper_payload):
                wrapper_parsed = parse_tag_raw(wrapper_tag_raw)
                if wrapper_parsed.field_number != 1 or wrapper_parsed.wire_type != 2:
                    continue
                _, node_def_payload = split_length_delimited_value_raw(wrapper_value_raw)
                node_signal_name = _extract_signal_name_from_node_def_payload(node_def_payload)
                if isinstance(node_signal_name, str) and _is_placeholder_signal_name(node_signal_name):
                    removable_node_def_ids.add(int(node_def_id))
                break

    removed_node_def_wrapper_count = 0
    removed_meta_count = 0
    section10_after_prune: list[tuple[bytes, bytes]] = []
    for tag_raw, value_raw in section10_after_node_defs:
        parsed = parse_tag_raw(tag_raw)
        if parsed.field_number == 2 and parsed.wire_type == 2:
            _, wrapper_payload = split_length_delimited_value_raw(value_raw)
            node_def_id = _extract_node_def_id_from_wrapper_payload(wrapper_payload)
            if isinstance(node_def_id, int) and int(node_def_id) in removable_node_def_ids:
                removed_node_def_wrapper_count += 1
                continue
            section10_after_prune.append((tag_raw, value_raw))
            continue

        if parsed.field_number == 5 and parsed.wire_type == 2:
            _, section5_payload_current = split_length_delimited_value_raw(value_raw)
            section5_chunks_current = _decode_chunks(section5_payload_current)
            section5_out: list[tuple[bytes, bytes]] = []
            for sec5_tag_raw, sec5_value_raw in section5_chunks_current:
                sec5_parsed = parse_tag_raw(sec5_tag_raw)
                if sec5_parsed.field_number == 2 and sec5_parsed.wire_type == 2:
                    _, meta_payload = split_length_delimited_value_raw(sec5_value_raw)
                    node_def_id = _get_first_varint_field(meta_payload, 5)
                    if isinstance(node_def_id, int) and int(node_def_id) in removable_node_def_ids:
                        removed_meta_count += 1
                        continue
                section5_out.append((sec5_tag_raw, sec5_value_raw))
            section10_after_prune.append((tag_raw, build_length_delimited_value_raw(encode_wire_chunks(section5_out))))
            continue

        section10_after_prune.append((tag_raw, value_raw))

    patched_section10_payload = encode_wire_chunks(section10_after_prune)
    root_tag_raw, _root_value_raw = root_chunks[section10_index]
    root_chunks[section10_index] = (root_tag_raw, build_length_delimited_value_raw(patched_section10_payload))
    output_payload_bytes = encode_wire_chunks(root_chunks)

    container_spec = read_gil_container_spec(input_path)
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=output_payload_bytes, container_spec=container_spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)

    return {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "imported_gia_files": [str(p) for p in gia_paths],
        "target_signal_names_from_gia_total": int(len(target_signal_names_from_gia)),
        "target_signal_names_in_gil_total": int(len(target_signal_names_in_gil)),
        "missing_expected_signal_names": list(missing_expected_signal_names),
        "placeholder_entry_renames": [
            {
                "chunk_index": int(chunk_idx),
                "from": str(entry_info_by_chunk_index.get(int(chunk_idx)).signal_name)
                if entry_info_by_chunk_index.get(int(chunk_idx))
                else "",
                "to": str(new_name),
                "signal_index": int(entry_info_by_chunk_index.get(int(chunk_idx)).signal_index)
                if entry_info_by_chunk_index.get(int(chunk_idx))
                and isinstance(entry_info_by_chunk_index.get(int(chunk_idx)).signal_index, int)
                else None,
            }
            for chunk_idx, new_name in sorted(placeholder_entry_renames_by_chunk.items(), key=lambda kv: int(kv[0]))
        ],
        "placeholder_rename_conflicts": list(placeholder_rename_conflicts),
        "gia_signal_names_by_file": gia_signal_names_by_file,
        "initial_signal_entries": int(len(initial_entries)),
        "removed_signal_entries": int(removed_entry_count),
        "id_remap_size": int(len(id_remap)),
        "id_remap": {str(k): int(v) for k, v in sorted(id_remap.items(), key=lambda kv: int(kv[0]))},
        "entry_name_changes": int(entry_name_change_count),
        "param_field6_patches": int(param_field6_patch_count),
        "node_instance_id_changes": int(node_instance_id_change_count),
        "node_def_name_changes": int(node_def_name_change_count),
        "graph_runtime_name_changes": int(graph_runtime_name_change_count),
        "removed_node_def_wrappers": int(removed_node_def_wrapper_count),
        "removed_node_def_meta_entries": int(removed_meta_count),
        "removable_node_def_ids": sorted(int(x) for x in removable_node_def_ids),
        "remap_conflicts": list(remap_conflicts),
        "skipped_index_conflicts": list(skipped_index_conflicts),
        "skipped_name_conflicts": list(skipped_name_conflicts),
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description=(
            "Repair signal damage in .gil based on imported .gia files: "
            "dedupe signal entries, remap graph node_def ids, normalize names, patch missing field_6, and prune orphans."
        )
    )
    parser.add_argument("input_gil_file", help="Input .gil file path")
    parser.add_argument("output_gil_file", help="Output .gil file path (must differ from input)")
    parser.add_argument(
        "--imported-gia",
        dest="imported_gia_files",
        action="append",
        required=True,
        help="Imported .gia file path (repeatable)",
    )
    parser.add_argument(
        "--no-prune-placeholder-orphans",
        dest="no_prune_placeholder_orphans",
        action="store_true",
        help="Disable pruning of unreferenced placeholder signal node_defs",
    )
    parser.add_argument(
        "--report",
        dest="report_json_file",
        default="",
        help="Optional JSON report output file path",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    report = _repair_gil_signals_from_imported_gia(
        input_gil_file_path=Path(str(args.input_gil_file)),
        output_gil_file_path=Path(str(args.output_gil_file)),
        imported_gia_files=[Path(x) for x in list(args.imported_gia_files or [])],
        prune_placeholder_orphans=(not bool(args.no_prune_placeholder_orphans)),
    )

    report_path_text = str(args.report_json_file or "").strip()
    if report_path_text:
        report_path = Path(report_path_text).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()



