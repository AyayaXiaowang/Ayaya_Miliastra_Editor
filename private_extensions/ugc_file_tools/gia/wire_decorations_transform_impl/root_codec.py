from __future__ import annotations

"""Root-level helpers for parsing and rebuilding decorations `.gia` proto bytes."""

from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from ugc_file_tools.gia.wire_decorations_transform_impl.constants import (
    ROOT_FIELD_ACCESSORIES,
    ROOT_FIELD_FILE_PATH,
    ROOT_FIELD_PARENTS,
    WIRE_TYPE_LENGTH_DELIMITED,
)
from ugc_file_tools.gia.wire_decorations_transform_impl.wire_utils import WireChunk
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_tag
from ugc_file_tools.wire.codec import encode_wire_chunks
from ugc_file_tools.wire.patch import build_length_delimited_value_raw, split_length_delimited_value_raw


def derive_file_path_from_base(*, base_file_path: str, output_file_name: str) -> str:
    """Derive a new Root.filePath by keeping the base prefix and replacing the final file name."""
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


def extract_root_file_path_text(root_parsed: Sequence[WireChunk]) -> str:
    """Extract Root.filePath(field_3) as UTF-8 text from parsed root chunks."""
    for c in list(root_parsed):
        if c.field_number == ROOT_FIELD_FILE_PATH and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED:
            _lr, payload = split_length_delimited_value_raw(c.value_raw)
            return payload.decode("utf-8", errors="replace")
    return ""


def extract_root_parent_and_accessory_units(root_parsed: Sequence[WireChunk]) -> Tuple[List[bytes], List[bytes]]:
    """Extract Root.field_1 parents and Root.field_2 accessories unit payload bytes in order."""
    parent_units: List[bytes] = []
    accessory_units: List[bytes] = []
    for c in list(root_parsed):
        if c.field_number == ROOT_FIELD_PARENTS and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED:
            _lr, payload = split_length_delimited_value_raw(c.value_raw)
            parent_units.append(bytes(payload))
        elif c.field_number == ROOT_FIELD_ACCESSORIES and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED:
            _lr, payload = split_length_delimited_value_raw(c.value_raw)
            accessory_units.append(bytes(payload))
    return parent_units, accessory_units


def rebuild_root_proto_bytes(
    *,
    root_parsed: Sequence[WireChunk],
    parent_units_by_original_index: Sequence[Optional[bytes]],
    accessory_units: Sequence[bytes],
    file_path_text: str,
) -> bytes:
    """Rebuild root proto bytes by replacing parents/accessories/filePath while preserving unknown fields and order."""
    new_file_path_value_raw = build_length_delimited_value_raw(str(file_path_text).encode("utf-8"))

    out_root_chunks: List[Tuple[bytes, bytes]] = []
    file_path_written = False
    parent_idx = 0
    accessory_idx = 0

    for c in list(root_parsed):
        if c.field_number == ROOT_FIELD_PARENTS and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED:
            if parent_idx >= len(parent_units_by_original_index):
                raise ValueError("internal error: parent index out of range")
            replacement = parent_units_by_original_index[parent_idx]
            parent_idx += 1
            if replacement is None:
                continue
            out_root_chunks.append((c.tag_raw, build_length_delimited_value_raw(replacement)))
            continue

        if c.field_number == ROOT_FIELD_ACCESSORIES and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED:
            if accessory_idx >= len(accessory_units):
                raise ValueError("internal error: accessory index out of range")
            out_root_chunks.append((c.tag_raw, build_length_delimited_value_raw(accessory_units[accessory_idx])))
            accessory_idx += 1
            continue

        if c.field_number == ROOT_FIELD_FILE_PATH and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED and not file_path_written:
            out_root_chunks.append((c.tag_raw, new_file_path_value_raw))
            file_path_written = True
            continue

        out_root_chunks.append((c.tag_raw, c.value_raw))

    if parent_idx != len(parent_units_by_original_index):
        raise ValueError("internal error: not all parent chunks consumed")
    if accessory_idx != len(accessory_units):
        raise ValueError("internal error: not all accessory chunks consumed")
    if not file_path_written:
        out_root_chunks.append((encode_tag(ROOT_FIELD_FILE_PATH, WIRE_TYPE_LENGTH_DELIMITED), new_file_path_value_raw))

    return encode_wire_chunks(out_root_chunks)


def output_file_name_from_path(output_gia_path: Path) -> str:
    """Return the file name part of an output path as a string."""
    return Path(str(output_gia_path)).name

