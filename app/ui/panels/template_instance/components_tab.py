"""Components tab for template/instance panel - Inspector 风格的通用组件管理。"""

from __future__ import annotations

from dataclasses import dataclass
import json
from functools import partial
from typing import Dict, Iterable, Optional, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets

from engine.configs.rules import COMPONENT_DEFINITIONS, get_entity_allowed_components
from engine.graph.models.entity_templates import get_all_component_types
from engine.graph.models.package_model import ComponentConfig, InstanceConfig, TemplateConfig
from app.ui.foundation.context_menu_builder import ContextMenuBuilder
from app.ui.foundation.debounce import Debouncer
from app.ui.foundation.dialog_utils import ask_yes_no_dialog, show_warning_dialog
from app.ui.foundation.scroll_helpers import scroll_to_bottom
from app.ui.foundation.theme_manager import Colors, Sizes, ThemeManager
from app.ui.foundation.toast_notification import ToastNotification
from app.ui.panels.panel_scaffold import build_scrollable_column
from app.ui.panels.template_instance.component_form_factory import create_component_form
from app.ui.panels.template_instance.component_picker_dialog import ComponentPickerDialog
from app.ui.panels.template_instance.tab_base import TemplateInstanceTabBase


@dataclass(frozen=True)
class ComponentRow:
    component: ComponentConfig
    label: str
    source: str  # template / inherited / additional
    foreground: Optional[str] = None


ComponentKey = Tuple[str, str]  # (source, component_type)


