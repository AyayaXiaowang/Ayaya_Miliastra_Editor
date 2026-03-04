from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from engine.configs.settings import settings


def _workspace_root_from_this_file() -> Path:
    # settings.py -> shape_editor_backend -> shape-editor -> private_extensions -> workspace_root
    return Path(__file__).resolve().parents[3]


def _try_guess_entity_base_gia_path() -> str:
    """
    兜底：当用户未配置 entity_base_gia_path 时，尝试从本地“接力目录”的样本推导一个可用的 base .gia。

    约定：
    - `ugc_file_tools/out/gia_entities_画布功能组.json` 中会记录 `source_gia_file`（真源样本路径）。
    - 若其父目录存在 `空模型加一个装饰物.gia`，优先使用它作为 entity_base_gia（最适配装饰物写入）。
    - 否则回退 `空模型.gia`。
    """
    workspace_root = _workspace_root_from_this_file()
    report_path = (
        workspace_root
        / "private_extensions"
        / "ugc_file_tools"
        / "out"
        / "gia_entities_画布功能组.json"
    ).resolve()
    if not report_path.is_file():
        return ""

    obj = json.loads(report_path.read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict):
        return ""
    source_gia = str(obj.get("source_gia_file") or "").strip()
    if source_gia == "":
        return ""

    base_dir = Path(source_gia).resolve().parent
    for name in ["空模型加一个装饰物.gia", "空模型.gia"]:
        candidate = (base_dir / name).resolve()
        if candidate.is_file() and candidate.suffix.lower() == ".gia":
            return str(candidate)
    return ""


def _try_guess_template_base_gia_path() -> str:
    """
    兜底：当用户未配置 template_base_gia_path 时，尝试从本地样本推导一个可用的“元件（模板）base .gia”。

    约定与策略：
    - 优先使用 `ugc_file_tools/out/gia_entities_画布功能组.json` 的 `source_gia_file` 所在目录；
    - 在该目录内查找常见命名的元件样本（例如 `装饰物元件.gia`）；
    - 若找不到，则尝试从 `_try_guess_entity_base_gia_path()` 的同目录继续查找。
    """
    workspace_root = _workspace_root_from_this_file()
    report_path = (
        workspace_root
        / "private_extensions"
        / "ugc_file_tools"
        / "out"
        / "gia_entities_画布功能组.json"
    ).resolve()

    candidates: list[Path] = []
    if report_path.is_file():
        obj = json.loads(report_path.read_text(encoding="utf-8-sig"))
        if isinstance(obj, dict):
            source_gia = str(obj.get("source_gia_file") or "").strip()
            if source_gia:
                candidates.append(Path(source_gia).resolve().parent)

    ent_base = str(_try_guess_entity_base_gia_path() or "").strip()
    if ent_base:
        candidates.append(Path(ent_base).resolve().parent)

    # 常见命名：按优先级排序
    names = [
        "装饰物元件.gia",
        "导出元件.gia",
        "导出为元件.gia",
        "元件.gia",
        "模板.gia",
    ]

    for base_dir in candidates:
        if not base_dir.is_dir():
            continue
        for name in names:
            p = (base_dir / name).resolve()
            if p.is_file() and p.suffix.lower() == ".gia":
                return str(p)
    return ""


JsonDict = Dict[str, Any]


def _normalize_hex_color(value: str) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    if not text.startswith("#"):
        return text
    if len(text) == 4:
        # #RGB -> #RRGGBB
        r, g, b = text[1], text[2], text[3]
        return f"#{r}{r}{g}{g}{b}{b}"
    return text


def _default_template_id_map() -> dict[str, dict[str, int]]:
    # 与 `private_extensions/shape-editor/app.js` 的调色板保持一致（值留空=0，需用户配置真实模板 ID）。
    rect_colors = [
        "#E0D6C8",
        "#FBAF5C",
        "#BAB296",
        "#C47F5C",
        "#AF5254",
        "#9D482F",
        "#3E7B5C",
        "#464749",
        "#765F51",
    ]
    circle_colors = [
        "#F3D199",
        "#DBA4A2",
        "#EBD8A5",
        "#EEECE7",
    ]
    rect = {c: 0 for c in rect_colors}
    circle = {c: 0 for c in circle_colors}
    return {"rect": rect, "circle": circle}


