from copy import deepcopy
from datetime import datetime
from typing import Dict, Optional

from PyQt6 import QtCore, QtWidgets

from engine.configs.components.ui_control_group_model import (
    UIControlGroupTemplate,
    UILayout,
)
from ui.foundation.context_menu_builder import ContextMenuBuilder
from ui.foundation.dialog_utils import (
    apply_standard_button_box_labels,
    show_info_dialog,
    show_warning_dialog,
)
from ui.foundation.theme_manager import Colors, ThemeManager, Sizes
from ui.foundation.toast_notification import ToastNotification
from ui.foundation.toolbar_utils import apply_standard_toolbar
from ui.panels.ui_control_group_crud import (
    confirm_entity_delete,
    prompt_entity_name,
    validate_unique_entity_name,
)
from ui.panels.ui_control_panel_base import UIControlPanelBase
from ui.panels.ui_control_group_preview_helpers import render_template_on_preview
from ui.panels.ui_control_group_store import UIControlGroupStore
from ui.panels.ui_control_group_template_tree import TemplateTreeWidget
from ui.panels.panel_search_support import SidebarSearchController

from .ui_control_group_collapsible_section import CollapsibleSection
from .ui_control_group_template_helpers import resize_widget_in_store, translate_widget_in_store

__all__ = ["UILayoutPanel"]


def _create_section_label(text: str, *, top_margin: bool = False) -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    margin_top = Sizes.PADDING_MEDIUM if top_margin else 0
    label.setStyleSheet(
        f"""
        {ThemeManager.heading(level=4)}
        padding: {Sizes.PADDING_SMALL}px;
        margin-top: {margin_top}px;
    """
    )
    return label


