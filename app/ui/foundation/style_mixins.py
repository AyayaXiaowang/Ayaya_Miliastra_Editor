"""Reusable mixin that applies standard theme styles to Qt widgets."""

from PyQt6 import QtWidgets

from app.ui.foundation.theme_manager import ThemeManager, Colors


class StyleMixin:
    """为 Qt 组件提供快捷的主题样式应用方法。

    约定优先级（新代码推荐顺序）：
    - 面板 / 复杂容器：优先使用 `apply_panel_style`
    - 表单/配置对话框：优先使用 `apply_form_dialog_style`
    - 单张卡片：使用 `apply_card_style`
    其他方法主要用于兼容旧代码或少数特殊场景，不建议在新模块中随意扩散。
    """

    def apply_widget_style(self) -> None:
        if isinstance(self, QtWidgets.QWidget):
            self.setStyleSheet(
                f"""
                {type(self).__name__} {{
                    background-color: {ThemeManager.Colors.BG_MAIN};
                }}
                {ThemeManager.button_style()}
                {ThemeManager.input_style()}
                {ThemeManager.combo_box_style()}
                {ThemeManager.spin_box_style()}
                {ThemeManager.tree_style()}
                {ThemeManager.list_style()}
                {ThemeManager.table_style()}
                {ThemeManager.splitter_style()}
                {ThemeManager.scrollbar_style()}
            """
            )

    def apply_dialog_style(self) -> None:
        if isinstance(self, QtWidgets.QDialog):
            self.setStyleSheet(
                f"""
                QDialog {{
                    background-color: {ThemeManager.Colors.BG_CARD};
                }}
                {ThemeManager.button_style()}
                {ThemeManager.input_style()}
                {ThemeManager.combo_box_style()}
                {ThemeManager.spin_box_style()}
                {ThemeManager.scrollbar_style()}
                {ThemeManager.group_box_style()}
            """
            )

    def apply_form_dialog_style(self) -> None:
        if isinstance(self, QtWidgets.QDialog):
            self.setStyleSheet(ThemeManager.dialog_form_style())

    def apply_panel_style(self) -> None:
        if isinstance(self, QtWidgets.QWidget):
            self.setStyleSheet(ThemeManager.panel_style())

    def apply_card_style(self, border_radius: int | None = None) -> None:
        if isinstance(self, QtWidgets.QWidget):
            self.setStyleSheet(ThemeManager.card_style(border_radius))

    def apply_minimal_style(self) -> None:
        if isinstance(self, QtWidgets.QWidget):
            self.setStyleSheet(
                f"""
                {type(self).__name__} {{
                    background-color: {ThemeManager.Colors.BG_CARD};
                }}
            """
            )

    def apply_list_widget_style(self) -> None:
        if isinstance(self, QtWidgets.QWidget):
            self.setStyleSheet(
                f"""
                {type(self).__name__} {{
                    background-color: {ThemeManager.Colors.BG_MAIN};
                }}
                {ThemeManager.button_style()}
                {ThemeManager.input_style()}
                {ThemeManager.tree_style()}
                {ThemeManager.list_style()}
                {ThemeManager.table_style()}
                {ThemeManager.splitter_style()}
                {ThemeManager.scrollbar_style()}
            """
            )

    def apply_management_widget_style(self) -> None:
        if isinstance(self, QtWidgets.QWidget):
            self.setStyleSheet(
                f"""
                {type(self).__name__} {{
                    background-color: {ThemeManager.Colors.BG_MAIN};
                }}
                {ThemeManager.button_style()}
                {ThemeManager.input_style()}
                {ThemeManager.combo_box_style()}
                {ThemeManager.spin_box_style()}
                {ThemeManager.tree_style()}
                {ThemeManager.table_style()}
                {ThemeManager.scrollbar_style()}
            """
            )