def _default_baseline_profiles_from_doc() -> dict[str, JsonDict]:
    """
    基于用户提供的 `ugc_file_tools/out/gia_entities_画布功能组.json` 口径沉淀的基准表。

    说明：
    - 该表用于“回写 GIA”时做相对换算（在模板基准 scale/yaw 的基础上叠加用户缩放/旋转）；
    - x/z 的基准值不作为布局真源：布局由网页画布决定；这里主要依赖 base_y 与 base_scale。
    """
    # 规则：由 shape_editor_backend.export_gia 推导 axis_mode
    return {
        # rectangles
        "#464749": {
            "shape_kind": "rect",
            "template_id": 20002129,
            "base_pos": {"y": 1.5039632320404053},
            "base_scale": {"x": 6.0, "y": 0.009999999776482582, "z": 6.0},
            "base_yaw_deg": 90.0,
            "base_rot_deg": {"x": 0.0, "y": 90.0, "z": 90.0},
            "pivot": "center",
            # 该模板的 base_rot 会导致画布平面内 X/Z 轴互换（width->local-Z, height->local-X）
            "axis_mode": "swap_xz",
        },
        "#E0D6C8": {
            "shape_kind": "rect",
            "template_id": 20002159,
            "base_pos": {"y": 1.5039632320404053},
            "base_scale": {"x": 2.5, "y": 0.009999999776482582, "z": 2.5},
            "base_yaw_deg": 90.0,
            "base_rot_deg": {"x": 0.0, "y": 90.0, "z": -90.0},
            "pivot": "center",
            # 该模板同样需要 swap_xz（否则宽高会互换，表现为横条变竖条）
            "axis_mode": "swap_xz",
        },
        "#765F51": {
            "shape_kind": "rect",
            "template_id": 20002164,
            "base_pos": {"y": 1.5039632320404053},
            "base_scale": {"x": 0.6000000238418579, "y": 0.009999999776482582, "z": 0.6000000238418579},
            "base_yaw_deg": 0.0,
            "base_rot_deg": {"x": 90.0, "y": 0.0, "z": 0.0},
            "pivot": "center",
        },
        "#9D482F": {
            "shape_kind": "rect",
            "template_id": 20001870,
            "base_pos": {"y": 1.5039632320404053},
            "base_scale": {"x": 1.0, "y": 0.009999999776482582, "z": 1.0},
            "base_yaw_deg": 0.0,
            "base_rot_deg": {"x": 90.0, "y": 0.0, "z": 0.0},
            "pivot": "center",
        },
        "#AF5254": {
            "shape_kind": "rect",
            "template_id": 20002609,
            "base_pos": {"y": -0.004291653633117676},
            "base_scale": {"x": 0.5799999833106995, "y": 0.75, "z": 0.009999999776482582},
            "base_yaw_deg": 0.0,
            # 用户确认：20002609 为底部中心 pivot
            "pivot": "bottom_center",
        },
        "#3E7B5C": {
            "shape_kind": "rect",
            "template_id": 20002605,
            "base_pos": {"y": -0.004291653633117676},
            "base_scale": {"x": 0.6000000238418579, "y": 15.0, "z": 0.009999999776482582},
            "base_yaw_deg": 0.0,
            "pivot": "bottom_center",
        },
        "#C47F5C": {
            "shape_kind": "rect",
            "template_id": 20002607,
            "base_pos": {"y": -0.004291653633117676},
            "base_scale": {"x": 0.5799999833106995, "y": 15.0, "z": 0.009999999776482582},
            "base_yaw_deg": 0.0,
            "pivot": "bottom_center",
        },
        "#BAB296": {
            "shape_kind": "rect",
            "template_id": 20001831,
            "base_pos": {"y": -0.004291653633117676},
            "base_scale": {"x": 0.6000000238418579, "y": 0.6000000238418579, "z": 0.009999999776482582},
            "base_yaw_deg": 0.0,
            # 用户口径：该模板在真源表现为“底边 pivot + 高度沿 local-Y 的薄片”，不应走启发式的 height->Z 分支。
            "height_axis": "y",
            "pivot": "bottom_center",
        },
        "#FBAF5C": {
            "shape_kind": "rect",
            # 来源：E:\千星奇域\接力\1.gia（由 ugc_file_tools tool list_gia_entities 导出）
            "template_id": 20001383,
            "base_pos": {"y": -0.004291653633117676},
            "base_scale": {"x": 8.0, "y": 2.6500000953674316, "z": 0.009999999776482582},
            "base_yaw_deg": 0.0,
            "pivot": "bottom_center",
        },
        # circles
        "#F3D199": {
            "shape_kind": "circle",
            "template_id": 20002522,
            "base_pos": {"y": 1.5039632320404053},
            "base_scale": {"x": 6.5, "y": 0.009999999776482582, "z": 7.0},
            "base_yaw_deg": 0.0,
            "base_rot_deg": {"x": -90.0, "y": 0.0, "z": 0.0},
            "pivot": "center",
        },
        "#DBA4A2": {
            "shape_kind": "circle",
            "template_id": 20002523,
            "base_pos": {"y": 1.5039632320404053},
            "base_scale": {"x": 3.5999999046325684, "y": 0.009999999776482582, "z": 3.5999999046325684},
            "base_yaw_deg": 0.0,
            "base_rot_deg": {"x": -90.0, "y": 0.0, "z": 0.0},
            "pivot": "center",
        },
        "#E9D7A5": {
            "shape_kind": "circle",
            "template_id": 20002524,
            "base_pos": {"y": 1.5039632320404053},
            "base_scale": {"x": 3.5999999046325684, "y": 0.009999999776482582, "z": 3.5999999046325684},
            "base_yaw_deg": 0.0,
            "base_rot_deg": {"x": -90.0, "y": 0.0, "z": 0.0},
            "pivot": "center",
        },
        "#EEECE7": {
            "shape_kind": "circle",
            "template_id": 20002565,
            "base_pos": {"y": 1.5039632320404053},
            "base_scale": {"x": 4.300000190734863, "y": 0.009999999776482582, "z": 4.300000190734863},
            "base_yaw_deg": 0.0,
            "base_rot_deg": {"x": 90.0, "y": 0.0, "z": 0.0},
            "pivot": "center",
        },
    }