class ComponentsTab(TemplateInstanceTabBase):
    """通用组件标签页（Inspector 风格）。

    核心目标：
    - 以“可滚动卡片列表”呈现组件
    - 组件卡片：折叠/菜单/摘要/（可选）详细编辑
    - 底部固定按钮：添加通用组件（带搜索的选择器）
    """

    _CLIPBOARD_MIME = "application/x-ugc-component-settings+json"
    _EXCLUDED_COMPONENT_TYPES_FOR_PICKER = {"自定义变量"}  # 本项目自定义变量已独立为变量标签页

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._component_type_cache: Optional[list[str]] = None
        self._is_read_only: bool = False

        self._scroll_area: Optional[QtWidgets.QScrollArea] = None
        self._components_container: Optional[QtWidgets.QWidget] = None
        self._components_layout: Optional[QtWidgets.QVBoxLayout] = None
        self._add_button: Optional[QtWidgets.QPushButton] = None

        self._card_widgets: dict[ComponentKey, QtWidgets.QWidget] = {}
        self._summary_labels: dict[ComponentKey, QtWidgets.QLabel] = {}
        self._expanded_state: dict[ComponentKey, bool] = {}
        self._details_state: dict[ComponentKey, bool] = {}

        self._settings_change_debouncer = Debouncer(self)
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        scroll_area, container, column_layout = build_scrollable_column(
            self,
            spacing=Sizes.SPACING_MEDIUM,
            margins=(
                Sizes.SPACING_MEDIUM,
                Sizes.SPACING_MEDIUM,
                Sizes.SPACING_MEDIUM,
                Sizes.SPACING_MEDIUM,
            ),
            add_trailing_stretch=False,
        )
        root_layout.addWidget(scroll_area, 1)

        self._scroll_area = scroll_area
        self._components_container = container
        self._components_layout = column_layout

        bottom_bar = QtWidgets.QFrame(self)
        bottom_bar.setObjectName("ComponentsBottomActionBar")
        bottom_bar.setStyleSheet(
            f"""
            QFrame#ComponentsBottomActionBar {{
                background-color: {Colors.BG_MAIN};
                border-top: 1px solid {Colors.BORDER_LIGHT};
            }}
            """
        )
        bottom_layout = QtWidgets.QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_SMALL,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_SMALL,
        )
        bottom_layout.setSpacing(Sizes.SPACING_SMALL)

        add_button = QtWidgets.QPushButton("+ 添加通用组件", bottom_bar)
        add_button.setMinimumHeight(max(Sizes.INPUT_HEIGHT, 34))
        add_button.clicked.connect(self._add_component)
        bottom_layout.addWidget(add_button, 1)

        self._add_button = add_button
        root_layout.addWidget(bottom_bar, 0)

    # ------------------------------------------------------------------ 生命周期钩子
    def _reset_ui(self) -> None:
        self._clear_component_cards()

    def _refresh_ui(self) -> None:
        self._rebuild_component_cards()
        self._apply_read_only_state()

    # ------------------------------------------------------------------ 卡片构建
    def _clear_component_cards(self) -> None:
        if self._components_layout is None:
            return
        while self._components_layout.count():
            item = self._components_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._card_widgets.clear()
        self._summary_labels.clear()

    def _rebuild_component_cards(self) -> None:
        if self._components_layout is None:
            return
        self._clear_component_cards()

        rows = list(self._iter_component_rows())
        current_keys = {(row.source, row.component.component_type) for row in rows}
        self._expanded_state = {
            key: value for key, value in self._expanded_state.items() if key in current_keys
        }
        self._details_state = {
            key: value for key, value in self._details_state.items() if key in current_keys
        }

        if not rows:
            placeholder = QtWidgets.QLabel(
                "尚未为当前对象添加通用组件。\n点击下方“+ 添加通用组件”开始挂载。",
                self,
            )
            placeholder.setObjectName("ComponentsEmptyPlaceholder")
            placeholder.setWordWrap(True)
            placeholder.setAlignment(
                QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop
            )
            placeholder.setStyleSheet(ThemeManager.hint_text_style())
            self._components_layout.addWidget(placeholder)
            self._components_layout.addStretch(1)
            return

        for row in rows:
            key: ComponentKey = (row.source, row.component.component_type)
            card = self._create_component_card(row, key)
            self._card_widgets[key] = card
            self._components_layout.addWidget(card)

        self._components_layout.addStretch(1)

    def _create_component_card(self, row: ComponentRow, key: ComponentKey) -> QtWidgets.QWidget:
        card = QtWidgets.QFrame(self._components_container)
        card.setObjectName("ComponentCard")
        card.setStyleSheet(
            f"""
            QFrame#ComponentCard {{
                background-color: {Colors.BG_CARD};
                border-radius: {Sizes.RADIUS_MEDIUM}px;
                border: 1px solid {Colors.BORDER_LIGHT};
            }}
            """
        )

        can_edit = (not self._is_read_only) and not (
            self.object_type != "template" and row.source == "inherited"
        )
        can_remove = can_edit

        expanded = self._expanded_state.get(key, True)
        show_details = self._details_state.get(key, False)

        main_layout = QtWidgets.QVBoxLayout(card)
        main_layout.setContentsMargins(
            Sizes.PADDING_LARGE,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_LARGE,
            Sizes.PADDING_MEDIUM,
        )
        main_layout.setSpacing(Sizes.SPACING_SMALL)

        # Header --------------------------------------------------------
        header_row = QtWidgets.QWidget(card)
        header_layout = QtWidgets.QHBoxLayout(header_row)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(Sizes.SPACING_SMALL)

        collapse_button = QtWidgets.QToolButton(header_row)
        collapse_button.setCheckable(True)
        collapse_button.setChecked(expanded)
        collapse_button.setAutoRaise(True)
        collapse_button.setText("▼" if expanded else "▶")
        collapse_button.setStyleSheet(
            "QToolButton { background: transparent; border: none; padding: 0px; }"
        )
        header_layout.addWidget(collapse_button)

        title_label = QtWidgets.QLabel(row.label, header_row)
        title_font = title_label.font()
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_color = row.foreground or Colors.TEXT_PRIMARY
        title_label.setStyleSheet(f"color: {title_color};")
        title_label.setWordWrap(True)
        header_layout.addWidget(title_label, 1)

        menu_button = QtWidgets.QToolButton(header_row)
        menu_button.setAutoRaise(True)
        menu_button.setText("⋯")
        menu_button.setToolTip("组件操作")
        header_layout.addWidget(menu_button)

        main_layout.addWidget(header_row)

        # Body ----------------------------------------------------------
        body_widget = QtWidgets.QWidget(card)
        body_layout = QtWidgets.QVBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(Sizes.SPACING_SMALL)

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

        if row.component.component_type == "自定义变量":
            migration_hint = QtWidgets.QLabel(
                "提示：本项目的“自定义变量”已迁移为独立标签页（关卡变量代码定义 + 实例覆写）。\n"
                "此处仅作为兼容展示（如遇旧数据）。",
                body_widget,
            )
            migration_hint.setWordWrap(True)
            migration_hint.setStyleSheet(f"color: {Colors.TEXT_HINT};")
            body_layout.addWidget(migration_hint)

        summary_label = QtWidgets.QLabel(self._build_summary_text(row.component), body_widget)
        summary_label.setWordWrap(True)
        summary_label.setStyleSheet(f"color: {Colors.TEXT_HINT};")
        body_layout.addWidget(summary_label)
        self._summary_labels[key] = summary_label

        details_container = QtWidgets.QWidget(body_widget)
        details_layout = QtWidgets.QVBoxLayout(details_container)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(Sizes.SPACING_SMALL)

        form_widget = create_component_form(
            row.component.component_type,
            row.component.settings,
            details_container,
            on_settings_changed=partial(self._on_component_settings_changed, key),
            resource_manager=self.resource_manager,
            package_index_manager=self.package_index_manager,
        )
        if form_widget is not None:
            details_layout.addWidget(form_widget)
        else:
            placeholder_label = QtWidgets.QLabel(
                "当前组件暂无专用编辑器。\n"
                "你仍可以通过节点图/管理配置等入口配置其更复杂的参数。",
                details_container,
            )
            placeholder_label.setWordWrap(True)
            placeholder_label.setStyleSheet(f"color: {Colors.TEXT_HINT}; font-size: 9pt;")
            details_layout.addWidget(placeholder_label)

        details_container.setVisible(bool(show_details))
        details_container.setEnabled(bool(can_edit))
        body_layout.addWidget(details_container)

        body_widget.setVisible(bool(expanded))
        main_layout.addWidget(body_widget)

        # Footer --------------------------------------------------------
        footer_row = QtWidgets.QWidget(card)
        footer_layout = QtWidgets.QHBoxLayout(footer_row)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(Sizes.SPACING_SMALL)

        detail_button = QtWidgets.QPushButton("详细编辑" if not show_details else "收起编辑", footer_row)
        footer_layout.addWidget(detail_button)
        footer_layout.addStretch(1)
        main_layout.addWidget(footer_row)

        # 交互：折叠/展开
        def _on_collapsed_toggled(checked: bool) -> None:
            self._expanded_state[key] = bool(checked)
            body_widget.setVisible(bool(checked))
            collapse_button.setText("▼" if checked else "▶")

        collapse_button.toggled.connect(_on_collapsed_toggled)

        # 交互：详细编辑（同卡片内展开）
        def _toggle_details() -> None:
            self._details_state[key] = not bool(self._details_state.get(key, False))
            details_container.setVisible(bool(self._details_state[key]))
            detail_button.setText("收起编辑" if self._details_state[key] else "详细编辑")
            if not self._expanded_state.get(key, True):
                collapse_button.setChecked(True)

        detail_button.clicked.connect(_toggle_details)

        # 交互：菜单
        def _open_menu() -> None:
            builder = ContextMenuBuilder(self)

            builder.add_action(
                "删除组件",
                partial(self._remove_component_by_row, row),
                enabled=bool(can_remove),
            )
            builder.add_action(
                "重置参数",
                partial(self._reset_component_settings, key, row),
                enabled=bool(can_edit),
            )
            builder.add_separator()
            builder.add_action(
                "复制配置",
                partial(self._copy_component_settings, row),
                enabled=True,
            )
            builder.add_action(
                "粘贴配置",
                partial(self._paste_component_settings, key, row),
                enabled=bool(can_edit),
            )

            builder.exec_global(QtGui.QCursor.pos())

        menu_button.clicked.connect(_open_menu)

        return card

    # ------------------------------------------------------------------ 摘要文本
    @staticmethod
    def _build_summary_text(component: ComponentConfig) -> str:
        settings = component.settings if isinstance(component.settings, dict) else {}
        component_type = str(component.component_type or "")

        if component_type == "背包":
            cap_raw = settings.get("背包容量", 20)
            cap = int(cap_raw) if isinstance(cap_raw, int) else 20
            return f"背包容量: {cap}"

        if component_type == "铭牌":
            raw_list = settings.get("铭牌配置列表", [])
            count = len(raw_list) if isinstance(raw_list, list) else 0
            return f"铭牌配置数量: {count}"

        if component_type == "选项卡":
            raw_list = settings.get("选项卡列表", [])
            count = len(raw_list) if isinstance(raw_list, list) else 0
            return f"选项卡数量: {count}"

        if component_type == "自定义变量":
            raw_list = settings.get("已定义自定义变量", [])
            count = len(raw_list) if isinstance(raw_list, list) else 0
            return f"变量数量: {count}"

        if not settings:
            return "尚未配置参数。"
        return f"已配置字段: {len(settings)}"

    # ------------------------------------------------------------------ 组件增删改
    def _add_component(self) -> None:
        if not self.current_object or not self.service:
            return
        if self._is_read_only:
            return

        available_types = self._get_available_component_types_for_context()
        if not available_types:
            show_warning_dialog(self, "不可用", "当前上下文没有可添加的通用组件类型。")
            return

        dialog = ComponentPickerDialog(
            available_types,
            COMPONENT_DEFINITIONS,
            parent=self,
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        selected_type = dialog.get_selected_component_type()
        if not selected_type:
            return

        comp = ComponentConfig(component_type=selected_type)
        if self.service.add_component(self.current_object, self.object_type, comp):
            focus_key: ComponentKey
            if self.object_type == "template":
                focus_key = ("template", selected_type)
            else:
                focus_key = ("additional", selected_type)
            self._rebuild_component_cards()
            self.data_changed.emit()
            self._scroll_to_component_card(focus_key)
            ToastNotification.show_message(self, f"已添加组件：{selected_type}", "success")

    def _remove_component_by_row(self, row: ComponentRow) -> None:
        if not self.current_object or not self.service:
            return

        if row.source == "inherited" and self.object_type != "template":
            show_warning_dialog(self, "无法删除", "继承自模板的组件无法在实体面板中删除，请在模板面板修改。")
            return

        should_remove = ask_yes_no_dialog(
            self,
            "确认删除组件",
            f"确定要删除组件“{row.component.component_type}”吗？",
            default_yes=False,
        )
        if not should_remove:
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

    def _reset_component_settings(self, key: ComponentKey, row: ComponentRow) -> None:
        should_reset = ask_yes_no_dialog(
            self,
            "重置参数",
            f"确定要重置组件“{row.component.component_type}”的配置参数吗？\n（会清空 settings 字段）",
            default_yes=False,
        )
        if not should_reset:
            return
        row.component.settings = {}
        self._refresh_summary_label(key, row.component)
        self._schedule_settings_changed()
        ToastNotification.show_message(self, "已重置组件参数。", "success")

    def _on_component_settings_changed(self, key: ComponentKey) -> None:
        if self._is_read_only:
            return
        self._schedule_settings_changed()
        card_row = self._get_row_by_key(key)
        if card_row is None:
            return
        self._refresh_summary_label(key, card_row.component)

    def _schedule_settings_changed(self) -> None:
        self._settings_change_debouncer.debounce(200, self._emit_data_changed)

    def _emit_data_changed(self) -> None:
        self.data_changed.emit()

    def _refresh_summary_label(self, key: ComponentKey, component: ComponentConfig) -> None:
        label = self._summary_labels.get(key)
        if label is None:
            return
        label.setText(self._build_summary_text(component))

    def _get_row_by_key(self, key: ComponentKey) -> Optional[ComponentRow]:
        for row in self._iter_component_rows():
            if (row.source, row.component.component_type) == key:
                return row
        return None

    # ------------------------------------------------------------------ 复制/粘贴（剪贴板）
    def _copy_component_settings(self, row: ComponentRow) -> None:
        payload = {
            "component_type": row.component.component_type,
            "settings": row.component.settings if isinstance(row.component.settings, dict) else {},
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        mime = QtCore.QMimeData()
        mime.setData(self._CLIPBOARD_MIME, text.encode("utf-8"))
        mime.setText(text)
        QtWidgets.QApplication.clipboard().setMimeData(mime)
        ToastNotification.show_message(self, "已复制组件配置到剪贴板。", "success")

    def _paste_component_settings(self, key: ComponentKey, row: ComponentRow) -> None:
        clipboard = QtWidgets.QApplication.clipboard()
        mime = clipboard.mimeData()
        if mime is None or (not mime.hasFormat(self._CLIPBOARD_MIME)):
            show_warning_dialog(self, "无法粘贴", "剪贴板中没有可用的组件配置。")
            return

        raw_bytes = bytes(mime.data(self._CLIPBOARD_MIME))
        text = raw_bytes.decode("utf-8")
        payload = json.loads(text)
        if not isinstance(payload, dict):
            show_warning_dialog(self, "无法粘贴", "剪贴板数据格式不正确。")
            return
        payload_type = payload.get("component_type")
        if payload_type != row.component.component_type:
            show_warning_dialog(
                self,
                "无法粘贴",
                f"剪贴板配置属于“{payload_type}”，当前组件为“{row.component.component_type}”。",
            )
            return
        settings = payload.get("settings")
        if not isinstance(settings, dict):
            show_warning_dialog(self, "无法粘贴", "剪贴板配置缺少 settings 字段或类型不正确。")
            return

        row.component.settings = dict(settings)
        self._refresh_summary_label(key, row.component)
        self._schedule_settings_changed()
        ToastNotification.show_message(self, "已粘贴组件配置。", "success")

    # ------------------------------------------------------------------ 组件列表
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
                yield ComponentRow(comp, f"⚙️ {comp.component_type}", "template")
            return
        if self.object_type == "level_entity":
            for comp in level_components:
                yield ComponentRow(comp, f"【额外】 ⚙️ {comp.component_type}", "additional")
            return
        for comp in template_components:
            yield ComponentRow(
                comp,
                f"🔗 [继承] ⚙️ {comp.component_type}",
                "inherited",
                foreground=Colors.TEXT_DISABLED,
            )
        for comp in instance_components:
            yield ComponentRow(comp, f"【额外】 ⚙️ {comp.component_type}", "additional")

    # ------------------------------------------------------------------ 可添加组件类型（按上下文过滤）
    def _get_available_component_types_for_context(self) -> list[str]:
        if self._component_type_cache is None:
            self._component_type_cache = list(get_all_component_types())

        all_types = list(self._component_type_cache)
        entity_type = self._get_entity_type_for_context()
        allowed = get_entity_allowed_components(entity_type) if entity_type else []
        allowed_set = set(str(x) for x in allowed) if isinstance(allowed, list) else set()

        if allowed_set:
            available = [t for t in all_types if t in allowed_set]
        else:
            available = list(all_types)

        # 掉落物：收窄组件类型（避免出现大量与掉落物无关的组件）
        if self._is_drop_item_context():
            allowed_for_drop = ["特效播放", "碰撞触发源", "铭牌"]
            available = [t for t in available if t in allowed_for_drop]

        available = [t for t in available if t not in self._EXCLUDED_COMPONENT_TYPES_FOR_PICKER]
        return available

    def _get_entity_type_for_context(self) -> str:
        obj = self.current_object
        if obj is None:
            return ""
        if self.object_type == "template" and isinstance(obj, TemplateConfig):
            return str(obj.entity_type or "")
        if self.object_type == "instance" and isinstance(obj, InstanceConfig):
            template_obj = self._template_for_instance(obj)
            if isinstance(template_obj, TemplateConfig):
                return str(template_obj.entity_type or "")
            metadata = getattr(obj, "metadata", {}) or {}
            if isinstance(metadata, dict):
                value = metadata.get("entity_type", "")
                return str(value or "")
            return ""
        if self.object_type == "level_entity" and isinstance(obj, InstanceConfig):
            metadata = getattr(obj, "metadata", {}) or {}
            if isinstance(metadata, dict):
                value = metadata.get("entity_type", "关卡")
                return str(value or "关卡")
            return "关卡"
        return ""

    # ------------------------------------------------------------------ 滚动定位
    def _scroll_to_component_card(self, key: ComponentKey) -> None:
        if self._scroll_area is None:
            return
        card = self._card_widgets.get(key)
        if card is not None:
            self._scroll_area.ensureWidgetVisible(card)
            return
        scroll_to_bottom(self._scroll_area)

    # ------------------------------------------------------------------ 只读模式
    def set_read_only(self, read_only: bool) -> None:
        self._is_read_only = bool(read_only)
        self._apply_read_only_state()
        self._rebuild_component_cards()

    def _apply_read_only_state(self) -> None:
        if self._add_button is not None:
            self._add_button.setEnabled((not self._is_read_only) and bool(self.current_object))



