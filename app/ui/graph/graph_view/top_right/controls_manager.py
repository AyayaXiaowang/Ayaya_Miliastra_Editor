"""右上角控件管理器

负责管理视图右上角的浮动按钮（自动排版按钮 + 可选额外按钮）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PyQt6 import QtWidgets, QtCore
from app.ui.graph.graph_palette import GraphPalette

if TYPE_CHECKING:
    from app.ui.graph.graph_view import GraphView


class TopRightControlsManager:
    """右上角控件管理器
    
    负责创建、定位和管理右上角浮动按钮。
    """
    
    @staticmethod
    def ensure_auto_layout_button(view: "GraphView") -> QtWidgets.QPushButton:
        """确保自动排版按钮存在并配置好样式
        
        Returns:
            自动排版按钮实例
        """
        if hasattr(view, 'auto_layout_button') and view.auto_layout_button:
            return view.auto_layout_button
        
        # 创建自动排版按钮（浮动在右上角）
        button = QtWidgets.QPushButton("⚡ 自动排版", view)
        button.setToolTip("根据节点依赖关系自动重新排列节点位置\n（仅在节点图无错误时可用）")
        button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {GraphPalette.BTN_PRIMARY};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {GraphPalette.BTN_PRIMARY_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {GraphPalette.BTN_PRIMARY_PRESSED};
            }}
            QPushButton:disabled {{
                background-color: {GraphPalette.BTN_DISABLED_BG};
                color: {GraphPalette.BTN_DISABLED_TEXT};
            }}
        """
        )
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        button.raise_()  # 确保按钮在最上层
        
        view.auto_layout_button = button
        return button
    
    @staticmethod
    def update_position(view: "GraphView") -> None:
        """更新右上角浮动控件位置（自动排版按钮 + 可选额外按钮）"""
        margin = 10
        spacing = 8

        current_right = view.width() - margin
        y = margin

        # 优先放置额外按钮在最右侧（如预览页的"编辑"）
        if hasattr(view, 'extra_top_right_button') and view.extra_top_right_button and view.extra_top_right_button.isVisible():
            extra_w = view.extra_top_right_button.sizeHint().width()
            extra_x = current_right - extra_w
            view.extra_top_right_button.move(extra_x, y)
            current_right = extra_x - spacing

        # 再放置自动排版按钮（若可见）
        if hasattr(view, 'auto_layout_button') and view.auto_layout_button and view.auto_layout_button.isVisible():
            button_w = view.auto_layout_button.sizeHint().width()
            button_x = current_right - button_w
            view.auto_layout_button.move(button_x, y)
    
    @staticmethod
    def set_extra_button(view: "GraphView", widget: QtWidgets.QWidget) -> None:
        """设置右上角的额外操作按钮，并立即定位。
        
        提示：按钮应以本视图为父控件，避免覆盖顺序问题。
        """
        view.extra_top_right_button = widget
        if widget.parent() is not view:
            widget.setParent(view)
        widget.raise_()
        TopRightControlsManager.update_position(view)
    
    @staticmethod
    def raise_all(view: "GraphView") -> None:
        """将所有控件提升到最上层"""
        if hasattr(view, 'auto_layout_button') and view.auto_layout_button:
            view.auto_layout_button.raise_()
        if hasattr(view, 'extra_top_right_button') and view.extra_top_right_button:
            view.extra_top_right_button.raise_()

