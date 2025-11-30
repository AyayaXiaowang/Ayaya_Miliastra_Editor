"""
界面控件组管理器 - 主界面
包含界面布局管理和界面控件组库两个 Tab。
"""

from enum import Enum
from typing import Optional, Union

from PyQt6 import QtCore, QtWidgets

from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_view import PackageView
from ui.foundation.dialog_utils import show_warning_dialog
from ui.foundation.ui_preview_canvas import UIPreviewCanvas
from ui.panels.ui_control_group_layout_panel import UILayoutPanel
from ui.panels.ui_control_group_template_panel import UITemplateLibraryPanel
from ui.panels.ui_control_group_store import UIControlGroupStore

__all__ = ["UIControlGroupManager"]


class PreviewSource(str, Enum):
    LAYOUT = "layout"
    TEMPLATE = "template"


class UIControlGroupSession(QtCore.QObject):
    """封装包绑定与保存调度，削减 UI 控件管理器本身的职责。"""

    data_saved = QtCore.pyqtSignal()

    def __init__(self, store: UIControlGroupStore, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store
        self.current_package: Optional[Union[PackageView, GlobalResourceView]] = None
        self._save_timer = QtCore.QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._commit)

    def bind_package(self, package: Optional[Union[PackageView, GlobalResourceView]]) -> None:
        self.current_package = package
        if package:
            self.store.load_from_package(package)

    def schedule_save(self) -> None:
        if not self.current_package:
            return
        self._save_timer.start()

    def commit_now(self) -> None:
        if not self.current_package:
            return
        self._save_timer.stop()
        self._commit()

    def _commit(self) -> None:
        if not self.current_package:
            return
        self.store.save_to_package(self.current_package)
        self.data_saved.emit()


class UIControlGroupManager(QtWidgets.QWidget):
    """界面控件组管理器主界面。"""

    open_player_editor_requested = QtCore.pyqtSignal()
    widget_selected = QtCore.pyqtSignal(str, str)
    widget_moved = QtCore.pyqtSignal(str, str, float, float)
    widget_resized = QtCore.pyqtSignal(str, str, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.current_package: Optional[Union[PackageView, GlobalResourceView]] = None
        self.current_layout_id: Optional[str] = None
        self.current_template_id: Optional[str] = None

        self.store = UIControlGroupStore()
        self.session = UIControlGroupSession(self.store, self)
        self._canvas_map: dict[str, UIPreviewCanvas] = {}

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tab_widget = QtWidgets.QTabWidget()

        self.layout_panel = UILayoutPanel(self.store, self)
        self.layout_panel.layout_selected.connect(self._on_layout_selected)
        self.layout_panel.layout_changed.connect(self._on_layout_changed)
        self.layout_panel.open_player_editor_requested.connect(self.open_player_editor_requested)
        self.tab_widget.addTab(self.layout_panel, "界面布局")

        self.template_panel = UITemplateLibraryPanel(self.store, self)
        self.template_panel.template_selected.connect(self._on_template_selected)
        self.template_panel.template_changed.connect(self._on_template_changed)
        self.template_panel.template_add_requested.connect(self._handle_template_add_request)
        self.tab_widget.addTab(self.template_panel, "界面控件组库")

        layout.addWidget(self.tab_widget)
        self._register_preview_canvas(PreviewSource.LAYOUT, self.layout_panel.preview_canvas)
        self._register_preview_canvas(PreviewSource.TEMPLATE, self.template_panel.preview_canvas)

    def set_package(self, package: Union[PackageView, GlobalResourceView]) -> None:
        self.current_package = package
        self.session.bind_package(package)
        self._refresh_ui()

    def _refresh_ui(self) -> None:
        self.layout_panel.refresh_layouts()
        self.template_panel.refresh_templates()

    def _on_layout_selected(self, layout_id: str) -> None:
        self.current_layout_id = layout_id
        self.layout_panel.show_layout_preview(layout_id)

    def _on_layout_changed(self) -> None:
        self.store.rebuild_widget_index()
        self.session.schedule_save()

    def _on_template_selected(self, template_id: str) -> None:
        self.current_template_id = template_id
        self.template_panel.show_template_preview(template_id)

    def _on_template_changed(self) -> None:
        self.store.rebuild_widget_index()
        self.layout_panel.refresh_layouts()
        self.session.schedule_save()

    def _handle_template_add_request(self, template_id: str) -> None:
        if template_id not in self.store.templates:
            show_warning_dialog(self, "提示", "模板不存在或已删除")
            return
        added = self.layout_panel.add_template_to_current_layout(template_id)
        if added:
            self.session.schedule_save()

    def _register_preview_canvas(self, source: Union[str, PreviewSource], canvas: UIPreviewCanvas) -> None:
        source_key = source.value if isinstance(source, PreviewSource) else str(source)
        self._canvas_map[source_key] = canvas

        def emit_selected(widget_id: str, *, src=source_key) -> None:
            self.widget_selected.emit(src, widget_id)

        def emit_moved(widget_id: str, x: float, y: float, *, src=source_key) -> None:
            self.widget_moved.emit(src, widget_id, x, y)

        def emit_resized(widget_id: str, width: float, height: float, *, src=source_key) -> None:
            self.widget_resized.emit(src, widget_id, width, height)

        canvas.widget_selected.connect(emit_selected)
        canvas.widget_moved.connect(emit_moved)
        canvas.widget_resized.connect(emit_resized)

    def update_widget_preview(self, source: str, widget_id: str, config: dict) -> None:
        canvas = self._canvas_map.get(source)
        if canvas:
            canvas.update_widget_preview(widget_id, config)

    def notify_widget_updated(self, source: Union[str, PreviewSource]) -> None:
        """由设置面板统一回调，触发对应面板的保存链路。"""
        normalized = (
            source
            if isinstance(source, str)
            else source.value
        )
        if normalized == PreviewSource.LAYOUT.value and hasattr(self, "layout_panel"):
            self.layout_panel.layout_changed.emit()
        elif normalized == PreviewSource.TEMPLATE.value and hasattr(self, "template_panel"):
            self.template_panel.template_changed.emit()

