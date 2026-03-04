from __future__ import annotations

import base64
import io
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


# ---------------------------------------------------------------------------
#  Lab 色彩空间 预量化（Pre-quantization）
#  在 PerfectPixel 标准像素化之前，将原图每个像素映射到最近的调色板颜色，
#  消除抗锯齿/压缩伪影/渐变带来的微小色差，避免后续采样产生"麻子"碎色。
# ---------------------------------------------------------------------------

def _hex_to_rgb_array(hex_colors: list[str]) -> np.ndarray:
    """将 ['#RRGGBB', ...] 转为 (N, 3) uint8 数组。"""
    out = np.empty((len(hex_colors), 3), dtype=np.uint8)
    for i, h in enumerate(hex_colors):
        h = h.strip().lstrip("#")
        out[i, 0] = int(h[0:2], 16)
        out[i, 1] = int(h[2:4], 16)
        out[i, 2] = int(h[4:6], 16)
    return out


def _srgb_to_linear(v: np.ndarray) -> np.ndarray:
    """sRGB [0,1] -> linear [0,1]，向量化。"""
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def _rgb_uint8_to_lab(rgb: np.ndarray) -> np.ndarray:
    """
    (..., 3) uint8 RGB -> (..., 3) float64 CIE Lab。
    支持任意前导维度。
    """
    shape = rgb.shape
    flat = rgb.reshape(-1, 3).astype(np.float64) / 255.0

    # sRGB -> linear
    lin = _srgb_to_linear(flat)

    # linear RGB -> XYZ (D65)
    mat = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ])
    xyz = lin @ mat.T  # (N, 3)

    # D65 白点
    xn, yn, zn = 0.95047, 1.0, 1.08883
    xyz[:, 0] /= xn
    xyz[:, 1] /= yn
    xyz[:, 2] /= zn

    # f(t)
    delta = 6.0 / 29.0
    delta3 = delta ** 3
    f = np.where(xyz > delta3, np.cbrt(xyz), xyz / (3.0 * delta * delta) + 4.0 / 29.0)

    L = 116.0 * f[:, 1] - 16.0
    a = 500.0 * (f[:, 0] - f[:, 1])
    b = 200.0 * (f[:, 1] - f[:, 2])

    lab = np.stack([L, a, b], axis=-1)
    return lab.reshape(shape)


def prequantize_to_palette(rgb: np.ndarray, palette_hex: list[str]) -> np.ndarray:
    """
    将 (H, W, 3) uint8 RGB 图像的每个像素映射到 palette_hex 中 Lab DE76 最近的颜色。

    返回 (H, W, 3) uint8 RGB（颜色仅来自调色板）。
    """
    if not palette_hex:
        return rgb.copy()

    H, W = rgb.shape[:2]
    palette_rgb = _hex_to_rgb_array(palette_hex)  # (P, 3)
    palette_lab = _rgb_uint8_to_lab(palette_rgb)   # (P, 3)

    # 将图像展平为 (N, 3)，转 Lab
    pixels_lab = _rgb_uint8_to_lab(rgb.reshape(-1, 3))  # (N, 3)

    # 计算每个像素到每个调色板颜色的 DE76^2 距离
    # pixels_lab: (N, 3), palette_lab: (P, 3)
    # 利用广播：(N, 1, 3) - (P, 3) -> (N, P, 3) -> sum -> (N, P)
    diff = pixels_lab[:, np.newaxis, :] - palette_lab[np.newaxis, :, :]  # (N, P, 3)
    dist_sq = np.sum(diff * diff, axis=2)  # (N, P)

    # 每个像素取最近调色板索引
    nearest_idx = np.argmin(dist_sq, axis=1)  # (N,)

    # 用调色板 RGB 替换
    out = palette_rgb[nearest_idx].reshape(H, W, 3)
    return out


def _ensure_perfect_pixel_importable() -> None:
    """
    本仓库内的 perfectPixel 源码位于：
    - private_extensions/shape-editor/perfectPixel/src/perfect_pixel

    这里通过将 `perfectPixel/src` 注入 sys.path 来直接 `import perfect_pixel`。
    """
    tool_dir = Path(__file__).resolve().parent.parent
    perfect_pixel_src = (tool_dir / "perfectPixel" / "src").resolve()
    if not perfect_pixel_src.is_dir():
        raise FileNotFoundError(f"未找到 perfectPixel/src：{str(perfect_pixel_src)!r}")
    text = str(perfect_pixel_src)
    if text not in sys.path:
        sys.path.insert(0, text)


def _parse_image_data_url(data_url: str) -> tuple[str, bytes]:
    s = str(data_url or "").strip()
    if not s.startswith("data:"):
        raise ValueError("image_data_url 必须是 data URL（data:image/...;base64,...）")
    if ";base64," not in s:
        raise ValueError("image_data_url 必须包含 ';base64,'")
    header, b64 = s.split(",", 1)
    mime = header[5:].split(";", 1)[0].strip().lower()
    data = base64.b64decode(str(b64 or "").strip())
    return mime, data


def _decode_rgb_from_bytes(data: bytes) -> np.ndarray:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    arr = np.array(img)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"输入图片不是 RGB：shape={arr.shape!r}")
    return arr.astype(np.uint8, copy=False)


def _encode_png_data_url(rgb: np.ndarray) -> str:
    arr = np.asarray(rgb)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"输出不是 RGB：shape={arr.shape!r}")
    out = Image.fromarray(arr.astype(np.uint8, copy=False), mode="RGB")
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def refine_image_data_url_with_perfect_pixel(
    *,
    image_data_url: str,
    sample_method: str = "center",
    refine_intensity: float = 0.30,
    fix_square: bool = True,
    palette_hex: list[str] | None = None,
) -> dict[str, Any]:
    """
    将任意输入图（data url）转换为 PerfectPixel 的"标准像素矩阵图"（PNG data url）。

    若提供 palette_hex（如 RECT_COLORS），则在 PerfectPixel 标准像素化 **之前** 先做
    Lab DE76 预量化：把原图每个像素统一到调色板最近色，消除抗锯齿/压缩/渐变带来的
    碎色，使后续采样结果干净纯粹。

    返回：
    - ok
    - refined_w/refined_h：标准像素矩阵尺寸
    - image_data_url：PNG data url（像素矩阵图）
    """
    _ensure_perfect_pixel_importable()
    from perfect_pixel import get_perfect_pixel  # type: ignore[import-not-found]

    _mime, data = _parse_image_data_url(image_data_url)
    rgb = _decode_rgb_from_bytes(data)

    # ---- 预量化：在 PerfectPixel 之前将颜色统一到支持色 ----
    if palette_hex:
        rgb = prequantize_to_palette(rgb, palette_hex)

    refined_w, refined_h, out_rgb = get_perfect_pixel(
        rgb,
        sample_method=str(sample_method or "center"),
        refine_intensity=float(refine_intensity),
        fix_square=bool(fix_square),
        debug=False,
    )
    if refined_w is None or refined_h is None:
        return {
            "ok": False,
            "error": "PerfectPixel 网格识别失败：请换一张更像素风的图或调整参数",
        }

    out_url = _encode_png_data_url(out_rgb)
    return {
        "ok": True,
        "refined_w": int(refined_w),
        "refined_h": int(refined_h),
        "image_data_url": str(out_url),
    }
