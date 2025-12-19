# -*- coding: utf-8 -*-
"""
editor_capture 模块的子包
将原有的超大文件拆分为多个职责清晰的子模块
"""

# 从各子模块导出公共接口
from .dpi_awareness import ensure_dpi_awareness_once, set_dpi_awareness
from .roi_config import (
    REGIONS_CONFIG,
    get_region_rect,
    get_region_center,
    clip_to_graph_region,
    clip_to_image_bounds,
)
from .roi_constraints import resolve_search_region, clip_region_with_graph
from .cache import (
    set_enforce_graph_roi,
    reset_capture_state,
    enforce_graph_roi_context,
    disable_graph_roi_context,
)
from .screen_capture import (
    capture_client_image,
    capture_window,
    capture_window_strict,
    capture_full_screen,
    capture_region,
    capture_screen_region,
    get_region_image
)
from .ocr import ocr_recognize_region, get_ocr_engine
from .color_scanner import find_color_rectangles, prepare_color_scan_image
from .template_matcher import match_template
from .mouse_ops import (
    click_left_button,
    click_right_button,
    drag_left_button,
    drag_right_button,
    get_cursor_pos
)
from .utils import (
    get_window_rect,
    input_text,
    input_text_via_clipboard,
    get_chinese_font
)

__all__ = [
    # DPI感知
    'ensure_dpi_awareness_once',
    'set_dpi_awareness',
    # 区域配置
    'REGIONS_CONFIG',
    'get_region_rect',
    'get_region_center',
    'clip_to_graph_region',
    'clip_to_image_bounds',
    'resolve_search_region',
    'clip_region_with_graph',
    # 缓存控制
    'set_enforce_graph_roi',
    'reset_capture_state',
    'enforce_graph_roi_context',
    'disable_graph_roi_context',
    # 截图
    'capture_client_image',
    'capture_window',
    'capture_window_strict',
    'capture_full_screen',
    'capture_region',
    'capture_screen_region',
    'get_region_image',
    # OCR
    'ocr_recognize_region',
    'get_ocr_engine',
    # 颜色扫描
    'find_color_rectangles',
    'prepare_color_scan_image',
    # 模板匹配
    'match_template',
    # 鼠标操作
    'click_left_button',
    'click_right_button',
    'drag_left_button',
    'drag_right_button',
    'get_cursor_pos',
    # 工具函数
    'get_window_rect',
    'input_text',
    'input_text_via_clipboard',
    'get_chinese_font',
]