@dataclass(frozen=True, slots=True)
class ShapeEditorSettings:
    entity_base_gia_path: str
    # “元件（模板）导出”用的 base .gia（参考：用户提供的“导出元件.gia”）
    template_base_gia_path: str
    accessory_template_gia_path: str
    # 坐标锚点口径（导出时决定“画布里的哪个点”映射到世界坐标 pos）：
    # - center：以画布外接矩形中心点为坐标（不做 pivot 转换）
    # - game_pivot：以画布中心点为输入，按模板真实 pivot（profile.pivot：center/bottom_center）转换后导出
    #              （用于解决“游戏 pivot 不一致导致相对位置漂移”的核心问题）
    # - payload_anchor：优先使用 payload.anchor（由前端写入），缺失时回退 center
    position_anchor_mode: str
    units_per_100px: float
    baseline_profiles_by_color: dict[str, JsonDict]
    # 某些模板为“立起来的薄片/竖条”，在 doc 中体现为 base_scale.z≈0.01 且 base_scale.y 显著大于 1；
    # 这类形状的“2D 高度”应映射到 scale.y（而不是 scale.z）。
    upright_y_axis_threshold: float
    thin_axis_threshold: float
    # 旋转方向：由于画布 Y 轴向下、且 world Z 做了翻转，默认取 -angle（更符合直觉）。
    yaw_sign: float


def _get_settings_file_path() -> Path:
    runtime_cache_root = Path(getattr(settings, "RUNTIME_CACHE_ROOT", "app/runtime/cache")).resolve()
    runtime_cache_root.mkdir(parents=True, exist_ok=True)
    return (runtime_cache_root / "shape_editor_settings.json").resolve()


def get_shape_editor_settings_file_path() -> Path:
    return _get_settings_file_path()


