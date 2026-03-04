from __future__ import annotations

import json
import math
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ugc_file_tools.beyond_local_export import get_beyond_local_export_dir
from ugc_file_tools.gia.entity_decorations_writer import build_entity_gia_with_decorations_wire
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir

from .settings import ShapeEditorSettings, _normalize_hex_color, get_shape_editor_settings_file_path


JsonDict = Dict[str, Any]

_EPS = 1e-9


def _clamp(v: float, lo: float, hi: float) -> float:
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _deg_to_rad(deg: float) -> float:
    return float(deg) * math.pi / 180.0


def _rad_to_deg(rad: float) -> float:
    return float(rad) * 180.0 / math.pi


def _quat_mul(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    """
    Hamilton product. Quaternion is (w, x, y, z).
    """
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    )


def _quat_from_axis_angle(axis: str, deg: float) -> Tuple[float, float, float, float]:
    """
    Build quaternion from axis-angle in degrees.
    axis: "x"|"y"|"z"
    """
    half = _deg_to_rad(deg) * 0.5
    s = math.sin(half)
    c = math.cos(half)
    if axis == "x":
        return (c, s, 0.0, 0.0)
    if axis == "y":
        return (c, 0.0, s, 0.0)
    if axis == "z":
        return (c, 0.0, 0.0, s)
    raise ValueError(f"axis 必须是 x/y/z，got: {axis!r}")


def _quat_to_matrix3(q: Tuple[float, float, float, float]) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
    w, x, y, z = q
    xx = x * x
    yy = y * y
    zz = z * z
    xy = x * y
    xz = x * z
    yz = y * z
    wx = w * x
    wy = w * y
    wz = w * z

    m00 = 1.0 - 2.0 * (yy + zz)
    m01 = 2.0 * (xy - wz)
    m02 = 2.0 * (xz + wy)

    m10 = 2.0 * (xy + wz)
    m11 = 1.0 - 2.0 * (xx + zz)
    m12 = 2.0 * (yz - wx)

    m20 = 2.0 * (xz - wy)
    m21 = 2.0 * (yz + wx)
    m22 = 1.0 - 2.0 * (xx + yy)
    return ((m00, m01, m02), (m10, m11, m12), (m20, m21, m22))


def _euler_zxy_deg_to_quat(x_deg: float, y_deg: float, z_deg: float) -> Tuple[float, float, float, float]:
    """
    Z-X-Y order (documented as: rotate z, then x, then y).

    对应到 quaternion 组合：q = qy * qx * qz（右侧先作用）。
    """
    qz = _quat_from_axis_angle("z", float(z_deg))
    qx = _quat_from_axis_angle("x", float(x_deg))
    qy = _quat_from_axis_angle("y", float(y_deg))
    return _quat_mul(_quat_mul(qy, qx), qz)


def _matrix3_to_euler_zxy_deg(
    m: Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]
) -> Tuple[float, float, float]:
    """
    Decompose rotation matrix into Euler angles (x,y,z) with order R = Ry * Rx * Rz。
    这与 `_euler_zxy_deg_to_quat`（z -> x -> y）口径一致。
    """
    (m00, _m01, m02), (m10, m11, m12), (m20, _m21, m22) = m

    # m12 = -sin(x)
    sx = _clamp(-float(m12), -1.0, 1.0)
    x = math.asin(sx)
    cx = math.cos(x)

    if abs(cx) > _EPS:
        z = math.atan2(float(m10), float(m11))
        y = math.atan2(float(m02), float(m22))
    else:
        # gimbal lock (x ~ +/-90). Choose z=0 and solve y from remaining terms.
        z = 0.0
        y = math.atan2(-float(m20), float(m00))

    return (_rad_to_deg(x), _rad_to_deg(y), _rad_to_deg(z))


