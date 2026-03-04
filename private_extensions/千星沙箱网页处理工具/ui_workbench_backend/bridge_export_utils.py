from __future__ import annotations

import copy
from typing import Any, Optional


class _UiWorkbenchBridgeExportUtilsMixin:
    @staticmethod
    def _parse_canvas_size_key(value: str) -> Optional[tuple[float, float]]:
        text = str(value or "").strip().lower()
        if "x" not in text:
            return None
        left, right = text.split("x", 1)
        try_w = left.strip()
        try_h = right.strip()
        if try_w.isdigit() and try_h.isdigit():
            w = float(int(try_w))
            h = float(int(try_h))
            if w > 0 and h > 0:
                return (w, h)
        return None

    @staticmethod
    def _sanitize_windows_file_stem(text: str) -> str:
        raw = str(text or "").strip()
        if raw == "":
            return "untitled"
        # Windows 文件名禁止：<>:"/\|?* 以及控制字符
        forbidden = '<>:"/\\\\|?*'
        out_chars: list[str] = []
        for ch in raw:
            code = ord(ch)
            if code < 32:
                out_chars.append("_")
                continue
            if ch in forbidden:
                out_chars.append("_")
                continue
            out_chars.append(ch)
        cleaned = "".join(out_chars).strip().strip(".")
        if cleaned == "":
            return "untitled"
        if len(cleaned) > 80:
            return cleaned[:80]
        return cleaned

    @classmethod
    def _sanitize_bundle_payload_for_gil_writeback(cls, bundle_payload: dict) -> None:
        """就地清洗 bundle payload：确保写回 `.gil` 时不会因“不支持的颜色 hex”等输入问题失败。"""
        if not isinstance(bundle_payload, dict):
            return
        for widget in cls._iter_ui_widgets_from_bundle(bundle_payload):
            if str(widget.get("widget_type") or "").strip() != "进度条":
                continue
            settings = widget.get("settings")
            if not isinstance(settings, dict):
                continue
            raw = str(settings.get("color") or "").strip()
            if raw == "":
                continue
            settings["color"] = cls._normalize_progressbar_color_hex(raw)

    @staticmethod
    def _iter_ui_widgets_from_bundle(bundle_payload: dict) -> list[dict[str, Any]]:
        if not isinstance(bundle_payload, dict):
            return []

        layout_node = bundle_payload.get("layout")
        if isinstance(layout_node, dict):
            widgets_node = layout_node.get("widgets")
            if isinstance(widgets_node, list) and widgets_node:
                out: list[dict[str, Any]] = []
                for w in widgets_node:
                    if isinstance(w, dict):
                        out.append(w)
                return out

        templates = bundle_payload.get("templates")
        if not isinstance(templates, list):
            return []
        out2: list[dict[str, Any]] = []
        for template in templates:
            if not isinstance(template, dict):
                continue
            widgets = template.get("widgets")
            if not isinstance(widgets, list):
                continue
            for w in widgets:
                if isinstance(w, dict):
                    out2.append(w)
        return out2

    @staticmethod
    def _convert_ui_bundle_to_inline_widgets_bundle(bundle_payload: dict) -> dict:
        """将 Workbench bundle（layout+templates）转换为 inline widgets（layout.widgets）。

        用途：写回 `.gil` 场景不需要 templates/custom_groups 引用关系，只需要 widgets 列表即可。
        """
        if not isinstance(bundle_payload, dict):
            return bundle_payload
        if str(bundle_payload.get("bundle_type") or "") != "ui_workbench_ui_layout_bundle":
            return bundle_payload

        layout_node = bundle_payload.get("layout")
        if not isinstance(layout_node, dict):
            return bundle_payload

        # 已是 inline：直接返回
        if isinstance(layout_node.get("widgets"), list) and layout_node.get("widgets"):
            return bundle_payload

        templates = bundle_payload.get("templates")
        if not isinstance(templates, list):
            return bundle_payload

        templates_by_id: dict[str, dict[str, Any]] = {}
        for template in templates:
            if not isinstance(template, dict):
                continue
            tid = str(template.get("template_id") or "").strip()
            if tid == "":
                continue
            templates_by_id[tid] = template

        ordered_template_ids: list[str] = []
        custom_groups = layout_node.get("custom_groups")
        if isinstance(custom_groups, list):
            for item in custom_groups:
                tid = str(item or "").strip()
                if tid == "":
                    continue
                if tid in templates_by_id and tid not in ordered_template_ids:
                    ordered_template_ids.append(tid)
        for tid in sorted(templates_by_id.keys()):
            if tid not in ordered_template_ids:
                ordered_template_ids.append(tid)

        widgets: list[dict[str, Any]] = []
        for tid in ordered_template_ids:
            template = templates_by_id.get(tid)
            if not isinstance(template, dict):
                continue
            widget_list = template.get("widgets")
            if not isinstance(widget_list, list):
                continue
            for w in widget_list:
                if isinstance(w, dict):
                    widgets.append(w)

        if not widgets:
            return bundle_payload

        new_bundle = copy.deepcopy(bundle_payload)
        new_layout = new_bundle.get("layout")
        if not isinstance(new_layout, dict):
            return bundle_payload
        new_layout["widgets"] = widgets
        # 避免在本场景产生“引用模板”的误解：删掉引用信息与模板列表
        if "custom_groups" in new_layout:
            del new_layout["custom_groups"]
        if "templates" in new_bundle:
            del new_bundle["templates"]
        new_bundle["bundle_version"] = 2
        return new_bundle

    @classmethod
    def _normalize_progressbar_color_hex(cls, color_text: str) -> str:
        """把任意 hex 颜色量化到“千星沙箱进度条可表达的五色调色板”。

        约定：
        - 返回值为调色板 hex（大写、6 位），或空字符串（让下游使用默认绿色）。
        - 不解析/支持 `rgb(...)`/颜色名：写回端本质只接受 hex。
        """
        raw = str(color_text or "").strip()
        if raw == "":
            return ""
        upper = raw.upper()

        # 直接命中调色板：原样返回（保证大写）
        if upper in {
            cls._PROGRESSBAR_PALETTE_HEX_WHITE,
            cls._PROGRESSBAR_PALETTE_HEX_GREEN,
            cls._PROGRESSBAR_PALETTE_HEX_YELLOW,
            cls._PROGRESSBAR_PALETTE_HEX_BLUE,
            cls._PROGRESSBAR_PALETTE_HEX_RED,
        }:
            return upper

        rgba = cls._try_parse_hex_to_rgba(upper)
        if rgba is None:
            return ""

        r, g, b, _a = rgba

        # 灰度/低饱和：归为“白色”（暖白）
        max_c = max(r, g, b)
        min_c = min(r, g, b)
        delta_c = max_c - min_c
        if max_c <= 0:
            return cls._PROGRESSBAR_PALETTE_HEX_WHITE
        saturation = float(delta_c) / float(max_c)
        if saturation < 0.12:
            return cls._PROGRESSBAR_PALETTE_HEX_WHITE

        hue = cls._rgb_to_hue_degrees(r, g, b)
        # Hue buckets tuned for “语义更像”：偏红→红，偏黄/金→黄，偏绿→绿，其余→蓝
        if hue < 25.0 or hue >= 335.0:
            return cls._PROGRESSBAR_PALETTE_HEX_RED
        if hue < 70.0:
            return cls._PROGRESSBAR_PALETTE_HEX_YELLOW
        if hue < 170.0:
            return cls._PROGRESSBAR_PALETTE_HEX_GREEN
        return cls._PROGRESSBAR_PALETTE_HEX_BLUE

    @staticmethod
    def _try_parse_hex_to_rgba(color_hex_text: str) -> tuple[int, int, int, int] | None:
        text = str(color_hex_text or "").strip()
        if not text.startswith("#"):
            return None
        hex_part = text[1:]
        if len(hex_part) not in (3, 4, 6, 8):
            return None
        if not all(ch in "0123456789ABCDEFabcdef" for ch in hex_part):
            return None

        if len(hex_part) == 3:
            r = int(hex_part[0] + hex_part[0], 16)
            g = int(hex_part[1] + hex_part[1], 16)
            b = int(hex_part[2] + hex_part[2], 16)
            return (r, g, b, 255)
        if len(hex_part) == 4:
            r = int(hex_part[0] + hex_part[0], 16)
            g = int(hex_part[1] + hex_part[1], 16)
            b = int(hex_part[2] + hex_part[2], 16)
            a = int(hex_part[3] + hex_part[3], 16)
            return (r, g, b, a)
        if len(hex_part) == 6:
            r = int(hex_part[0:2], 16)
            g = int(hex_part[2:4], 16)
            b = int(hex_part[4:6], 16)
            return (r, g, b, 255)
        # len == 8
        r = int(hex_part[0:2], 16)
        g = int(hex_part[2:4], 16)
        b = int(hex_part[4:6], 16)
        a = int(hex_part[6:8], 16)
        return (r, g, b, a)

    @staticmethod
    def _rgb_to_hue_degrees(r: int, g: int, b: int) -> float:
        rf = float(max(0, min(255, int(r)))) / 255.0
        gf = float(max(0, min(255, int(g)))) / 255.0
        bf = float(max(0, min(255, int(b)))) / 255.0
        max_v = max(rf, gf, bf)
        min_v = min(rf, gf, bf)
        delta = max_v - min_v
        if delta <= 1e-9:
            return 0.0

        if max_v == rf:
            hue = 60.0 * (((gf - bf) / delta) % 6.0)
        elif max_v == gf:
            hue = 60.0 * (((bf - rf) / delta) + 2.0)
        else:
            hue = 60.0 * (((rf - gf) / delta) + 4.0)

        if hue < 0.0:
            hue += 360.0
        if hue >= 360.0:
            hue = hue % 360.0
        return float(hue)

