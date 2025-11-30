from __future__ import annotations

from typing import Optional, Dict, Any, List
from PIL import Image, ImageDraw, ImageFont
import textwrap
import os
from io import BytesIO


def _measure_text(font: ImageFont.ImageFont, text: str) -> tuple[int, int]:
    safe_text = text or ""
    if hasattr(font, "getbbox"):
        left, top, right, bottom = font.getbbox(safe_text)
        return max(0, int(right - left)), max(0, int(bottom - top))
    if hasattr(font, "getsize"):
        width, height = font.getsize(safe_text)
        return max(0, int(width)), max(0, int(height))
    dummy = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(dummy)
    left, top, right, bottom = draw.textbbox((0, 0), safe_text, font=font)
    return max(0, int(right - left)), max(0, int(bottom - top))


def compose_reference_panel(
    base_image: Image.Image,
    *,
    title: str,
    content_image: Optional[Image.Image] = None,
    content_image_path: Optional[str] = None,
    content_text: Optional[str] = None,
    max_width_ratio: float = 0.22,
    max_height_ratio: float = 0.40,
) -> Image.Image:
    if content_image is None and (not content_text or not content_text.strip()):
        return base_image

    base_mode = base_image.mode
    canvas = base_image.convert("RGBA")
    canvas_w, canvas_h = canvas.size
    panel_margin = 18
    padding = 10

    font = ImageFont.load_default()
    header_text = (title or "").strip()
    header_height = _measure_text(font, header_text or "参考")[1]

    max_panel_w = max(160, int(canvas_w * max_width_ratio))
    max_panel_h = max(140, int(canvas_h * max_height_ratio))

    ref_image = None
    if content_image is not None:
        ref_image = content_image.convert("RGBA")
    elif content_image_path and os.path.exists(content_image_path):
        with Image.open(content_image_path) as tpl_raw:
            ref_image = tpl_raw.convert("RGBA")
    if ref_image is not None:
        img_w, img_h = ref_image.size
        if img_w == 0 or img_h == 0:
            ref_image = None
        else:
            max_img_w = max_panel_w - padding * 2
            max_img_h = max_panel_h - padding * 2 - header_height - 6
            scale = min(1.0, max_img_w / img_w, max_img_h / img_h)
            scaled_size = (max(1, int(img_w * scale)), max(1, int(img_h * scale)))
            if scaled_size != ref_image.size:
                ref_image = ref_image.resize(scaled_size, Image.LANCZOS)

    text_lines: List[str] = []
    if ref_image is None and content_text:
        normalized = content_text.strip().replace("\r", " ").replace("\n", " ")
        if normalized:
            wrapped = textwrap.wrap(normalized, width=22)
            text_lines = wrapped[:6]

    line_height = _measure_text(font, "A")[1] + 2
    text_height = len(text_lines) * line_height
    text_width = max((_measure_text(font, line)[0] for line in text_lines), default=0)

    panel_w = max_panel_w
    if ref_image is not None:
        panel_w = min(max_panel_w, max(ref_image.size[0] + padding * 2, header_height + padding * 2 + 80))
    elif text_lines:
        panel_w = min(max_panel_w, max(text_width + padding * 2, 180))

    content_height = ref_image.size[1] if ref_image is not None else text_height
    panel_h = min(max_panel_h, header_height + padding + content_height + padding)

    panel = Image.new("RGBA", (panel_w, panel_h), (12, 12, 14, 210))
    draw = ImageDraw.Draw(panel)
    if header_text:
        draw.text((padding, padding // 2), header_text, fill=(255, 255, 255, 230), font=font)
    draw.rectangle([(0, 0), (panel_w - 1, panel_h - 1)], outline=(255, 255, 255, 180), width=1)

    content_top = padding + header_height + 4
    if ref_image is not None:
        panel.paste(ref_image, (padding, content_top))
    elif text_lines:
        text_y = content_top
        for line in text_lines:
            draw.text((padding, text_y), line, fill=(230, 230, 230, 230), font=font)
            text_y += line_height

    paste_x = canvas_w - panel_w - panel_margin
    paste_y = panel_margin
    canvas.alpha_composite(panel, (paste_x, paste_y))
    return canvas.convert(base_mode)


def build_reference_panel_payload(
    title: str,
    *,
    text: Optional[str] = None,
    image_path: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {'title': title}
    if text:
        payload['text'] = text
    if image_path:
        payload['image_path'] = image_path
        with Image.open(image_path) as tpl_raw:
            buffer = BytesIO()
            tpl_raw.save(buffer, format='PNG')
            payload['image_bytes'] = buffer.getvalue()
    return payload

