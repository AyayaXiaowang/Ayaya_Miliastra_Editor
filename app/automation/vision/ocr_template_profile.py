from __future__ import annotations

"""
OCR 模板 profile 解析与自动选择。

背景：
- OCR/模板匹配对像素级缩放非常敏感，因此模板资源需要按“分辨率档位 + Windows 缩放百分比 + 语言”分组。
- 资源目录约定为：assets/ocr_templates/<profile_name>/...

profile_name 推荐格式：
- <resolution>-<scale>-<locale> 例如：4K-100-CN、4K-125-CN
- <resolution>-<locale> 例如：4K-CN（legacy：不包含缩放信息）

匹配策略（面向未来 2K/1080 扩展）：
- 分辨率按“屏幕短边”与目标档位短边（4K=2160、2K=1440、1080=1080）做近似匹配，
  允许一定比例偏差以放宽长宽比要求（例如 1080x900 可匹配到 1080 档位）。
- 缩放优先精确匹配（100/125/150...），若缺失则可回退到 legacy profile 或最近档位。

注意：
- 本模块不吞异常；如检测或解析失败会直接抛出错误，交由上层决定如何提示。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple, List, Dict
import ctypes
import os
import sys

from app.automation.capture.dpi_awareness import ensure_dpi_awareness_once


_ENV_OCR_TEMPLATE_PROFILE = "GRAPH_GENERATER_OCR_TEMPLATE_PROFILE"

# 分辨率档位（按“屏幕短边”定义；不强制要求严格长宽比）
_RESOLUTION_SHORT_SIDE_BASELINE: Dict[str, int] = {
    "4K": 2160,
    "2K": 1440,
    "1080": 1080,
}

# 允许的短边相对偏差（例如 1080 vs 900 => 16.7%）
_MAX_RESOLUTION_RELATIVE_DELTA = 0.25


@dataclass(frozen=True)
class DetectedDisplaySettings:
    screen_width_px: int
    screen_height_px: int
    dpi_x: int
    scale_percent: int

    @property
    def short_side_px(self) -> int:
        return int(min(self.screen_width_px, self.screen_height_px))

    @property
    def long_side_px(self) -> int:
        return int(max(self.screen_width_px, self.screen_height_px))


@dataclass(frozen=True)
class OcrTemplateProfile:
    name: str
    resolution_tag: str
    scale_percent: Optional[int]
    locale: str


@dataclass(frozen=True)
class OcrTemplateProfileSelection:
    workspace_root: Path
    templates_root: Path
    detected_display: DetectedDisplaySettings
    available_profiles: Tuple[OcrTemplateProfile, ...]
    selected_profile: OcrTemplateProfile
    selected_reason: str
    matched_resolution_tag: Optional[str]
    matched_scale_percent: Optional[int]
    is_exact_match: bool
    mismatch_reason: str

    @property
    def selected_profile_name(self) -> str:
        return str(self.selected_profile.name)

    @property
    def available_profile_names(self) -> List[str]:
        return [profile.name for profile in self.available_profiles]


_DEFAULT_WORKSPACE_ROOT: Optional[Path] = None
_DEFAULT_PROFILE_NAME: Optional[str] = None

_CACHED_AUTO_WORKSPACE_ROOT: Optional[Path] = None
_CACHED_AUTO_TEMPLATES_MTIME_NS: Optional[int] = None
_CACHED_AUTO_ENV_OVERRIDE: str = ""
_CACHED_AUTO_SELECTION: Optional[OcrTemplateProfileSelection] = None


def set_default_ocr_template_profile(workspace_root: Path, profile_name: str) -> None:
    """设置默认 OCR 模板 profile（供无法显式传参的调用方复用）。"""
    global _DEFAULT_WORKSPACE_ROOT, _DEFAULT_PROFILE_NAME
    _DEFAULT_WORKSPACE_ROOT = Path(workspace_root).resolve()
    _DEFAULT_PROFILE_NAME = str(profile_name or "").strip()


def get_default_ocr_template_profile(workspace_root: Path) -> Optional[str]:
    """返回默认 OCR 模板 profile；仅当 workspace_root 一致时才返回。"""
    if _DEFAULT_WORKSPACE_ROOT is None or _DEFAULT_PROFILE_NAME is None:
        return None
    if Path(workspace_root).resolve() != _DEFAULT_WORKSPACE_ROOT:
        return None
    return _DEFAULT_PROFILE_NAME


def _parse_profile_dir_name(dir_name: str) -> Optional[OcrTemplateProfile]:
    name_text = str(dir_name or "").strip()
    if not name_text:
        return None
    parts = [part.strip() for part in name_text.split("-") if part.strip()]
    if len(parts) == 3:
        resolution_tag, scale_text, locale = parts
        if not scale_text.isdigit():
            return None
        return OcrTemplateProfile(
            name=name_text,
            resolution_tag=str(resolution_tag).upper(),
            scale_percent=int(scale_text),
            locale=str(locale).upper(),
        )
    if len(parts) == 2:
        resolution_tag, locale = parts
        return OcrTemplateProfile(
            name=name_text,
            resolution_tag=str(resolution_tag).upper(),
            scale_percent=None,
            locale=str(locale).upper(),
        )
    return None


def scan_ocr_template_profiles(workspace_root: Path) -> List[OcrTemplateProfile]:
    """扫描 workspace 下 assets/ocr_templates 目录，返回可用 profile 列表。"""
    workspace_root_resolved = Path(workspace_root).resolve()
    templates_root = workspace_root_resolved / "assets" / "ocr_templates"
    if not templates_root.exists():
        return []

    profiles: List[OcrTemplateProfile] = []
    for child in templates_root.iterdir():
        if not child.is_dir():
            continue
        profile = _parse_profile_dir_name(child.name)
        if profile is None:
            continue
        profiles.append(profile)

    # 稳定排序：resolution_tag -> scale_percent(None last) -> locale -> name
    def _sort_key(profile: OcrTemplateProfile) -> tuple:
        scale_value = profile.scale_percent if profile.scale_percent is not None else 10_000
        return (profile.resolution_tag, int(scale_value), profile.locale, profile.name)

    profiles.sort(key=_sort_key)
    return profiles


def _detect_windows_display_settings() -> DetectedDisplaySettings:
    """检测 Windows 主屏分辨率与缩放（DPI）。"""
    if sys.platform != "win32":
        raise RuntimeError("display detection is only supported on Windows (win32)")

    # 统一打开 Per-Monitor DPI awareness，避免 GetSystemMetrics 返回逻辑像素
    ensure_dpi_awareness_once()

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    screen_width_px = int(user32.GetSystemMetrics(0))
    screen_height_px = int(user32.GetSystemMetrics(1))

    # DPI：优先使用 LOGPIXELSX（与屏幕缩放相关）
    hdc = user32.GetDC(0)
    LOGPIXELSX = 88
    dpi_x = int(gdi32.GetDeviceCaps(hdc, int(LOGPIXELSX)))
    user32.ReleaseDC(0, hdc)

    scale_percent_float = (float(dpi_x) / 96.0) * 100.0 if dpi_x > 0 else 100.0
    scale_percent = int(round(scale_percent_float))
    if scale_percent <= 0:
        scale_percent = 100

    return DetectedDisplaySettings(
        screen_width_px=screen_width_px,
        screen_height_px=screen_height_px,
        dpi_x=dpi_x,
        scale_percent=scale_percent,
    )


def _resolution_tag_to_baseline_short_side_px(resolution_tag: str) -> Optional[int]:
    normalized = str(resolution_tag or "").strip().upper()
    if not normalized:
        return None
    baseline = _RESOLUTION_SHORT_SIDE_BASELINE.get(normalized)
    if baseline is not None:
        return int(baseline)
    if normalized.isdigit():
        value = int(normalized)
        return value if value > 0 else None
    return None


def _match_resolution_tag(
    *,
    screen_short_side_px: int,
    candidate_tags: Iterable[str],
) -> Optional[str]:
    best_tag: Optional[str] = None
    best_ratio: Optional[float] = None
    for tag in candidate_tags:
        baseline = _resolution_tag_to_baseline_short_side_px(tag)
        if baseline is None or baseline <= 0:
            continue
        ratio = abs(float(screen_short_side_px) - float(baseline)) / float(baseline)
        if best_ratio is None or ratio < float(best_ratio):
            best_ratio = float(ratio)
            best_tag = str(tag).upper()
    if best_tag is None or best_ratio is None:
        return None
    if float(best_ratio) > float(_MAX_RESOLUTION_RELATIVE_DELTA):
        return None
    return best_tag


def resolve_ocr_template_profile_selection(
    workspace_root: Path,
    *,
    preferred_locale: str = "CN",
) -> OcrTemplateProfileSelection:
    """解析并选择最合适的 OCR 模板 profile，返回完整选择结果（含提示所需信息）。"""
    workspace_root_resolved = Path(workspace_root).resolve()
    templates_root = workspace_root_resolved / "assets" / "ocr_templates"
    templates_root_mtime_ns = templates_root.stat().st_mtime_ns if templates_root.exists() else 0

    env_override = str(os.environ.get(_ENV_OCR_TEMPLATE_PROFILE, "") or "").strip()
    if env_override:
        override_dir = templates_root / env_override
        if not override_dir.exists() or not override_dir.is_dir():
            raise ValueError(
                f"环境变量 {_ENV_OCR_TEMPLATE_PROFILE}='{env_override}' 指向的模板目录不存在：{override_dir}"
            )

    global _CACHED_AUTO_WORKSPACE_ROOT, _CACHED_AUTO_TEMPLATES_MTIME_NS, _CACHED_AUTO_ENV_OVERRIDE, _CACHED_AUTO_SELECTION
    if (
        _CACHED_AUTO_SELECTION is not None
        and _CACHED_AUTO_WORKSPACE_ROOT is not None
        and Path(_CACHED_AUTO_WORKSPACE_ROOT).resolve() == workspace_root_resolved
        and int(_CACHED_AUTO_TEMPLATES_MTIME_NS or 0) == int(templates_root_mtime_ns)
        and str(_CACHED_AUTO_ENV_OVERRIDE or "") == env_override
    ):
        return _CACHED_AUTO_SELECTION

    detected_display = _detect_windows_display_settings()

    available_profiles = scan_ocr_template_profiles(workspace_root_resolved)
    if not available_profiles:
        raise RuntimeError(f"未找到任何 OCR 模板 profile：{templates_root}")

    locale_text = str(preferred_locale or "").strip().upper() or "CN"
    locale_profiles = [profile for profile in available_profiles if profile.locale == locale_text]
    if not locale_profiles:
        locale_profiles = list(available_profiles)

    # 1) 环境变量强制指定
    if env_override:
        forced_profile = None
        for profile in locale_profiles:
            if profile.name == env_override:
                forced_profile = profile
                break
        if forced_profile is None:
            # env_override 目录存在但不符合解析规则（例如名字不满足 <res>-<scale>-<locale>）
            forced_profile = OcrTemplateProfile(
                name=env_override,
                resolution_tag="",
                scale_percent=None,
                locale=locale_text,
            )
        selection = OcrTemplateProfileSelection(
            workspace_root=workspace_root_resolved,
            templates_root=templates_root,
            detected_display=detected_display,
            available_profiles=tuple(available_profiles),
            selected_profile=forced_profile,
            selected_reason=f"env_override({_ENV_OCR_TEMPLATE_PROFILE})",
            matched_resolution_tag=None,
            matched_scale_percent=int(detected_display.scale_percent),
            is_exact_match=False,
            mismatch_reason="profile forced by env override",
        )
        _CACHED_AUTO_WORKSPACE_ROOT = workspace_root_resolved
        _CACHED_AUTO_TEMPLATES_MTIME_NS = int(templates_root_mtime_ns)
        _CACHED_AUTO_ENV_OVERRIDE = env_override
        _CACHED_AUTO_SELECTION = selection
        return selection

    # 2) 若上层已设置默认 profile，优先复用
    default_profile_name = get_default_ocr_template_profile(workspace_root_resolved)
    if default_profile_name:
        matched_profile = None
        for profile in locale_profiles:
            if profile.name == default_profile_name:
                matched_profile = profile
                break
        if matched_profile is not None:
            selection = OcrTemplateProfileSelection(
                workspace_root=workspace_root_resolved,
                templates_root=templates_root,
                detected_display=detected_display,
                available_profiles=tuple(available_profiles),
                selected_profile=matched_profile,
                selected_reason="default_profile",
                matched_resolution_tag=matched_profile.resolution_tag or None,
                matched_scale_percent=matched_profile.scale_percent,
                is_exact_match=True,
                mismatch_reason="",
            )
            _CACHED_AUTO_WORKSPACE_ROOT = workspace_root_resolved
            _CACHED_AUTO_TEMPLATES_MTIME_NS = int(templates_root_mtime_ns)
            _CACHED_AUTO_ENV_OVERRIDE = env_override
            _CACHED_AUTO_SELECTION = selection
            return selection

    # 3) 自动匹配：分辨率档位 + 缩放
    distinct_tags = sorted({profile.resolution_tag for profile in locale_profiles if profile.resolution_tag})
    matched_resolution_tag = _match_resolution_tag(
        screen_short_side_px=int(detected_display.short_side_px),
        candidate_tags=distinct_tags,
    )

    selected_profile: Optional[OcrTemplateProfile] = None
    selected_reason = ""
    is_exact_match = False
    mismatch_reason = ""

    matched_scale_percent = int(detected_display.scale_percent)

    def _pick_default_profile_fallback() -> OcrTemplateProfile:
        # 优先选择 legacy 的 4K-CN（若存在），否则选择 locale_profiles 的第一个
        preferred_legacy_name = f"4K-{locale_text}"
        for profile in locale_profiles:
            if profile.name == preferred_legacy_name:
                return profile
        return locale_profiles[0]

    if matched_resolution_tag is None:
        selected_profile = _pick_default_profile_fallback()
        selected_reason = "fallback_unmatched_resolution"
        is_exact_match = False
        mismatch_reason = "unmatched_resolution"
    else:
        tag_profiles = [profile for profile in locale_profiles if profile.resolution_tag == matched_resolution_tag]
        if not tag_profiles:
            selected_profile = _pick_default_profile_fallback()
            selected_reason = "fallback_no_profiles_for_resolution"
            is_exact_match = False
            mismatch_reason = "no_profiles_for_resolution"
        else:
            exact_scale_profiles = [
                profile for profile in tag_profiles
                if profile.scale_percent is not None and int(profile.scale_percent) == int(matched_scale_percent)
            ]
            if exact_scale_profiles:
                selected_profile = exact_scale_profiles[0]
                selected_reason = "exact_match"
                is_exact_match = True
            else:
                legacy_profiles = [profile for profile in tag_profiles if profile.scale_percent is None]
                has_scaled_variants = any(profile.scale_percent is not None for profile in tag_profiles)
                if legacy_profiles:
                    selected_profile = legacy_profiles[0]
                    selected_reason = "legacy_fallback"
                    # 仅当该分辨率档位没有任何 scale 变体时，将 legacy 视为“完全匹配”
                    is_exact_match = (not has_scaled_variants)
                    if has_scaled_variants:
                        mismatch_reason = "missing_scale_variant"
                else:
                    scaled_profiles = [profile for profile in tag_profiles if profile.scale_percent is not None]
                    if not scaled_profiles:
                        selected_profile = tag_profiles[0]
                        selected_reason = "fallback_profile_without_scale_info"
                        is_exact_match = False
                        mismatch_reason = "missing_scale_info"
                    else:
                        # 选择最接近的 scale 档位
                        scaled_profiles.sort(
                            key=lambda profile: abs(int(profile.scale_percent or 0) - int(matched_scale_percent))
                        )
                        selected_profile = scaled_profiles[0]
                        selected_reason = "nearest_scale"
                        is_exact_match = False
                        mismatch_reason = "scale_mismatch"

    if selected_profile is None:
        selected_profile = _pick_default_profile_fallback()
        selected_reason = "fallback_internal"
        is_exact_match = False
        mismatch_reason = "internal_fallback"

    selection = OcrTemplateProfileSelection(
        workspace_root=workspace_root_resolved,
        templates_root=templates_root,
        detected_display=detected_display,
        available_profiles=tuple(available_profiles),
        selected_profile=selected_profile,
        selected_reason=selected_reason,
        matched_resolution_tag=matched_resolution_tag,
        matched_scale_percent=matched_scale_percent,
        is_exact_match=bool(is_exact_match),
        mismatch_reason=str(mismatch_reason or ""),
    )

    _CACHED_AUTO_WORKSPACE_ROOT = workspace_root_resolved
    _CACHED_AUTO_TEMPLATES_MTIME_NS = int(templates_root_mtime_ns)
    _CACHED_AUTO_ENV_OVERRIDE = env_override
    _CACHED_AUTO_SELECTION = selection
    return selection


def resolve_ocr_template_profile_name(workspace_root: Path, *, preferred_locale: str = "CN") -> str:
    """返回应使用的 OCR 模板 profile 名称（目录名）。"""
    selection = resolve_ocr_template_profile_selection(workspace_root, preferred_locale=preferred_locale)
    return selection.selected_profile_name


def build_ocr_template_profile_mismatch_hint(selection: OcrTemplateProfileSelection) -> str:
    """构造“模板 profile 与显示设置不匹配”提示文案；若无需提示则返回空字符串。"""
    if selection is None:
        return ""
    if bool(selection.is_exact_match):
        return ""

    detected = selection.detected_display
    available = selection.available_profile_names
    available_text = "，".join(available) if available else "(无)"

    matched_resolution = selection.matched_resolution_tag
    locale_text = selection.selected_profile.locale or "CN"
    resolution_candidates: List[str] = []
    scale_candidates: List[int] = []
    if matched_resolution:
        for profile in selection.available_profiles:
            if profile.locale != locale_text:
                continue
            if profile.resolution_tag != matched_resolution:
                continue
            resolution_candidates.append(profile.name)
            if profile.scale_percent is not None:
                scale_candidates.append(int(profile.scale_percent))
    scale_candidates = sorted({int(value) for value in scale_candidates})

    recommend_lines: List[str] = []
    if resolution_candidates:
        recommend_lines.append(f"建议优先使用同档位模板：{ '，'.join(resolution_candidates) }")
    if scale_candidates:
        recommend_lines.append(f"可用缩放档位：{ ' / '.join(str(v) + '%' for v in scale_candidates) }")

    recommend_text = "；".join(recommend_lines) if recommend_lines else "建议调整到已有模板 profile，或补充对应模板目录。"

    return (
        "⚠ OCR 模板 profile 可能与当前显示设置不匹配。\n"
        f" - 检测到显示：{detected.screen_width_px}x{detected.screen_height_px}，缩放 {detected.scale_percent}%\n"
        f" - 可用模板 profile：{available_text}\n"
        f" - 当前选择：{selection.selected_profile_name}（原因：{selection.selected_reason}）\n"
        f" - {recommend_text}"
    )


