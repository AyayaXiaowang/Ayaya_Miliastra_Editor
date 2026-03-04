"""Project-level decorations merge helpers (pure Python, no PyQt).

This module provides utilities to merge "common_inspector.model.decorations" from multiple
`InstanceConfig` objects into a single target instance, optionally applying a simple centering
transform.

Data contract (UI-aligned):
- Decorations are stored at: `instance.metadata["common_inspector"]["model"]["decorations"]`
- Each decoration item is a dict, typically containing:
  - instanceId, displayName, isVisible, assetId, parentId
  - transform: {pos:{x,y,z}, rot:{x,y,z}, scale:{x,y,z}, isLocked}
  - physics: {enableCollision, isClimbable, showPreview}

Notes:
- This module intentionally does NOT depend on any `app.ui.*` code to keep `app/models -> app.ui`
  boundary intact. It also does not require `private_extensions`.
- Re-parenting/world-keeping is implemented using TRS matrix math (Unity-like Euler ZXY convention):
  for each decoration local transform L under source parent Psrc, we compute:
    L' = inv(Pdst) ∘ Psrc ∘ L
  so that the decoration world position stays unchanged after moving under the target parent.
  Rotation/scale are best-effort because pure TRS cannot represent shear (a common case with non-uniform scale + rotation).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime
from secrets import token_hex
from typing import Any, Iterable, Mapping, MutableMapping, Optional, Sequence, Tuple

from engine.graph.models.package_model import InstanceConfig, TemplateConfig
from app.common.trs_math import TRS, decompose_mat4_to_trs, mat4_from_trs, mat4_inv_trs, mat4_mul

COMMON_INSPECTOR_KEY = "common_inspector"
_MODEL_KEY = "model"
_DECORATIONS_KEY = "decorations"


@dataclass(frozen=True, slots=True)
class MergeDecorationsOutcome:
    target_instance: InstanceConfig
    merged_decorations: list[dict[str, object]]
    source_instance_ids: list[str]
    source_instances_with_decorations: list[str]
    skipped_instance_ids: list[str]
    warnings: list[str]
    centered: bool
    center_mode: str
    center_axes: str
    center_policy: str
    center_point: tuple[float, float, float] | None
    shift_applied: tuple[float, float, float] | None


@dataclass(frozen=True, slots=True)
class MergeTemplateDecorationsOutcome:
    target_template: TemplateConfig
    merged_decorations: list[dict[str, object]]
    source_template_ids: list[str]
    source_templates_with_decorations: list[str]
    skipped_template_ids: list[str]
    warnings: list[str]
    centered: bool
    center_mode: str
    center_axes: str
    center_point: tuple[float, float, float] | None
    shift_applied: tuple[float, float, float] | None


def _safe_str(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _safe_bool(value: object, default: bool) -> bool:
    return bool(value) if isinstance(value, bool) else bool(default)


def _safe_int(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, float) and not isinstance(value, bool):
        return int(value)
    return int(default)


def _safe_float(value: object, default: float) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return float(default)


def _generate_prefixed_id(prefix: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    random_suffix = token_hex(2)
    return f"{prefix}_{timestamp}_{random_suffix}"


def _ensure_dict_field(parent: MutableMapping[str, object], key: str) -> MutableMapping[str, object]:
    current = parent.get(key)
    if isinstance(current, MutableMapping):
        return current
    new_value: dict[str, object] = {}
    parent[key] = new_value
    return new_value


def _as_float3(seq: object, *, default: tuple[float, float, float]) -> tuple[float, float, float]:
    if isinstance(seq, Sequence) and not isinstance(seq, (str, bytes)) and len(seq) == 3:
        x, y, z = seq[0], seq[1], seq[2]
        return (
            _safe_float(x, default[0]),
            _safe_float(y, default[1]),
            _safe_float(z, default[2]),
        )
    return tuple(float(v) for v in default)


def _as_numeric_float3(seq: object) -> tuple[float, float, float] | None:
    """Parse a numeric vec3 strictly (no fallback coercion).

    Notes
    - This is used for `metadata["ugc_scale"]`, which is emitted by some import pipelines and is
      treated as the authoritative scale for UGC writeback.
    """
    if isinstance(seq, Sequence) and not isinstance(seq, (str, bytes)) and len(seq) == 3:
        x, y, z = seq[0], seq[1], seq[2]
        if isinstance(x, (int, float)) and not isinstance(x, bool) and isinstance(y, (int, float)) and not isinstance(y, bool) and isinstance(z, (int, float)) and not isinstance(z, bool):
            return (float(x), float(y), float(z))
    return None


def _get_instance_scale(instance: InstanceConfig) -> tuple[float, float, float]:
    """Resolve instance parent scale used by keep_world reparenting.

    Priority
    - `instance.metadata["ugc_scale"]` (when present and valid)  ✅ matches `.gia` import/writeback
    - `instance.scale`
    """
    meta = getattr(instance, "metadata", None)
    if isinstance(meta, Mapping):
        ugc_scale = _as_numeric_float3(meta.get("ugc_scale"))
        if ugc_scale is not None:
            return ugc_scale
    return _as_float3(getattr(instance, "scale", None), default=(1.0, 1.0, 1.0))


def _get_decoration_pos(deco: Mapping[str, object]) -> tuple[float, float, float]:
    tf = deco.get("transform")
    if isinstance(tf, Mapping):
        pos = tf.get("pos")
        if isinstance(pos, Mapping):
            return (
                _safe_float(pos.get("x"), 0.0),
                _safe_float(pos.get("y"), 0.0),
                _safe_float(pos.get("z"), 0.0),
            )
    return 0.0, 0.0, 0.0


def _set_decoration_pos(deco: MutableMapping[str, object], *, pos: tuple[float, float, float]) -> None:
    tf = deco.get("transform")
    if not isinstance(tf, MutableMapping):
        tf = {}
        deco["transform"] = tf
    pos_dict = tf.get("pos")
    if not isinstance(pos_dict, MutableMapping):
        pos_dict = {}
        tf["pos"] = pos_dict
    pos_dict["x"] = float(pos[0])
    pos_dict["y"] = float(pos[1])
    pos_dict["z"] = float(pos[2])


def _get_decoration_trs(deco: Mapping[str, object]) -> TRS:
    tf = deco.get("transform")
    if not isinstance(tf, Mapping):
        tf = {}
    pos = tf.get("pos") if isinstance(tf.get("pos"), Mapping) else {}
    rot = tf.get("rot") if isinstance(tf.get("rot"), Mapping) else {}
    scale = tf.get("scale") if isinstance(tf.get("scale"), Mapping) else {}

    return TRS(
        pos=(
            _safe_float(pos.get("x"), 0.0),
            _safe_float(pos.get("y"), 0.0),
            _safe_float(pos.get("z"), 0.0),
        ),
        rot_deg=(
            _safe_float(rot.get("x"), 0.0),
            _safe_float(rot.get("y"), 0.0),
            _safe_float(rot.get("z"), 0.0),
        ),
        scale=(
            _safe_float(scale.get("x"), 1.0),
            _safe_float(scale.get("y"), 1.0),
            _safe_float(scale.get("z"), 1.0),
        ),
    )


def _set_decoration_trs(deco: MutableMapping[str, object], *, trs: TRS) -> None:
    tf = deco.get("transform")
    if not isinstance(tf, MutableMapping):
        tf = {}
        deco["transform"] = tf

    pos_dict = tf.get("pos")
    if not isinstance(pos_dict, MutableMapping):
        pos_dict = {}
        tf["pos"] = pos_dict
    rot_dict = tf.get("rot")
    if not isinstance(rot_dict, MutableMapping):
        rot_dict = {}
        tf["rot"] = rot_dict
    scale_dict = tf.get("scale")
    if not isinstance(scale_dict, MutableMapping):
        scale_dict = {}
        tf["scale"] = scale_dict

    pos_dict["x"], pos_dict["y"], pos_dict["z"] = float(trs.pos[0]), float(trs.pos[1]), float(trs.pos[2])
    rot_dict["x"], rot_dict["y"], rot_dict["z"] = (
        float(trs.rot_deg[0]),
        float(trs.rot_deg[1]),
        float(trs.rot_deg[2]),
    )
    scale_dict["x"], scale_dict["y"], scale_dict["z"] = (
        float(trs.scale[0]),
        float(trs.scale[1]),
        float(trs.scale[2]),
    )


def _mul_rs_mat4_vec3(m: tuple[tuple[float, float, float, float], ...], v: tuple[float, float, float]) -> tuple[float, float, float]:
    """Multiply the upper-left 3x3 (rotation*scale) of a mat4 by a vec3."""
    x, y, z = float(v[0]), float(v[1]), float(v[2])
    return (
        float(m[0][0] * x + m[0][1] * y + m[0][2] * z),
        float(m[1][0] * x + m[1][1] * y + m[1][2] * z),
        float(m[2][0] * x + m[2][1] * y + m[2][2] * z),
    )


def _normalize_decoration(raw: Mapping[str, object]) -> dict[str, object]:
    # Keep unknown fields, but ensure core keys exist for downstream tooling.
    out: dict[str, object] = dict(raw)
    instance_id = _safe_str(out.get("instanceId") or out.get("id"))
    if not instance_id:
        instance_id = _generate_prefixed_id("deco")

    display_name = _safe_str(out.get("displayName") or out.get("name") or instance_id)
    out["instanceId"] = instance_id
    out["displayName"] = display_name
    out["isVisible"] = _safe_bool(out.get("isVisible"), True)
    out["assetId"] = _safe_int(out.get("assetId"), 0)
    out["parentId"] = _safe_str(out.get("parentId") or "GI_RootNode") or "GI_RootNode"

    tf = out.get("transform") if isinstance(out.get("transform"), Mapping) else {}
    pos = tf.get("pos") if isinstance(tf.get("pos"), Mapping) else {}
    rot = tf.get("rot") if isinstance(tf.get("rot"), Mapping) else {}
    scale = tf.get("scale") if isinstance(tf.get("scale"), Mapping) else {}
    out["transform"] = {
        "pos": {
            "x": _safe_float(pos.get("x"), 0.0),
            "y": _safe_float(pos.get("y"), 0.0),
            "z": _safe_float(pos.get("z"), 0.0),
        },
        "rot": {
            "x": _safe_float(rot.get("x"), 0.0),
            "y": _safe_float(rot.get("y"), 0.0),
            "z": _safe_float(rot.get("z"), 0.0),
        },
        "scale": {
            "x": _safe_float(scale.get("x"), 1.0),
            "y": _safe_float(scale.get("y"), 1.0),
            "z": _safe_float(scale.get("z"), 1.0),
        },
        "isLocked": _safe_bool(tf.get("isLocked"), False),
    }

    physics = out.get("physics") if isinstance(out.get("physics"), Mapping) else {}
    out["physics"] = {
        "enableCollision": _safe_bool(physics.get("enableCollision"), False),
        "isClimbable": _safe_bool(physics.get("isClimbable"), False),
        "showPreview": _safe_bool(physics.get("showPreview"), False),
    }
    return out


def _extract_instance_decorations(instance: InstanceConfig) -> list[dict[str, object]]:
    meta = getattr(instance, "metadata", None)
    if not isinstance(meta, Mapping):
        return []
    inspector = meta.get(COMMON_INSPECTOR_KEY)
    if not isinstance(inspector, Mapping):
        return []
    model = inspector.get(_MODEL_KEY)
    if not isinstance(model, Mapping):
        return []
    raw_decorations = model.get(_DECORATIONS_KEY)
    if not isinstance(raw_decorations, list):
        return []

    decorations: list[dict[str, object]] = []
    for entry in raw_decorations:
        if isinstance(entry, Mapping):
            decorations.append(_normalize_decoration(entry))
    return decorations


def _extract_template_decorations(template: TemplateConfig) -> list[dict[str, object]]:
    meta = getattr(template, "metadata", None)
    if not isinstance(meta, Mapping):
        return []
    inspector = meta.get(COMMON_INSPECTOR_KEY)
    if not isinstance(inspector, Mapping):
        return []
    model = inspector.get(_MODEL_KEY)
    if not isinstance(model, Mapping):
        return []
    raw_decorations = model.get(_DECORATIONS_KEY)
    if not isinstance(raw_decorations, list):
        return []

    decorations: list[dict[str, object]] = []
    for entry in raw_decorations:
        if isinstance(entry, Mapping):
            decorations.append(_normalize_decoration(entry))
    return decorations


def _apply_axes(value: tuple[float, float, float], axes: str) -> tuple[float, float, float]:
    axes_norm = str(axes or "").strip().lower()
    allowed = {"x", "y", "z"}
    want = set(axes_norm)
    if not want or (want - allowed):
        # fallback to xyz
        want = {"x", "y", "z"}
    x, y, z = float(value[0]), float(value[1]), float(value[2])
    return (
        x if "x" in want else 0.0,
        y if "y" in want else 0.0,
        z if "z" in want else 0.0,
    )


def _compute_center(
    positions: Sequence[tuple[float, float, float]],
    *,
    mode: str,
) -> tuple[float, float, float]:
    if not positions:
        return 0.0, 0.0, 0.0
    mode_norm = str(mode or "").strip().lower()
    if mode_norm not in {"bbox", "mean"}:
        mode_norm = "bbox"

    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    zs = [p[2] for p in positions]
    if mode_norm == "mean":
        n = float(len(positions))
        return (sum(xs) / n, sum(ys) / n, sum(zs) / n)
    # bbox
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0, (min(zs) + max(zs)) / 2.0)


def merge_instance_decorations(
    *,
    source_instances: Iterable[InstanceConfig],
    target_instance: InstanceConfig,
    include_target_existing: bool = True,
    center: bool = False,
    center_mode: str = "bbox",
    center_axes: str = "xyz",
    center_policy: str = "keep_world",
) -> MergeDecorationsOutcome:
    """Merge decorations from sources into target (best-effort).

    Parameters
    - include_target_existing: when True, target's existing decorations are kept and included.
    - center_policy:
      - keep_world: shift target.position by +shift and decorations by -shift.
      - move_decorations: shift decorations by -shift, keep target.position unchanged.
    """
    warnings: list[str] = []
    source_ids: list[str] = []
    source_with_decorations: list[str] = []
    skipped_ids: list[str] = []

    target_pos = _as_float3(getattr(target_instance, "position", None), default=(0.0, 0.0, 0.0))
    target_rot = _as_float3(getattr(target_instance, "rotation", None), default=(0.0, 0.0, 0.0))
    target_scale = _get_instance_scale(target_instance)

    target_parent_trs = TRS(pos=tuple(target_pos), rot_deg=tuple(target_rot), scale=tuple(target_scale))
    inv_target_parent = mat4_inv_trs(pos=target_parent_trs.pos, rot_deg=target_parent_trs.rot_deg, scale=target_parent_trs.scale)

    # RS matrix for keep_world centering compensation (pos=0)
    target_parent_rs = mat4_from_trs(pos=(0.0, 0.0, 0.0), rot_deg=target_parent_trs.rot_deg, scale=target_parent_trs.scale)

    # Start with existing target decorations (optional)
    merged: list[dict[str, object]] = []
    if include_target_existing:
        merged.extend(_extract_instance_decorations(target_instance))

    # Merge from sources
    for inst in list(source_instances):
        if not isinstance(inst, InstanceConfig):
            continue
        sid = _safe_str(getattr(inst, "instance_id", ""))
        if sid:
            source_ids.append(sid)

        src_pos = _as_float3(getattr(inst, "position", None), default=(0.0, 0.0, 0.0))
        src_rot = _as_float3(getattr(inst, "rotation", None), default=(0.0, 0.0, 0.0))
        src_scale = _get_instance_scale(inst)

        decos = _extract_instance_decorations(inst)
        if not decos:
            if sid:
                skipped_ids.append(sid)
            continue

        if sid:
            source_with_decorations.append(sid)

        # keep_world reparent (full TRS):
        #   local' = inv(target_parent) ∘ source_parent ∘ local
        src_parent_trs = TRS(pos=tuple(src_pos), rot_deg=tuple(src_rot), scale=tuple(src_scale))
        src_parent = mat4_from_trs(pos=src_parent_trs.pos, rot_deg=src_parent_trs.rot_deg, scale=src_parent_trs.scale)
        rel = mat4_mul(inv_target_parent, src_parent)
        for deco in decos:
            local = _get_decoration_trs(deco)
            local_mat = mat4_from_trs(pos=local.pos, rot_deg=local.rot_deg, scale=local.scale)
            new_mat = mat4_mul(rel, local_mat)
            new_local = decompose_mat4_to_trs(new_mat)
            _set_decoration_trs(deco, trs=new_local)
            merged.append(dict(deco))

    if not merged:
        raise ValueError("未找到可合并的装饰物：所选实体均不包含 common_inspector.model.decorations。")

    # Ensure instanceId unique & non-empty
    used: set[str] = set()
    for deco in merged:
        raw_id = _safe_str(deco.get("instanceId") or "")
        if not raw_id or raw_id in used:
            new_id = _generate_prefixed_id("deco")
            while new_id in used:
                new_id = _generate_prefixed_id("deco")
            deco["instanceId"] = new_id
            raw_id = new_id
        used.add(raw_id)

    center_point: tuple[float, float, float] | None = None
    shift_applied: tuple[float, float, float] | None = None

    do_center = bool(center)
    policy = str(center_policy or "").strip().lower()
    if policy not in {"keep_world", "move_decorations"}:
        policy = "keep_world"

    if do_center:
        positions = [_get_decoration_pos(d) for d in merged]
        center_point = _compute_center(positions, mode=str(center_mode or "bbox"))
        shift = _apply_axes(center_point, str(center_axes or "xyz"))
        shift_applied = shift

        if any(abs(v) > 1e-12 for v in shift):
            for deco in merged:
                x, y, z = _get_decoration_pos(deco)
                _set_decoration_pos(
                    deco,
                    pos=(x - shift[0], y - shift[1], z - shift[2]),
                )

            if policy == "keep_world":
                # parent_new = parent_old ∘ T(shift_local)  ->  pos += (R*S) * shift_local
                dx, dy, dz = _mul_rs_mat4_vec3(target_parent_rs, tuple(shift))
                target_pos = (target_pos[0] + dx, target_pos[1] + dy, target_pos[2] + dz)

    # Build updated target instance (do not mutate original in place)
    new_target = copy.deepcopy(target_instance)
    new_target.position = [float(target_pos[0]), float(target_pos[1]), float(target_pos[2])]

    new_meta: dict[str, object] = {}
    if isinstance(getattr(new_target, "metadata", None), Mapping):
        new_meta = copy.deepcopy(getattr(new_target, "metadata"))
    new_target.metadata = new_meta
    inspector2 = _ensure_dict_field(new_meta, COMMON_INSPECTOR_KEY)
    model2 = _ensure_dict_field(inspector2, _MODEL_KEY)
    model2[_DECORATIONS_KEY] = [dict(d) for d in merged]

    return MergeDecorationsOutcome(
        target_instance=new_target,
        merged_decorations=[dict(d) for d in merged],
        source_instance_ids=list(source_ids),
        source_instances_with_decorations=list(source_with_decorations),
        skipped_instance_ids=list(skipped_ids),
        warnings=list(dict.fromkeys(warnings)),  # keep order, dedupe
        centered=bool(do_center),
        center_mode=str(center_mode or "bbox"),
        center_axes=str(center_axes or "xyz"),
        center_policy=str(policy),
        center_point=center_point,
        shift_applied=shift_applied,
    )


def merge_template_decorations(
    *,
    source_templates: Iterable[TemplateConfig],
    target_template: TemplateConfig,
    include_target_existing: bool = True,
    center: bool = False,
    center_mode: str = "bbox",
    center_axes: str = "xyz",
) -> MergeTemplateDecorationsOutcome:
    """Merge decorations from source templates into target template (pure metadata merge).

    Unlike instances, templates don't have a world transform; this function only merges and
    optionally centers decoration local positions.
    """
    warnings: list[str] = []
    source_ids: list[str] = []
    source_with_decorations: list[str] = []
    skipped_ids: list[str] = []

    merged: list[dict[str, object]] = []
    if include_target_existing:
        merged.extend(_extract_template_decorations(target_template))

    for tmpl in list(source_templates):
        if not isinstance(tmpl, TemplateConfig):
            continue
        tid = _safe_str(getattr(tmpl, "template_id", ""))
        if tid:
            source_ids.append(tid)

        decos = _extract_template_decorations(tmpl)
        if not decos:
            if tid:
                skipped_ids.append(tid)
            continue
        if tid:
            source_with_decorations.append(tid)
        for deco in decos:
            merged.append(dict(deco))

    if not merged:
        raise ValueError("未找到可合并的装饰物：所选元件均不包含 common_inspector.model.decorations。")

    used: set[str] = set()
    for deco in merged:
        raw_id = _safe_str(deco.get("instanceId") or "")
        if not raw_id or raw_id in used:
            new_id = _generate_prefixed_id("deco")
            while new_id in used:
                new_id = _generate_prefixed_id("deco")
            deco["instanceId"] = new_id
            raw_id = new_id
        used.add(raw_id)

    center_point: tuple[float, float, float] | None = None
    shift_applied: tuple[float, float, float] | None = None

    do_center = bool(center)
    if do_center:
        positions = [_get_decoration_pos(d) for d in merged]
        center_point = _compute_center(positions, mode=str(center_mode or "bbox"))
        shift = _apply_axes(center_point, str(center_axes or "xyz"))
        shift_applied = shift
        if any(abs(v) > 1e-12 for v in shift):
            for deco in merged:
                x, y, z = _get_decoration_pos(deco)
                _set_decoration_pos(deco, pos=(x - shift[0], y - shift[1], z - shift[2]))

    new_target = copy.deepcopy(target_template)
    new_meta: dict[str, object] = {}
    if isinstance(getattr(new_target, "metadata", None), Mapping):
        new_meta = copy.deepcopy(getattr(new_target, "metadata"))
    new_target.metadata = new_meta
    inspector2 = _ensure_dict_field(new_meta, COMMON_INSPECTOR_KEY)
    model2 = _ensure_dict_field(inspector2, _MODEL_KEY)
    model2[_DECORATIONS_KEY] = [dict(d) for d in merged]

    return MergeTemplateDecorationsOutcome(
        target_template=new_target,
        merged_decorations=[dict(d) for d in merged],
        source_template_ids=list(source_ids),
        source_templates_with_decorations=list(source_with_decorations),
        skipped_template_ids=list(skipped_ids),
        warnings=list(dict.fromkeys(warnings)),
        centered=bool(do_center),
        center_mode=str(center_mode or "bbox"),
        center_axes=str(center_axes or "xyz"),
        center_point=center_point,
        shift_applied=shift_applied,
    )

