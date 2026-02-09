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
    def ensure_search_button(view: "GraphView") -> QtWidgets.QPushButton:
        """确保“画布搜索”按钮存在并配置好样式。"""
        if hasattr(view, "search_button") and view.search_button:
            return view.search_button

        button = QtWidgets.QPushButton("🔍 搜索", view)
        button.setToolTip("打开画布内搜索（Ctrl+F）")
        button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {GraphPalette.INPUT_BG};
                color: {GraphPalette.TEXT_LABEL};
                border: 1px solid {GraphPalette.BORDER_SUBTLE};
                border-radius: 4px;
                padding: 8px 12px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {GraphPalette.GRID_BOLD};
                border-color: {GraphPalette.INPUT_BORDER_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {GraphPalette.BORDER_MUTED};
            }}
            QPushButton:disabled {{
                background-color: {GraphPalette.BTN_DISABLED_BG};
                color: {GraphPalette.BTN_DISABLED_TEXT};
                border-color: {GraphPalette.BTN_DISABLED_BG};
            }}
        """
        )
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        button.raise_()

        view.search_button = button
        return button
    
    @staticmethod
    def update_position(view: "GraphView") -> None:
        """更新右上角浮动控件位置（主按钮 + 扩展按钮 + 自动排版 + 搜索）。"""
        margin = 10
        spacing = 8

        current_right = view.width() - margin
        y = margin

        # 1) 主按钮（Host 级，最右侧）：例如预览页“编辑”、编辑器“前往执行”
        if hasattr(view, 'extra_top_right_button') and view.extra_top_right_button and view.extra_top_right_button.isVisible():
            extra_w = view.extra_top_right_button.sizeHint().width()
            extra_x = current_right - extra_w
            view.extra_top_right_button.move(extra_x, y)
            current_right = extra_x - spacing

        # 2) 扩展按钮（插件注入，位于主按钮与自动排版之间）
        extension_widgets = getattr(view, "extra_top_right_extension_widgets", None)
        if isinstance(extension_widgets, list) and extension_widgets:
            for widget in extension_widgets:
                if widget is None:
                    continue
                if not widget.isVisible():
                    continue
                w = widget.sizeHint().width()
                x = current_right - w
                widget.move(x, y)
                current_right = x - spacing

        # 再放置自动排版按钮（若可见）
        if hasattr(view, 'auto_layout_button') and view.auto_layout_button and view.auto_layout_button.isVisible():
            button_w = view.auto_layout_button.sizeHint().width()
            button_x = current_right - button_w
            view.auto_layout_button.move(button_x, y)
            current_right = button_x - spacing

        # 最后放置搜索按钮（默认常驻，位于自动排版按钮左侧）
        if hasattr(view, "search_button") and view.search_button and view.search_button.isVisible():
            search_w = view.search_button.sizeHint().width()
            search_x = current_right - search_w
            view.search_button.move(search_x, y)
    
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
    def ensure_extension_widget_list(view: "GraphView") -> list[QtWidgets.QWidget]:
        widgets = getattr(view, "extra_top_right_extension_widgets", None)
        if isinstance(widgets, list):
            return widgets
        widgets = []
        setattr(view, "extra_top_right_extension_widgets", widgets)
        return widgets

    @staticmethod
    def add_extension_widget(view: "GraphView", widget: QtWidgets.QWidget) -> None:
        """追加一个扩展控件（插件注入），并立即定位。"""
        widgets = TopRightControlsManager.ensure_extension_widget_list(view)
        if widget not in widgets:
            widgets.append(widget)
        if widget.parent() is not view:
            widget.setParent(view)
        widget.raise_()
        TopRightControlsManager.update_position(view)

    @staticmethod
    def set_extension_widgets_visible(view: "GraphView", visible: bool) -> None:
        """统一切换扩展控件的可见性（例如 TODO 预览借用画布时隐藏）。"""
        widgets = getattr(view, "extra_top_right_extension_widgets", None)
        if not isinstance(widgets, list) or not widgets:
            return
        for widget in widgets:
            if widget is None:
                continue
            widget.setVisible(bool(visible))
        TopRightControlsManager.update_position(view)
    
    @staticmethod
    def raise_all(view: "GraphView") -> None:
        """将所有控件提升到最上层"""
        if hasattr(view, 'auto_layout_button') and view.auto_layout_button:
            view.auto_layout_button.raise_()
        if hasattr(view, "search_button") and view.search_button:
            view.search_button.raise_()
        extension_widgets = getattr(view, "extra_top_right_extension_widgets", None)
        if isinstance(extension_widgets, list) and extension_widgets:
            for widget in extension_widgets:
                if widget is not None:
                    widget.raise_()
        if hasattr(view, 'extra_top_right_button') and view.extra_top_right_button:
            view.extra_top_right_button.raise_()

