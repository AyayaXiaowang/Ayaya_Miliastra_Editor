"""节点图画布内联控件样式（GraphPalette 固定配色）。

本模块集中提供节点图画布内联控件（QGraphicsProxyWidget 内嵌 QWidget）的 QSS 片段与尺寸常量，
避免在具体控件中重复拼装样式字符串。

注意：
- 画布与节点图图形项使用 `GraphPalette` 固定深色调色板，不随全局 `ThemeManager` 主题切换；
- 本模块仅返回字符串/常量，不直接调用 Qt API。
"""

from __future__ import annotations

from app.ui.graph.graph_palette import GraphPalette

# =========================
# 尺寸常量（像素）
# =========================

# 布尔值下拉框（图内联）
GRAPH_INLINE_BOOL_COMBO_WIDTH_PX = 100
GRAPH_INLINE_BOOL_COMBO_MIN_HEIGHT_PX = 18
GRAPH_INLINE_BOOL_COMBO_HEIGHT_EXTRA_PX = 5  # fontMetrics.height() + extra：紧凑但避免 Win10/DPI 下裁剪
GRAPH_INLINE_BOOL_COMBO_RADIUS_PX = 2
GRAPH_INLINE_BOOL_COMBO_TEXT_PADDING_LEFT_PX = 3
GRAPH_INLINE_BOOL_COMBO_ARROW_RESERVED_PX = 16  # padding-right：为 drop-down/arrow 预留空间
GRAPH_INLINE_BOOL_COMBO_DROP_DOWN_WIDTH_PX = 14
GRAPH_INLINE_BOOL_COMBO_ARROW_MARGIN_RIGHT_PX = 6
GRAPH_INLINE_BOOL_COMBO_ARROW_TRIANGLE_HALF_WIDTH_PX = 4
GRAPH_INLINE_BOOL_COMBO_ARROW_TRIANGLE_HEIGHT_PX = 6

# 三维向量输入（图内联）
GRAPH_INLINE_VECTOR3_CONTAINER_HEIGHT_PX = 20
GRAPH_INLINE_VECTOR3_CONTAINER_WIDTH_PX = 150
GRAPH_INLINE_VECTOR3_CONTAINER_LAYOUT_SPACING_PX = 2
GRAPH_INLINE_VECTOR3_AXIS_LAYOUT_SPACING_PX = 1
GRAPH_INLINE_VECTOR3_LINE_EDIT_WIDTH_PX = 30
GRAPH_INLINE_VECTOR3_LINE_EDIT_MAX_HEIGHT_PX = 16
GRAPH_INLINE_VECTOR3_LINE_EDIT_RADIUS_PX = 2
GRAPH_INLINE_VECTOR3_LINE_EDIT_PADDING_HORIZONTAL_PX = 3
GRAPH_INLINE_VECTOR3_LABEL_FONT_SIZE_PX = 8
GRAPH_INLINE_VECTOR3_LINE_EDIT_FONT_SIZE_PX = 8


# =========================
# QSS 片段
# =========================


def graph_inline_bool_combo_box_style() -> str:
    """节点图内联布尔下拉框样式（是/否）。"""
    return f"""
        QComboBox {{
            background-color: {GraphPalette.INPUT_BG};
            color: {GraphPalette.TEXT_LABEL};
            border: 1px solid {GraphPalette.INPUT_BORDER};
            border-radius: {GRAPH_INLINE_BOOL_COMBO_RADIUS_PX}px;
            /* 紧凑的上下 padding：避免字体基线贴边导致“被裁断”，同时保持整体高度小 */
            padding-top: 1px;
            padding-bottom: 1px;
            padding-left: {GRAPH_INLINE_BOOL_COMBO_TEXT_PADDING_LEFT_PX}px;
            padding-right: {GRAPH_INLINE_BOOL_COMBO_ARROW_RESERVED_PX}px;  /* 给 drop-down/arrow 预留空间，避免裁剪 */
        }}
        QComboBox:hover {{
            border: 1px solid {GraphPalette.INPUT_BORDER_HOVER};
        }}
        QComboBox::drop-down {{
            border: none;
            width: {GRAPH_INLINE_BOOL_COMBO_DROP_DOWN_WIDTH_PX}px;
            subcontrol-origin: padding;
            subcontrol-position: center right;
        }}
        QComboBox::down-arrow {{
            /* 用 QSS 画稳定的三角形：必须显式声明 width/height，否则在部分样式/DPI 下会退化成方块 */
            width: 0px;
            height: 0px;
            image: none;
            border-left: {GRAPH_INLINE_BOOL_COMBO_ARROW_TRIANGLE_HALF_WIDTH_PX}px solid transparent;
            border-right: {GRAPH_INLINE_BOOL_COMBO_ARROW_TRIANGLE_HALF_WIDTH_PX}px solid transparent;
            border-top: {GRAPH_INLINE_BOOL_COMBO_ARROW_TRIANGLE_HEIGHT_PX}px solid {GraphPalette.TEXT_LABEL};
            margin-right: {GRAPH_INLINE_BOOL_COMBO_ARROW_MARGIN_RIGHT_PX}px;
        }}
    """


def graph_inline_vector3_container_style() -> str:
    """节点图内联三维向量输入容器样式（X/Y/Z 三轴输入）。"""
    return f"""
        QWidget {{
            background-color: transparent;
        }}
        QLabel {{
            color: {GraphPalette.TEXT_SECONDARY};
            font-size: {GRAPH_INLINE_VECTOR3_LABEL_FONT_SIZE_PX}px;
        }}
        QLineEdit {{
            background-color: {GraphPalette.INPUT_BG};
            color: {GraphPalette.TEXT_LABEL};
            border: 1px solid {GraphPalette.INPUT_BORDER};
            border-radius: {GRAPH_INLINE_VECTOR3_LINE_EDIT_RADIUS_PX}px;
            padding: 0px {GRAPH_INLINE_VECTOR3_LINE_EDIT_PADDING_HORIZONTAL_PX}px;
            font-size: {GRAPH_INLINE_VECTOR3_LINE_EDIT_FONT_SIZE_PX}px;
            max-height: {GRAPH_INLINE_VECTOR3_LINE_EDIT_MAX_HEIGHT_PX}px;
        }}
        QLineEdit:focus {{
            border: 1px solid {GraphPalette.INPUT_BORDER_HOVER};
        }}
    """


