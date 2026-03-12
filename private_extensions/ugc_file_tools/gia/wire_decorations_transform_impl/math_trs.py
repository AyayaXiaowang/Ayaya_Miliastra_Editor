from __future__ import annotations

"""TRS and matrix math helpers used by keep_world centering policy."""

import math
from typing import List, Tuple

from ugc_file_tools.gia.wire_decorations_transform_impl.constants import (
    DEG_FULL_TURN,
    DEG_HALF_TURN,
    EPS_EULER_CX,
    EPS_TINY,
)

MAT3_DIM = 3
MAT4_DIM = 4

Mat3 = Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]
Mat4 = Tuple[
    Tuple[float, float, float, float],
    Tuple[float, float, float, float],
    Tuple[float, float, float, float],
    Tuple[float, float, float, float],
]


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value into the inclusive range [lo, hi]."""
    if value < lo:
        return float(lo)
    if value > hi:
        return float(hi)
    return float(value)


def deg_to_rad(deg: float) -> float:
    """Convert degrees into radians."""
    return float(deg) * math.pi / DEG_HALF_TURN


def rad_to_deg(rad: float) -> float:
    """Convert radians into degrees."""
    return float(rad) * DEG_HALF_TURN / math.pi


def normalize_deg(deg: float) -> float:
    """Normalize degrees into [-180, 180) with small values snapped to 0."""
    v = (float(deg) + DEG_HALF_TURN) % DEG_FULL_TURN - DEG_HALF_TURN
    if abs(v) < EPS_TINY:
        return 0.0
    return float(v)


def mat3_transpose(m: Mat3) -> Mat3:
    """Transpose a 3x3 matrix."""
    return (
        (float(m[0][0]), float(m[1][0]), float(m[2][0])),
        (float(m[0][1]), float(m[1][1]), float(m[2][1])),
        (float(m[0][2]), float(m[1][2]), float(m[2][2])),
    )


def mat3_mul_vec3(m: Mat3, v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Multiply a 3x3 matrix by a vec3."""
    x, y, z = float(v[0]), float(v[1]), float(v[2])
    return (
        float(m[0][0] * x + m[0][1] * y + m[0][2] * z),
        float(m[1][0] * x + m[1][1] * y + m[1][2] * z),
        float(m[2][0] * x + m[2][1] * y + m[2][2] * z),
    )


def mat3_from_euler_deg_unity_zxy(rot_deg: Tuple[float, float, float]) -> Mat3:
    """Convert Unity-style Euler(deg) into a rotation matrix using the z/x/y convention."""
    x_rad = deg_to_rad(float(rot_deg[0]))
    y_rad = deg_to_rad(float(rot_deg[1]))
    z_rad = deg_to_rad(float(rot_deg[2]))

    cx, sx = math.cos(x_rad), math.sin(x_rad)
    cy, sy = math.cos(y_rad), math.sin(y_rad)
    cz, sz = math.cos(z_rad), math.sin(z_rad)

    r00 = cy * cz + sy * sx * sz
    r01 = -cy * sz + sy * sx * cz
    r02 = sy * cx

    r10 = cx * sz
    r11 = cx * cz
    r12 = -sx

    r20 = -sy * cz + cy * sx * sz
    r21 = sy * sz + cy * sx * cz
    r22 = cy * cx

    return (
        (float(r00), float(r01), float(r02)),
        (float(r10), float(r11), float(r12)),
        (float(r20), float(r21), float(r22)),
    )


def euler_deg_unity_zxy_from_mat3(r: Mat3) -> Tuple[float, float, float]:
    """Convert a rotation matrix into Unity-style Euler(deg) matching mat3_from_euler_deg_unity_zxy."""
    sin_x = clamp(-float(r[1][2]), -1.0, 1.0)
    x = math.asin(sin_x)
    cx = math.cos(x)

    if abs(cx) > EPS_EULER_CX:
        z = math.atan2(float(r[1][0]), float(r[1][1]))
        y = math.atan2(float(r[0][2]), float(r[2][2]))
    else:
        z = 0.0
        if x > 0.0:
            y = math.atan2(float(r[0][1]), float(r[0][0]))
        else:
            y = math.atan2(-float(r[0][1]), float(r[0][0]))

    return (normalize_deg(rad_to_deg(x)), normalize_deg(rad_to_deg(y)), normalize_deg(rad_to_deg(z)))


def mat4_from_trs(*, pos: Tuple[float, float, float], rot_deg: Tuple[float, float, float], scale: Tuple[float, float, float]) -> Mat4:
    """Build a 4x4 matrix from TRS(position, rotation, scale)."""
    r = mat3_from_euler_deg_unity_zxy(tuple(rot_deg))
    sx, sy, sz = float(scale[0]), float(scale[1]), float(scale[2])
    a00, a01, a02 = float(r[0][0] * sx), float(r[0][1] * sy), float(r[0][2] * sz)
    a10, a11, a12 = float(r[1][0] * sx), float(r[1][1] * sy), float(r[1][2] * sz)
    a20, a21, a22 = float(r[2][0] * sx), float(r[2][1] * sy), float(r[2][2] * sz)
    px, py, pz = float(pos[0]), float(pos[1]), float(pos[2])
    return (
        (a00, a01, a02, px),
        (a10, a11, a12, py),
        (a20, a21, a22, pz),
        (0.0, 0.0, 0.0, 1.0),
    )


