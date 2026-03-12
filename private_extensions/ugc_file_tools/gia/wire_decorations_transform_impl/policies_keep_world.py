from __future__ import annotations

"""Policy implementation for keep_world centering strategy."""

from typing import Any, Dict, List, Optional, Sequence, Tuple

from ugc_file_tools.gia.wire_decorations_transform_impl.accessory_codec import patch_accessory_unit
from ugc_file_tools.gia.wire_decorations_transform_impl.center_utils import compute_center
from ugc_file_tools.gia.wire_decorations_transform_impl.graph_unit_codec import (
    build_packed_accessory_ids,
    clear_graph_unit_related_ids,
    extract_graph_unit_id,
    extract_graph_unit_trs,
    patch_graph_unit_pos,
    patch_graph_unit_related_ids,
    patch_packed_ids_inside_parent_graph,
)
from ugc_file_tools.gia.wire_decorations_transform_impl.math_trs import (
    Mat4,
    decompose_mat4_to_trs,
    mat4_from_trs,
    mat4_inv_trs,
    mat4_mul,
)

ORIGIN = (0.0, 0.0, 0.0)


def _build_parent_maps(parent_units: Sequence[bytes]) -> Tuple[Dict[int, bytes], Dict[int, int]]:
    """Build (parent_unit_by_id, parent_index_by_id) mappings from Root.field_1 GraphUnit list."""
    parent_unit_by_id: Dict[int, bytes] = {}
    parent_index_by_id: Dict[int, int] = {}
    for idx, u in enumerate(list(parent_units)):
        uid = int(extract_graph_unit_id(u))
        if uid in parent_unit_by_id:
            raise ValueError(f"duplicated parent GraphUnit id in Root.field_1: {uid}")
        parent_unit_by_id[uid] = bytes(u)
        parent_index_by_id[uid] = int(idx)
    return parent_unit_by_id, parent_index_by_id


def _collect_involved_parent_ids(
    accessory_items: Sequence[Dict[str, Any]],
    *,
    merge_applicable: bool,
    target_parent_unit_id: Optional[int],
) -> List[int]:
    """Collect parent ids that must be resolved to keep world transforms consistent."""
    involved_parent_ids = sorted({int(it["parent_id_int"]) for it in list(accessory_items)})
    if merge_applicable and isinstance(target_parent_unit_id, int):
        if int(target_parent_unit_id) not in involved_parent_ids:
            involved_parent_ids.append(int(target_parent_unit_id))
            involved_parent_ids.sort()
    return involved_parent_ids


def _compute_parent_trs_and_mats(
    *,
    parent_unit_by_id: Dict[int, bytes],
    involved_parent_ids: Sequence[int],
) -> Tuple[Dict[int, Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]], Dict[int, Mat4]]:
    """Compute parent TRS and parent matrices for all involved parent ids."""
    parent_trs_by_id: Dict[int, Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]] = {}
    parent_mat_by_id: Dict[int, Mat4] = {}
    for pid in list(involved_parent_ids):
        if int(pid) not in parent_unit_by_id:
            raise ValueError(f"accessory 绑定的 parent_id={pid} 不存在于 Root.field_1（无法保持世界坐标不动）")
        trs = extract_graph_unit_trs(parent_unit_by_id[int(pid)])
        parent_trs_by_id[int(pid)] = trs
        parent_mat_by_id[int(pid)] = mat4_from_trs(pos=trs[0], rot_deg=trs[1], scale=trs[2])
    return parent_trs_by_id, parent_mat_by_id


def _compute_accessory_world_mats(accessory_items: Sequence[Dict[str, Any]], *, parent_mat_by_id: Dict[int, Mat4]) -> List[Tuple[float, float, float]]:
    """Compute and attach world matrices/positions to accessory_items and return world position list."""
    world_positions_all: List[Tuple[float, float, float]] = []
    for it in list(accessory_items):
        pid = int(it["parent_id_int"])
        parent_mat = parent_mat_by_id[pid]
        local_mat = mat4_from_trs(
            pos=tuple(it["local_pos"]),
            rot_deg=tuple(it["local_rot_deg"]),
            scale=tuple(it["local_scale"]),
        )
        world_mat = mat4_mul(parent_mat, local_mat)
        wx, wy, wz = float(world_mat[0][3]), float(world_mat[1][3]), float(world_mat[2][3])
        it["world_mat"] = world_mat
        it["world_pos"] = (wx, wy, wz)
        world_positions_all.append((wx, wy, wz))
    return world_positions_all