def _compose_canvas_angle_on_world_z(
    *,
    base_rot_deg: Tuple[float, float, float],
    canvas_angle_deg: float,
    delta_sign: float,
    delta_offset_deg: float,
) -> Tuple[float, float, float]:
    """
    将网页画布的 angle 视为“世界 Z 轴”的增量旋转，与模板基准旋转合成，输出新的 Euler(x,y,z)。

    - delta_sign 默认 -1：将“画布顺时针为正”的角度映射为右手系旋转（常见直觉）。
    - 该合成会自然产生“多数模板主要表现为 Z 在变，但某些模板会主要体现在 X/Y”的效果，
      这正是模板自带 base_rot_deg 造成的轴混合。
    """
    bx, by, bz = base_rot_deg
    base_q = _euler_zxy_deg_to_quat(float(bx), float(by), float(bz))

    delta_deg = float(delta_offset_deg) + float(delta_sign) * float(canvas_angle_deg)
    delta_q = _quat_from_axis_angle("z", float(delta_deg))

    # world-axis delta: pre-multiply
    final_q = _quat_mul(delta_q, base_q)
    m = _quat_to_matrix3(final_q)
    return _matrix3_to_euler_zxy_deg(m)


def _as_int(value: object, *, field_name: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, float) and not isinstance(value, bool):
        return int(value)
    raise ValueError(f"{field_name} 必须是 int，got: {value!r}")


def _as_float(value: object, *, field_name: str) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    raise ValueError(f"{field_name} 必须是 float/int，got: {value!r}")


def _get_profile(settings_obj: ShapeEditorSettings, *, color: str) -> JsonDict:
    color_key = _normalize_hex_color(color)
    if not color_key:
        raise ValueError("shape.color 不能为空")
    prof = settings_obj.baseline_profiles_by_color.get(color_key)
    if not isinstance(prof, dict):
        raise ValueError(f"未找到颜色基准配置：color={color_key!r}")
    return prof


