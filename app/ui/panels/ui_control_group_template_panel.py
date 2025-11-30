from datetime import datetime
from typing import Optional

from PyQt6 import QtCore, QtWidgets

from engine.configs.components.ui_control_group_model import (
    TEMPLATE_WIDGET_TYPES,
    UIControlGroupTemplate,
    UIWidgetConfig,
    create_template_widget_preset,
)
from ui.foundation.base_widgets import FormDialog
from ui.foundation.context_menu_builder import ContextMenuBuilder
from ui.foundation.dialog_utils import show_info_dialog, show_warning_dialog
from ui.panels.ui_control_group_crud import (
    confirm_entity_delete,
    prompt_entity_name,
    validate_unique_entity_name,
)
from ui.panels.ui_control_group_preview_helpers import render_template_on_preview
from ui.panels.ui_control_group_store import UIControlGroupStore
from ui.panels.ui_control_group_template_tree import TemplateTreeWidget
from ui.panels.ui_control_panel_base import UIControlPanelBase
from ui.panels.panel_search_support import SidebarSearchController
from .ui_control_group_template_helpers import (
    is_custom_template,
    resize_widget_in_store,
    translate_widget_in_store,
)

__all__ = ["UITemplateLibraryPanel"]


class UITemplateLibraryPanel(UIControlPanelBase):
    """界面控件组库面板。"""

    template_selected = QtCore.pyqtSignal(str)
    template_changed = QtCore.pyqtSignal()
    template_add_requested = QtCore.pyqtSignal(str)

    def __init__(self, store: UIControlGroupStore, parent=None):
        super().__init__(parent)

        self.store = store
        self.current_template: Optional[UIControlGroupTemplate] = None
        self._template_filter_text: str = ""
        self._search_controller: Optional[SidebarSearchController] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        left_widget, left_layout = self.create_left_container()

        self._search_controller = SidebarSearchController(
            "搜索模板…",
            self._on_search_changed,
            parent=self,
        )
        left_layout.addWidget(self._search_controller.widget)

        self.template_list = TemplateTreeWidget("■ 界面控件组详情", self)
        self.template_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.template_list.customContextMenuRequested.connect(self._show_template_context_menu)
        self.template_list.currentItemChanged.connect(self._on_template_list_changed)
        left_layout.addWidget(self.template_list)

        add_template_btn = QtWidgets.QPushButton("+ 添加界面控件模板")
        add_template_btn.clicked.connect(self._add_template)
        left_layout.addWidget(add_template_btn)

        middle_layout = self.build_main_layout(left_widget)

        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()

        self.save_btn = QtWidgets.QPushButton("保存修改")
        self.save_btn.clicked.connect(self._save_template)
        btn_layout.addWidget(self.save_btn)

        self.save_as_btn = QtWidgets.QPushButton("另存为模板")
        self.save_as_btn.clicked.connect(self._save_as_template)
        btn_layout.addWidget(self.save_as_btn)

        self.add_to_layout_btn = QtWidgets.QPushButton("添加到当前布局")
        self.add_to_layout_btn.setToolTip("将此模板添加到左侧界面布局")
        self.add_to_layout_btn.clicked.connect(self._add_current_to_layout)
        btn_layout.addWidget(self.add_to_layout_btn)

        middle_layout.addLayout(btn_layout)
        self._update_button_states()

    def refresh_templates(self) -> None:
        query = self._search_controller.value if self._search_controller else ""
        self.template_list.refresh(
            self.store.templates,
            predicate=is_custom_template,
            query=query,
        )
        self._update_button_states()

    def show_template_preview(self, template_id: str) -> None:
        template = self.store.templates.get(template_id)
        self.current_template = template

        self.preview_canvas.clear_preview()
        if template:
            render_template_on_preview(self.preview_canvas, template, select_first=True)
        self._update_button_states()

    def _add_template(self) -> None:
        dialog = FormDialog("添加界面控件模板", parent=self)
        type_combo = dialog.add_combo_box("widget_type", "选择控件类型:", TEMPLATE_WIDGET_TYPES)
        dialog.add_line_edit("widget_name", "控件名称:", placeholder="输入控件名称（可选）")

        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            widget_type = dialog.value("widget_type")
            template = create_template_widget_preset(widget_type)

            custom_name = dialog.value("widget_name").strip()
            if custom_name:
                normalized = validate_unique_entity_name(
                    self,
                    custom_name,
                    entity_label="模板",
                    existing_names=[tpl.template_name for tpl in self.store.templates.values()],
                )
                if not normalized:
                    return
                template.template_name = normalized

            self.store.templates[template.template_id] = template
            self.refresh_templates()
            self.template_changed.emit()

            self.template_selected.emit(template.template_id)
            self.show_template_preview(template.template_id)

    def _show_template_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.template_list.itemAt(pos)
        if not item or not item.data(0, QtCore.Qt.ItemDataRole.UserRole):
            return

        template_id = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        template = self.store.templates.get(template_id)
        if not template:
            return

        builder = ContextMenuBuilder(self)
        builder.add_action("重命名", lambda: self._rename_template(template_id))
        builder.add_action("删除模板", lambda: self._delete_template(template_id))
        builder.exec_for(self.template_list, pos)

    def _rename_template(self, template_id: str) -> None:
        if template_id not in self.store.templates:
            return

        template = self.store.templates[template_id]
        name = prompt_entity_name(
            self,
            title="重命名模板",
            label="请输入新名称:",
            text=template.template_name,
        )
        if not name:
            return
        normalized = validate_unique_entity_name(
            self,
            name,
            entity_label="模板",
            existing_names=[tpl.template_name for tpl in self.store.templates.values()],
            exclude_name=template.template_name,
        )
        if not normalized:
            return
        template.template_name = normalized
        template.updated_at = datetime.now().isoformat()
        self.refresh_templates()
        self.template_changed.emit()

    def _delete_template(self, template_id: str) -> None:
        if template_id not in self.store.templates:
            return

        if confirm_entity_delete(
            self,
            self.store.templates[template_id].template_name,
            extra_message="如果有布局引用此模板，也会一并删除。",
        ):
            del self.store.templates[template_id]
            self.store.remove_template_from_layouts(template_id)
            self.refresh_templates()
            self.template_changed.emit()

    def _save_template(self) -> None:
        if self.current_template:
            self.current_template.updated_at = datetime.now().isoformat()
            self.template_changed.emit()
            show_info_dialog(self, "成功", "模板已保存")

    def _save_as_template(self) -> None:
        if not self.current_template:
            return

        name = prompt_entity_name(
            self,
            title="另存为模板",
            label="请输入新模板名称:",
            text=self.current_template.template_name,
        )
        if name:
            normalized = validate_unique_entity_name(
                self,
                name,
                entity_label="模板",
                existing_names=[tpl.template_name for tpl in self.store.templates.values()],
            )
            if not normalized:
                return
            new_template_id = self.store.generate_template_id("template_custom")
            now = datetime.now().isoformat()

            new_template = UIControlGroupTemplate(
                template_id=new_template_id,
                template_name=normalized,
                is_combination=self.current_template.is_combination,
                widgets=[
                    UIWidgetConfig.deserialize(w.serialize()) for w in self.current_template.widgets
                ],
                group_position=self.current_template.group_position,
                group_size=self.current_template.group_size,
                description=self.current_template.description,
                created_at=now,
                updated_at=now,
            )

            self.store.templates[new_template_id] = new_template
            self.refresh_templates()
            self.template_changed.emit()

    def _add_current_to_layout(self) -> None:
        if not self.current_template:
            show_warning_dialog(self, "提示", "请先选择一个模板")
            return
        self.template_add_requested.emit(self.current_template.template_id)

    def _on_template_list_changed(self, current, previous) -> None:
        if current and current.data(0, QtCore.Qt.ItemDataRole.UserRole):
            template_id = current.data(0, QtCore.Qt.ItemDataRole.UserRole)
            self.template_selected.emit(template_id)
        else:
            self.current_template = None
            self.preview_canvas.clear_preview()
            self._update_button_states()

    def _on_search_changed(self, normalized: str) -> None:
        if normalized == self._template_filter_text:
            return
        self._template_filter_text = normalized
        self.template_list.apply_filter(normalized)

    def _update_template_name(self, template: UIControlGroupTemplate, new_name: str) -> None:
        if new_name and new_name != template.template_name:
            template.template_name = new_name
            template.updated_at = datetime.now().isoformat()
            self.refresh_templates()
            self.template_changed.emit()

    def _on_widget_moved(self, widget_id: str, x: float, y: float) -> None:
        changed, template_id = translate_widget_in_store(self.store, widget_id, x=x, y=y)
        if not changed:
            return
        current_id = getattr(self.current_template, "template_id", None)
        if template_id != current_id:
            return
        self.template_changed.emit()

    def _on_widget_resized(self, widget_id: str, width: float, height: float) -> None:
        changed, template_id = resize_widget_in_store(self.store, widget_id, width=width, height=height)
        if not changed:
            return
        current_id = getattr(self.current_template, "template_id", None)
        if template_id != current_id:
            return
        self.template_changed.emit()

    def _update_button_states(self) -> None:
        has_template = self.current_template is not None
        self.save_btn.setEnabled(has_template)
        self.save_as_btn.setEnabled(has_template)
        self.add_to_layout_btn.setEnabled(has_template)

