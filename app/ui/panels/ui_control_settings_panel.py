"""
界面控件设置（全局面板）

用途：在主窗口右侧全局 Tab 中集中编辑界面控件（名称、可见、类型化配置）。
数据流：
  - 绑定管理器后，监听聚合的 widget_selected/widget_moved/widget_resized 信号（由两套预览画布统一发射）。
  - 选中控件 → 加载基础信息与类型化配置面板 → 配置变更回写到 UIWidgetConfig.settings。
  - 回写后通过管理器请求刷新预览，并触发 layout_changed/template_changed 以驱动保存。

注意：不包含设备/空间相关设置；设备选择仍在各页面中部工具栏中处理。
"""

from PyQt6 import QtCore, QtWidgets
from typing import Optional, Tuple, Any

from ui.foundation.theme_manager import Sizes, ThemeManager
from ui.panels.ui_control_group_store import UIControlGroupStore
from ui.panels.panel_scaffold import PanelScaffold, SectionCard
from ui.panels.ui_widget_config_panels import BaseWidgetConfigPanel, create_config_panel
from ui.panels.ui_control_group_manager import PreviewSource


class UIControlSettingsPanel(PanelScaffold):
    """界面控件设置面板（放置于主窗口右侧全局 Tab）"""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            parent,
            title="界面控件设置",
            description="集中编辑界面控件的基础信息与类型配置，支持布局与模板双来源联动。",
        )

        self.bound_manager: Optional[QtWidgets.QWidget] = None
        self.bound_store: Optional[UIControlGroupStore] = None
        self.current_template: Optional[Any] = None  # UIControlGroupTemplate
        self.current_widget: Optional[Any] = None    # UIWidgetConfig
        self.current_source: Optional[PreviewSource] = None
        self.type_panel_widget: Optional[QtWidgets.QWidget] = None
        self._manager_source: Optional[QtWidgets.QWidget] = None
        self._panel_cache: dict[str, BaseWidgetConfigPanel] = {}
        self._panel_managed_keys: dict[str, set[str]] = {}
        self._placeholder_widget: Optional[QtWidgets.QLabel] = None
        self._active_widget_id: str = ""

        self._setup_ui()
        self.set_empty_state()

    def _setup_ui(self) -> None:
        base_section = SectionCard("基础信息", "命名、显隐以及控件所在分组的位置尺寸概览")
        base_form_widget = QtWidgets.QWidget()
        base_form = QtWidgets.QFormLayout(base_form_widget)
        base_form.setContentsMargins(0, 0, 0, 0)
        base_form.setSpacing(Sizes.SPACING_MEDIUM)

        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.editingFinished.connect(self._on_name_changed)

        self.visible_check = QtWidgets.QCheckBox("初始可见")
        self.visible_check.stateChanged.connect(self._on_visible_changed)

        self.position_label = QtWidgets.QLabel("")
        self.size_label = QtWidgets.QLabel("")

        base_form.addRow("名称:", self.name_edit)
        base_form.addRow("", self.visible_check)
        base_form.addRow("位置:", self.position_label)
        base_form.addRow("大小:", self.size_label)
        base_section.add_content_widget(base_form_widget)
        self.body_layout.addWidget(base_section)

        type_section = SectionCard("类型配置", "根据控件类型加载对应配置表单")
        type_container = QtWidgets.QWidget()
        self.type_stack = QtWidgets.QStackedLayout(type_container)
        self.type_stack.setContentsMargins(0, 0, 0, 0)
        self._placeholder_widget = QtWidgets.QLabel("未选中任何界面控件\n请在中部预览中点击一个控件")
        self._placeholder_widget.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._placeholder_widget.setStyleSheet(f"{ThemeManager.hint_text_style()} padding:20px;")
        self.type_stack.addWidget(self._placeholder_widget)
        self.type_panel_widget = self._placeholder_widget
        type_section.add_content_widget(type_container)
        self.body_layout.addWidget(type_section, 1)

    # ----------------------------------------------------------------------------------
    # 绑定与信号接入
    # ----------------------------------------------------------------------------------
    def bind_manager(self, manager: QtWidgets.QWidget) -> None:
        """绑定界面控件组管理器，接入两个预览画布的选中/移动/缩放信号。"""
        self._disconnect_manager_signals()
        self.bound_manager = manager
        self.bound_store = getattr(manager, "store", None)
        self._manager_source = manager
        if manager:
            manager.widget_selected.connect(self._on_widget_selected)
            manager.widget_moved.connect(self._on_widget_moved)
            manager.widget_resized.connect(self._on_widget_resized)
        self.set_empty_state()

    # ----------------------------------------------------------------------------------
    # 事件处理
    # ----------------------------------------------------------------------------------
    def _on_widget_selected(self, source: str, widget_id: str) -> None:
        """选中某个控件后，加载其配置。"""
        if not self.bound_manager:
            self.set_empty_state()
            return

        found_template, found_widget = self._find_widget_by_id(widget_id)
        if not found_template or not found_widget:
            self.set_empty_state()
            return

        self.current_template = found_template
        self.current_widget = found_widget
        normalized_source = self._normalize_source(source)
        if not normalized_source:
            self.set_empty_state()
            return
        self.current_source = normalized_source
        self._active_widget_id = found_widget.widget_id

        # 刷新基础信息
        self.name_edit.setText(found_widget.widget_name)
        self.visible_check.setChecked(found_widget.initial_visible)
        self._update_pos_size_labels(found_widget.position, found_widget.size)

        # 重建类型化配置面板
        self._build_type_panel(found_widget)

    def _on_widget_moved(self, source: str, widget_id: str, x: float, y: float) -> None:
        normalized_source = self._normalize_source(source)
        if (
            self.current_widget
            and widget_id == self.current_widget.widget_id
            and self.current_template
            and normalized_source == self.current_source
        ):
            # 位置显示更新（真实数据写回由管理页处理）
            self._update_pos_size_labels((x, y), self.current_widget.size)

    def _on_widget_resized(self, source: str, widget_id: str, width: float, height: float) -> None:
        normalized_source = self._normalize_source(source)
        if (
            self.current_widget
            and widget_id == self.current_widget.widget_id
            and self.current_template
            and normalized_source == self.current_source
        ):
            # 尺寸显示更新（真实数据写回由管理页处理）
            self._update_pos_size_labels(self.current_widget.position, (width, height))

    def _on_name_changed(self) -> None:
        if not self.current_widget or not self.current_template or not self.bound_manager:
            return
        new_name = self.name_edit.text()
        if new_name and new_name != self.current_widget.widget_name:
            self.current_widget.widget_name = new_name
            self._refresh_preview_and_emit_changed()

    def _on_visible_changed(self, state: int) -> None:
        if not self.current_widget or not self.current_template or not self.bound_manager:
            return
        is_visible = state == QtCore.Qt.CheckState.Checked.value
        if is_visible != self.current_widget.initial_visible:
            self.current_widget.initial_visible = is_visible
            self._refresh_preview_and_emit_changed()

    # ----------------------------------------------------------------------------------
    # 内部工具
    # ----------------------------------------------------------------------------------
    def _find_widget_by_id(self, widget_id: str) -> Tuple[Optional[Any], Optional[Any]]:
        """在管理器的模板集合中查找指定 widget_id 对应的 (template, widget)。"""
        if not self.bound_store:
            return None, None
        return self.bound_store.find_widget(widget_id)

    def _build_type_panel(self, widget_obj: Any) -> None:
        panel_type = widget_obj.widget_type
        config_dict = {
            "widget_id": widget_obj.widget_id,
            "widget_type": panel_type,
            "settings": dict(widget_obj.settings),
        }

        panel = self._panel_cache.get(panel_type)
        if panel is None:
            created = create_config_panel(panel_type, self)
            if created:
                created.config_changed.connect(self._handle_config_panel_changed)
                self._panel_cache[panel_type] = created
                self.type_stack.addWidget(created)
            panel = created

        if panel:
            self.type_panel_widget = panel
            self.type_stack.setCurrentWidget(panel)
            panel.load_config(config_dict)
        else:
            self._show_placeholder("该控件类型暂不支持类型化配置")

    def _refresh_preview_and_emit_changed(self) -> None:
        """根据当前模板/控件组位置尺寸刷新预览，并发出上游更改信号。"""
        config_dict = self.current_widget.serialize()
        # 预览刷新
        manager = self.bound_manager
        if not manager or not self.current_source:
            return
        manager.update_widget_preview(self.current_source.value, self.current_widget.widget_id, config_dict)

        self._notify_manager_persist()

    def _update_pos_size_labels(self, pos_tuple: Tuple[float, float], size_tuple: Tuple[float, float]) -> None:
        self.position_label.setText(f"({pos_tuple[0]:.0f}, {pos_tuple[1]:.0f})")
        self.size_label.setText(f"({size_tuple[0]:.0f}, {size_tuple[1]:.0f})")

    def _disconnect_manager_signals(self) -> None:
        if not self._manager_source:
            return
        try:
            self._manager_source.widget_selected.disconnect(self._on_widget_selected)
        except (TypeError, AttributeError):
            pass

    def _normalize_source(self, source: str | PreviewSource) -> Optional[PreviewSource]:
        if isinstance(source, PreviewSource):
            return source
        if source == PreviewSource.LAYOUT.value:
            return PreviewSource.LAYOUT
        if source == PreviewSource.TEMPLATE.value:
            return PreviewSource.TEMPLATE
        return None
        try:
            self._manager_source.widget_moved.disconnect(self._on_widget_moved)
        except (TypeError, AttributeError):
            pass
        try:
            self._manager_source.widget_resized.disconnect(self._on_widget_resized)
        except (TypeError, AttributeError):
            pass
        self._manager_source = None

    def _handle_config_panel_changed(self, updated_config: dict) -> None:
        if not self.current_widget or not self.current_template:
            return
        widget_id = updated_config.get("widget_id")
        if widget_id != self.current_widget.widget_id:
            return

        panel_settings = updated_config.get("settings", {}) or {}
        panel_type = self.current_widget.widget_type
        incoming_keys = set(panel_settings.keys())
        previous_keys = self._panel_managed_keys.get(panel_type, set())

        merged_settings = dict(self.current_widget.settings)
        changed = False

        for key, value in panel_settings.items():
            if merged_settings.get(key) != value:
                merged_settings[key] = value
                changed = True

        removed_keys = previous_keys - incoming_keys
        for key in removed_keys:
            if key in merged_settings:
                merged_settings.pop(key)
                changed = True

        self._panel_managed_keys[panel_type] = incoming_keys
        if not changed:
            return

        self.current_widget.settings = merged_settings
        self._refresh_preview_and_emit_changed()

    def _show_placeholder(self, message: str) -> None:
        if self._placeholder_widget:
            self._placeholder_widget.setText(message)
            self.type_panel_widget = self._placeholder_widget
            self.type_stack.setCurrentWidget(self._placeholder_widget)

    def _notify_manager_persist(self) -> None:
        if not self.bound_manager or not self.current_source:
            return
        notifier = getattr(self.bound_manager, "notify_widget_updated", None)
        if callable(notifier):
            notifier(self.current_source)

    def set_empty_state(self) -> None:
        """重置为空状态。"""
        self.current_template = None
        self.current_widget = None
        self.current_source = None
        self._active_widget_id = ""
        self.name_edit.setText("")
        self.visible_check.setChecked(True)
        self.position_label.setText("")
        self.size_label.setText("")

        if self._placeholder_widget:
            self.type_stack.setCurrentWidget(self._placeholder_widget)
            self.type_panel_widget = self._placeholder_widget