def _build_decorations_report(
    *,
    canvas_width: float,
    canvas_height: float,
    objects: List[JsonDict],
    settings_obj: ShapeEditorSettings,
) -> JsonDict:
    if canvas_width <= 0 or canvas_height <= 0:
        raise ValueError(f"canvas 尺寸非法：{canvas_width}x{canvas_height}")

    units_per_px = float(settings_obj.units_per_100px) / 100.0
    if units_per_px <= 0:
        raise ValueError(f"units_per_100px 必须 > 0，got: {settings_obj.units_per_100px!r}")

    # 基线高度（base_y）归一化：
    # 用户口径：画布内相对布局应只由“锚点坐标（center/bottom_center）”决定，
    # 不应因为不同模板在样本 `.gia` 里保存的 `base_pos.y` 不同而额外拉开间距。
    #
    # 规则：若本次导出包含 bottom_center 模板，则以 bottom_center 的 base_y 作为全局基线；
    # 否则使用所有模板里最小的 base_y（避免把某些模板抬高到另一个“楼层”）。
    base_y_candidates_bottom: List[float] = []
    base_y_candidates_all: List[float] = []
    for raw in objects:
        if not isinstance(raw, dict):
            continue
        is_ref = raw.get("isReference")
        if isinstance(is_ref, bool) and is_ref:
            continue
        shape_type = str(raw.get("type") or "").strip().lower()
        if shape_type not in {"rect", "circle"}:
            continue
        color = _normalize_hex_color(str(raw.get("color") or ""))
        profile = _get_profile(settings_obj, color=color)
        base_pos_raw = profile.get("base_pos")
        base_pos_for_base_y: JsonDict = dict(base_pos_raw) if isinstance(base_pos_raw, dict) else {}
        by_raw = base_pos_for_base_y.get("y")
        base_y = float(by_raw) if isinstance(by_raw, (int, float)) and not isinstance(by_raw, bool) else 0.0
        base_y_candidates_all.append(float(base_y))
        pivot_text = str(profile.get("pivot") or "").strip().lower()
        if pivot_text == "bottom_center":
            base_y_candidates_bottom.append(float(base_y))

    if base_y_candidates_bottom:
        base_y_common = float(min(base_y_candidates_bottom))
    elif base_y_candidates_all:
        base_y_common = float(min(base_y_candidates_all))
    else:
        base_y_common = 0.0

    decorations: List[JsonDict] = []
    auto_index = 0
    for raw in objects:
        if not isinstance(raw, dict):
            continue

        is_ref = raw.get("isReference")
        if isinstance(is_ref, bool) and is_ref:
            continue

        shape_type = str(raw.get("type") or "").strip().lower()
        if shape_type not in {"rect", "circle"}:
            continue

        color = _normalize_hex_color(str(raw.get("color") or ""))
        profile = _get_profile(settings_obj, color=color)
        template_id = int(profile.get("template_id") or 0)
        if template_id <= 0:
            raise ValueError(f"未配置 template_id：color={color!r}（请在 shape_editor_settings.json baseline_profiles_by_color 补全）")

        base_pos_raw = profile.get("base_pos")
        base_pos: JsonDict = dict(base_pos_raw) if isinstance(base_pos_raw, dict) else {}
        base_scale_raw = profile.get("base_scale")
        base_scale: JsonDict = dict(base_scale_raw) if isinstance(base_scale_raw, dict) else {}

        # 注意：base_y 使用“本批导出统一基线”，避免不同模板的样本 base_pos.y 破坏相对布局。
        base_y = float(base_y_common)

        bsx_raw = base_scale.get("x")
        bsy_raw = base_scale.get("y")
        bsz_raw = base_scale.get("z")
        base_sx = float(bsx_raw) if isinstance(bsx_raw, (int, float)) and not isinstance(bsx_raw, bool) else 1.0
        base_sy = float(bsy_raw) if isinstance(bsy_raw, (int, float)) and not isinstance(bsy_raw, bool) else 1.0
        base_sz = float(bsz_raw) if isinstance(bsz_raw, (int, float)) and not isinstance(bsz_raw, bool) else 1.0

        base_yaw_raw = profile.get("base_yaw_deg")
        base_yaw = float(base_yaw_raw) if isinstance(base_yaw_raw, (int, float)) and not isinstance(base_yaw_raw, bool) else 0.0

        base_rot_raw = profile.get("base_rot_deg")
        base_rot: JsonDict = dict(base_rot_raw) if isinstance(base_rot_raw, dict) else {}
        brx_raw = base_rot.get("x")
        bry_raw = base_rot.get("y")
        brz_raw = base_rot.get("z")
        base_rx = float(brx_raw) if isinstance(brx_raw, (int, float)) and not isinstance(brx_raw, bool) else 0.0
        base_ry = float(bry_raw) if isinstance(bry_raw, (int, float)) and not isinstance(bry_raw, bool) else float(base_yaw)
        base_rz = float(brz_raw) if isinstance(brz_raw, (int, float)) and not isinstance(brz_raw, bool) else 0.0

        width = _as_float(raw.get("width"), field_name="shape.width")
        height = _as_float(raw.get("height"), field_name="shape.height")
        angle = _as_float(raw.get("angle", 0.0), field_name="shape.angle")

        # 坐标锚点口径：
        # - canvas 上“相邻/贴边”的直觉通常基于图形的可见外接矩形，而不是某些模板的 mesh pivot。
        # - 若不同形状使用不同 pivot（例如有的使用 bottom_center，有的使用 center），
        #   即便画布里看起来贴边，导出后也可能在世界坐标里产生“被拉开”的视觉效果。
        # 因此提供设置 `position_anchor_mode`：
        # - center：总是用中心点
        # - game_pivot：以中心点为输入，按模板真实 pivot（profile.pivot）转换为 pivot 点再导出
        # - payload_anchor：优先用 payload.anchor（由前端写入），缺失时回退 center

        def _compute_center_anchor_px() -> Tuple[float, float]:
            centered = raw.get("centered")
            if isinstance(centered, dict) and isinstance(centered.get("x"), (int, float)) and isinstance(centered.get("y"), (int, float)):
                # centered coords: origin at canvas center, Y up
                cx = float(canvas_width) / 2.0 + float(centered["x"])
                cy = float(canvas_height) / 2.0 - float(centered["y"])
                return (cx, cy)
            left = _as_float(raw.get("left"), field_name="shape.left")
            top = _as_float(raw.get("top"), field_name="shape.top")
            return (left + width / 2.0, top + height / 2.0)

        def _compute_payload_anchor_or_fallback_px() -> Tuple[float, float]:
            anchor_centered = raw.get("anchor_centered")
            if (
                isinstance(anchor_centered, dict)
                and isinstance(anchor_centered.get("x"), (int, float))
                and isinstance(anchor_centered.get("y"), (int, float))
            ):
                ax = float(canvas_width) / 2.0 + float(anchor_centered["x"])
                ay = float(canvas_height) / 2.0 - float(anchor_centered["y"])
                return (ax, ay)
            anchor = raw.get("anchor")
            if isinstance(anchor, dict) and isinstance(anchor.get("x"), (int, float)) and isinstance(anchor.get("y"), (int, float)):
                return (float(anchor["x"]), float(anchor["y"]))
            return _compute_center_anchor_px()

        # 坐标系约定（按用户最新口径）：
        # - X：左右（向右为正）
        # - Y：上下（向上为正；网页 Y 向下，所以取负）
        # - Z：层级/深度（一般不动；需要时每层 0.001 量级）
        bz_raw = base_pos.get("z")
        base_z = float(bz_raw) if isinstance(bz_raw, (int, float)) and not isinstance(bz_raw, bool) else 0.0

        # 相对缩放（基于网页默认尺寸 100px）
        sx_mul = float(width) / 100.0
        sy_mul = float(height) / 100.0

        # 轴映射：
        # - “薄片立起来”的模板：base_scale.z 很薄 且 base_scale.y 显著 > 1 => 2D 高度映射到 scale.y
        # - 其余：2D 高度映射到 scale.z（flat in XZ）
        # 注意：此处不仅影响 scale 轴映射，也影响 bottom_center pivot 的“中心→底边”偏移方向。
        # 部分模板虽然 base_scale.y 不大，但在真源里仍应视为“高度沿 local-Y 的 upright 薄片”，
        # 需要在 profile 中显式标注 height_axis 来覆盖启发式推导。
        height_axis = str(profile.get("height_axis") or "").strip().lower()
        if height_axis == "y":
            is_upright_y = True
        elif height_axis == "z":
            is_upright_y = False
        else:
            thin_th = float(settings_obj.thin_axis_threshold)
            upright_th = float(settings_obj.upright_y_axis_threshold)
            is_upright_y = (abs(base_sz) <= thin_th) and (abs(base_sy) > upright_th)

        # 平面内 X/Z 轴交换（关键修复）：
        # 部分模板的 `base_rot_deg` 会使“画布宽度方向（world X）”对应到 local-Z，
        # “画布高度方向（world Y）”对应到 local-X。
        # 若仍按默认假设（width->local-X, height->local-Z）计算 scale，就会出现“横竖互换”
        # —— 在像素画导入的黑白横条上最明显（导出后变成竖条）。
        #
        # 该问题只影响非 upright_y（height->local-Z）分支；upright_y 通常已是 local-X/local-Y 对齐。
        # 支持 profile 显式指定 `axis_mode`：
        # - auto（默认）：基于 base_rot 自动检测是否需要 swap_xz
        # - normal/xz：不交换
        # - swap_xz/zx：交换（将 sx_mul 与 sy_mul 互换）
        axis_mode = str(profile.get("axis_mode") or "").strip().lower()
        swap_xz = False
        if not is_upright_y:
            if axis_mode:
                if axis_mode in {"auto"}:
                    pass
                elif axis_mode in {"swap_xz", "swap", "zx", "z_x"}:
                    swap_xz = True
                elif axis_mode in {"normal", "xz", "x_z"}:
                    swap_xz = False
                else:
                    raise ValueError(
                        "axis_mode 仅支持 auto/normal/swap_xz（别名：xz/zx/swap），"
                        f"got: {axis_mode!r}"
                    )
            if (not axis_mode) or axis_mode == "auto":
                base_q0 = _euler_zxy_deg_to_quat(float(base_rx), float(base_ry), float(base_rz))
                m0 = _quat_to_matrix3(base_q0)
                (m00, _m01, m02), (m10, _m11, m12), (_m20, _m21, _m22) = m0
                # local-X 更接近 world Y 且 local-Z 更接近 world X => swap_xz
                if abs(float(m00)) < abs(float(m10)) and abs(float(m02)) > abs(float(m12)):
                    swap_xz = True
            if swap_xz:
                sx_mul, sy_mul = sy_mul, sx_mul

        if is_upright_y:
            scale_x = float(base_sx) * float(sx_mul)
            scale_y = float(base_sy) * float(sy_mul)
            scale_z = float(base_sz)
        else:
            scale_x = float(base_sx) * float(sx_mul)
            scale_y = float(base_sy)
            scale_z = float(base_sz) * float(sy_mul)

        # 位置锚点计算（在 scale 之后做）：game_pivot 的偏移量必须基于“模板真实世界尺寸”，不能用 px 直接换算。
        #
        # 兼容策略（重要）：
        # - 旧前端：anchor_centered == centered（只提供中心点语义），需要 game_pivot 做中心→pivot 推导。
        # - 新前端：会按模板 pivot 写入 pivot-aware 的 anchor_centered（例如 bottom_center 用“底边中心点”），
        #   这时应优先直接使用 payload_anchor；否则会出现“中心点对齐，但导出的 pos.y 因 scale 不同而被拉开”的错觉。
        anchor_mode = str(getattr(settings_obj, "position_anchor_mode", "game_pivot") or "").strip().lower()
        if anchor_mode == "game_pivot":
            pivot_hint = str(raw.get("pivot") or "").strip().lower()
            centered_hint = raw.get("centered")
            anchor_centered_hint = raw.get("anchor_centered")
            if (
                pivot_hint in {"bottom_center", "center"}
                and isinstance(centered_hint, dict)
                and isinstance(anchor_centered_hint, dict)
                and isinstance(centered_hint.get("x"), (int, float))
                and isinstance(centered_hint.get("y"), (int, float))
                and isinstance(anchor_centered_hint.get("x"), (int, float))
                and isinstance(anchor_centered_hint.get("y"), (int, float))
            ):
                if float(anchor_centered_hint["x"]) != float(centered_hint["x"]) or float(anchor_centered_hint["y"]) != float(centered_hint["y"]):
                    anchor_mode = "payload_anchor"
        cx_px, cy_px = _compute_center_anchor_px()
        if anchor_mode == "payload_anchor":
            ax_px, ay_px = _compute_payload_anchor_or_fallback_px()
        elif anchor_mode == "center":
            ax_px, ay_px = (cx_px, cy_px)
        else:
            # game_pivot：以中心点为输入，根据模板 pivot 把 pivot 点求出来（世界单位）
            pivot_text = str(profile.get("pivot") or "").strip().lower()
            if pivot_text not in {"center", "bottom_center"}:
                pivot_text = "center"
            ax_px, ay_px = (cx_px, cy_px)

        # 先算“中心点”的世界坐标（所有模式都需要）
        center_world_x = (cx_px - canvas_width / 2.0) * units_per_px
        center_world_y = float(base_y) + (-(cy_px - canvas_height / 2.0) * units_per_px)
        # layer offset: use export order as stable z-index (0.001 per item)
        center_world_z = float(base_z) + float(auto_index) * 0.001

        # 再决定最终 pivot/world pos
        pos_x = center_world_x
        pos_y = center_world_y
        pos_z = center_world_z
        if anchor_mode == "payload_anchor":
            pos_x = (ax_px - canvas_width / 2.0) * units_per_px
            pos_y = float(base_y) + (-(ay_px - canvas_height / 2.0) * units_per_px)
            pos_z = center_world_z
        elif anchor_mode == "center":
            # 已是中心点
            pass
        else:
            # game_pivot：把“中心点布局”转换成“模板真实 pivot 位置”
            pivot_text = str(profile.get("pivot") or "").strip().lower()
            if pivot_text not in {"center", "bottom_center"}:
                pivot_text = "center"
            if pivot_text == "bottom_center":
                # pivot 偏移必须在“物体局部轴”上计算，再用最终旋转转到世界坐标：
                # - upright_y：2D 高度映射到 local-Y（scale_y）
                # - else：2D 高度映射到 local-Z（scale_z）
                if is_upright_y:
                    off_local = (0.0, -float(scale_y) * 0.5, 0.0)
                else:
                    off_local = (0.0, 0.0, -float(scale_z) * 0.5)

                prof_yaw_sign = profile.get("yaw_sign")
                yaw_sign = (
                    float(prof_yaw_sign)
                    if isinstance(prof_yaw_sign, (int, float)) and not isinstance(prof_yaw_sign, bool)
                    else float(settings_obj.yaw_sign)
                )
                prof_yaw_offset = profile.get("yaw_offset_deg", 0.0)
                yaw_offset_deg = (
                    float(prof_yaw_offset)
                    if isinstance(prof_yaw_offset, (int, float)) and not isinstance(prof_yaw_offset, bool)
                    else 0.0
                )
                delta_deg = float(yaw_offset_deg) + float(yaw_sign) * float(angle)
                base_q = _euler_zxy_deg_to_quat(float(base_rx), float(base_ry), float(base_rz))
                delta_q = _quat_from_axis_angle("z", float(delta_deg))
                final_q = _quat_mul(delta_q, base_q)
                m = _quat_to_matrix3(final_q)
                (m00, m01, m02), (m10, m11, m12), (m20, m21, m22) = m
                lx, ly, lz = off_local
                dx = m00 * lx + m01 * ly + m02 * lz
                dy = m10 * lx + m11 * ly + m12 * lz
                dz = m20 * lx + m21 * ly + m22 * lz

                pos_x = float(center_world_x) + float(dx)
                pos_y = float(center_world_y) + float(dy)
                pos_z = float(center_world_z) + float(dz)

        label = str(raw.get("label") or "").strip()
        if not label:
            auto_index += 1
            label = f"{shape_type}_{auto_index}"

        # 旋转换算（旋转合成）：
        # - base_rot_deg：真源模板在游戏里“已经旋过”的基准欧拉角（不应被用户角度覆盖）
        # - angle：网页里用户看到的增量角度（Fabric 角度，单位：deg）
        # - yaw_sign：增量角度的符号（默认 -1.0：顺时针为正 -> world-Z 负向旋转）
        # - yaw_offset_deg：增量角度的零点补偿（按颜色配置；与 angle 同口径）
        prof_yaw_sign = profile.get("yaw_sign")
        yaw_sign = (
            float(prof_yaw_sign)
            if isinstance(prof_yaw_sign, (int, float)) and not isinstance(prof_yaw_sign, bool)
            else float(settings_obj.yaw_sign)
        )
        prof_yaw_offset = profile.get("yaw_offset_deg", 0.0)
        yaw_offset_deg = (
            float(prof_yaw_offset)
            if isinstance(prof_yaw_offset, (int, float)) and not isinstance(prof_yaw_offset, bool)
            else 0.0
        )
        out_rx, out_ry, out_rz = _compose_canvas_angle_on_world_z(
            base_rot_deg=(float(base_rx), float(base_ry), float(base_rz)),
            canvas_angle_deg=float(angle),
            delta_sign=float(yaw_sign),
            delta_offset_deg=float(yaw_offset_deg),
        )

        decorations.append(
            {
                "name": label,
                "template_id": int(template_id),
                "pos": [float(pos_x), float(pos_y), float(pos_z)],
                "scale": [float(scale_x), float(scale_y), float(scale_z)],
                # 兼容口径：
                # - yaw_deg：仍写入 y 分量，便于老工具只看 yaw 的场景
                # - rot_deg：三轴欧拉角（deg），用于正确应用画布旋转并保留模板预旋转
                "yaw_deg": float(out_ry),
                "rot_deg": [float(out_rx), float(out_ry), float(out_rz)],
            }
        )

    return {
        "parent_struct": {"name": "shape_editor_canvas"},
        "decorations": decorations,
    }