class LayoutListPanel(QtWidgets.QWidget):
    """左侧布局列表面板：负责布局列表、搜索与复制粘贴，不直接操作预览画布。"""

    layout_selected = QtCore.pyqtSignal(str)
    selection_cleared = QtCore.pyqtSignal()
    layout_changed = QtCore.pyqtSignal()

    def __init__(self, store: UIControlGroupStore, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store
        self._layout_filter_text: str = ""
        self._layout_search: Optional[SidebarSearchController] = None
        self._copied_layout_payload: Optional[dict] = None
        self._paste_button: Optional[QtWidgets.QPushButton] = None

        self.layout_list = QtWidgets.QListWidget()
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(_create_section_label("■ 界面布局"))

        self._layout_search = SidebarSearchController(
            "搜索布局…",
            self._apply_layout_filter,
            parent=self,
        )
        layout.addWidget(self._layout_search.widget)

        toolbar = QtWidgets.QHBoxLayout()
        apply_standard_toolbar(toolbar)
        add_btn = QtWidgets.QPushButton("+ 新建布局")
        add_btn.clicked.connect(self._add_layout)
        copy_btn = QtWidgets.QPushButton("复制")
        copy_btn.clicked.connect(self._handle_copy_requested)
        paste_btn = QtWidgets.QPushButton("粘贴")
        paste_btn.clicked.connect(self._paste_layout)
        toolbar.addWidget(add_btn)
        toolbar.addWidget(copy_btn)
        toolbar.addWidget(paste_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.layout_list.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.layout_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.layout_list.customContextMenuRequested.connect(self._show_layout_context_menu)
        self.layout_list.currentItemChanged.connect(self._on_layout_list_changed)
        layout.addWidget(self.layout_list)

        self._paste_button = paste_btn
        self._paste_button.setEnabled(False)

    @property
    def current_layout_id(self) -> Optional[str]:
        item = self.layout_list.currentItem()
        if not item:
            return None
        return item.data(QtCore.Qt.ItemDataRole.UserRole)

    def refresh_layouts(self) -> None:
        selected_id = self.current_layout_id
        self.layout_list.clear()

        query = self._layout_search.value if self._layout_search else ""
        sorted_layouts = sorted(
            self.store.layouts.items(),
            key=lambda pair: pair[1].layout_name.casefold(),
        )
        for layout_id, layout in sorted_layouts:
            if query and query not in layout.layout_name.casefold():
                continue
            item = QtWidgets.QListWidgetItem(layout.layout_name)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, layout_id)
            self.layout_list.addItem(item)

        if selected_id and selected_id in self.store.layouts:
            self._select_layout_by_id(selected_id)
        elif self.layout_list.count() > 0:
            self.layout_list.setCurrentRow(0)
        else:
            self.selection_cleared.emit()

    def _apply_layout_filter(self, normalized: str) -> None:
        if normalized == self._layout_filter_text:
            return
        self._layout_filter_text = normalized
        self.refresh_layouts()

    def _add_layout(self) -> None:
        name = prompt_entity_name(
            self,
            title="新建布局",
            label="请输入布局名称:",
            placeholder="新的界面布局",
        )
        if not name:
            return
        normalized = validate_unique_entity_name(
            self,
            name,
            entity_label="布局",
            existing_names=[layout.layout_name for layout in self.store.layouts.values()],
        )
        if not normalized:
            return
        layout = self._create_layout(name=normalized)
        self.store.layouts[layout.layout_id] = layout
        self.refresh_layouts()
        self.layout_changed.emit()

    def _show_layout_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.layout_list.itemAt(pos)
        if not item:
            return

        layout_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        builder = ContextMenuBuilder(self)
        builder.add_action("重命名", lambda: self._rename_layout(layout_id))
        builder.add_action("复制", lambda: self._duplicate_layout(layout_id))
        can_delete = layout_id != "layout_default"
        builder.add_action("删除", lambda: self._delete_layout(layout_id), enabled=can_delete)
        builder.exec_for(self.layout_list, pos)

    def _rename_layout(self, layout_id: str) -> None:
        if layout_id not in self.store.layouts:
            return

        layout = self.store.layouts[layout_id]
        name = prompt_entity_name(
            self,
            title="重命名布局",
            label="请输入新名称:",
            text=layout.layout_name,
        )
        if not name:
            return
        normalized = validate_unique_entity_name(
            self,
            name,
            entity_label="布局",
            existing_names=[value.layout_name for value in self.store.layouts.values()],
            exclude_name=layout.layout_name,
        )
        if not normalized:
            return
        layout.layout_name = normalized
        layout.updated_at = datetime.now().isoformat()
        self.refresh_layouts()
        self.layout_changed.emit()

    def _duplicate_layout(self, layout_id: Optional[str]) -> None:
        if not layout_id or layout_id not in self.store.layouts:
            return

        original = self.store.layouts[layout_id]
        new_layout = self._clone_layout_from_payload(
            {
                "layout_name": original.layout_name,
                "builtin_widgets": list(original.builtin_widgets),
                "custom_groups": list(original.custom_groups),
                "default_for_player": original.default_for_player,
                "description": original.description,
                "visibility_overrides": dict(original.visibility_overrides),
            },
            name_seed=original.layout_name,
        )
        self.store.layouts[new_layout.layout_id] = new_layout
        self.refresh_layouts()
        self.layout_changed.emit()

    def _select_layout_by_id(self, layout_id: Optional[str]) -> None:
        if not layout_id:
            return
        for row in range(self.layout_list.count()):
            item = self.layout_list.item(row)
            if item and item.data(QtCore.Qt.ItemDataRole.UserRole) == layout_id:
                self.layout_list.setCurrentRow(row)
                break

    def _paste_layout(self) -> None:
        if not self._copied_layout_payload:
            show_info_dialog(self, "提示", "请先复制一个布局")
            return

        payload = deepcopy(self._copied_layout_payload)
        base_name = payload.get("layout_name", "新布局")
        new_layout = self._clone_layout_from_payload(payload, name_seed=base_name)
        self.store.layouts[new_layout.layout_id] = new_layout
        self.refresh_layouts()
        self.layout_changed.emit()

    def _clone_layout_from_payload(self, payload: dict, *, name_seed: str) -> UILayout:
        return self._create_layout(
            name=self._generate_copy_name(name_seed),
            builtin=list(payload.get("builtin_widgets", [])),
            custom=list(payload.get("custom_groups", [])),
            default_for_player=payload.get("default_for_player"),
            description=payload.get("description", ""),
            visibility_overrides=payload.get("visibility_overrides", {}),
        )

    def _delete_layout(self, layout_id: str) -> None:
        if layout_id not in self.store.layouts or layout_id == "layout_default":
            return

        if confirm_entity_delete(self, self.store.layouts[layout_id].layout_name):
            layout_name = self.store.layouts[layout_id].layout_name
            del self.store.layouts[layout_id]
            self.refresh_layouts()
            self.layout_changed.emit()
            ToastNotification.show_message(self, f"已删除布局 '{layout_name}'。", "success")

    def _create_layout(
        self,
        *,
        name: str,
        layout_id: Optional[str] = None,
        builtin: Optional[list[str]] = None,
        custom: Optional[list[str]] = None,
        default_for_player: Optional[str] = None,
        description: str = "",
        visibility_overrides: Optional[Dict[str, bool]] = None,
    ) -> UILayout:
        layout_id = layout_id or self.store.generate_layout_id()
        now = datetime.now().isoformat()
        return UILayout(
            layout_id=layout_id,
            layout_name=name,
            builtin_widgets=list(builtin or []),
            custom_groups=list(custom or []),
            default_for_player=default_for_player,
            description=description,
            created_at=now,
            updated_at=now,
            visibility_overrides=dict(visibility_overrides or {}),
        )

    def _handle_copy_requested(self) -> None:
        layout_id = self.current_layout_id
        if not layout_id or layout_id not in self.store.layouts:
            return
        layout = self.store.layouts[layout_id]
        self._copied_layout_payload = layout.serialize()
        self._update_paste_button_state(True)

    def _update_paste_button_state(self, is_enabled: bool = False) -> None:
        if self._paste_button:
            self._paste_button.setEnabled(is_enabled)

    def _generate_copy_name(self, base_name: str) -> str:
        suffix = "_副本"
        existing_names = {layout.layout_name for layout in self.store.layouts.values()}
        candidate = f"{base_name}{suffix}"
        counter = 2
        while candidate in existing_names:
            candidate = f"{base_name}{suffix}{counter}"
            counter += 1
        return candidate

    def _on_layout_list_changed(self, current, previous) -> None:  # noqa: ARG002
        if current:
            layout_id = current.data(QtCore.Qt.ItemDataRole.UserRole)
            if layout_id:
                self.layout_selected.emit(layout_id)
        else:
            self.selection_cleared.emit()


class LayoutDetailController(QtCore.QObject):
    """布局详情控制器：负责布局详情、模板卡片与预览画布联动。"""

    layout_changed = QtCore.pyqtSignal()

    def __init__(
        self,
        store: UIControlGroupStore,
        preview_canvas,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.preview_canvas = preview_canvas
        self.current_layout: Optional[UILayout] = None
        self._builtin_section: Optional[CollapsibleSection] = None
        self._custom_section: Optional[CollapsibleSection] = None
        self._empty_hint_label: Optional[QtWidgets.QLabel] = None
        self._template_item_pool: Dict[str, "TemplateEntryWidget"] = {}

        self._detail_container = QtWidgets.QWidget()
        self._detail_layout = QtWidgets.QVBoxLayout(self._detail_container)
        self._detail_layout.setContentsMargins(4, 4, 4, 4)
        self._detail_layout.setSpacing(6)

        self._init_detail_sections()

        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(self._detail_container)

    @property
    def widget(self) -> QtWidgets.QWidget:
        return self._scroll

    def clear(self) -> None:
        self.current_layout = None
        self.preview_canvas.clear_preview()
        self._set_detail_visibility(False)

    def show_layout_preview(self, layout_id: str) -> None:
        layout = self.store.layouts.get(layout_id)
        self.current_layout = layout
        self._set_detail_visibility(layout is not None)

        if not layout:
            self.preview_canvas.clear_preview()
            return

        self._render_sections_for_layout(layout)
        self._render_layout_on_canvas(layout)

    def add_template_to_current_layout(self, template_id: str) -> bool:
        host = self._host_widget()
        if not self.current_layout:
            show_warning_dialog(host, "提示", "请先选择一个布局")
            return False
        if template_id not in self.store.templates:
            show_warning_dialog(host, "提示", "模板不存在或已被删除")
            return False
        if template_id in self.current_layout.custom_groups:
            show_info_dialog(host, "提示", "该模板已在当前布局中")
            return False

        self.current_layout.custom_groups.append(template_id)
        self.current_layout.updated_at = datetime.now().isoformat()
        self._rerender_detail_sections()
        self._render_layout_on_canvas(self.current_layout)
        self.layout_changed.emit()
        return True

    def remove_widget_from_layout(self, template_id: str) -> None:
        if not self.current_layout:
            return

        if template_id in self.current_layout.custom_groups:
            self.current_layout.custom_groups.remove(template_id)
            self.current_layout.visibility_overrides.pop(template_id, None)
            self.current_layout.updated_at = datetime.now().isoformat()
            self._rerender_detail_sections()
            self._render_layout_on_canvas(self.current_layout)
            self.layout_changed.emit()

    def handle_widget_moved(self, widget_id: str, x: float, y: float) -> None:
        changed, _ = translate_widget_in_store(self.store, widget_id, x=x, y=y)
        if changed:
            self.layout_changed.emit()

    def handle_widget_resized(self, widget_id: str, width: float, height: float) -> None:
        changed, _ = resize_widget_in_store(self.store, widget_id, width=width, height=height)
        if changed:
            self.layout_changed.emit()

    def _host_widget(self) -> Optional[QtWidgets.QWidget]:
        parent = self.parent()
        if isinstance(parent, QtWidgets.QWidget):
            return parent
        return None

    def _render_sections_for_layout(self, layout: UILayout) -> None:
        templates = self.store.templates
        self._prune_template_item_pool()

        self._render_template_section(
            section=self._builtin_section,
            template_ids=layout.builtin_widgets,
            templates=templates,
            layout=layout,
            is_builtin=True,
        )
        self._render_template_section(
            section=self._custom_section,
            template_ids=layout.custom_groups,
            templates=templates,
            layout=layout,
            is_builtin=False,
        )

    def _render_template_section(
        self,
        *,
        section: Optional[CollapsibleSection],
        template_ids: list[str],
        templates: Dict[str, UIControlGroupTemplate],
        layout: UILayout,
        is_builtin: bool,
    ) -> None:
        if not section:
            return
        section.clear_content()
        section.setVisible(bool(template_ids) or not is_builtin)

        if not template_ids:
            if not is_builtin:
                section.add_widget(self._create_empty_custom_hint())
            return

        for template_id in template_ids:
            template = templates.get(template_id)
            if not template:
                continue
            visible_state = self._get_layout_visibility(layout, template_id, template)
            widget_item = self._obtain_template_widget(template.template_id)
            widget_item.configure(template, is_builtin=is_builtin, visible=visible_state)
            section.add_widget(widget_item)

    def _obtain_template_widget(self, template_id: str) -> "TemplateEntryWidget":
        widget = self._template_item_pool.get(template_id)
        if widget is None:
            host = self._host_widget()
            widget = TemplateEntryWidget(template_id, host)
            widget.clicked.connect(self._on_template_row_clicked)
            widget.visibility_changed.connect(self._on_template_visibility_toggled)
            widget.remove_requested.connect(self.remove_widget_from_layout)
            self._template_item_pool[template_id] = widget
        return widget

    def _prune_template_item_pool(self) -> None:
        valid_ids = set(self.store.templates.keys())
        for template_id, widget in list(self._template_item_pool.items()):
            if template_id not in valid_ids:
                widget.deleteLater()
                self._template_item_pool.pop(template_id, None)

    def _on_template_row_clicked(self, template_id: str) -> None:
        template = self.store.templates.get(template_id)
        if not template or not template.widgets:
            return
        first_widget = template.widgets[0]
        self.preview_canvas.select_widget(first_widget.widget_id)

    def _on_template_visibility_toggled(self, template_id: str, visible: bool) -> None:
        if not self.current_layout:
            return
        template = self.store.templates.get(template_id)
        if not template:
            return
        default_visible = self._is_template_visible(template)
        overrides = self.current_layout.visibility_overrides
        if visible == default_visible:
            overrides.pop(template_id, None)
        else:
            overrides[template_id] = visible
        self.current_layout.updated_at = datetime.now().isoformat()
        template = self.store.templates.get(template_id)
        if template:
            self._apply_template_visibility_to_preview(template, visible)
        else:
            self._render_layout_on_canvas(self.current_layout)
        self.layout_changed.emit()

    def _get_layout_visibility(
        self,
        layout: UILayout,
        template_id: str,
        template: UIControlGroupTemplate,
    ) -> bool:
        if template_id in layout.visibility_overrides:
            return layout.visibility_overrides[template_id]
        return self._is_template_visible(template)

    @staticmethod
    def _is_template_visible(template: UIControlGroupTemplate) -> bool:
        return all(widget.initial_visible for widget in template.widgets) if template.widgets else True

    def _init_detail_sections(self) -> None:
        self._empty_hint_label = QtWidgets.QLabel("请选择一个布局后查看控件详情")
        self._empty_hint_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._empty_hint_label.setStyleSheet(
            f"color: {Colors.TEXT_PLACEHOLDER}; padding: 16px 0;"
        )
        self._detail_layout.addWidget(self._empty_hint_label)

        self._builtin_section = CollapsibleSection("固有内容")
        self._builtin_section.setCollapsed(False)
        self._detail_layout.addWidget(self._builtin_section)

        self._custom_section = CollapsibleSection("自定义")
        self._custom_section.setCollapsed(False)
        self._detail_layout.addWidget(self._custom_section)

        self._detail_layout.addStretch()
        self._set_detail_visibility(False)

    def _create_empty_custom_hint(self) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel('暂无自定义控件\n点击下方"添加界面控件"按钮添加')
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            f"color: {Colors.TEXT_PLACEHOLDER}; padding: 10px; font-size: 10px;"
        )
        return label

    def _set_detail_visibility(self, has_layout: bool) -> None:
        if self._empty_hint_label:
            self._empty_hint_label.setVisible(not has_layout)
        if self._builtin_section:
            self._builtin_section.setVisible(has_layout)
        if self._custom_section:
            self._custom_section.setVisible(has_layout)

    def _rerender_detail_sections(self) -> None:
        if not self.current_layout:
            return
        self._render_sections_for_layout(self.current_layout)

    def _render_layout_on_canvas(self, layout: UILayout) -> None:
        self.preview_canvas.clear_preview()
        templates = self.store.templates
        ordered_ids = list(layout.builtin_widgets) + list(layout.custom_groups)
        for template_id in ordered_ids:
            template = templates.get(template_id)
            if not template:
                continue
            visible_state = self._get_layout_visibility(layout, template_id, template)
            overrides: Dict[str, object] = {"initial_visible": visible_state}
            if template_id in layout.builtin_widgets:
                overrides["is_builtin"] = True
            render_template_on_preview(self.preview_canvas, template, overrides=overrides)

    def _apply_template_visibility_to_preview(
        self,
        template: UIControlGroupTemplate,
        visible_state: bool,
    ) -> None:
        missing_widget = False
        for widget in template.widgets:
            if widget.widget_id not in self.preview_canvas.widget_items:
                missing_widget = True
                continue
            widget_config = widget.serialize()
            widget_config["initial_visible"] = visible_state
            self.preview_canvas.update_widget_preview(widget.widget_id, widget_config)
        if missing_widget and self.current_layout:
            self._render_layout_on_canvas(self.current_layout)


class UILayoutPanel(UIControlPanelBase):
    """界面布局面板。"""

    open_player_editor_requested = QtCore.pyqtSignal()
    layout_selected = QtCore.pyqtSignal(str)
    layout_changed = QtCore.pyqtSignal()

    def __init__(self, store: UIControlGroupStore, parent=None):
        super().__init__(parent)

        self.store = store
        self._list_panel: Optional[LayoutListPanel] = None
        self._detail_controller: Optional[LayoutDetailController] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        left_widget, left_layout = self.create_left_container()

        self._list_panel = LayoutListPanel(self.store, self)
        self._list_panel.layout_selected.connect(self.layout_selected)
        self._list_panel.selection_cleared.connect(self._on_layout_selection_cleared)
        self._list_panel.layout_changed.connect(self.layout_changed)
        left_layout.addWidget(self._list_panel)

        left_layout.addWidget(_create_section_label("■ 布局详情", top_margin=True))
        self._detail_controller = LayoutDetailController(self.store, self.preview_canvas, parent=self)
        self._detail_controller.layout_changed.connect(self.layout_changed)
        left_layout.addWidget(self._detail_controller.widget, 1)

        self._build_footer(left_layout)
        self.build_main_layout(left_widget)

    def _build_footer(self, left_layout: QtWidgets.QVBoxLayout) -> None:
        add_widget_bottom_btn = QtWidgets.QPushButton("添加界面控件")
        add_widget_bottom_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        add_widget_bottom_btn.clicked.connect(self._add_widget_to_layout)
        left_layout.addWidget(add_widget_bottom_btn)

    def refresh_layouts(self) -> None:
        if self._list_panel:
            self._list_panel.refresh_layouts()

    def show_layout_preview(self, layout_id: str) -> None:
        if self._detail_controller:
            self._detail_controller.show_layout_preview(layout_id)

    def _add_widget_to_layout(self) -> None:
        if not self._detail_controller or not self._detail_controller.current_layout:
            show_warning_dialog(self, "提示", "请先选择一个布局")
            return

        dialog = AddWidgetDialog(self.store.templates, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            template_id = dialog.get_selected_template()
            if template_id:
                self.add_template_to_current_layout(template_id)

    def add_template_to_current_layout(self, template_id: str) -> bool:
        if not self._detail_controller:
            return False
        return self._detail_controller.add_template_to_current_layout(template_id)

    def _on_layout_selection_cleared(self) -> None:
        if self._detail_controller:
            self._detail_controller.clear()

    def _on_widget_moved(self, widget_id: str, x: float, y: float) -> None:
        if self._detail_controller:
            self._detail_controller.handle_widget_moved(widget_id, x, y)

    def _on_widget_resized(self, widget_id: str, width: float, height: float) -> None:
        if self._detail_controller:
            self._detail_controller.handle_widget_resized(widget_id, width, height)


class TemplateEntryWidget(QtWidgets.QFrame):
    """可复用的模板条目小部件。"""

    clicked = QtCore.pyqtSignal(str)
    visibility_changed = QtCore.pyqtSignal(str, bool)
    remove_requested = QtCore.pyqtSignal(str)

    def __init__(self, template_id: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.template_id = template_id
        self.setObjectName("TemplateEntryWidget")
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"""
            QFrame#TemplateEntryWidget {{
                background-color: transparent;
                border: none;
            }}
            QFrame#TemplateEntryWidget:hover {{
                background-color: {Colors.BG_SELECTED};
            }}
        """
        )

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.icon_label = QtWidgets.QLabel()
        self.icon_label.setFixedWidth(20)
        self.icon_label.setStyleSheet(f"background: transparent; color: {Colors.PRIMARY};")
        layout.addWidget(self.icon_label)

        self.name_label = QtWidgets.QLabel()
        self.name_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        layout.addWidget(self.name_label, 1)

        self._visible_check = QtWidgets.QCheckBox("可见")
        self._visible_check.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        self._visible_check.toggled.connect(self._emit_visibility_changed)
        layout.addWidget(self._visible_check)

        self._remove_button = QtWidgets.QPushButton("×")
        self._remove_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._remove_button.setFixedSize(22, 22)
        self._remove_button.setStyleSheet(
            f"""
            QPushButton {{
                border: none;
                color: {Colors.TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                color: {Colors.ERROR};
            }}
        """
        )
        self._remove_button.setToolTip("移除此控件")
        self._remove_button.clicked.connect(lambda: self.remove_requested.emit(self.template_id))
        layout.addWidget(self._remove_button)

    def configure(
        self,
        template: UIControlGroupTemplate,
        *,
        is_builtin: bool,
        visible: bool,
    ) -> None:
        self.icon_label.setText("●" if not template.is_combination else "■")
        self.name_label.setText(template.template_name)
        self._visible_check.blockSignals(True)
        self._visible_check.setChecked(visible)
        self._visible_check.blockSignals(False)
        self._remove_button.setVisible(not is_builtin)

    def mouseReleaseEvent(self, event):  # type: ignore[override]
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit(self.template_id)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _emit_visibility_changed(self, checked: bool) -> None:
        self.visibility_changed.emit(self.template_id, checked)


class AddWidgetDialog(QtWidgets.QDialog):
    """布局内添加控件的选择对话框。"""

    def __init__(self, templates: Dict[str, UIControlGroupTemplate], parent=None):
        super().__init__(parent)

        self.templates = templates
        self.selected_template_id: Optional[str] = None

        self.setWindowTitle("添加界面控件")
        self.setFixedSize(400, 500)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        layout.addWidget(QtWidgets.QLabel("选择要添加的控件组模板:"))

        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("搜索模板…")
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        layout.addWidget(self.search_edit)

        self.template_tree = TemplateTreeWidget("自定义模板", self)
        self.template_tree.currentItemChanged.connect(self._on_selection_changed)
        self.template_tree.refresh(self.templates)
        layout.addWidget(self.template_tree)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        apply_standard_button_box_labels(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_selection_changed(self, current, previous) -> None:
        self.selected_template_id = self.template_tree.current_template_id()

    def get_selected_template(self) -> Optional[str]:
        return self.selected_template_id

    def _on_search_text_changed(self, text: str) -> None:
        normalized = text.strip().casefold()
        self.template_tree.apply_filter(normalized)

