"""Components tab for template/instance panel."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Iterable, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from engine.configs.rules import COMPONENT_DEFINITIONS
from engine.graph.models.entity_templates import get_all_component_types
from engine.graph.models.package_model import ComponentConfig
from ui.foundation import input_dialogs
from ui.foundation.dialog_utils import show_warning_dialog
from ui.foundation.context_menu_builder import ContextMenuBuilder
from ui.foundation.theme_manager import Colors, Sizes
from ui.foundation.toast_notification import ToastNotification
from ui.panels.template_instance.component_form_factory import create_component_form
from ui.panels.template_instance.tab_base import TemplateInstanceTabBase


@dataclass(frozen=True)
class ComponentRow:
    component: ComponentConfig
    label: str
    source: str
    foreground: Optional[str] = None


class ComponentsTab(TemplateInstanceTabBase):
    """组件标签页，区分模板继承与额外组件。"""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._component_type_cache: Optional[list[str]] = None
        self._is_read_only: bool = False
        self._add_button: Optional[QtWidgets.QPushButton] = None
        self._scroll_area: Optional[QtWidgets.QScrollArea] = None
        self._components_container: Optional[QtWidgets.QWidget] = None
        self._components_layout: Optional[QtWidgets.QVBoxLayout] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = self._init_panel_layout(
            [
                ("+ 添加组件", self._add_component),
                ("删除", self._remove_component),
            ]
        )
        # 捕获工具条上的“添加组件”按钮，供只读模式统一禁用
        toolbar_item = layout.itemAt(0)
        toolbar_layout = toolbar_item.layout() if toolbar_item is not None else None
        if isinstance(toolbar_layout, QtWidgets.QHBoxLayout):
            for index in range(toolbar_layout.count()):
                layout_item = toolbar_layout.itemAt(index)
                if layout_item is None:
                    continue
                widget = layout_item.widget()
                if isinstance(widget, QtWidgets.QPushButton) and self._add_button is None:
                    self._add_button = widget
                    break

        scroll_area = QtWidgets.QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        container = QtWidgets.QWidget(scroll_area)
        components_layout = QtWidgets.QVBoxLayout(container)
        components_layout.setContentsMargins(
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
        )
        components_layout.setSpacing(Sizes.SPACING_MEDIUM)

        scroll_area.setWidget(container)
        layout.addWidget(scroll_area, 1)

        self._scroll_area = scroll_area
        self._components_container = container
        self._components_layout = components_layout

    def _reset_ui(self) -> None:
        self._clear_component_cards()

    def _refresh_ui(self) -> None:
        self._rebuild_component_cards()

    # 组件卡片构建 -----------------------------------------------------------
    def _clear_component_cards(self) -> None:
        if self._components_layout is None:
            return
        while self._components_layout.count():
            layout_item = self._components_layout.takeAt(0)
            if layout_item is None:
                continue
            widget = layout_item.widget()
            if widget is not None:
                widget.deleteLater()

    def _rebuild_component_cards(self) -> None:
        if self._components_layout is None:
            return
        self._clear_component_cards()

        rows = list(self._iter_component_rows())
        if not rows:
            placeholder = QtWidgets.QLabel(
                "尚未为当前对象添加通用组件。\n"
                "点击上方“+ 添加组件”按钮，为元件或实体挂载组件。",
                self,
            )
            placeholder.setObjectName("ComponentsEmptyPlaceholder")
            placeholder.setWordWrap(True)
            placeholder.setAlignment(
                QtCore.Qt.AlignmentFlag.AlignLeft
                | QtCore.Qt.AlignmentFlag.AlignTop
            )
            placeholder.setStyleSheet(f"color: {Colors.TEXT_HINT};")
            self._components_layout.addWidget(placeholder)
            self._components_layout.addStretch(1)
            return

        for row in rows:
            group = self._create_component_group(row)
            self._components_layout.addWidget(group)

        self._components_layout.addStretch(1)

    def _create_component_group(self, row: ComponentRow) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox(row.component.component_type)

        layout = QtWidgets.QVBoxLayout(group)
        layout.setContentsMargins(
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_SMALL,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
        )
        layout.setSpacing(Sizes.SPACING_SMALL)

        # 头部：折叠按钮 + 标签 + 可选删除按钮
        header_layout = QtWidgets.QHBoxLayout()

        toggle_button = QtWidgets.QToolButton(group)
        toggle_button.setCheckable(True)
        toggle_button.setChecked(True)
        toggle_button.setArrowType(QtCore.Qt.ArrowType.DownArrow)
        toggle_button.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly
        )
        toggle_button.setAutoRaise(True)
        toggle_button.setStyleSheet(
            "QToolButton { background: transparent; border: none; padding: 0px; }"
        )
        header_layout.addWidget(toggle_button)

        title_label = QtWidgets.QLabel(row.label)
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)

        can_remove = not self._is_read_only and not (
            self.object_type != "template" and row.source == "inherited"
        )
        if can_remove:
            remove_button = QtWidgets.QPushButton("删除组件", group)
            remove_button.setObjectName("ComponentRemoveButton")
            remove_button.clicked.connect(
                partial(self._remove_component_by_row, row)
            )
            header_layout.addWidget(remove_button)

        layout.addLayout(header_layout)

        # 折叠主体区域：描述 + 配置表单或占位说明
        body_widget = QtWidgets.QWidget(group)
        body_layout = QtWidgets.QVBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(Sizes.SPACING_SMALL)

        # 描述：优先使用组件规则表中的描述，其次使用模型上的 description
        definition = COMPONENT_DEFINITIONS.get(row.component.component_type, {})
        description_text = (
            str(definition.get("description") or "").strip()
            or str(row.component.description or "").strip()
        )
        if description_text:
            desc_label = QtWidgets.QLabel(description_text, body_widget)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
            body_layout.addWidget(desc_label)

        # 配置表单区域：尝试根据组件类型创建表单，失败则展示占位说明
        form_widget = create_component_form(
            row.component.component_type,
            row.component.settings,
            body_widget,
            resource_manager=self.resource_manager,
            package_index_manager=self.package_index_manager,
        )
        if form_widget is not None:
            body_layout.addWidget(form_widget)
        else:
            placeholder_label = QtWidgets.QLabel(
                "当前组件的详细配置暂未在此面板开放编辑，如需修改请在相关管理配置或专用面板中完成。",
                body_widget,
            )
            placeholder_label.setWordWrap(True)
            placeholder_label.setStyleSheet(
                f"color: {Colors.TEXT_HINT}; font-size: 9pt;"
            )
            body_layout.addWidget(placeholder_label)

        layout.addWidget(body_widget)

        def _on_toggle(checked: bool) -> None:
            body_widget.setVisible(checked)
            toggle_button.setArrowType(
                QtCore.Qt.ArrowType.DownArrow
                if checked
                else QtCore.Qt.ArrowType.RightArrow
            )

        toggle_button.toggled.connect(_on_toggle)

        return group

    def _add_component(self) -> None:
        if not self.current_object or not self.service:
            return
        if self._component_type_cache is None:
            self._component_type_cache = list(get_all_component_types())

        available_types = list(self._component_type_cache)

        # 掉落物：仅允许四种组件类型
        if self._is_drop_item_context():
            allowed_for_drop = ["特效播放", "碰撞触发源", "铭牌", "自定义变量"]
            available_types = [t for t in available_types if t in allowed_for_drop]
            if not available_types:
                show_warning_dialog(
                    self,
                    "不可用",
                    "掉落物的组件仅支持：特效播放、碰撞触发源、铭牌、自定义变量。",
                )
                return

        if not available_types:
            return

        builder = ContextMenuBuilder(self)
        selected_type_holder: list[str] = []

        def _on_type_selected(component_type: str) -> None:
            selected_type_holder.clear()
            selected_type_holder.append(component_type)

        for component_type in available_types:
            builder.add_action(
                component_type,
                lambda ct=component_type: _on_type_selected(ct),
            )

        builder.exec_at_global_pos(QtGui.QCursor.pos())
        if not selected_type_holder:
            return

        selected_type = selected_type_holder[0]

        comp = ComponentConfig(component_type=selected_type)
        if self.service.add_component(self.current_object, self.object_type, comp):
            self._rebuild_component_cards()
            self.data_changed.emit()

    def _remove_component(self) -> None:
        if not self.current_object or not self.service:
            return

        rows = list(self._iter_component_rows())
        if not rows:
            return

        # 仅允许删除非继承组件
        deletable_rows = [
            row
            for row in rows
            if not (self.object_type != "template" and row.source == "inherited")
        ]
        if not deletable_rows:
            show_warning_dialog(
                self,
                "无法删除",
                "当前对象的组件均来自模板继承，请在模板面板中修改。",
            )
            return

        labels = [row.label for row in deletable_rows]
        selected_label = input_dialogs.prompt_item(
            self,
            "删除组件",
            "选择要删除的组件：",
            labels,
        )
        if selected_label is None:
            return

        try:
            index = labels.index(selected_label)
        except ValueError:
            return

        selected_row = deletable_rows[index]
        self._remove_component_by_row(selected_row)

    def _remove_component_by_row(self, row: ComponentRow) -> None:
        if not self.current_object or not self.service:
            return
        if row.source == "inherited" and self.object_type != "template":
            show_warning_dialog(
                self,
                "无法删除",
                "无法删除从模板继承的组件，请在模板面板中修改。",
            )
            return
        if self.service.remove_component(
            self.current_object,
            self.object_type,
            row.component,
            row.source,
        ):
            self._rebuild_component_cards()
            self.data_changed.emit()
            ToastNotification.show_message(self, "已删除组件。", "success")

    def _iter_component_rows(self) -> Iterable[ComponentRow]:
        if not self.current_object:
            return []
        template_components, instance_components, level_components = self._collect_context_lists(
            template_attr="default_components",
            instance_attr="additional_components",
            level_attr="additional_components",
        )
        if self.object_type == "template":
            for comp in template_components:
                yield ComponentRow(comp, comp.component_type, "template")
            return
        if self.object_type == "level_entity":
            for comp in level_components:
                yield ComponentRow(
                    comp, f"【额外】 ⚙️ {comp.component_type}", "additional"
                )
            return
        for comp in template_components:
            yield ComponentRow(
                comp,
                f"🔗 [继承] ⚙️ {comp.component_type}",
                "inherited",
                foreground=Colors.TEXT_DISABLED,
            )
        for comp in instance_components:
            yield ComponentRow(
                comp, f"【额外】 ⚙️ {comp.component_type}", "additional"
            )

    # 只读模式 ---------------------------------------------------------------
    def set_read_only(self, read_only: bool) -> None:
        """切换组件标签页的只读状态。

        只读模式下：
        - 禁用“添加组件”按钮；
        - 组件列表以分组卡片形式只读展示当前继承/额外组件，不在只读模式下提供删除入口。
        """
        self._is_read_only = read_only
        if self._add_button is not None:
            self._add_button.setEnabled(not read_only)
        # 重新构建组件卡片以根据只读状态更新内部删除按钮
        self._rebuild_component_cards()



