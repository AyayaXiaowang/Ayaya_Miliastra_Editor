"""全局主题管理器：聚合 token、样式工厂与缓存。

本模块负责：
- 通过 `ThemeRegistry` 暴露 Colors/Sizes/Icons/Gradients token
- 将 `theme.styles` 中的组件/组合样式函数做统一缓存
- 提供应用级别样式注入与常用 QSS 片段入口
- 转发画布网格绘制与 HTML 模板（实现位于独立模块）
"""

from __future__ import annotations

from typing import Callable, cast

from PyQt6 import QtCore, QtGui, QtWidgets

from ui.foundation.canvas_background import draw_grid_background as _draw_grid_background
from ui.foundation.theme import ThemeRegistry
from ui.foundation.theme.styles import (
    component_styles,
    composite_styles,
    semantic_styles,
    html_templates,
)

Colors = ThemeRegistry.colors
Sizes = ThemeRegistry.sizes
Icons = ThemeRegistry.icons
Gradients = ThemeRegistry.gradients
HTMLStyles = html_templates.HTMLStyles


class ThemeManager:
    """协调主题 token 与样式工厂的单例式入口。"""

    Colors = Colors
    Sizes = Sizes
    Icons = Icons
    Gradients = Gradients
    HTMLStyles = HTMLStyles

    _style_cache: dict[str, str] = {}

    @classmethod
    def _cached(cls, key: str, factory: Callable[[], str]) -> str:
        cached = cls._style_cache.get(key)
        if cached is None:
            cached = factory()
            cls._style_cache[key] = cached
        return cached

    # ========= 渐变 =========

    @staticmethod
    def gradient_primary() -> str:
        return Gradients.primary_horizontal()

    @staticmethod
    def gradient_primary_vertical() -> str:
        return Gradients.primary_vertical()

    @staticmethod
    def gradient_card() -> str:
        return Gradients.card()

    @staticmethod
    def gradient_badge() -> str:
        return Gradients.badge()

    @staticmethod
    def gradient_button() -> str:
        return Gradients.button()

    # ========= 原子样式 =========

    @classmethod
    def card_style(cls, border_radius: int | None = None) -> str:
        key = f"card::{border_radius if border_radius is not None else 'default'}"
        return cls._cached(key, lambda: component_styles.card_style(border_radius))

    @classmethod
    def button_style(cls) -> str:
        return cls._cached("button", component_styles.button_style)

    @classmethod
    def input_style(cls) -> str:
        return cls._cached("input", component_styles.input_style)

    @classmethod
    def tree_style(cls) -> str:
        return cls._cached("tree", component_styles.tree_style)

    @classmethod
    def list_style(cls) -> str:
        return cls._cached("list", component_styles.list_style)

    @classmethod
    def left_panel_style(cls) -> str:
        return cls._cached("left_panel", component_styles.left_panel_style)

    @classmethod
    def table_style(cls) -> str:
        return cls._cached("table", component_styles.table_style)

    @classmethod
    def scrollbar_style(cls) -> str:
        return cls._cached("scrollbar", component_styles.scrollbar_style)

    @classmethod
    def tab_style(cls) -> str:
        return cls._cached("tab", component_styles.tab_style)

    @classmethod
    def right_side_tab_style(cls) -> str:
        return cls._cached("right_side_tab", component_styles.right_side_tab_style)

    @classmethod
    def splitter_style(cls) -> str:
        return cls._cached("splitter", component_styles.splitter_style)

    @classmethod
    def combo_box_style(cls) -> str:
        return cls._cached("combo_box", component_styles.combo_box_style)

    @classmethod
    def spin_box_style(cls) -> str:
        return cls._cached("spin_box", component_styles.spin_box_style)

    @classmethod
    def group_box_style(cls) -> str:
        return cls._cached("group_box", component_styles.group_box_style)

    @classmethod
    def dialog_style(cls) -> str:
        return cls._cached("dialog", component_styles.dialog_style)

    @classmethod
    def navigation_button_style(cls) -> str:
        """左侧导航按钮的专用样式。"""
        return cls._cached("navigation_button", component_styles.navigation_button_style)

    @classmethod
    def toast_style(cls) -> str:
        """Toast 内容卡片样式。"""
        return cls._cached("toast", component_styles.toast_content_style)

    # ========= 组合样式 =========

    @classmethod
    def dialog_surface_style(
        cls,
        *,
        include_inputs: bool = True,
        include_tables: bool = False,
        include_scrollbars: bool = True,
    ) -> str:
        key = f"dialog_surface::{include_inputs}-{include_tables}-{include_scrollbars}"
        return cls._cached(
            key,
            lambda: composite_styles.dialog_surface_style(
                include_inputs=include_inputs,
                include_tables=include_tables,
                include_scrollbars=include_scrollbars,
            ),
        )

    @classmethod
    def dialog_form_style(cls) -> str:
        return cls._cached("dialog_form", composite_styles.dialog_form_style)

    @classmethod
    def card_list_style(cls) -> str:
        return cls._cached("card_list", composite_styles.card_list_style)

    @classmethod
    def panel_style(cls) -> str:
        return cls._cached("panel", composite_styles.panel_style)

    @classmethod
    def global_style(cls) -> str:
        return cls._cached("global", composite_styles.global_style)

    # ========= 语义与文本 =========

    @classmethod
    def context_menu_style(cls) -> str:
        return cls._cached("context_menu", component_styles.context_menu_style)

    @classmethod
    def heading(cls, level: int = 3) -> str:
        key = f"heading::{level}"
        return cls._cached(key, lambda: semantic_styles.heading(level))

    @classmethod
    def semantic_success(cls, font_size: int | None = None) -> str:
        key = f"semantic_success::{font_size or 'default'}"
        return cls._cached(key, lambda: semantic_styles.semantic_success(font_size))

    @classmethod
    def semantic_error(cls, font_size: int | None = None) -> str:
        key = f"semantic_error::{font_size or 'default'}"
        return cls._cached(key, lambda: semantic_styles.semantic_error(font_size))

    @classmethod
    def info_label_style(cls) -> str:
        return cls._cached("info_label", component_styles.info_label_style)

    @classmethod
    def info_label_simple_style(cls) -> str:
        return cls._cached("info_label_simple", component_styles.info_label_simple_style)

    @classmethod
    def info_label_dark_style(cls) -> str:
        return cls._cached("info_label_dark", component_styles.info_label_dark_style)

    @classmethod
    def readonly_input_style(cls) -> str:
        return cls._cached("readonly_input", component_styles.readonly_input_style)

    @classmethod
    def hint_text_style(cls) -> str:
        return cls._cached("hint_text", component_styles.hint_text_style)

    @classmethod
    def subtle_info_style(cls) -> str:
        return cls._cached("subtle_info", component_styles.subtle_info_style)

    # ========= 应用入口 =========

    @classmethod
    def apply_app_style(cls, app: QtWidgets.QApplication) -> None:
        app.setFont(QtGui.QFont("Microsoft YaHei UI", Sizes.FONT_NORMAL))
        app.setStyleSheet(cls.global_style())

        class WheelGuardFilter(QtCore.QObject):
            """
            全局滚轮防误触过滤器：
            - 禁止通过滚轮切换 Tab（QTabBar）
            - 下拉框：仅在弹出列表已展开时允许滚轮更改选项；未展开时将滚轮交给外层可滚动容器
            - 数值框：完全禁止通过滚轮更改数值，始终将滚轮交给外层可滚动容器
            """

            def _redirect_wheel_to_scroll_parent(
                self,
                source: QtCore.QObject,
                event: QtGui.QWheelEvent,
            ) -> None:
                """将滚轮事件转发给最近的 QAbstractScrollArea，使页面/表格仍可滚动。"""
                if not isinstance(source, QtWidgets.QWidget):
                    return

                scroll_parent: QtWidgets.QAbstractScrollArea | None = None
                obj: QtCore.QObject | None = source
                while obj is not None:
                    if isinstance(obj, QtWidgets.QAbstractScrollArea):
                        scroll_parent = obj
                        break
                    obj = obj.parent()

                if scroll_parent is None:
                    return

                viewport = scroll_parent.viewport()
                target: QtWidgets.QWidget = viewport if viewport is not None else scroll_parent

                global_pos_f = event.globalPosition()
                global_point = QtCore.QPoint(int(global_pos_f.x()), int(global_pos_f.y()))
                local_pos = target.mapFromGlobal(global_point)

                redirected_event = QtGui.QWheelEvent(
                    QtCore.QPointF(local_pos),
                    global_pos_f,
                    event.pixelDelta(),
                    event.angleDelta(),
                    event.buttons(),
                    event.modifiers(),
                    event.phase(),
                    event.inverted(),
                )
                QtWidgets.QApplication.sendEvent(target, redirected_event)

            def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
                if event.type() is not QtCore.QEvent.Type.Wheel:
                    return False
                wheel_event = cast(QtGui.QWheelEvent, event)

                # 1) TabBar：禁止任何滚轮切换标签
                obj: QtCore.QObject | None = watched
                while obj is not None:
                    if isinstance(obj, QtWidgets.QTabBar):
                        return True
                    obj = obj.parent()

                # 2) 下拉框：仅在下拉列表展开时允许滚轮
                combo: QtWidgets.QComboBox | None = None
                obj = watched
                while obj is not None:
                    if isinstance(obj, QtWidgets.QComboBox):
                        combo = obj
                        break
                    obj = obj.parent()
                if combo is not None:
                    view = combo.view()
                    if view is None or not view.isVisible():
                        # 未展开下拉列表时，不让下拉框改变选项，但将滚轮交给外层可滚动容器
                        self._redirect_wheel_to_scroll_parent(watched, wheel_event)
                        return True
                    return False

                # 3) 数值框（QAbstractSpinBox 及子类）：不允许通过滚轮调整数值
                spin: QtWidgets.QAbstractSpinBox | None = None
                obj = watched
                while obj is not None:
                    if isinstance(obj, QtWidgets.QAbstractSpinBox):
                        spin = obj
                        break
                    obj = obj.parent()
                if spin is not None:
                    # 数值框无论是否获得焦点，都不响应滚轮，将滚轮交给外层可滚动容器
                    self._redirect_wheel_to_scroll_parent(watched, wheel_event)
                    return True

                return False

        wheel_guard_filter = WheelGuardFilter(app)
        app._wheel_guard_filter = wheel_guard_filter  # type: ignore[attr-defined]
        app.installEventFilter(wheel_guard_filter)

    @staticmethod
    def draw_grid_background(painter, rect, grid_size: int = 50) -> None:
        _draw_grid_background(painter, rect, grid_size)


