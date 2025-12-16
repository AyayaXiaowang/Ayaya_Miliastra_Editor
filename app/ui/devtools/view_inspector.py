"""轻量级 UI 检查器：悬停高亮控件并显示名称（开发调试用）。

本模块不关心业务语义，仅提供一个基于鼠标悬停的视图检查工具：
- 在主窗口内移动鼠标时，高亮当前命中的控件矩形；
- 在鼠标附近展示控件的 Qt 类名与 objectName，辅助定位布局与对象树。

集成方式（示例）：
    inspector = WidgetHoverInspector(main_window)
    inspector.set_enabled(True)   # 开启检查器
    inspector.set_enabled(False)  # 关闭检查器

建议仅在开发环境或显式开启的“开发者模式”下使用（例如通过 F12 开关）。
"""

from __future__ import annotations

from typing import Optional

from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.foundation.theme.tokens.colors import Colors
from app.ui.panels.config_component_registry import find_config_component


class WidgetHoverInspector(QtCore.QObject):
    """悬停控件检查器。

    - 仅在指定主窗口内部生效；
    - 使用 QRubberBand 高亮当前控件边界；
    - 使用悬浮 QLabel 展示控件的类名与 objectName。
    """

    def __init__(self, main_window: QtWidgets.QMainWindow) -> None:
        super().__init__(main_window)
        self._main_window = main_window
        self._enabled = False

        # 当前被“选中/锁定”的控件（用于高亮与信息展示）
        self._current_widget: Optional[QtWidgets.QWidget] = None
        self._selection_locked: bool = False

        # 高亮矩形（覆盖在主窗口上）
        self._highlight_band = QtWidgets.QRubberBand(
            QtWidgets.QRubberBand.Shape.Rectangle,
            self._main_window,
        )
        self._highlight_band.hide()

        # 信息标签（显示当前选中控件的调试信息，可选中与右键复制全部文本）
        self._info_label = QtWidgets.QLabel(self._main_window)
        self._info_label.setObjectName("widgetHoverInspectorLabel")
        self._info_label.setStyleSheet(
            f"""
            QLabel#widgetHoverInspectorLabel {{
                background-color: {Colors.BG_DARK};
                color: {Colors.TEXT_ON_PRIMARY};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }}
            """
        )
        self._info_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
            | QtCore.Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._info_label.hide()

        self._info_label.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self._info_label.customContextMenuRequested.connect(self._on_info_label_context_menu)

    def set_enabled(self, enabled: bool) -> None:
        """开启或关闭检查器。

        开启时在 QApplication 上安装事件过滤器；关闭时移除并清理叠加层。
        """
        if self._enabled == enabled:
            return

        self._enabled = enabled
        application = QtWidgets.QApplication.instance()
        if application is None:
            return

        if enabled:
            application.installEventFilter(self)
        else:
            application.removeEventFilter(self)
            self._clear_overlay()

    def is_enabled(self) -> bool:
        """当前是否处于启用状态。"""
        return self._enabled

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        """拦截全局鼠标事件，用于更新高亮与信息标签。"""
        if not self._enabled:
            return False

        if event.type() == QtCore.QEvent.Type.MouseMove:
            self._handle_mouse_move()
        elif event.type() == QtCore.QEvent.Type.MouseButtonPress:
            mouse_event = event  # type: ignore[assignment]
            self._handle_mouse_press(mouse_event)

        return False

    def _handle_mouse_move(self) -> None:
        application = QtWidgets.QApplication.instance()
        if application is None:
            return

        # 若当前已锁定选中控件，则忽略鼠标移动（允许用户移动到右上角信息条进行右键操作）
        if self._selection_locked:
            return

        global_position = QtGui.QCursor.pos()
        widget_at_cursor = application.widgetAt(global_position)

        if widget_at_cursor is None:
            self._clear_overlay()
            return

        # 仅在当前主窗口内部高亮，避免干扰其它窗口或对话框
        if widget_at_cursor.window() is not self._main_window:
            self._clear_overlay()
            return

        # 避免自身控件触发递归高亮
        if widget_at_cursor is self._info_label or widget_at_cursor is self._highlight_band:
            return

        if widget_at_cursor is self._current_widget:
            self._update_label_position(global_position)
            return

        self._current_widget = widget_at_cursor
        self._update_overlay_for_widget(widget_at_cursor, global_position)

    def _handle_mouse_press(self, mouse_event: QtCore.QEvent) -> None:
        """处理鼠标按下事件：左键点击某个控件时锁定当前选中目标。"""
        if not isinstance(mouse_event, QtGui.QMouseEvent):
            return

        if mouse_event.button() != QtCore.Qt.MouseButton.LeftButton:
            return

        application = QtWidgets.QApplication.instance()
        if application is None:
            return

        global_position = mouse_event.globalPosition().toPoint()
        widget_at_cursor = application.widgetAt(global_position)
        if widget_at_cursor is None:
            return

        if widget_at_cursor.window() is not self._main_window:
            return

        if widget_at_cursor is self._info_label or widget_at_cursor is self._highlight_band:
            return

        self._selection_locked = True
        self._current_widget = widget_at_cursor
        self._update_overlay_for_widget(widget_at_cursor, global_position)

    def _update_overlay_for_widget(
        self,
        target_widget: QtWidgets.QWidget,
        global_position: QtCore.QPoint,
    ) -> None:
        """根据命中的控件更新高亮矩形和信息标签。"""
        top_left_in_main = target_widget.mapTo(self._main_window, QtCore.QPoint(0, 0))
        target_geometry = QtCore.QRect(top_left_in_main, target_widget.size())

        self._highlight_band.setGeometry(target_geometry)
        self._highlight_band.show()

        overlay_text = self._build_overlay_text(target_widget)
        self._info_label.setText(overlay_text)
        self._info_label.adjustSize()

        self._update_label_position(global_position)
        self._info_label.show()
        self._info_label.raise_()

    def _update_label_position(self, global_position: QtCore.QPoint) -> None:
        """在主窗口右上角放置信息标签（固定位置，便于右键操作）。"""
        del global_position
        label_width = self._info_label.width()
        label_height = self._info_label.height()

        x_position = self._main_window.width() - label_width - 16
        y_position = 16

        if x_position < 8:
            x_position = 8
        if y_position < 8:
            y_position = 8

        self._info_label.move(x_position, y_position)

    def _clear_overlay(self) -> None:
        """隐藏当前高亮与信息标签。"""
        self._current_widget = None
        self._selection_locked = False
        self._highlight_band.hide()
        self._info_label.hide()

    def _on_info_label_context_menu(self, position: QtCore.QPoint) -> None:
        """在信息标签上右键：直接复制当前标签全部文本到剪贴板。"""
        del position
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(self._info_label.text())

    def _build_debug_summary(
        self,
        class_name: str,
        object_name: str,
        full_class_path: str,
        module_file_path: str,
    ) -> str:
        """构造一段可复制的调试摘要文本。"""
        object_line = "objectName: <empty>"
        if object_name:
            object_line = f"objectName: {object_name}"

        module_line = "module file: <unknown>"
        if module_file_path:
            module_line = f"module file: {module_file_path}"

        lines = [
            f"class: {class_name}",
            f"full class: {full_class_path}",
            object_line,
            module_line,
        ]
        return "\n".join(lines)

    def _build_overlay_text(self, widget: QtWidgets.QWidget) -> str:
        """构造信息标签中展示的多行摘要文本（带简单标题与源码归属信息）。"""
        qt_class_name = widget.metaObject().className()
        object_name = widget.objectName()
        display_object = object_name or "<no objectName>"

        python_class_name = type(widget).__name__
        python_module_name = type(widget).__module__

        owner_widget = self._find_owner_widget(widget)
        owner_line = ""
        source_file_line = ""

        if owner_widget is not None:
            owner_class_name = type(owner_widget).__name__
            owner_module_name = type(owner_widget).__module__
            module_file_path = self._guess_source_file_from_module(type(owner_widget))
            if owner_widget is widget:
                owner_line = f"owner: self ({owner_class_name}, {owner_module_name})"
            else:
                owner_line = f"owner: {owner_class_name} ({owner_module_name})"
            if module_file_path:
                source_file_line = f"source file: {module_file_path}"
            else:
                source_file_line = "source file: <Qt 内置或未知模块>"
        else:
            module_file_path = self._guess_source_file_from_module(type(widget))
            if module_file_path:
                source_file_line = f"source file: {module_file_path}"
            else:
                source_file_line = "source file: <Qt 内置或未知模块>"

        layout = widget.layout()
        if layout is not None:
            layout_name = type(layout).__name__
        else:
            layout_name = "<no layout>"

        size = widget.size()
        size_text = f"{size.width()}x{size.height()}"

        hierarchy = self._build_widget_hierarchy_path(widget)

        panel_title_line = self._get_panel_title_line(owner_widget)
        tab_context_line = self._get_tab_context_line(widget)
        config_component_line = self._get_config_component_line(owner_widget, widget)

        lines = [
            "[UI 检查器] 当前控件调试信息",
            f"Qt: {qt_class_name}  ({display_object})",
            f"Python: {python_class_name}  ({python_module_name})",
            source_file_line,
        ]
        if owner_line:
            lines.append(owner_line)
        if panel_title_line:
            lines.append(panel_title_line)
        if tab_context_line:
            lines.append(tab_context_line)
        if config_component_line:
            lines.append(config_component_line)
        lines.append(f"layout: {layout_name}   size: {size_text}")
        lines.append(f"path: {hierarchy}")
        return "\n".join(lines)

    def _build_widget_hierarchy_path(self, widget: QtWidgets.QWidget) -> str:
        """构造从主窗口到当前控件的简化层级路径（最多若干级）。"""
        parts: list[str] = []
        current: Optional[QtWidgets.QWidget] = widget

        # 限制最大层级深度，避免路径过长
        max_depth = 6
        depth = 0

        while current is not None and current is not self._main_window and depth < max_depth:
            name = current.objectName()
            if name:
                label = name
            else:
                label = current.metaObject().className()
            parts.append(label)

            parent = current.parent()
            if isinstance(parent, QtWidgets.QWidget):
                current = parent
            else:
                current = None

            depth += 1

        parts.append("MainWindow")
        parts.reverse()
        return " / ".join(parts)

    def _get_config_component_line(
        self,
        owner_widget: Optional[QtWidgets.QWidget],
        target_widget: QtWidgets.QWidget,
    ) -> str:
        """若当前控件位于已注册的配置组件分组中，返回对应的配置组件 ID 行。

        仅针对右侧属性栏中的 QGroupBox 分组块（例如玩家模板的“生效目标”“基础”“复苏”等）
        和技能面板的“基础信息/基础设置/连段配置/数值配置/生命周期管理”分组。
        """
        if owner_widget is None:
            return ""

        panel_class_name = type(owner_widget).__name__

        group_box = target_widget
        if not isinstance(group_box, QtWidgets.QGroupBox):
            parent = target_widget.parent()
            if isinstance(parent, QtWidgets.QGroupBox):
                group_box = parent
            else:
                return ""

        title = group_box.title()
        if not title:
            return ""

        definition = find_config_component(panel_class_name, title)
        if definition is None:
            return ""

        return f"config component: {definition.id} ({title})"

    def _guess_source_file_from_module(self, widget_class: type[QtCore.QObject]) -> str:
        """根据类的模块名推断工程内的源码文件路径（相对路径字符串）。

        规则：
        - ui.*       → app/ui/...
        - app.*      → app/...
        - engine.*   → engine/...
        其它模块返回空字符串，表示未知。
        """
        module_name = widget_class.__module__
        if module_name.startswith("ui."):
            components = module_name.split(".")[1:]
            relative_path = Path("app") / "ui" / Path("/".join(components) + ".py")
            return str(relative_path.as_posix())
        if module_name.startswith("app."):
            components = module_name.split(".")[1:]
            relative_path = Path("app") / Path("/".join(components) + ".py")
            return str(relative_path.as_posix())
        if module_name.startswith("engine."):
            components = module_name.split(".")[1:]
            relative_path = Path("engine") / Path("/".join(components) + ".py")
            return str(relative_path.as_posix())
        return ""

    def _find_owner_widget(self, widget: QtWidgets.QWidget) -> Optional[QtWidgets.QWidget]:
        """寻找源码归属控件：

        返回当前控件或其父链上，第一个模块名以 ui./app./engine. 开头的控件，
        便于根据模块名与文件路径快速跳转到相关源码（如自定义面板类或主容器）。
        """
        current: Optional[QtWidgets.QWidget] = widget
        while current is not None:
            module_name = type(current).__module__
            if (
                module_name.startswith("ui.")
                or module_name.startswith("app.")
                or module_name.startswith("engine.")
            ):
                return current
            parent = current.parent()
            if isinstance(parent, QtWidgets.QWidget):
                current = parent
            else:
                current = None
        return None

    def _get_panel_title_line(self, owner_widget: Optional[QtWidgets.QWidget]) -> str:
        """若 owner 是右侧 PanelScaffold 子类，尝试读取其标题文本。"""
        if owner_widget is None:
            return ""
        title_label = getattr(owner_widget, "title_label", None)
        if isinstance(title_label, QtWidgets.QLabel):
            title_text = title_label.text().strip()
            if title_text:
                return f"panel title: {title_text}"
        return ""

    def _get_tab_context_line(self, widget: QtWidgets.QWidget) -> str:
        """查找最近的 QTabWidget，并给出所属标签页文本与索引。"""
        current: Optional[QtWidgets.QWidget] = widget
        tab_widget: Optional[QtWidgets.QTabWidget] = None
        page_widget: Optional[QtWidgets.QWidget] = None

        while current is not None and current is not self._main_window:
            parent = current.parent()
            if isinstance(parent, QtWidgets.QTabWidget):
                tab_widget = parent
                page_widget = current
                break
            if isinstance(parent, QtWidgets.QWidget):
                current = parent
            else:
                current = None

        if tab_widget is None or page_widget is None:
            return ""

        index = tab_widget.indexOf(page_widget)
        if index < 0:
            for i in range(tab_widget.count()):
                candidate = tab_widget.widget(i)
                if candidate is not None and candidate.isAncestorOf(widget):
                    page_widget = candidate
                    index = i
                    break

        tab_name = tab_widget.objectName() or "<unnamed tab widget>"
        if index < 0:
            return f"tab: {tab_name} (index: <unknown>)"

        tab_text = tab_widget.tabText(index) or "<no tab text>"
        return f"tab: {tab_name} -> \"{tab_text}\" (index {index})"