def _build_merged_parent_units(
    *,
    parent_units: Sequence[bytes],
    candidate_parent_indices: Sequence[int],
    target_parent_index: int,
    new_target_parent_bytes: bytes,
    drop_other_parents: bool,
) -> List[Optional[bytes]]:
    """Build the updated Root.field_1 parent list after merge by keeping order and optionally dropping other parents."""
    candidate_set = {int(i) for i in list(candidate_parent_indices)}
    out: List[Optional[bytes]] = []
    for idx, u in enumerate(list(parent_units)):
        if idx == int(target_parent_index):
            out.append(bytes(new_target_parent_bytes))
            continue
        if idx in candidate_set:
            if bool(drop_other_parents):
                out.append(None)
            else:
                out.append(bytes(clear_graph_unit_related_ids(u)))
            continue
        out.append(bytes(u))
    return out


def _patch_accessories_for_merge(
    *,
    accessory_items: Sequence[Dict[str, Any]],
    inv_target_after: Mat4,
    target_parent_unit_id: int,
) -> List[bytes]:
    """Patch accessories by rebinding to target parent and compensating local TRS to keep world unchanged."""
    new_accessory_units: List[bytes] = []
    for it in list(accessory_items):
        local_new_mat = mat4_mul(inv_target_after, it["world_mat"])
        new_pos, new_rot_deg, new_scale = decompose_mat4_to_trs(local_new_mat)
        out_unit = patch_accessory_unit(
            bytes(it["unit_bytes"]),
            new_pos=tuple(new_pos),
            new_rot_deg=tuple(new_rot_deg),
            new_scale=tuple(new_scale),
            new_parent_unit_id=int(target_parent_unit_id),
        )
        new_accessory_units.append(bytes(out_unit))
    return new_accessory_units


def _patch_accessories_for_center_per_parent(
    *,
    accessory_items: Sequence[Dict[str, Any]],
    parent_new_pos_by_id: Dict[int, Tuple[float, float, float]],
    parent_trs_by_id: Dict[int, Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]],
) -> List[bytes]:
    """Patch accessories local positions to compensate moved parents while preserving world positions."""
    new_accessory_units: List[bytes] = []
    for it in list(accessory_items):
        pid = int(it["parent_id_int"])
        p1 = parent_new_pos_by_id.get(pid, parent_trs_by_id[pid][0])
        _p0, r0, s0 = parent_trs_by_id[pid]
        wx, wy, wz = tuple(it["world_pos"])
        delta = (float(wx - p1[0]), float(wy - p1[1]), float(wz - p1[2]))
        inv_rs = mat4_inv_trs(pos=ORIGIN, rot_deg=tuple(r0), scale=tuple(s0))
        new_local = (
            float(inv_rs[0][0] * delta[0] + inv_rs[0][1] * delta[1] + inv_rs[0][2] * delta[2]),
            float(inv_rs[1][0] * delta[0] + inv_rs[1][1] * delta[1] + inv_rs[1][2] * delta[2]),
            float(inv_rs[2][0] * delta[0] + inv_rs[2][1] * delta[1] + inv_rs[2][2] * delta[2]),
        )
        out_unit = patch_accessory_unit(
            bytes(it["unit_bytes"]),
            new_pos=new_local,
            new_rot_deg=None,
            new_scale=None,
            new_parent_unit_id=None,
        )
        new_accessory_units.append(bytes(out_unit))
    return new_accessory_units


