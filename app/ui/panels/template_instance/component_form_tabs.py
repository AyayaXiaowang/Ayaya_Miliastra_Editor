"""“选项卡”通用组件表单。"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from PyQt6 import QtWidgets

from app.ui.dialogs.graph_selection_dialog import GraphSelectionDialog
from app.ui.foundation import dialog_utils
from app.ui.foundation.theme_manager import ThemeManager
from app.ui.forms.schema_bound_form import FormComboOption, FormFieldSpec, SchemaBoundForm


class TabConfigForm(QtWidgets.QWidget):
    """“选项卡”组件配置表单。

    对应通用组件中的“选项卡”配置，可为同一个造物实体配置多个选项卡：
    - 每个选项卡有独立的序号、初始生效开关与排序等级；
    - 每个选项卡可以挂接一个本地过滤器节点图（客户端），用于判定“对谁显示/对谁不显示”。

    settings 结构与 `engine.configs.components.tab_configs.TabComponentConfig.to_dict()` 对齐：
    - settings["选项卡列表"] -> 若干 {选项序号, 选项卡图标, 初始生效, 排序等级, 本地过滤器, 过滤器节点图}
    - settings["初始生效选项卡"] -> 初始生效选项卡序号列表
    - settings["触发区域"]       -> 触发区域字典列表（当前表单仅保持原状，不提供编辑 UI）
    """

    def __init__(
        self,
        settings: Dict[str, object],
        parent: QtWidgets.QWidget,
        *,
        on_settings_changed: Optional[Callable[[], None]] = None,
        resource_manager: Optional[object] = None,
        package_index_manager: Optional[object] = None,
    ) -> None:
        super().__init__(parent)
        self._settings: Dict[str, object] = settings
        self._on_settings_changed = on_settings_changed
        self._resource_manager = resource_manager
        self._package_index_manager = package_index_manager
        self._tab_dicts: List[Dict[str, Any]] = []
        self._cards_layout: Optional[QtWidgets.QVBoxLayout] = None

        self._init_base_structure()
        self._build_ui()
        self._rebuild_cards()

    # ------------------------------------------------------------------ 基础结构与加载

    def _init_base_structure(self) -> None:
        """确保 settings 中存在选项卡所需的基础字段。"""
        raw_list = self._settings.get("选项卡列表")
        if isinstance(raw_list, list):
            self._tab_dicts = [
                item if isinstance(item, dict) else {}
                for item in raw_list
            ]
        else:
            self._tab_dicts = []
        self._settings["选项卡列表"] = self._tab_dicts

        initial_active_tabs = self._settings.get("初始生效选项卡")
        if not isinstance(initial_active_tabs, list):
            self._settings["初始生效选项卡"] = []

        raw_trigger_areas = self._settings.get("触发区域")
        if isinstance(raw_trigger_areas, list):
            self._settings["触发区域"] = list(raw_trigger_areas)
        else:
            self._settings["触发区域"] = []

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(6)

        hint_label = QtWidgets.QLabel(
            "为当前造物配置多个选项卡，每个选项卡可以绑定一个本地过滤器节点图（客户端），"
            "用于按玩家条件决定“对谁显示/对谁不显示”。",
            self,
        )
        hint_label.setWordWrap(True)
        from app.ui.foundation.theme_manager import Colors

        hint_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        layout.addWidget(hint_label)

        toolbar_layout = QtWidgets.QHBoxLayout()
        add_button = QtWidgets.QPushButton("+ 添加选项卡", self)
        add_button.clicked.connect(self._on_add_tab_clicked)
        toolbar_layout.addWidget(add_button)
        toolbar_layout.addStretch(1)
        layout.addLayout(toolbar_layout)

        container = QtWidgets.QWidget(self)
        cards_layout = QtWidgets.QVBoxLayout(container)
        cards_layout.setContentsMargins(0, 4, 0, 0)
        cards_layout.setSpacing(6)
        layout.addWidget(container)

        self._cards_layout = cards_layout

    def _clear_cards(self) -> None:
        if self._cards_layout is None:
            return
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _rebuild_cards(self) -> None:
        if self._cards_layout is None:
            return

        self._clear_cards()

        if not self._tab_dicts:
            self._tab_dicts.append(self._create_default_tab(len(self._tab_dicts)))

        self._renumber_tabs()

        for index, tab_dict in enumerate(self._tab_dicts, start=1):
            card = self._create_card_widget(index, tab_dict)
            self._cards_layout.addWidget(card)

        self._cards_layout.addStretch(1)

    def _create_default_tab(self, existing_count: int) -> Dict[str, Any]:
        tab_index = existing_count + 1
        return {
            "选项序号": tab_index,
            "选项卡图标": "",
            "初始生效": tab_index == 1,
            "排序等级": 1,
            "本地过滤器": "",
            "过滤器节点图": "",
        }

    def _renumber_tabs(self) -> None:
        for index, tab_dict in enumerate(self._tab_dicts, start=1):
            if not isinstance(tab_dict, dict):
                continue
            tab_dict["选项序号"] = index
            if "排序等级" not in tab_dict:
                tab_dict["排序等级"] = 1
            if "选项卡图标" not in tab_dict or not isinstance(tab_dict["选项卡图标"], str):
                tab_dict["选项卡图标"] = ""
            if "本地过滤器" not in tab_dict or not isinstance(tab_dict["本地过滤器"], str):
                tab_dict["本地过滤器"] = ""
            if "过滤器节点图" not in tab_dict or not isinstance(tab_dict["过滤器节点图"], str):
                tab_dict["过滤器节点图"] = ""
            if "初始生效" not in tab_dict:
                tab_dict["初始生效"] = False

        self._sync_initial_active_indices()

    def _sync_initial_active_indices(self) -> None:
        active_indices: List[int] = []
        for tab_dict in self._tab_dicts:
            if not isinstance(tab_dict, dict):
                continue
            is_active = tab_dict.get("初始生效", False) is True
            index_raw = tab_dict.get("选项序号")
            if is_active and isinstance(index_raw, int):
                active_indices.append(index_raw)
        self._settings["初始生效选项卡"] = active_indices

    def _notify_settings_changed(self) -> None:
        if self._on_settings_changed is not None:
            self._on_settings_changed()

    # ------------------------------------------------------------------ 卡片与字段绑定

    def _create_card_widget(self, index: int, tab_dict: Dict[str, Any]) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox(f"选项卡 序号: {index}", self)

        main_layout = QtWidgets.QVBoxLayout(group)
        main_layout.setContentsMargins(8, 6, 8, 8)
        main_layout.setSpacing(4)

        header_layout = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("选项卡", group)
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)

        remove_button = QtWidgets.QPushButton("删除此选项卡", group)
        remove_button.clicked.connect(lambda: self._on_remove_tab_clicked(tab_dict))
        header_layout.addWidget(remove_button)

        main_layout.addLayout(header_layout)

        form_layout = QtWidgets.QFormLayout()
        form_layout.setContentsMargins(0, 4, 0, 0)
        form_layout.setSpacing(4)

        index_label = QtWidgets.QLabel(str(index), group)
        form_layout.addRow("选项序号:", index_label)

        def _on_any_field_changed(_: Any) -> None:
            self._notify_settings_changed()

        def _on_initial_active_changed(_: Any) -> None:
            self._sync_initial_active_indices()
            self._notify_settings_changed()

        field_specs = [
            FormFieldSpec(
                key="选项卡图标",
                label="选项卡图标:",
                kind="line_edit",
                default="",
                placeholder="可选：图标资源 ID 或名称",
                on_changed=_on_any_field_changed,
            ),
            FormFieldSpec(
                key="排序等级",
                label="排序等级:",
                kind="int_spin",
                default=1,
                minimum_int=-9999,
                maximum_int=9999,
                on_changed=_on_any_field_changed,
            ),
            FormFieldSpec(
                key="初始生效",
                label="初始生效:",
                kind="bool",
                default=False,
                use_toggle_switch=True,
                on_changed=_on_initial_active_changed,
            ),
            FormFieldSpec(
                key="本地过滤器",
                label="本地过滤器:",
                kind="combo",
                default="",
                combo_options=[
                    FormComboOption("无", ""),
                    FormComboOption("布尔过滤器", "布尔过滤器"),
                ],
                on_changed=_on_any_field_changed,
            ),
        ]

        schema_form = SchemaBoundForm(group, field_specs, tab_dict)
        schema_form.build_into(form_layout)
        # 绑定器需要保活：信号回调引用实例方法，避免局部变量被提前回收
        group._schema_form = schema_form  # type: ignore[attr-defined]

        filter_graph_row = QtWidgets.QWidget(group)
        filter_graph_layout = QtWidgets.QHBoxLayout(filter_graph_row)
        filter_graph_layout.setContentsMargins(0, 0, 0, 0)
        filter_graph_layout.setSpacing(4)

        filter_graph_edit = QtWidgets.QLineEdit(filter_graph_row)
        filter_graph_edit.setStyleSheet(ThemeManager.input_style())
        filter_graph_edit.setPlaceholderText("点击右侧按钮选择节点图，或手动输入ID")
        filter_graph_value_raw = tab_dict.get("过滤器节点图", "")
        filter_graph_value = (
            str(filter_graph_value_raw) if isinstance(filter_graph_value_raw, str) else ""
        )
        filter_graph_edit.setText(filter_graph_value)
        filter_graph_edit.textChanged.connect(
            lambda text: self._on_filter_graph_changed(tab_dict, text)
        )
        filter_graph_layout.addWidget(filter_graph_edit, 1)

        filter_graph_button = QtWidgets.QPushButton("点击选择", filter_graph_row)
        filter_graph_button.setStyleSheet(ThemeManager.button_style())
        filter_graph_button.clicked.connect(
            lambda: self._on_select_filter_graph_clicked(tab_dict, filter_graph_edit)
        )
        filter_graph_layout.addWidget(filter_graph_button)

        form_layout.addRow("过滤器节点图:", filter_graph_row)

        main_layout.addLayout(form_layout)

        return group

    # ------------------------------------------------------------------ 事件处理

    def _on_add_tab_clicked(self) -> None:
        new_tab = self._create_default_tab(len(self._tab_dicts))
        self._tab_dicts.append(new_tab)
        self._renumber_tabs()
        self._rebuild_cards()
        self._notify_settings_changed()

    def _on_remove_tab_clicked(self, tab_dict: Dict[str, Any]) -> None:
        if not self._tab_dicts:
            return
        if len(self._tab_dicts) == 1:
            dialog_utils.show_warning_dialog(self, "无法删除", "至少需要保留一个选项卡。")
            return
        if tab_dict not in self._tab_dicts:
            return
        self._tab_dicts.remove(tab_dict)
        self._renumber_tabs()
        self._rebuild_cards()
        self._notify_settings_changed()

    def _on_filter_graph_changed(self, tab_dict: Dict[str, Any], text: str) -> None:
        tab_dict["过滤器节点图"] = text.strip()
        self._notify_settings_changed()

    def _on_select_filter_graph_clicked(
        self,
        tab_dict: Dict[str, Any],
        line_edit: QtWidgets.QLineEdit,
    ) -> None:
        if not self._resource_manager or not self._package_index_manager:
            dialog_utils.show_warning_dialog(self, "未配置", "当前环境未提供节点图库资源管理器。")
            return
        dialog = GraphSelectionDialog(
            resource_manager=self._resource_manager,
            package_index_manager=self._package_index_manager,
            parent=self,
            allowed_graph_type="client",
            allowed_folder_prefix="本地过滤器节点图",
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        graph_id = dialog.get_selected_graph_id()
        if not graph_id:
            return
        line_edit.setText(graph_id)
        self._on_filter_graph_changed(tab_dict, graph_id)


__all__ = ["TabConfigForm"]


