from __future__ import annotations

"""Stable internal API for wire_decorations_transform facade."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ugc_file_tools.gia.container import unwrap_gia_container, validate_gia_container_file, wrap_gia_container
from ugc_file_tools.gia.wire_decorations_transform_impl.accessory_codec import (
    extract_accessory_parent_unit_id,
    extract_accessory_payload_bytes,
    extract_accessory_trs,
)
from ugc_file_tools.gia.wire_decorations_transform_impl.center_utils import normalize_axes
from ugc_file_tools.gia.wire_decorations_transform_impl.graph_unit_codec import (
    extract_graph_unit_id,
    extract_graph_unit_name,
    graph_unit_has_related_ids,
)
from ugc_file_tools.gia.wire_decorations_transform_impl.policies_keep_world import apply_keep_world_policy
from ugc_file_tools.gia.wire_decorations_transform_impl.policies_move_decorations import apply_move_decorations_policy
from ugc_file_tools.gia.wire_decorations_transform_impl.root_codec import (
    derive_file_path_from_base,
    extract_root_file_path_text,
    extract_root_parent_and_accessory_units,
    output_file_name_from_path,
    rebuild_root_proto_bytes,
)
from ugc_file_tools.gia.wire_decorations_transform_impl.wire_utils import parse_chunks
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.wire.codec import decode_message_to_wire_chunks

MIN_CANDIDATE_PARENTS_FOR_MERGE = 2

CENTER_POLICY_MOVE_DECORATIONS = "move_decorations"
CENTER_POLICY_KEEP_WORLD = "keep_world"

DEFAULT_OUTPUT_FILE_NAME = "decorations_centered.gia"


def _normalize_center_policy(center_policy: str) -> str:
    """Normalize center_policy into a known policy identifier string."""
    policy = str(center_policy or "").strip().lower()
    if policy not in {CENTER_POLICY_MOVE_DECORATIONS, CENTER_POLICY_KEEP_WORLD}:
        raise ValueError(
            f"invalid center_policy: {center_policy!r} (expected '{CENTER_POLICY_MOVE_DECORATIONS}'|'{CENTER_POLICY_KEEP_WORLD}')"
        )
    return str(policy)


def _select_target_parent(
    *,
    parent_units: Sequence[bytes],
    candidate_parent_indices: Sequence[int],
    merge_applicable: bool,
    target_parent_id: Optional[int],
    target_parent_name: str,
) -> Tuple[Optional[int], Optional[int]]:
    """Select the target parent index and unit id for merge or reporting."""
    target_parent_index: Optional[int] = None
    target_parent_unit_id: Optional[int] = None

    if bool(merge_applicable):
        if isinstance(target_parent_id, int):
            want_id = int(target_parent_id)
            matched = [i for i in list(candidate_parent_indices) if extract_graph_unit_id(parent_units[int(i)]) == want_id]
            if not matched:
                raise ValueError(f"未找到 target_parent_id={want_id}（candidate parents: {list(candidate_parent_indices)}）")
            if len(matched) >= MIN_CANDIDATE_PARENTS_FOR_MERGE:
                raise ValueError(f"target_parent_id={want_id} 匹配到多个 parent（不允许歧义）")
            target_parent_index = int(matched[0])
        else:
            name_text = str(target_parent_name or "").strip()
            if name_text != "":
                matched = [
                    i
                    for i in list(candidate_parent_indices)
                    if extract_graph_unit_name(parent_units[int(i)]).strip() == name_text
                ]
                if not matched:
                    raise ValueError(f"未找到 target_parent_name={name_text!r}")
                if len(matched) >= MIN_CANDIDATE_PARENTS_FOR_MERGE:
                    raise ValueError(f"target_parent_name={name_text!r} 匹配到多个 parent（请改用 --target-parent-id）")
                target_parent_index = int(matched[0])
            else:
                target_parent_index = int(list(candidate_parent_indices)[0])

        target_parent_unit_id = int(extract_graph_unit_id(parent_units[int(target_parent_index)]))
        return target_parent_index, target_parent_unit_id

    if list(candidate_parent_indices):
        target_parent_index = int(list(candidate_parent_indices)[0])
        target_parent_unit_id = int(extract_graph_unit_id(parent_units[int(target_parent_index)]))
    return target_parent_index, target_parent_unit_id


def _parse_accessory_items(accessory_units: Sequence[bytes]) -> List[Dict[str, Any]]:
    """Parse accessory GraphUnit list into items with ids, parent binds, and local TRS."""
    accessory_items: List[Dict[str, Any]] = []
    for unit in list(accessory_units):
        unit_bytes = bytes(unit)
        unit_id_int = int(extract_graph_unit_id(unit_bytes))
        local_pos, local_rot_deg, local_scale = extract_accessory_trs(unit_bytes)
        payload_bytes = extract_accessory_payload_bytes(unit_bytes)
        parent_id_int = int(extract_accessory_parent_unit_id(payload_bytes))
        accessory_items.append(
            {
                "unit_bytes": unit_bytes,
                "unit_id_int": int(unit_id_int),
                "parent_id_int": int(parent_id_int),
                "local_pos": (float(local_pos[0]), float(local_pos[1]), float(local_pos[2])),
                "local_rot_deg": (float(local_rot_deg[0]), float(local_rot_deg[1]), float(local_rot_deg[2])),
                "local_scale": (float(local_scale[0]), float(local_scale[1]), float(local_scale[2])),
            }
        )
    return accessory_items


def _compute_new_root_file_path(
    *,
    keep_file_path: bool,
    file_path_override: str,
    base_file_path_text: str,
    output_gia_path: Path,
) -> str:
    """Compute the Root.filePath text for output based on keep/override/default rules."""
    file_path_text = str(file_path_override or "").strip()
    if bool(keep_file_path):
        return str(base_file_path_text)
    if file_path_text != "":
        return str(file_path_text)
    output_name = output_file_name_from_path(output_gia_path)
    return derive_file_path_from_base(base_file_path=str(base_file_path_text), output_file_name=str(output_name))


def _load_root_from_gia_file(
    *, input_gia_path: Path, check_header: bool
) -> Tuple[Path, List[Any], str, List[bytes], List[bytes]]:
    """Load and parse root from a `.gia` container file and extract its key fields."""
    resolved_input_path = Path(input_gia_path).resolve()
    if not resolved_input_path.is_file():
        raise FileNotFoundError(f"input gia file not found: {str(resolved_input_path)!r}")
    if bool(check_header):
        validate_gia_container_file(resolved_input_path)

    proto_bytes = unwrap_gia_container(resolved_input_path, check_header=False)
    root_chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=proto_bytes, start_offset=0, end_offset=len(proto_bytes))
    if consumed != len(proto_bytes):
        raise ValueError("root wire decode not fully consumed")
    root_parsed = parse_chunks(root_chunks_raw)

    base_file_path_text = extract_root_file_path_text(root_parsed)
    parent_units, accessory_units = extract_root_parent_and_accessory_units(root_parsed)
    if not list(accessory_units):
        raise ValueError("root 缺少 accessories(field_2)")

    return resolved_input_path, root_parsed, str(base_file_path_text), list(parent_units), list(accessory_units)


def _prepare_merge_selection(
    *,
    parent_units: Sequence[bytes],
    do_merge: bool,
    target_parent_id: Optional[int],
    target_parent_name: str,
) -> Tuple[List[int], bool, Optional[int], Optional[int]]:
    """Compute merge applicability and select the target parent when needed."""
    candidate_parent_indices = [i for i, u in enumerate(list(parent_units)) if graph_unit_has_related_ids(u)]
    merge_applicable = bool(do_merge) and len(candidate_parent_indices) >= MIN_CANDIDATE_PARENTS_FOR_MERGE
    target_parent_index, target_parent_unit_id = _select_target_parent(
        parent_units=parent_units,
        candidate_parent_indices=candidate_parent_indices,
        merge_applicable=merge_applicable,
        target_parent_id=target_parent_id,
        target_parent_name=str(target_parent_name or ""),
    )
    return list(candidate_parent_indices), bool(merge_applicable), target_parent_index, target_parent_unit_id


def _apply_policy(
    *,
    policy: str,
    parent_units: Sequence[bytes],
    accessory_items: Sequence[Dict[str, Any]],
    candidate_parent_indices: Sequence[int],
    merge_applicable: bool,
    target_parent_index: Optional[int],
    target_parent_unit_id: Optional[int],
    drop_other_parents: bool,
    do_center: bool,
    center_mode: str,
    want_x: bool,
    want_y: bool,
    want_z: bool,
) -> Dict[str, Any]:
    """Apply the selected center/merge policy and return patch result for root rebuild."""
    if str(policy) == CENTER_POLICY_MOVE_DECORATIONS:
        return apply_move_decorations_policy(
            parent_units=parent_units,
            accessory_items=accessory_items,
            candidate_parent_indices=candidate_parent_indices,
            merge_applicable=merge_applicable,
            target_parent_index=target_parent_index,
            target_parent_unit_id=target_parent_unit_id,
            drop_other_parents=bool(drop_other_parents),
            do_center=bool(do_center),
            center_mode=str(center_mode),
            want_x=bool(want_x),
            want_y=bool(want_y),
            want_z=bool(want_z),
        )
    return apply_keep_world_policy(
        parent_units=parent_units,
        accessory_items=accessory_items,
        candidate_parent_indices=candidate_parent_indices,
        merge_applicable=merge_applicable,
        target_parent_index=target_parent_index,
        target_parent_unit_id=target_parent_unit_id,
        drop_other_parents=bool(drop_other_parents),
        do_center=bool(do_center),
        center_mode=str(center_mode),
        want_x=bool(want_x),
        want_y=bool(want_y),
        want_z=bool(want_z),
    )


def _write_output_gia(
    *,
    root_parsed: Sequence[Any],
    policy_result: Dict[str, Any],
    output_gia_path: Path,
    file_path_text: str,
) -> Tuple[Path, bytes]:
    """Rebuild and write the output `.gia`, returning the resolved output path and root proto bytes."""
    resolved_output_path = Path(output_gia_path)
    out_proto = rebuild_root_proto_bytes(
        root_parsed=root_parsed,
        parent_units_by_original_index=list(policy_result["parent_units_by_original_index"]),
        accessory_units=list(policy_result["accessory_units"]),
        file_path_text=str(file_path_text),
    )
    out_bytes = wrap_gia_container(out_proto)
    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_output_path.write_bytes(out_bytes)
    return resolved_output_path, bytes(out_proto)


def merge_and_center_decorations_gia_wire(
    *,
    input_gia_path: Path,
    output_gia_path: Path,
    check_header: bool,
    center_mode: str,
    center_axes: str,
    center_policy: str,
    do_center: bool,
    do_merge: bool,
    target_parent_id: Optional[int],
    target_parent_name: str,
    drop_other_parents: bool,
    keep_file_path: bool,
    file_path_override: str,
) -> Dict[str, Any]:
    """Merge and/or center a decorations `.gia` using wire-level minimal patches."""
    resolved_input_path, root_parsed, base_file_path_text, parent_units, accessory_units = _load_root_from_gia_file(
        input_gia_path=Path(input_gia_path),
        check_header=bool(check_header),
    )
    policy = _normalize_center_policy(str(center_policy))
    want_x, want_y, want_z = normalize_axes(center_axes)
    candidate_parent_indices, merge_applicable, target_parent_index, target_parent_unit_id = _prepare_merge_selection(
        parent_units=parent_units,
        do_merge=bool(do_merge),
        target_parent_id=target_parent_id,
        target_parent_name=str(target_parent_name or ""),
    )
    accessory_items = _parse_accessory_items(accessory_units)
    policy_result = _apply_policy(
        policy=str(policy),
        parent_units=parent_units,
        accessory_items=accessory_items,
        candidate_parent_indices=candidate_parent_indices,
        merge_applicable=bool(merge_applicable),
        target_parent_index=target_parent_index,
        target_parent_unit_id=target_parent_unit_id,
        drop_other_parents=bool(drop_other_parents),
        do_center=bool(do_center),
        center_mode=str(center_mode),
        want_x=bool(want_x),
        want_y=bool(want_y),
        want_z=bool(want_z),
    )

    resolved_output_path = resolve_output_file_path_in_out_dir(Path(output_gia_path), default_file_name=DEFAULT_OUTPUT_FILE_NAME)
    new_file_path_text = _compute_new_root_file_path(
        keep_file_path=bool(keep_file_path),
        file_path_override=str(file_path_override or ""),
        base_file_path_text=str(base_file_path_text),
        output_gia_path=resolved_output_path,
    )
    output_path_written, out_proto = _write_output_gia(
        root_parsed=root_parsed,
        policy_result=policy_result,
        output_gia_path=resolved_output_path,
        file_path_text=str(new_file_path_text),
    )

    return {
        "input_gia_file": str(resolved_input_path),
        "output_gia_file": str(output_path_written),
        "accessories_count": len(accessory_units),
        "center_policy": str(policy),
        "center_space": str(policy_result["center_space"]),
        "shift_space": str(policy_result["shift_space"]),
        "center_mode": str(center_mode),
        "center_axes": str(center_axes),
        "center": dict(policy_result["center"]),
        "shift_applied": dict(policy_result["shift_applied"]),
        "merged": bool(policy_result["merged"]),
        "target_parent_unit_id": int(target_parent_unit_id) if target_parent_unit_id is not None else None,
        "target_parent_pos_before": policy_result.get("target_parent_pos_before"),
        "target_parent_pos_after": policy_result.get("target_parent_pos_after"),
        "file_path": str(new_file_path_text),
        "proto_size": len(out_proto),
    }