def export_canvas_payload_to_gia(
    *,
    package_id: str,
    canvas_payload: JsonDict,
    settings_obj: ShapeEditorSettings,
    base_gia_path: Path | None = None,
    output_file_stem: str | None,
    entity_name: str | None = None,
) -> JsonDict:
    package_id_text = str(package_id or "").strip()
    if package_id_text == "" or package_id_text == "global_view":
        raise ValueError("必须在“具体项目存档”上下文导出（global_view 不支持）")

    canvas = canvas_payload.get("canvas")
    if not isinstance(canvas, dict):
        raise ValueError("payload.canvas 必须是 object")
    canvas_width = _as_float(canvas.get("width"), field_name="canvas.width")
    canvas_height = _as_float(canvas.get("height"), field_name="canvas.height")

    objects = canvas_payload.get("objects")
    if not isinstance(objects, list):
        raise ValueError("payload.objects 必须是 list")

    entity_base_text = str(base_gia_path or "").strip()
    if entity_base_text == "":
        entity_base_text = str(settings_obj.entity_base_gia_path or "").strip()
    if entity_base_text == "":
        raise ValueError(f"未配置 entity_base_gia_path/base_gia_path：请先编辑 {str(get_shape_editor_settings_file_path())!r}")
    entity_base = Path(entity_base_text).resolve()
    if not entity_base.is_file():
        raise FileNotFoundError(f"未找到 entity_base_gia：{str(entity_base)!r}")
    if entity_base.suffix.lower() != ".gia":
        raise ValueError("entity_base_gia 必须是 .gia 文件")

    accessory_template_path_text = str(settings_obj.accessory_template_gia_path or "").strip()
    accessory_template = Path(accessory_template_path_text).resolve() if accessory_template_path_text else None
    if accessory_template is not None:
        if not accessory_template.is_file():
            raise FileNotFoundError(f"未找到 accessory_template_gia：{str(accessory_template)!r}")
        if accessory_template.suffix.lower() != ".gia":
            raise ValueError("accessory_template_gia 必须是 .gia 文件")

    report = _build_decorations_report(
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        objects=[obj for obj in objects if isinstance(obj, dict)],
        settings_obj=settings_obj,
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = str(output_file_stem or "").strip()
    if stem == "":
        stem = f"{package_id_text}_shape_canvas_{timestamp}"
    entity_name_text = str(entity_name or "").strip() or f"{package_id_text}_shape_canvas"

    report_path = resolve_output_file_path_in_out_dir(Path(f"{stem}.decorations.report.json"))
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    output_gia_path = resolve_output_file_path_in_out_dir(Path(f"{stem}.gia"))
    result = build_entity_gia_with_decorations_wire(
        entity_base_gia=entity_base,
        accessory_template_gia=accessory_template,
        decorations_report_json=report_path,
        output_gia_path=output_gia_path,
        check_header=False,
        limit_count=0,
        entity_name=entity_name_text,
    )

    output_gia_file = Path(str(result.get("output_gia_file") or "")).resolve()
    if not output_gia_file.is_file():
        raise FileNotFoundError(f"生成失败：未找到输出文件：{str(output_gia_file)!r}")

    dst_dir = get_beyond_local_export_dir()
    dst_dir.mkdir(parents=True, exist_ok=True)
    copied_path = (dst_dir / output_gia_file.name).resolve()
    shutil.copy2(output_gia_file, copied_path)

    return {
        "ok": True,
        "export_kind": "entity",
        "package_id": package_id_text,
        "report_path": str(report_path),
        "output_gia_file": str(output_gia_file),
        "exported_to": str(copied_path),
        "decorations_count": int(len(report.get("decorations") or [])),
        "entity_base_gia": str(entity_base),
        "accessory_template_gia": str(accessory_template) if accessory_template is not None else "",
        "canvas_width": float(canvas_width),
        "canvas_height": float(canvas_height),
    }