def _apply_keep_world_merge_branch(
    *,
    parent_units: Sequence[bytes],
    accessory_items: Sequence[Dict[str, Any]],
    candidate_parent_indices: Sequence[int],
    target_parent_index: int,
    target_parent_unit_id: int,
    drop_other_parents: bool,
    do_center: bool,
    want_x: bool,
    want_y: bool,
    want_z: bool,
    center_x: float,
    center_y: float,
    center_z: float,
    center_obj: Dict[str, float],
    parent_trs_by_id: Dict[int, Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]],
) -> Dict[str, Any]:
    """Apply keep_world merge branch by moving target parent and compensating accessory local TRS."""
    p0, r0, s0 = parent_trs_by_id[int(target_parent_unit_id)]
    target_parent_pos_before = {"x": float(p0[0]), "y": float(p0[1]), "z": float(p0[2])}

    if bool(do_center):
        p1 = (
            float(center_x) if want_x else float(p0[0]),
            float(center_y) if want_y else float(p0[1]),
            float(center_z) if want_z else float(p0[2]),
        )
    else:
        p1 = (float(p0[0]), float(p0[1]), float(p0[2]))
    target_parent_pos_after = {"x": float(p1[0]), "y": float(p1[1]), "z": float(p1[2])}

    shift_applied = {"x": float(p1[0] - p0[0]), "y": float(p1[1] - p0[1]), "z": float(p1[2] - p0[2])}

    accessory_unit_ids = [int(it["unit_id_int"]) for it in list(accessory_items)]
    packed_ids = build_packed_accessory_ids(accessory_unit_ids)

    new_target_parent = patch_graph_unit_related_ids(parent_units[int(target_parent_index)], unit_ids=accessory_unit_ids)
    new_target_parent = patch_packed_ids_inside_parent_graph(new_target_parent, packed_ids=packed_ids)
    new_target_parent = patch_graph_unit_pos(new_target_parent, new_pos=tuple(p1))

    parent_units_by_original_index = _build_merged_parent_units(
        parent_units=parent_units,
        candidate_parent_indices=candidate_parent_indices,
        target_parent_index=int(target_parent_index),
        new_target_parent_bytes=bytes(new_target_parent),
        drop_other_parents=bool(drop_other_parents),
    )

    inv_target_after = mat4_inv_trs(pos=tuple(p1), rot_deg=tuple(r0), scale=tuple(s0))
    new_accessory_units = _patch_accessories_for_merge(
        accessory_items=accessory_items,
        inv_target_after=inv_target_after,
        target_parent_unit_id=int(target_parent_unit_id),
    )
    return {
        "parent_units_by_original_index": parent_units_by_original_index,
        "accessory_units": new_accessory_units,
        "merged": True,
        "center_space": "world",
        "shift_space": "parent_world",
        "center": dict(center_obj),
        "shift_applied": dict(shift_applied),
        "target_parent_pos_before": target_parent_pos_before,
        "target_parent_pos_after": target_parent_pos_after,
    }


def _apply_keep_world_no_merge_no_center(
    *,
    parent_units: Sequence[bytes],
    accessory_items: Sequence[Dict[str, Any]],
    center_obj: Dict[str, float],
) -> Dict[str, Any]:
    """Return unchanged units for keep_world when do_center is False and merge is disabled."""
    shift_applied = {"x": 0.0, "y": 0.0, "z": 0.0}
    parent_units_by_original_index: List[Optional[bytes]] = [bytes(u) for u in list(parent_units)]
    new_accessory_units = [bytes(it["unit_bytes"]) for it in list(accessory_items)]
    return {
        "parent_units_by_original_index": parent_units_by_original_index,
        "accessory_units": new_accessory_units,
        "merged": False,
        "center_space": "world",
        "shift_space": "parent_world",
        "center": dict(center_obj),
        "shift_applied": dict(shift_applied),
        "target_parent_pos_before": None,
        "target_parent_pos_after": None,
    }


