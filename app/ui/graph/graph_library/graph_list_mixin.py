from PyQt6 import QtCore, QtWidgets
from typing import List, Optional, Dict, Callable
from datetime import datetime

from engine.resources.resource_manager import ResourceType
from engine.resources.package_view import PackageView
from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.unclassified_resource_view import UnclassifiedResourceView
from engine.graph.models.graph_config import GraphConfig
from engine.graph.models.graph_model import GraphModel
from app.ui.dialogs.graph_detail_dialog import GraphDetailDialog
from app.ui.foundation import input_dialogs
from app.ui.foundation.context_menu_builder import ContextMenuBuilder
from app.ui.foundation.id_generator import generate_prefixed_id
from app.ui.foundation.toast_notification import ToastNotification
from app.ui.graph.library_pages.graph_card_widget import GraphCardWidget


class GraphListMixin:
    """节点图卡片列表与图操作相关逻辑"""

    @property
    def _graph_metadata_cache(self) -> Dict[str, dict]:
        cache = getattr(self, "__graph_metadata_cache", None)
        if cache is None:
            cache = {}
            setattr(self, "__graph_metadata_cache", cache)
        return cache

    def _invalidate_graph_metadata(self, graph_id: Optional[str] = None) -> None:
        cache = getattr(self, "__graph_metadata_cache", None)
        if cache is None:
            return
        if graph_id is None:
            cache.clear()
        else:
            cache.pop(graph_id, None)

    def _load_graph_metadata_with_cache(self, graph_id: str) -> Optional[dict]:
        metadata = self._graph_metadata_cache.get(graph_id)
        if metadata is None:
            metadata = self.resource_manager.load_graph_metadata(graph_id)
            if metadata:
                self._graph_metadata_cache[graph_id] = metadata
        return metadata

    def _list_graphs_in_folder_tree(self, graph_type: str, folder_path: str) -> List[dict]:
        """在当前类型下列出指定文件夹及其所有子文件夹中的节点图。

        说明：
        - 用于节点图库左侧选中父级文件夹时，中间列表能够显示整个子树下的所有节点图，
          而不是仅限于当前这一层目录。
        - 仅在 `current_folder` 非空时使用；根目录依旧走类型视图的“无 folder_path”逻辑。
        """
        sanitized_folder = self.resource_manager.sanitize_folder_path(folder_path) if folder_path else ""
        if not sanitized_folder:
            return self.resource_manager.list_graphs_by_type(graph_type)

        graphs_in_type = self.resource_manager.list_graphs_by_type(graph_type)
        prefix = f"{sanitized_folder}/"
        scoped_graphs: List[dict] = []
        for graph_info in graphs_in_type:
            graph_folder = graph_info.get("folder_path", "") or ""
            if graph_folder == sanitized_folder or graph_folder.startswith(prefix):
                scoped_graphs.append(graph_info)
        return scoped_graphs

    def _refresh_graph_list(self) -> None:
        """刷新节点图列表（使用卡片显示）"""
        # 节点图库页面在模式切换时会被频繁触发 refresh；若资源库指纹与当前视图上下文未变，
        # 则跳过全量枚举与排序，直接复用现有卡片与选中状态，避免 UI 卡顿。
        current_package_key: tuple[str, str] = ("none", "")
        if isinstance(self.current_package, PackageView):
            current_package_key = ("package", self.current_package.package_id)
        elif isinstance(self.current_package, GlobalResourceView):
            current_package_key = ("global", "")
        elif isinstance(self.current_package, UnclassifiedResourceView):
            current_package_key = ("unclassified", "")

        resource_fingerprint = self.resource_manager.get_resource_library_fingerprint()
        refresh_signature = (
            resource_fingerprint,
            current_package_key,
            self.current_graph_type,
            self.current_folder,
            self.current_sort_by,
        )
        previous_signature = getattr(self, "__graph_list_refresh_signature", None)
        if previous_signature == refresh_signature:
            return
        setattr(self, "__graph_list_refresh_signature", refresh_signature)

        allowed_graph_ids = None
        if isinstance(self.current_package, PackageView):
            pkg_resources = self.package_index_manager.get_package_resources(self.current_package.package_id)
            allowed_graph_ids = set(pkg_resources.graphs) if pkg_resources else set()

        if self.current_folder:
            graphs = self._list_graphs_in_folder_tree(self.current_graph_type, self.current_folder)
        else:
            # 根目录：展示当前类型下的所有节点图，不按 folder_path 进行额外过滤；
            # 具体“是否属于当前视图/存档”的约束交由后续 allowed_graph_ids /
            # UnclassifiedResourceView 等视图模型负责。
            graphs = self.resource_manager.list_graphs_by_type(self.current_graph_type)

        if isinstance(self.current_package, UnclassifiedResourceView):
            unclassified_ids = self.current_package.get_unclassified_graph_ids()
            graphs = [g for g in graphs if g.get("graph_id") in unclassified_ids]
        elif allowed_graph_ids is not None:
            graphs = [g for g in graphs if g.get("graph_id") in allowed_graph_ids]

        graph_data_list = []
        for graph_info in graphs:
            graph_id = graph_info["graph_id"]
            metadata = self._load_graph_metadata_with_cache(graph_id)
            if metadata:
                ref_count = self.reference_tracker.get_reference_count(graph_id)
                modified_time = metadata.get("modified_time", "")
                if isinstance(modified_time, (int, float)):
                    timestamp_dt = datetime.fromtimestamp(modified_time)
                    time_str = timestamp_dt.strftime("%Y-%m-%d %H:%M:%S")
                    timestamp_value = modified_time
                else:
                    time_str = str(modified_time)
                    try:
                        timestamp_value = datetime.fromisoformat(time_str).timestamp()
                    except ValueError:
                        timestamp_value = 0

                node_count = int(metadata.get("node_count") or 0)
                edge_count = int(metadata.get("edge_count") or 0)
                graph_data = {
                    "graph_id": metadata["graph_id"],
                    "name": metadata["name"],
                    "graph_type": metadata["graph_type"],
                    "folder_path": metadata["folder_path"],
                    "description": metadata["description"],
                    "last_modified": time_str,
                    "last_modified_ts": timestamp_value,
                    "node_count": node_count,
                    "edge_count": edge_count,
                    "is_corrupted": False,
                }
                graph_data_list.append({"graph_id": graph_id, "data": graph_data, "ref_count": ref_count})
            else:
                ref_count = self.reference_tracker.get_reference_count(graph_id)
                graph_data = {
                    "graph_id": graph_id,
                    "name": f"⚠️ {graph_id} (损坏)",
                    "graph_type": self.current_graph_type,
                    "folder_path": graph_info.get("folder_path", ""),
                    "description": "节点图文件损坏或无法解析，请检查代码文件",
                    "last_modified": "未知",
                    "last_modified_ts": 0,
                    "node_count": 0,
                    "edge_count": 0,
                    "is_corrupted": True,
                }
                graph_data_list.append({"graph_id": graph_id, "data": graph_data, "ref_count": ref_count})

        graph_data_list = self._sort_graphs(graph_data_list)

        desired_ids = [item["graph_id"] for item in graph_data_list]
        desired_id_set = set(desired_ids)

        # 移除已不存在的卡片
        for obsolete_id in list(self.graph_cards.keys()):
            if obsolete_id not in desired_id_set:
                obsolete_card = self.graph_cards.pop(obsolete_id)
                self.graph_container_layout.removeWidget(obsolete_card)
                obsolete_card.deleteLater()

        previous_snapshot = getattr(self, "__graph_snapshot", {})
        new_snapshot: Dict[str, tuple] = {}

        for item in graph_data_list:
            graph_id = item["graph_id"]
            graph_data = item["data"]
            ref_count = item["ref_count"]
            has_error = self.error_tracker.has_error(graph_id)
            snapshot_entry = self._build_graph_snapshot_entry(graph_data, ref_count, has_error)
            new_snapshot[graph_id] = snapshot_entry

            if graph_id in self.graph_cards:
                card = self.graph_cards[graph_id]
                if previous_snapshot.get(graph_id) != snapshot_entry:
                    card.update_graph_info(graph_data, ref_count, has_error)
            else:
                card = GraphCardWidget(
                    graph_id,
                    graph_data,
                    ref_count,
                    self.resource_manager,
                    self.graph_container_widget,
                    has_error=has_error,
                )
                # 节点图库只读模式下不允许从卡片进入变量编辑，对应按钮隐藏
                if getattr(self, "graph_library_read_only", False):
                    card.set_variables_button_enabled(False)
                card.clicked.connect(self._on_graph_card_clicked)
                card.double_clicked.connect(self._on_graph_card_double_clicked)
                card.edit_clicked.connect(self._on_graph_card_double_clicked)
                card.variables_clicked.connect(self._on_variables_clicked)
                card.reference_clicked.connect(self._on_reference_clicked)
                self.graph_cards[graph_id] = card
                self.graph_container_layout.insertWidget(self.graph_container_layout.count() - 1, card)

        setattr(self, "__graph_snapshot", new_snapshot)

        previous_order = getattr(self, "__graph_order", [])
        if previous_order != desired_ids:
            self._reorder_graph_cards(desired_ids)
        setattr(self, "__graph_order", desired_ids)

        if self.selected_graph_id and self.selected_graph_id in self.graph_cards:
            self.graph_cards[self.selected_graph_id].set_selected(True)
        elif desired_ids and self.isVisible():
            self._on_graph_card_clicked(desired_ids[0])

    def _sort_graphs(self, graph_list: List[dict]) -> List[dict]:
        """根据当前排序方式对节点图列表排序"""
        sorters: Dict[str, Callable[[dict], object]] = {
            "modified": lambda item: item["data"].get("last_modified_ts", 0),
            "name": lambda item: item["data"].get("name", "").lower(),
            "nodes": lambda item: item["data"].get("node_count", 0),
            "references": lambda item: item["ref_count"],
        }
        sorter = sorters.get(self.current_sort_by)
        if sorter:
            reverse_flag = self.current_sort_by in {"modified", "nodes", "references"}
            return sorted(graph_list, key=sorter, reverse=reverse_flag)
        return graph_list

    def _on_graph_card_clicked(self, graph_id: str) -> None:
        """卡片点击"""
        if self.selected_graph_id and self.selected_graph_id in self.graph_cards:
            self.graph_cards[self.selected_graph_id].set_selected(False)
        self.selected_graph_id = graph_id
        if graph_id in self.graph_cards:
            self.graph_cards[graph_id].set_selected(True)
        self.graph_selected.emit(graph_id)

    def _on_graph_card_double_clicked(self, graph_id: str) -> None:
        """卡片双击 - 打开编辑"""
        if graph_id in self.graph_cards:
            card_data = None
            for card in self.graph_cards.values():
                if hasattr(card, "graph_id") and card.graph_id == graph_id:
                    metadata = self.resource_manager.load_graph_metadata(graph_id)
                    if not metadata:
                        card_data = {"is_corrupted": True}
                        break
            if card_data and card_data.get("is_corrupted"):
                self.show_error(
                    "无法打开节点图",
                    f"节点图 '{graph_id}' 已损坏，无法打开编辑。\n\n可能的原因：\n"
                    "• 代码文件包含语法错误\n"
                    "• 使用了不存在的节点类型\n"
                    "• 文件被手动修改导致格式错误\n\n"
                    "建议：\n"
                    "• 检查资源库中的代码文件\n"
                    "• 查看控制台输出中的详细错误信息\n"
                    "• 如果有备份，尝试从备份恢复",
                )
                return

        graph_data = self.resource_manager.load_resource(ResourceType.GRAPH, graph_id)
        if graph_data:
            self.graph_double_clicked.emit(graph_id, graph_data)
        else:
            self.show_warning("加载失败", f"无法加载节点图 '{graph_id}'。\n\n请检查文件是否存在或是否已损坏。")

    def _on_reference_clicked(self, graph_id: str) -> None:
        """点击引用按钮 - 显示引用详情"""
        self._show_graph_detail_by_id(graph_id)

    def _on_variables_clicked(self, graph_id: str) -> None:
        """点击节点图变量按钮 - 打开节点图变量编辑对话框"""
        # 节点图库只读模式：变量在 UI 中仅供查看，不能通过图库对话框写回到代码
        if getattr(self, "graph_library_read_only", False):
            if hasattr(self, "show_warning"):
                self.show_warning(
                    "变量只读",
                    "当前节点图库为只读模式：节点图变量只能在对应的 Python 文件中维护，"
                    "不能在图库页面直接编辑并保存。",
                )
            return
        from app.ui.dialogs.graph_variable_dialog import GraphVariableDialog

        graph_data = self.resource_manager.load_resource(ResourceType.GRAPH, graph_id)
        if not graph_data:
            self.show_warning("警告", "无法加载节点图数据")
            return

        graph_config = GraphConfig.deserialize(graph_data)
        graph_model = GraphModel.deserialize(graph_config.data)
        dialog = GraphVariableDialog(graph_model, self)
        dialog.variables_updated.connect(lambda: self._on_graph_variables_updated(graph_id, graph_model, graph_config))
        dialog.exec()

    def _on_graph_variables_updated(self, graph_id: str, graph_model: GraphModel, graph_config: GraphConfig) -> None:
        """节点图变量更新后保存"""
        # 只读模式下不从图库对图变量做任何持久化写入
        if getattr(self, "graph_library_read_only", False):
            return
        graph_config.data = graph_model.serialize()
        graph_config.update_timestamp()
        self.resource_manager.save_resource(ResourceType.GRAPH, graph_id, graph_config.serialize())
        self._invalidate_graph_metadata(graph_id)

    def _add_graph(self) -> None:
        """新建节点图"""
        # 节点图库只读模式：禁止在 UI 中新建节点图，图文件仅由代码维护
        if getattr(self, "graph_library_read_only", False):
            if hasattr(self, "show_warning"):
                self.show_warning(
                    "只读模式",
                    "当前节点图库为只读模式，不能在 UI 中新建节点图；"
                    "请在 assets/资源库/节点图 下通过 Python 文件定义新图。",
                )
            return
        name = input_dialogs.prompt_text(self, "新建节点图", "请输入节点图名称:")
        if not name:
            return

        if self.current_graph_type == "all":
            type_choice = input_dialogs.prompt_item(
                self,
                "选择类型",
                "请选择节点图类型:",
                ["服务器", "客户端"],
                current_index=0,
                editable=False,
            )
            if not type_choice:
                return
            graph_type = "server" if type_choice == "服务器" else "client"
        else:
            graph_type = self.current_graph_type

        graph_id = generate_prefixed_id("graph")
        graph_config = GraphConfig(
            graph_id=graph_id,
            name=name,
            graph_type=graph_type,
            folder_path=self.current_folder,
            data={
                "nodes": [],
                "edges": [],
                "graph_id": graph_id,
                "graph_name": name,
                "description": "",
                "graph_variables": [],
                "metadata": {"graph_type": graph_type},
            },
        )
        self.resource_manager.save_resource(ResourceType.GRAPH, graph_id, graph_config.serialize())
        self._invalidate_graph_metadata(graph_id)
        self._refresh_graph_list()
        self.selected_graph_id = graph_id
        if graph_id in self.graph_cards:
            self.graph_cards[graph_id].set_selected(True)
            self.graph_selected.emit(graph_id)

    def _delete_selected(self) -> None:
        """删除选中的节点图或文件夹"""
        if getattr(self, "graph_library_read_only", False):
            if hasattr(self, "show_warning"):
                self.show_warning(
                    "只读模式",
                    "当前节点图库为只读模式，不能在 UI 中删除节点图或文件夹。",
                )
            return
        if self.selected_graph_id:
            self._delete_graph_by_id(self.selected_graph_id)
        else:
            folder_item = self.folder_tree.currentItem()
            if folder_item:
                self._delete_folder(folder_item)

    def _delete_graph_by_id(self, graph_id: str) -> None:
        """删除节点图"""
        if getattr(self, "graph_library_read_only", False):
            return
        graph_data = self.resource_manager.load_resource(ResourceType.GRAPH, graph_id)
        if not graph_data:
            return

        graph_config = GraphConfig.deserialize(graph_data)
        ref_count = self.reference_tracker.get_reference_count(graph_id)
        if ref_count > 0:
            message = (
                f"节点图 '{graph_config.name}' 被 {ref_count} 个对象引用。\n删除后这些引用将失效，确定要删除吗？"
            )
        else:
            message = f"确定要删除节点图 '{graph_config.name}' 吗？"
        if not self.confirm("确认删除", message):
            return
        self.resource_manager.delete_resource(ResourceType.GRAPH, graph_id)
        self._invalidate_graph_metadata(graph_id)
        self._refresh_graph_list()
        host_widget: Optional[QtWidgets.QWidget]
        if isinstance(self, QtWidgets.QWidget):
            host_widget = self
        else:
            window = getattr(self, "window", None)
            candidate = window() if callable(window) else window
            host_widget = candidate if isinstance(candidate, QtWidgets.QWidget) else None
        ToastNotification.show_message(
            host_widget or QtWidgets.QApplication.activeWindow(),
            f"已删除节点图 '{graph_config.name}'。",
            "success",
        )

    def _move_graph(self) -> None:
        """移动节点图到文件夹"""
        if getattr(self, "graph_library_read_only", False):
            if hasattr(self, "show_warning"):
                self.show_warning(
                    "只读模式",
                    "当前节点图库为只读模式，不能在 UI 中移动节点图到其它文件夹。",
                )
            return
        if not self.selected_graph_id:
            self.show_warning("警告", "请先选择要移动的节点图")
            return

        graph_id = self.selected_graph_id
        graph_data = self.resource_manager.load_resource(ResourceType.GRAPH, graph_id)
        if not graph_data:
            return

        graph_config = GraphConfig.deserialize(graph_data)
        folders = self.resource_manager.get_all_graph_folders()
        type_folders = folders.get(graph_config.graph_type, [])
        folder_choices = ["<根目录>"] + type_folders
        target_folder = input_dialogs.prompt_item(
            self,
            "移动到文件夹",
            f"选择 '{graph_config.name}' 的目标文件夹:",
            folder_choices,
            current_index=0,
            editable=False,
        )
        if not target_folder:
            return
        new_folder_path = "" if target_folder == "<根目录>" else target_folder
        graph_config.folder_path = new_folder_path
        graph_config.update_timestamp()
        self.resource_manager.save_resource(ResourceType.GRAPH, graph_id, graph_config.serialize())
        self._refresh_folder_tree()
        self._invalidate_graph_metadata(graph_id)
        self._refresh_graph_list()

    def _filter_graphs(self, text: str) -> None:
        """过滤节点图"""
        search_text = text.lower()
        for graph_id, card in self.graph_cards.items():
            graph_data = card.graph_data
            name = graph_data.get("name", "").lower()
            description = graph_data.get("description", "").lower()
            card.setVisible(search_text in name or search_text in description)

    def _show_graph_context_menu(self, pos: QtCore.QPoint) -> None:
        """显示节点图右键菜单"""
        if getattr(self, "selection_mode", False):
            return
        clicked_card = None
        for graph_id, card in self.graph_cards.items():
            if card.geometry().contains(self.graph_container_widget.mapFrom(self.graph_scroll_area, pos)):
                clicked_card = card
                break

        builder = ContextMenuBuilder(self)
        read_only = getattr(self, "graph_library_read_only", False)
        if clicked_card:
            graph_id = clicked_card.graph_id
            if read_only:
                builder.add_action("查看节点图", lambda: self._on_graph_card_double_clicked(graph_id))
                builder.add_separator()
                builder.add_action("查看详情", lambda: self._show_graph_detail_by_id(graph_id))
            else:
                builder.add_action("编辑节点图", lambda: self._on_graph_card_double_clicked(graph_id))
                builder.add_separator()
                builder.add_action("移动到文件夹", self._move_graph)
                builder.add_separator()
                builder.add_action("查看详情", lambda: self._show_graph_detail_by_id(graph_id))
                builder.add_separator()
                builder.add_action("删除", lambda: self._delete_graph_by_id(graph_id))
        else:
            if not read_only:
                builder.add_action("+ 新建节点图", self._add_graph)
                builder.add_separator()
                builder.add_action("+ 新建文件夹", self._add_folder)
                builder.add_separator()
                builder.add_action("刷新列表", self.refresh)
            else:
                builder.add_action("刷新列表", self.refresh)
        builder.exec_for(self.graph_scroll_area, pos)

    def _show_graph_detail_by_id(self, graph_id: str) -> None:
        """显示节点图详情"""
        dialog = GraphDetailDialog(graph_id, self.resource_manager, self.package_index_manager, self)
        dialog.jump_to_reference.connect(self._on_jump_to_reference)
        dialog.exec()

    def _on_jump_to_reference(self, entity_type: str, entity_id: str, package_id: str) -> None:
        """处理从详情对话框跳转到实体"""
        self.jump_to_entity_requested.emit(entity_type, entity_id, package_id)

    def select_graph_by_id(self, graph_id: str, open_editor: bool = False) -> None:
        """程序化选择并（可选）打开指定ID的节点图"""
        metadata = self.resource_manager.load_graph_metadata(graph_id)
        if not metadata:
            self._refresh_graph_list()
            if graph_id in self.graph_cards:
                self._on_graph_card_clicked(graph_id)
                if open_editor:
                    QtCore.QTimer.singleShot(100, lambda: self._on_graph_card_double_clicked(graph_id))
            return

        graph_type = metadata.get("graph_type", "server")
        if graph_type != self.current_graph_type:
            for i in range(self.type_combo.count()):
                if self.type_combo.itemData(i) == graph_type:
                    self.type_combo.setCurrentIndex(i)
                    break

        target_folder = metadata.get("folder_path", "") or ""
        self.current_folder = target_folder
        self._refresh_graph_list()

        if graph_id in self.graph_cards:
            self._on_graph_card_clicked(graph_id)
            card = self.graph_cards[graph_id]
            self.scroll_to_widget(self.graph_scroll_area, card, center=True)
            if open_editor:
                QtCore.QTimer.singleShot(120, lambda: self._on_graph_card_double_clicked(graph_id))

    def get_selected_graph_id(self) -> Optional[str]:
        """返回当前选中的节点图 ID"""
        return getattr(self, "selected_graph_id", None)

    def _build_graph_snapshot_entry(
        self,
        graph_data: dict,
        ref_count: int,
        has_error: bool,
    ) -> tuple:
        return (
            graph_data.get("last_modified_ts"),
            graph_data.get("node_count"),
            graph_data.get("edge_count"),
            ref_count,
            graph_data.get("name"),
            graph_data.get("folder_path"),
            has_error,
        )

    def _reorder_graph_cards(self, ordered_ids: List[str]) -> None:
        layout = getattr(self, "graph_container_layout", None)
        if not layout:
            return
        spacer_index = max(0, layout.count() - 1)
        for order_index, graph_id in enumerate(ordered_ids):
            card = self.graph_cards.get(graph_id)
            if not card:
                continue
            current_index = layout.indexOf(card)
            target_index = min(order_index, spacer_index)
            if current_index != -1 and current_index != target_index:
                layout.insertWidget(target_index, card)

    def ensure_default_selection(self) -> None:
        """在常规模式下自动选中当前列表首个节点图。"""
        if getattr(self, "selection_mode", False):
            return
        if self.selected_graph_id and self.selected_graph_id in self.graph_cards:
            return
        order = getattr(self, "__graph_order", [])
        if not order:
            return
        first_graph_id = order[0]
        if first_graph_id in self.graph_cards:
            self._on_graph_card_clicked(first_graph_id)


