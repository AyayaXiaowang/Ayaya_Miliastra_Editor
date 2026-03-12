from __future__ import annotations

"""Policy implementation for move_decorations centering strategy."""

from typing import Any, Dict, List, Optional, Sequence, Tuple

from ugc_file_tools.gia.wire_decorations_transform_impl.accessory_codec import patch_accessory_unit
from ugc_file_tools.gia.wire_decorations_transform_impl.center_utils import compute_center
from ugc_file_tools.gia.wire_decorations_transform_impl.graph_unit_codec import (
    build_packed_accessory_ids,
    clear_graph_unit_related_ids,
    patch_graph_unit_related_ids,
    patch_packed_ids_inside_parent_graph,
)


def apply_move_decorations_policy(
    *,
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
    """Apply move_decorations policy to optionally merge and/or center accessory local positions."""
    local_positions = [tuple(it["local_pos"]) for it in list(accessory_items)]
    center_x, center_y, center_z = compute_center(local_positions, mode=str(center_mode))
    shift_x = float(center_x) if want_x else 0.0
    shift_y = float(center_y) if want_y else 0.0
    shift_z = float(center_z) if want_z else 0.0

    merged = False
    parent_units_by_original_index: List[Optional[bytes]] = [bytes(u) for u in list(parent_units)]

    candidate_set = {int(i) for i in list(candidate_parent_indices)}
    if merge_applicable and target_parent_index is not None and target_parent_unit_id is not None:
        accessory_unit_ids = [int(it["unit_id_int"]) for it in list(accessory_items)]
        packed_ids = build_packed_accessory_ids(accessory_unit_ids)

        new_target_parent = patch_graph_unit_related_ids(parent_units[int(target_parent_index)], unit_ids=accessory_unit_ids)
        new_target_parent = patch_packed_ids_inside_parent_graph(new_target_parent, packed_ids=packed_ids)

        new_parent_units: List[Optional[bytes]] = []
        for idx, u in enumerate(list(parent_units)):
            if idx == int(target_parent_index):
                new_parent_units.append(bytes(new_target_parent))
                continue
            if idx in candidate_set:
                if bool(drop_other_parents):
                    new_parent_units.append(None)
                else:
                    new_parent_units.append(bytes(clear_graph_unit_related_ids(u)))
                continue
            new_parent_units.append(bytes(u))
        parent_units_by_original_index = new_parent_units
        merged = True

    new_accessory_units: List[bytes] = []
    for it in list(accessory_items):
        out_unit = bytes(it["unit_bytes"])
        if merged and target_parent_unit_id is not None:
            out_unit = patch_accessory_unit(
                out_unit,
                new_pos=None,
                new_rot_deg=None,
                new_scale=None,
                new_parent_unit_id=int(target_parent_unit_id),
            )
        if bool(do_center):
            x, y, z = tuple(it["local_pos"])
            new_pos = (float(x - shift_x), float(y - shift_y), float(z - shift_z))
            out_unit = patch_accessory_unit(
                out_unit,
                new_pos=new_pos,
                new_rot_deg=None,
                new_scale=None,
                new_parent_unit_id=None,
            )
        new_accessory_units.append(bytes(out_unit))

    return {
        "parent_units_by_original_index": parent_units_by_original_index,
        "accessory_units": new_accessory_units,
        "merged": bool(merged),
        "center_space": "local",
        "shift_space": "decorations_local",
        "center": {"x": float(center_x), "y": float(center_y), "z": float(center_z)},
        "shift_applied": {"x": float(shift_x), "y": float(shift_y), "z": float(shift_z)},
        "target_parent_pos_before": None,
        "target_parent_pos_after": None,
    }