def mat4_mul(a: Mat4, b: Mat4) -> Mat4:
    """Multiply two 4x4 matrices."""
    out: List[List[float]] = [[0.0, 0.0, 0.0, 0.0] for _ in range(MAT4_DIM)]
    for i in range(MAT4_DIM):
        for j in range(MAT4_DIM):
            out[i][j] = float(a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j] + a[i][3] * b[3][j])
    return (tuple(out[0]), tuple(out[1]), tuple(out[2]), tuple(out[3]))  # type: ignore[return-value]


def mat4_inv_trs(*, pos: Tuple[float, float, float], rot_deg: Tuple[float, float, float], scale: Tuple[float, float, float]) -> Mat4:
    """Compute the inverse matrix for a TRS transform assuming non-singular scale."""
    sx, sy, sz = float(scale[0]), float(scale[1]), float(scale[2])
    if abs(sx) < EPS_TINY or abs(sy) < EPS_TINY or abs(sz) < EPS_TINY:
        raise ValueError(f"invalid scale for TRS inverse: scale={scale!r}")
    inv_sx, inv_sy, inv_sz = 1.0 / sx, 1.0 / sy, 1.0 / sz

    r = mat3_from_euler_deg_unity_zxy(tuple(rot_deg))
    rt = mat3_transpose(r)
    inv_a: Mat3 = (
        (float(rt[0][0] * inv_sx), float(rt[0][1] * inv_sx), float(rt[0][2] * inv_sx)),
        (float(rt[1][0] * inv_sy), float(rt[1][1] * inv_sy), float(rt[1][2] * inv_sy)),
        (float(rt[2][0] * inv_sz), float(rt[2][1] * inv_sz), float(rt[2][2] * inv_sz)),
    )

    px, py, pz = float(pos[0]), float(pos[1]), float(pos[2])
    inv_tx = -float(inv_a[0][0] * px + inv_a[0][1] * py + inv_a[0][2] * pz)
    inv_ty = -float(inv_a[1][0] * px + inv_a[1][1] * py + inv_a[1][2] * pz)
    inv_tz = -float(inv_a[2][0] * px + inv_a[2][1] * py + inv_a[2][2] * pz)

    return (
        (float(inv_a[0][0]), float(inv_a[0][1]), float(inv_a[0][2]), float(inv_tx)),
        (float(inv_a[1][0]), float(inv_a[1][1]), float(inv_a[1][2]), float(inv_ty)),
        (float(inv_a[2][0]), float(inv_a[2][1]), float(inv_a[2][2]), float(inv_tz)),
        (0.0, 0.0, 0.0, 1.0),
    )


def _vec3_length(v: Tuple[float, float, float]) -> float:
    """Compute the Euclidean length of a vec3."""
    return float(math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]))


def decompose_mat4_to_trs(m: Mat4) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
    """Decompose a 4x4 matrix into TRS(position, rotation, scale) using the internal Euler convention."""
    px, py, pz = float(m[0][3]), float(m[1][3]), float(m[2][3])

    c0 = (float(m[0][0]), float(m[1][0]), float(m[2][0]))
    c1 = (float(m[0][1]), float(m[1][1]), float(m[2][1]))
    c2 = (float(m[0][2]), float(m[1][2]), float(m[2][2]))

    sx, sy, sz = _vec3_length(c0), _vec3_length(c1), _vec3_length(c2)
    if sx < EPS_TINY or sy < EPS_TINY or sz < EPS_TINY:
        raise ValueError(f"cannot decompose TRS: singular scale from matrix (sx,sy,sz)=({sx},{sy},{sz})")

    r: Mat3 = (
        (float(m[0][0] / sx), float(m[0][1] / sy), float(m[0][2] / sz)),
        (float(m[1][0] / sx), float(m[1][1] / sy), float(m[1][2] / sz)),
        (float(m[2][0] / sx), float(m[2][1] / sy), float(m[2][2] / sz)),
    )

    det = (
        r[0][0] * (r[1][1] * r[2][2] - r[1][2] * r[2][1])
        - r[0][1] * (r[1][0] * r[2][2] - r[1][2] * r[2][0])
        + r[0][2] * (r[1][0] * r[2][1] - r[1][1] * r[2][0])
    )
    if float(det) < 0.0:
        sx = -float(sx)
        r = (
            (-float(r[0][0]), float(r[0][1]), float(r[0][2])),
            (-float(r[1][0]), float(r[1][1]), float(r[1][2])),
            (-float(r[2][0]), float(r[2][1]), float(r[2][2])),
        )

    rot_deg = euler_deg_unity_zxy_from_mat3(r)
    return (float(px), float(py), float(pz)), tuple(rot_deg), (float(sx), float(sy), float(sz))

