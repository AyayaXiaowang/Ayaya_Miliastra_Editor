"""轻量 TRS(平移/旋转/缩放) 矩阵数学（纯 Python，无 PyQt 依赖）。

用途
- 为“装饰物 keep_world 合并/重父级(re-parent)”等逻辑提供稳定的几何计算：
  - world = parent ∘ local
  - keep_world reparent: local' = inv(parent_new) ∘ parent_old ∘ local

约定
- rot_deg 为 Unity 常见的欧拉角顺序（经验）：ZXY（实现为 R = Ry(y) * Rx(x) * Rz(z)）。
- 本模块只追求“自洽 + 行为稳定”，而不是作为通用 3D 引擎数学库。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

Vec3 = Tuple[float, float, float]
Mat3 = Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]
Mat4 = Tuple[
    Tuple[float, float, float, float],
    Tuple[float, float, float, float],
    Tuple[float, float, float, float],
    Tuple[float, float, float, float],
]


@dataclass(frozen=True, slots=True)
class TRS:
    pos: Vec3
    rot_deg: Vec3
    scale: Vec3


def _clamp(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return float(lo)
    if value > hi:
        return float(hi)
    return float(value)


def _deg_to_rad(deg: float) -> float:
    return float(deg) * math.pi / 180.0


def _rad_to_deg(rad: float) -> float:
    return float(rad) * 180.0 / math.pi


def _normalize_deg(deg: float) -> float:
    # Normalize to [-180, 180)
    v = (float(deg) + 180.0) % 360.0 - 180.0
    if abs(v) < 1e-12:
        return 0.0
    return float(v)


def mat3_transpose(m: Mat3) -> Mat3:
    return (
        (float(m[0][0]), float(m[1][0]), float(m[2][0])),
        (float(m[0][1]), float(m[1][1]), float(m[2][1])),
        (float(m[0][2]), float(m[1][2]), float(m[2][2])),
    )


def mat3_from_euler_deg_unity_zxy(rot_deg: Vec3) -> Mat3:
    """
    Euler(deg) → rotation matrix（经验：z, x, y 顺序）：
    R = Ry(y) * Rx(x) * Rz(z)

    说明：该实现需与 `euler_deg_unity_zxy_from_mat3` 自洽，用于 keep_world/reparent 的几何保持。
    """
    x_rad = _deg_to_rad(float(rot_deg[0]))
    y_rad = _deg_to_rad(float(rot_deg[1]))
    z_rad = _deg_to_rad(float(rot_deg[2]))

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


def euler_deg_unity_zxy_from_mat3(r: Mat3) -> Vec3:
    """rotation matrix → Euler(deg)，匹配 `mat3_from_euler_deg_unity_zxy` 的约定。"""
    sin_x = _clamp(-float(r[1][2]), -1.0, 1.0)
    x = math.asin(sin_x)
    cx = math.cos(x)

    if abs(cx) > 1e-8:
        z = math.atan2(float(r[1][0]), float(r[1][1]))
        y = math.atan2(float(r[0][2]), float(r[2][2]))
    else:
        z = 0.0
        if x > 0.0:
            y = math.atan2(float(r[0][1]), float(r[0][0]))
        else:
            y = math.atan2(-float(r[0][1]), float(r[0][0]))

    return (_normalize_deg(_rad_to_deg(x)), _normalize_deg(_rad_to_deg(y)), _normalize_deg(_rad_to_deg(z)))


def mat4_from_trs(*, pos: Vec3, rot_deg: Vec3, scale: Vec3) -> Mat4:
    r = mat3_from_euler_deg_unity_zxy(tuple(rot_deg))
    sx, sy, sz = float(scale[0]), float(scale[1]), float(scale[2])
    # A = R * diag(scale)  (column-wise scale)
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
    out = [[0.0, 0.0, 0.0, 0.0] for _ in range(4)]
    for i in range(4):
        for j in range(4):
            out[i][j] = float(a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j] + a[i][3] * b[3][j])
    return (tuple(out[0]), tuple(out[1]), tuple(out[2]), tuple(out[3]))  # type: ignore[return-value]


def mat4_inv_trs(*, pos: Vec3, rot_deg: Vec3, scale: Vec3) -> Mat4:
    sx, sy, sz = float(scale[0]), float(scale[1]), float(scale[2])
    if abs(sx) < 1e-12 or abs(sy) < 1e-12 or abs(sz) < 1e-12:
        raise ValueError(f"invalid scale for TRS inverse: scale={scale!r}")
    inv_sx, inv_sy, inv_sz = 1.0 / sx, 1.0 / sy, 1.0 / sz

    r = mat3_from_euler_deg_unity_zxy(tuple(rot_deg))
    rt = mat3_transpose(r)
    # invA = S^-1 * R^T  (left-multiply diag => scale rows)
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


def decompose_mat4_to_trs(m: Mat4) -> TRS:
    px, py, pz = float(m[0][3]), float(m[1][3]), float(m[2][3])

    # columns of upper 3x3
    c0 = (float(m[0][0]), float(m[1][0]), float(m[2][0]))
    c1 = (float(m[0][1]), float(m[1][1]), float(m[2][1]))
    c2 = (float(m[0][2]), float(m[1][2]), float(m[2][2]))

    def length(v: Vec3) -> float:
        return float(math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]))

    sx, sy, sz = length(c0), length(c1), length(c2)
    if sx < 1e-12 or sy < 1e-12 or sz < 1e-12:
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
    return TRS(
        pos=(float(px), float(py), float(pz)),
        rot_deg=tuple(rot_deg),
        scale=(float(sx), float(sy), float(sz)),
    )


__all__ = [
    "Vec3",
    "Mat4",
    "TRS",
    "mat4_from_trs",
    "mat4_mul",
    "mat4_inv_trs",
    "decompose_mat4_to_trs",
]