def _apply_keep_world_no_merge_center_per_parent(
    *,
    parent_units: Sequence[bytes],
    accessory_items: Sequence[Dict[str, Any]],
    parent_trs_by_id: Dict[int, Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]],
    parent_index_by_id: Dict[int, int],
    center_mode: str,
    want_x: bool,
    want_y: bool,
    want_z: bool,
    center_obj: Dict[str, float],
) -> Dict[str, Any]:
    """Apply keep_world per-parent centering by moving each parent and compensating accessory local positions."""
    shift_applied = {"x": 0.0, "y": 0.0, "z": 0.0}
    parent_units_by_original_index: List[Optional[bytes]] = [bytes(u) for u in list(parent_units)]

    parent_new_pos_by_id: Dict[int, Tuple[float, float, float]] = {}
    group_world: Dict[int, List[Tuple[float, float, float]]] = {}
    for it in list(accessory_items):
        group_world.setdefault(int(it["parent_id_int"]), []).append(tuple(it["world_pos"]))
    for pid, pts in group_world.items():
        cpx, cpy, cpz = compute_center(pts, mode=str(center_mode))
        p0, _r0, _s0 = parent_trs_by_id[int(pid)]
        p1 = (
            float(cpx) if want_x else float(p0[0]),
            float(cpy) if want_y else float(p0[1]),
            float(cpz) if want_z else float(p0[2]),
        )
        parent_new_pos_by_id[int(pid)] = tuple(p1)

    for pid, p1 in parent_new_pos_by_id.items():
        idx = parent_index_by_id.get(int(pid))
        if idx is None:
            raise ValueError(f"internal error: parent_index missing for pid={pid}")
        parent_units_by_original_index[int(idx)] = patch_graph_unit_pos(parent_units_by_original_index[int(idx)], new_pos=tuple(p1))

    new_accessory_units = _patch_accessories_for_center_per_parent(
        accessory_items=accessory_items,
        parent_new_pos_by_id=parent_new_pos_by_id,
        parent_trs_by_id=parent_trs_by_id,
    )

    return {
        "parent_units_by_original_index": parent_units_by_original_index,
        "accessory_units": new_accessory_units,
        "merged": False,
        "center_space": "world",
        "shift_space": "parent_world",
        "center": dict(center_obj),
        "shift_applied": dict(shift_applied),
        "target_parent_pos_before": None,
        "target_parent_pos_after": None,
    }


def apply_keep_world_policy(
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
    """Apply keep_world policy to optionally merge and/or center while keeping accessory world transforms unchanged."""
    parent_unit_by_id, parent_index_by_id = _build_parent_maps(parent_units)
    involved_parent_ids = _collect_involved_parent_ids(
        accessory_items,
        merge_applicable=bool(merge_applicable),
        target_parent_unit_id=target_parent_unit_id,
    )
    parent_trs_by_id, parent_mat_by_id = _compute_parent_trs_and_mats(
        parent_unit_by_id=parent_unit_by_id,
        involved_parent_ids=involved_parent_ids,
    )
    world_positions_all = _compute_accessory_world_mats(accessory_items, parent_mat_by_id=parent_mat_by_id)

    center_x, center_y, center_z = compute_center(world_positions_all, mode=str(center_mode))
    center_obj = {"x": float(center_x), "y": float(center_y), "z": float(center_z)}

    if merge_applicable and target_parent_unit_id is not None and target_parent_index is not None:
        return _apply_keep_world_merge_branch(
            parent_units=parent_units,
            accessory_items=accessory_items,
            candidate_parent_indices=candidate_parent_indices,
            target_parent_index=int(target_parent_index),
            target_parent_unit_id=int(target_parent_unit_id),
            drop_other_parents=bool(drop_other_parents),
            do_center=bool(do_center),
            want_x=bool(want_x),
            want_y=bool(want_y),
            want_z=bool(want_z),
            center_x=float(center_x),
            center_y=float(center_y),
            center_z=float(center_z),
            center_obj=dict(center_obj),
            parent_trs_by_id=parent_trs_by_id,
        )

    if not bool(do_center):
        return _apply_keep_world_no_merge_no_center(
            parent_units=parent_units,
            accessory_items=accessory_items,
            center_obj=dict(center_obj),
        )

    return _apply_keep_world_no_merge_center_per_parent(
        parent_units=parent_units,
        accessory_items=accessory_items,
        parent_trs_by_id=parent_trs_by_id,
        parent_index_by_id=parent_index_by_id,
        center_mode=str(center_mode),
        want_x=bool(want_x),
        want_y=bool(want_y),
        want_z=bool(want_z),
        center_obj=dict(center_obj),
    )