def load_shape_editor_settings() -> ShapeEditorSettings:
    path = _get_settings_file_path()
    if not path.is_file():
        guessed_base = _try_guess_entity_base_gia_path()
        guessed_template_base = _try_guess_template_base_gia_path()
        return ShapeEditorSettings(
            entity_base_gia_path=str(guessed_base or "").strip(),
            template_base_gia_path=str(guessed_template_base or "").strip(),
            accessory_template_gia_path="",
            # 默认使用 payload_anchor：
            # - 画布编辑语义保持“几何中心点”不变（不受模板 pivot 影响）
            # - 前端会按模板 pivot 写入 pivot-aware 的 anchor_centered；后端直接按该锚点落盘
            #   （避免再依赖 scale 做中心→pivot 的二次推导）
            position_anchor_mode="payload_anchor",
            # 默认单位口径：100px 对应游戏里“标准直径/长度 3.0”
            # - 矩形标准长度=3
            # - 圆形半径=1.5（直径=3）
            units_per_100px=3.0,
            baseline_profiles_by_color=_default_baseline_profiles_from_doc(),
            upright_y_axis_threshold=1.0,
            thin_axis_threshold=0.05,
            yaw_sign=-1.0,
        )

    obj = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict):
        raise ValueError("shape_editor_settings.json 必须是 JSON object")

    position_anchor_mode_raw = str(obj.get("position_anchor_mode") or "").strip().lower()
    # backward compat:
    # - old "pivot" -> new "game_pivot"（旧语义等价于“按 pivot 导出”，但新命名更明确）
    if position_anchor_mode_raw == "pivot":
        position_anchor_mode_raw = "game_pivot"
    if position_anchor_mode_raw not in {"center", "game_pivot", "payload_anchor"}:
        position_anchor_mode_raw = "payload_anchor"

    units_raw = obj.get("units_per_100px", 3.0)
    units_per_100px = float(units_raw) if isinstance(units_raw, (int, float)) and not isinstance(units_raw, bool) else 3.0

    # 新口径：baseline_profiles_by_color
    profiles_raw = obj.get("baseline_profiles_by_color")
    baseline_profiles: dict[str, JsonDict] = _default_baseline_profiles_from_doc()
    if isinstance(profiles_raw, dict):
        merged: dict[str, JsonDict] = dict(baseline_profiles)
        for color_key, profile in profiles_raw.items():
            color = _normalize_hex_color(str(color_key or ""))
            if not color:
                continue
            if not isinstance(profile, dict):
                continue
            base_profile = dict(merged.get(color, {}))
            base_profile.update(dict(profile))
            merged[color] = base_profile
        baseline_profiles = merged

    # 兼容旧口径：template_id_map（若用户旧配置仍存在，则把 template_id 写回到 profile 上）
    template_id_map_raw = obj.get("template_id_map")
    if isinstance(template_id_map_raw, dict):
        for shape_type, color_map in template_id_map_raw.items():
            st = str(shape_type or "").strip().lower()
            if st not in {"rect", "circle"}:
                continue
            if not isinstance(color_map, dict):
                continue
            for color_key, tid in color_map.items():
                color = _normalize_hex_color(str(color_key or ""))
                if not color:
                    continue
                if not isinstance(tid, (int, float)) or isinstance(tid, bool):
                    continue
                profile = dict(baseline_profiles.get(color, {}))
                if profile:
                    profile["template_id"] = int(tid)
                    profile["shape_kind"] = st
                    baseline_profiles[color] = profile

    upright_th = obj.get("upright_y_axis_threshold", 1.0)
    thin_th = obj.get("thin_axis_threshold", 0.05)
    yaw_sign_raw = obj.get("yaw_sign", -1.0)
    upright_y_axis_threshold = float(upright_th) if isinstance(upright_th, (int, float)) and not isinstance(upright_th, bool) else 1.0
    thin_axis_threshold = float(thin_th) if isinstance(thin_th, (int, float)) and not isinstance(thin_th, bool) else 0.05
    yaw_sign = float(yaw_sign_raw) if isinstance(yaw_sign_raw, (int, float)) and not isinstance(yaw_sign_raw, bool) else -1.0

    entity_base_gia_path = str(obj.get("entity_base_gia_path") or "").strip()
    if entity_base_gia_path == "":
        entity_base_gia_path = str(_try_guess_entity_base_gia_path() or "").strip()

    template_base_gia_path = str(obj.get("template_base_gia_path") or "").strip()
    if template_base_gia_path == "":
        template_base_gia_path = str(_try_guess_template_base_gia_path() or "").strip()

    return ShapeEditorSettings(
        entity_base_gia_path=str(entity_base_gia_path or "").strip(),
        template_base_gia_path=str(template_base_gia_path or "").strip(),
        accessory_template_gia_path=str(obj.get("accessory_template_gia_path") or "").strip(),
        position_anchor_mode=str(position_anchor_mode_raw),
        units_per_100px=float(units_per_100px),
        baseline_profiles_by_color=baseline_profiles,
        upright_y_axis_threshold=float(upright_y_axis_threshold),
        thin_axis_threshold=float(thin_axis_threshold),
        yaw_sign=float(yaw_sign),
    )


def save_shape_editor_settings(settings_obj: ShapeEditorSettings) -> Path:
    path = _get_settings_file_path()
    payload: JsonDict = {
        "entity_base_gia_path": str(settings_obj.entity_base_gia_path or "").strip(),
        "template_base_gia_path": str(settings_obj.template_base_gia_path or "").strip(),
        "accessory_template_gia_path": str(settings_obj.accessory_template_gia_path or "").strip(),
        "position_anchor_mode": str(settings_obj.position_anchor_mode or "").strip() or "payload_anchor",
        "units_per_100px": float(settings_obj.units_per_100px),
        "baseline_profiles_by_color": settings_obj.baseline_profiles_by_color,
        "upright_y_axis_threshold": float(settings_obj.upright_y_axis_threshold),
        "thin_axis_threshold": float(settings_obj.thin_axis_threshold),
        "yaw_sign": float(settings_obj.yaw_sign),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

