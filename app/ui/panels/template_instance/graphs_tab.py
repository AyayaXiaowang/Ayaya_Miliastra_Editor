"""Graphs tab with list management and exposed variable overrides."""

from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass
from typing import Iterable, Optional, Union, Mapping

from PyQt6 import QtCore, QtGui, QtWidgets

from engine.graph.models.entity_templates import get_all_variable_types
from engine.graph.models.graph_config import GraphConfig
from engine.graph.models.package_model import GraphVariableConfig
from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.package_view import PackageView
from engine.resources.resource_manager import ResourceManager, ResourceType
from app.ui.dialogs.graph_selection_dialog import GraphSelectionDialog
from app.ui.foundation.context_menu_builder import ContextMenuBuilder
from app.ui.foundation.dialog_utils import (
    ask_yes_no_dialog,
    show_info_dialog,
    show_warning_dialog,
)
from app.ui.foundation.toast_notification import ToastNotification
from app.ui.foundation.theme_manager import Colors, Sizes
from app.ui.panels.template_instance.tab_base import TemplateInstanceTabBase
from app.ui.panels.template_instance_service import TemplateInstanceService
from app.runtime.services.graph_data_service import GraphDataService, GraphLoadPayload
from app.ui.panels.graph_async_loader import get_shared_graph_loader, GraphAsyncLoader
from app.ui.widgets.two_row_field_table_widget import TwoRowFieldTableWidget


@dataclass(frozen=True)
class GraphListEntry:
    graph_id: str
    prefix: str
    origin: str
    gray_out: bool = False


class GraphsTab(TemplateInstanceTabBase):
    """节点图标签页，负责节点图列表与暴露变量覆盖。"""

    graph_selected = QtCore.pyqtSignal(str, dict)

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        *,
        graph_data_provider: Optional[GraphDataService] = None,
    ):
        super().__init__(parent)
        self.graph_data_provider = graph_data_provider
        self.graph_loader: Optional[GraphAsyncLoader] = (
            get_shared_graph_loader(graph_data_provider) if graph_data_provider else None
        )
        self._graph_items: dict[str, QtWidgets.QListWidgetItem] = {}
        self._graph_details: dict[str, Optional[GraphConfig]] = {}
        self._pending_requests: dict[str, Future] = {}
        self._pending_graph_selection: Optional[str] = None
        self._current_graph_entries: list[GraphListEntry] = []
        self._current_exposed_graph_id: Optional[str] = None
        self._current_exposed_vars: list[GraphVariableConfig] = []
        self._exposed_dict_type_index: dict[int, tuple[str, str]] = {}
        # 可选的节点图选择范围限制：类型（server/client）与文件夹前缀
        self.allowed_graph_type: Optional[str] = None
        self.allowed_folder_prefix: Optional[str] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = self._init_panel_layout(
            [
                ("+ 添加节点图", self._add_graph),
                ("删除", self._remove_graph),
            ]
        )
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.graphs_list = QtWidgets.QListWidget()
        self.graphs_list.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.graphs_list.customContextMenuRequested.connect(
            self._on_graphs_context_menu
        )
        splitter.addWidget(self.graphs_list)

        exposed_vars_widget = QtWidgets.QWidget()
        exposed_layout = QtWidgets.QVBoxLayout(exposed_vars_widget)
        exposed_layout.setContentsMargins(
            Sizes.PADDING_SMALL,
            Sizes.PADDING_SMALL,
            Sizes.PADDING_SMALL,
            Sizes.PADDING_SMALL,
        )

        title = QtWidgets.QLabel("节点图暴露变量覆盖")
        title.setStyleSheet(
            f"color: {Colors.TEXT_PRIMARY}; font-weight: bold; font-size: {Sizes.FONT_NORMAL + 1}px;"
        )
        exposed_layout.addWidget(title)
        info = QtWidgets.QLabel("选中节点图后，在此处覆盖暴露变量的值")
        info.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: {Sizes.FONT_NORMAL}px;"
        )
        exposed_layout.addWidget(info)

        self.exposed_vars_table = TwoRowFieldTableWidget(
            get_all_variable_types(),
            parent=exposed_vars_widget,
            column_headers=["序号", "变量名", "数据类型", "覆盖值"],
        )
        self.exposed_vars_table.set_dict_type_resolver(
            self._resolve_exposed_dict_types
        )
        exposed_layout.addWidget(self.exposed_vars_table)
        splitter.addWidget(exposed_vars_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        self.graphs_list.itemDoubleClicked.connect(self._on_graph_double_clicked)
        self.graphs_list.itemClicked.connect(self._on_graph_clicked)
        self.exposed_vars_table.field_changed.connect(self._on_exposed_vars_changed)

    def _reset_ui(self) -> None:
        self.graphs_list.clear()
        self._current_graph_entries = []
        self._graph_items.clear()
        self._graph_details.clear()
        for future in self._pending_requests.values():
            future.cancel()
        self._pending_requests.clear()
        self._current_exposed_graph_id = None
        self._current_exposed_vars = []
        self._exposed_dict_type_index.clear()
        self.exposed_vars_table.clear_fields()

    def _refresh_ui(self) -> None:
        # 掉落物上下文：不支持挂节点图，改为只读提示
        if self._is_drop_item_context():
            self._setup_drop_readonly_state()
            return
        self.graphs_list.setEnabled(True)
        self.exposed_vars_table.setEnabled(True)
        self._load_graphs()

    def _setup_drop_readonly_state(self) -> None:
        """为掉落物显示只读提示，禁用节点图编辑能力。"""
        self.graphs_list.clear()
        self._graph_items.clear()
        self._graph_details.clear()
        self._current_graph_entries = []

        info_item = QtWidgets.QListWidgetItem("掉落物不支持挂节点图")
        info_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
        self.graphs_list.addItem(info_item)

        self.exposed_vars_table.setRowCount(0)
        self.graphs_list.setEnabled(False)
        self.exposed_vars_table.setEnabled(False)

    def _add_graph(self) -> None:
        if self._is_drop_item_context():
            show_warning_dialog(self, "不支持", "掉落物不支持挂节点图。")
            return
        if not self.resource_manager:
            show_warning_dialog(self, "未设置", "请先设置 ResourceManager")
            return
        if not self.current_object or not self.service:
            return
        dialog = GraphSelectionDialog(
            resource_manager=self.resource_manager,
            package_index_manager=self.package_index_manager,
            parent=self,
            allowed_graph_type=self.allowed_graph_type,
            allowed_folder_prefix=self.allowed_folder_prefix,
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        graph_id = dialog.get_selected_graph_id()
        if not graph_id:
            return
        if self.service.add_graph(self.current_object, self.object_type, graph_id):
            self._load_graphs()
            self.data_changed.emit()

    def set_allowed_graph_scope(
        self,
        graph_type: Optional[str] = None,
        folder_prefix: Optional[str] = None,
    ) -> None:
        """限制“添加节点图”对话框中可选的节点图范围。

        Args:
            graph_type: "server" / "client"，为 None 时不过滤节点图类型。
            folder_prefix: 节点图 folder_path 前缀（如 "技能节点图"），None 表示不过滤文件夹。
        """
        self.allowed_graph_type = graph_type
        if folder_prefix:
            self.allowed_folder_prefix = folder_prefix.strip()
        else:
            self.allowed_folder_prefix = None

    def _remove_graph(self) -> None:
        current_item = self.graphs_list.currentItem()
        if not current_item or not self.current_object or not self.service:
            return
        origin = current_item.data(QtCore.Qt.ItemDataRole.UserRole + 1)
        if origin == "inherited":
            show_warning_dialog(
                self,
                "无法移除",
                "继承自模板的节点图无法直接从实体摆放面板移除。\n请前往模板面板进行修改。",
            )
            return
        graph_id = current_item.data(QtCore.Qt.ItemDataRole.UserRole)
        should_remove = ask_yes_no_dialog(
            self,
            "确认移除",
            "确定要移除此节点图的引用吗？\n节点图本身不会被删除，仍保留在节点图库中。",
        )
        if not should_remove:
            return
        if self.service.remove_graph(self.current_object, self.object_type, graph_id, origin):
            self._load_graphs()
            self.data_changed.emit()
            ToastNotification.show_message(self, "已移除该节点图引用。", "success")

    def _on_graph_double_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        graph_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        graph_config = self._graph_details.get(graph_id)
        if graph_config:
            self.graph_selected.emit(graph_id, graph_config.data)
            return
        if graph_id in self._graph_details and graph_config is None:
            show_warning_dialog(self, "错误", f"节点图 '{graph_id}' 已被删除或无法读取。")
            return
        show_info_dialog(self, "提示", "节点图正在加载，请稍后再试。")
        self._request_graph_details(graph_id)

    def _on_graph_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        graph_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        self._pending_graph_selection = graph_id
        if graph_id in self._graph_details and self._graph_details[graph_id] is None:
            self._clear_exposed_vars()
            return
        graph_config = self._graph_details.get(graph_id)
        if not graph_config:
            self._clear_exposed_vars()
            self._request_graph_details(graph_id)
            return
        self._render_exposed_vars(graph_id, graph_config)

    def _render_exposed_vars(self, graph_id: str, graph_config: GraphConfig) -> None:
        self._current_exposed_graph_id = graph_id
        graph_variables = graph_config.data.get("graph_variables", [])
        exposed_vars = [
            GraphVariableConfig.deserialize(var)
            for var in graph_variables
            if var.get("is_exposed", False)
        ]
        self._current_exposed_vars = exposed_vars
        self._exposed_dict_type_index.clear()

        fields: list[dict[str, object]] = []
        for variable in exposed_vars:
            override_value = self._get_override_value(graph_id, variable.name)

            effective_value = self._compose_effective_value_for_display(
                variable, override_value
            )

            # 为字典类型记录键/值类型，供表格渲染使用
            if variable.variable_type.endswith("字典"):
                if isinstance(effective_value, Mapping):
                    key_type = (variable.dict_key_type or "").strip() or "字符串"
                    value_type = (variable.dict_value_type or "").strip() or "字符串"
                    self._exposed_dict_type_index[id(effective_value)] = (
                        key_type,
                        value_type,
                    )

            fields.append(
                {
                    "name": variable.name,
                    "type_name": variable.variable_type,
                    "value": effective_value,
                }
            )

        self.exposed_vars_table.load_fields(fields)

    def _clear_exposed_vars(self) -> None:
        self._current_exposed_graph_id = None
        self._current_exposed_vars = []
        self._exposed_dict_type_index.clear()
        self.exposed_vars_table.clear_fields()

    def _current_selection_id(self) -> Optional[str]:
        current_item = self.graphs_list.currentItem()
        if not current_item:
            return None
        return current_item.data(QtCore.Qt.ItemDataRole.UserRole)

    def _restore_selection(self, graph_id: Optional[str]) -> None:
        if not graph_id:
            return
        for row in range(self.graphs_list.count()):
            item = self.graphs_list.item(row)
            if item and item.data(QtCore.Qt.ItemDataRole.UserRole) == graph_id:
                self.graphs_list.setCurrentRow(row)
                break

    def _graph_entry_exists(self, graph_id: str) -> bool:
        return any(entry.graph_id == graph_id for entry in self._current_graph_entries)

    def _graph_entry_by_id(self, graph_id: str) -> Optional[GraphListEntry]:
        for entry in self._current_graph_entries:
            if entry.graph_id == graph_id:
                return entry
        return None

    def _get_override_value(self, graph_id: str, var_name: str) -> Optional[object]:
        overrides = getattr(self.current_object, "graph_variable_overrides", {})
        return overrides.get(graph_id, {}).get(var_name)

    def _compose_effective_value_for_display(
        self,
        variable: GraphVariableConfig,
        override_value: Optional[object],
    ) -> object:
        """根据默认值与覆盖值计算在表格中展示的实际数值。

        - 当未设置覆盖值或覆盖值等价于默认值时，直接展示默认值；
        - 当存在覆盖值且与默认值不同，则展示覆盖值。
        """
        default_value = variable.default_value

        if override_value is None:
            return default_value

        if self._values_equal_for_override(default_value, override_value):
            return default_value

        return override_value

    def _values_equal_for_override(
        self,
        default_value: Optional[object],
        current_value: Optional[object],
    ) -> bool:
        """判断当前值是否与默认值等价，用于决定是否需要写入覆盖。

        - 默认值为 None 时，将空字符串视为等价；
        - 其他情况直接使用 == 比较。
        """
        if default_value is None:
            if current_value is None:
                return True
            if isinstance(current_value, str) and not current_value.strip():
                return True
            return False
        return default_value == current_value

    def _resolve_exposed_dict_types(
        self,
        type_name: str,
        value_mapping: Mapping[str, object],
    ) -> tuple[str, str]:
        """为暴露变量的字典类型提供键/值类型展示信息。

        逻辑与图变量编辑表格保持一致：
        - 优先根据当前映射对象的 id 在索引表中查找；
        - 若找不到，则回退为“字符串/字符串”。
        """
        if not isinstance(value_mapping, Mapping):
            return "字符串", "字符串"

        mapping_id = id(value_mapping)
        if mapping_id in self._exposed_dict_type_index:
            return self._exposed_dict_type_index[mapping_id]

        return "字符串", "字符串"

    def _on_exposed_vars_changed(self) -> None:
        """当暴露变量表格内容变化时，将差异写入 graph_variable_overrides。

        这里不直接修改图本身的默认值，而是仅在值与默认值不同时写入覆盖，
        当用户将值改回默认值时自动清理对应的覆盖条目。
        """
        if (
            not self.current_object
            or not self.service
            or not self._current_exposed_graph_id
            or not self._current_exposed_vars
        ):
            return

        graph_id = self._current_exposed_graph_id
        vars_by_name: dict[str, GraphVariableConfig] = {
            variable.name: variable for variable in self._current_exposed_vars
        }

        fields = self.exposed_vars_table.get_all_fields()
        changed_any = False

        for field in fields:
            name_text = str(field.get("name", "")).strip()
            if not name_text:
                continue
            var_config = vars_by_name.get(name_text)
            if not var_config:
                continue

            current_value = field.get("value")
            default_value = var_config.default_value

            if self._values_equal_for_override(default_value, current_value):
                override_value: Optional[object] = None
            else:
                override_value = current_value

            if self.service.set_graph_variable_override(
                self.current_object,
                graph_id,
                name_text,
                override_value,
            ):
                changed_any = True

        if changed_any:
            self.data_changed.emit()

    def _on_graphs_context_menu(self, pos: QtCore.QPoint) -> None:
        item = self.graphs_list.itemAt(pos)
        if item is None:
            return
        builder = ContextMenuBuilder(self.graphs_list)
        builder.add_action("删除当前行", self._remove_graph)
        builder.exec_for(self.graphs_list, pos)

    def _load_graphs(self) -> None:
        previous_selection = self._current_selection_id()
        previous_scroll = self.graphs_list.verticalScrollBar().value()
        self.graphs_list.clear()
        self._graph_items.clear()
        if not self.current_object:
            self._graph_details.clear()
            return
        self._current_graph_entries = list(self._iter_graph_entries())
        current_ids = {entry.graph_id for entry in self._current_graph_entries}
        for graph_id in list(self._graph_details.keys()):
            if graph_id not in current_ids:
                self._graph_details.pop(graph_id, None)
                future = self._pending_requests.pop(graph_id, None)
                if future:
                    future.cancel()
        for entry in self._current_graph_entries:
            self._append_graph_item(entry)
        self._restore_selection(previous_selection)
        QtCore.QTimer.singleShot(0, lambda: self.graphs_list.verticalScrollBar().setValue(previous_scroll))

    def _iter_graph_entries(self) -> Iterable[GraphListEntry]:
        if not self.current_object:
            return []
        if self._is_drop_item_context():
            return []
        template_graphs, instance_graphs, level_graphs = self._collect_context_lists(
            template_attr="default_graphs",
            instance_attr="additional_graphs",
            level_attr="additional_graphs",
        )
        if self.object_type == "template":
            for graph_id in template_graphs:
                yield GraphListEntry(graph_id, "🧩", "template")
            return
        if self.object_type == "level_entity":
            for graph_id in level_graphs:
                yield GraphListEntry(graph_id, "【额外】", "additional")
            return
        for graph_id in template_graphs:
            yield GraphListEntry(graph_id, "🔗 [继承]", "inherited", gray_out=True)
        for graph_id in instance_graphs:
            yield GraphListEntry(graph_id, "【额外】", "additional")

    def _append_graph_item(self, entry: GraphListEntry) -> None:
        label = self._format_graph_label(entry)
        item = QtWidgets.QListWidgetItem(label)
        item.setData(QtCore.Qt.ItemDataRole.UserRole, entry.graph_id)
        item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, entry.origin)
        if entry.gray_out:
            item.setForeground(QtGui.QColor(Colors.TEXT_DISABLED))
        elif self._graph_details.get(entry.graph_id) is None and entry.graph_id in self._graph_details:
            item.setForeground(QtCore.Qt.GlobalColor.red)
        self._graph_items[entry.graph_id] = item
        self.graphs_list.addItem(item)
        self._request_graph_details(entry.graph_id)

    def _format_graph_label(self, entry: GraphListEntry) -> str:
        if entry.graph_id in self._graph_details:
            graph_config = self._graph_details[entry.graph_id]
            if graph_config is None:
                return f"{entry.prefix} ❌ [已删除: {entry.graph_id}]"
            type_icon = "🔷" if graph_config.graph_type == "server" else "🔶"
            return f"{entry.prefix} {type_icon} {graph_config.name}"
        return f"{entry.prefix} ⏳ 正在加载…"

    def _request_graph_details(self, graph_id: str) -> None:
        if graph_id in self._graph_details:
            return
        if graph_id in self._pending_requests:
            return
        if self.graph_loader:
            future = self.graph_loader.request_payload(graph_id, self._on_graph_payload_ready)
            self._pending_requests[graph_id] = future
            return
        graph_config = self._load_graph_config(graph_id)
        self._graph_details[graph_id] = graph_config
        self._update_graph_item_label(graph_id)

    def _load_graph_config(self, graph_id: str) -> Optional[GraphConfig]:
        if self.graph_data_provider:
            payload = self.graph_data_provider.load_graph_payload(graph_id)
            if payload.error:
                return None
            return payload.graph_config
        if not self.resource_manager:
            return None
        graph_data = self.resource_manager.load_resource(ResourceType.GRAPH, graph_id)
        if not graph_data:
            return None
        return GraphConfig.deserialize(graph_data)

    def _on_graph_payload_ready(self, graph_id: str, payload: GraphLoadPayload) -> None:
        self._pending_requests.pop(graph_id, None)
        if not self._graph_entry_exists(graph_id):
            return
        if payload.error:
            self._graph_details[graph_id] = None
        else:
            self._graph_details[graph_id] = payload.graph_config
        self._update_graph_item_label(graph_id)
        graph_config = self._graph_details.get(graph_id)
        if self._pending_graph_selection == graph_id and graph_config:
            self._render_exposed_vars(graph_id, graph_config)

    def _update_graph_item_label(self, graph_id: str) -> None:
        item = self._graph_items.get(graph_id)
        entry = self._graph_entry_by_id(graph_id)
        if not item or not entry:
            return
        item.setText(self._format_graph_label(entry))
        if entry.gray_out:
            item.setForeground(QtGui.QColor(Colors.TEXT_DISABLED))
        elif graph_id in self._graph_details and self._graph_details[graph_id] is None:
            item.setForeground(QtCore.Qt.GlobalColor.red)
        else:
            item.setForeground(QtGui.QColor(Colors.TEXT_PRIMARY))


