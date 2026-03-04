import copy

from PyQt6 import QtCore, QtWidgets
from pathlib import Path
from typing import List, Optional, Dict, Callable
from datetime import datetime

from engine.resources.resource_manager import ResourceType
from engine.resources.package_view import PackageView
from engine.resources.global_resource_view import GlobalResourceView
from engine.graph.models.graph_config import GraphConfig
from engine.graph.models.graph_model import GraphModel
from app.ui.dialogs.graph_detail_dialog import GraphDetailDialog
from app.ui.foundation import input_dialogs
from app.ui.foundation.context_menu_builder import ContextMenuBuilder
from app.ui.foundation.id_generator import generate_prefixed_id
from app.ui.foundation.toast_notification import ToastNotification
from app.ui.graph.library_pages.graph_card_widget import GraphCardWidget
from app.ui.graph.graph_library.graph_resource_async_loader import GraphResourceAsyncLoader
from app.ui.graph.graph_library.graph_metadata_load_thread import GraphMetadataLoadThread


class GraphListMixin:
    """节点图卡片列表与图操作相关逻辑"""

    def _resolve_graph_write_root_dir(self) -> Path:
        """解析“新建/复制节点图”的写入根目录。

        规则：
        - 全局视图（GlobalResourceView）：写入共享根目录
        - 具体存档视图（PackageView）：写入当前存档根目录
        """
        roots = list(self.resource_manager.get_current_resource_roots() or [])
        if not roots:
            raise ValueError("无法解析资源根目录：ResourceManager.get_current_resource_roots() 为空")

        folder_scope = str(getattr(self, "current_folder_scope", "") or "").strip().lower() or "all"
        if folder_scope == "shared":
            return roots[0]
        if folder_scope == "package":
            return roots[1] if len(roots) > 1 else roots[0]

        current_package = getattr(self, "current_package", None)
        if isinstance(current_package, GlobalResourceView):
            return roots[0]
        if isinstance(current_package, PackageView):
            if len(roots) > 1:
                return roots[1]
            return roots[0]
        return roots[1] if len(roots) > 1 else roots[0]

    @staticmethod
    def _force_invalidate_graph_list_refresh_signature(host: object) -> None:
        """使 `_refresh_graph_list` 不被 refresh_signature 短路。"""
        setattr(host, "__graph_list_refresh_signature", None)

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

    def _infer_graph_type_and_folder_path_from_file_path(self, file_path: Path) -> tuple[str, str]:
        """基于物理路径推断 graph_type 与 folder_path（无需读文件/解析 AST）。"""
        if not isinstance(file_path, Path):
            return "", ""

        parts = getattr(file_path, "parts", ())
        if not parts:
            return "", ""

        graph_type = ""
        folder_path = ""
        if "节点图" in parts:
            idx = parts.index("节点图")
            if idx + 1 < len(parts):
                graph_type = str(parts[idx + 1] or "").strip().lower()
                # 节点图/<server|client>/<folder...>/<file>.py
                folder_parts = parts[idx + 2 : -1]
                folder_path = "/".join([str(part) for part in folder_parts if str(part)])

        if graph_type not in {"server", "client"}:
            graph_type = ""
        folder_path = self.resource_manager.sanitize_folder_path(folder_path) if folder_path else ""
        return graph_type, folder_path

    def _ensure_graph_list_loading_label(self) -> QtWidgets.QLabel:
        """确保列表顶部存在一个“加载中”提示（幂等）。"""
        label = getattr(self, "_graph_list_loading_label", None)
        if isinstance(label, QtWidgets.QLabel):
            return label

        label = QtWidgets.QLabel("正在加载节点图信息…")
        label.setObjectName("graphListLoadingLabel")
        label.setWordWrap(True)
        label.setVisible(False)

        layout = getattr(self, "graph_container_layout", None)
        if isinstance(layout, QtWidgets.QVBoxLayout):
            layout.insertWidget(0, label)

        setattr(self, "_graph_list_loading_label", label)
        return label

    def _set_graph_list_loading_visible(self, visible: bool, *, text: str = "") -> None:
        label = self._ensure_graph_list_loading_label()
        if text:
            label.setText(str(text))
        label.setVisible(bool(visible))

    def _cancel_async_graph_metadata_load(self) -> None:
        prev_thread = getattr(self, "_async_graph_metadata_thread", None)
        if prev_thread is not None and hasattr(prev_thread, "isRunning") and prev_thread.isRunning():
            prev_thread.requestInterruption()
        setattr(self, "_async_graph_metadata_thread", None)

    def _resort_current_graph_cards(self) -> None:
        """基于当前卡片数据重新排序并移动 QWidget（不重建卡片）。"""
        order = list(getattr(self, "__graph_order", []) or [])
        if not order:
            return
        graph_data_list: List[dict] = []
        for graph_id in order:
            card = self.graph_cards.get(graph_id)
            if not card:
                continue
            graph_data_list.append(
                {"graph_id": graph_id, "data": card.graph_data, "ref_count": int(getattr(card, "reference_count", 0) or 0)}
            )
        sorted_list = self._sort_graphs(graph_data_list)
        desired_ids = [item["graph_id"] for item in sorted_list]
        if desired_ids != order:
            self._reorder_graph_cards(desired_ids)
            setattr(self, "__graph_order", desired_ids)

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

        resource_fingerprint = self.resource_manager.get_resource_library_fingerprint()
        current_folder_scope = str(getattr(self, "current_folder_scope", "") or "") or "all"
        refresh_signature = (
            resource_fingerprint,
            current_package_key,
            self.current_graph_type,
            current_folder_scope,
            self.current_folder,
            self.current_sort_by,
        )
        previous_signature = getattr(self, "__graph_list_refresh_signature", None)
        if previous_signature == refresh_signature:
            return
        setattr(self, "__graph_list_refresh_signature", refresh_signature)

        # 切目录时取消上一轮后台元数据加载，避免“点进新目录但旧目录还在补数据”造成抖动。
        generation = int(getattr(self, "_async_graph_list_generation", 0) or 0) + 1
        setattr(self, "_async_graph_list_generation", generation)
        self._cancel_async_graph_metadata_load()

        # 共享图集合：用于“当前项目视图”下混入共享资源时标记与过滤。
        shared_graph_ids: set[str] = set()
        resource_roots = list(self.resource_manager.get_current_resource_roots() or [])
        shared_root_dir = resource_roots[0].resolve() if resource_roots else None

        graph_paths = self.resource_manager.list_resource_file_paths(ResourceType.GRAPH)
        graph_ids = list(self.resource_manager.list_resources(ResourceType.GRAPH) or [])
        if isinstance(shared_root_dir, Path):
            for graph_id_value in graph_ids:
                graph_id = str(graph_id_value or "").strip()
                if not graph_id:
                    continue
                file_path = graph_paths.get(graph_id)
                if not isinstance(file_path, Path):
                    continue
                resolved_file = file_path.resolve()
                if hasattr(resolved_file, "is_relative_to"):
                    if resolved_file.is_relative_to(shared_root_dir):
                        shared_graph_ids.add(graph_id)
                else:
                    root_parts = shared_root_dir.parts
                    file_parts = resolved_file.parts
                    if len(file_parts) >= len(root_parts) and file_parts[: len(root_parts)] == root_parts:
                        shared_graph_ids.add(graph_id)

        allowed_graph_ids = None
        if isinstance(self.current_package, PackageView):
            pkg_resources = self.package_index_manager.get_package_resources(self.current_package.package_id)
            allowed_graph_ids = set(pkg_resources.graphs) if pkg_resources else set()
            # “当前项目视图”下仍应可见共享资源（共享根对所有存档可见）。
            allowed_graph_ids.update(shared_graph_ids)

        # 关键优化：切目录时先用“文件路径推断”快速列出 graph_id，不在 UI 线程读文件/解析 AST。
        sanitized_current_folder = (
            self.resource_manager.sanitize_folder_path(self.current_folder) if self.current_folder else ""
        )
        folder_prefix = f"{sanitized_current_folder}/" if sanitized_current_folder else ""
        current_folder_scope = str(getattr(self, "current_folder_scope", "") or "") or "all"
        current_graph_type = str(getattr(self, "current_graph_type", "") or "") or "server"

        fast_graph_entries: List[dict] = []
        for graph_id_value in graph_ids:
            graph_id = str(graph_id_value or "").strip()
            if not graph_id:
                continue
            if allowed_graph_ids is not None and graph_id not in allowed_graph_ids:
                continue

            file_path = graph_paths.get(graph_id)
            inferred_type = ""
            inferred_folder = ""
            if isinstance(file_path, Path):
                inferred_type, inferred_folder = self._infer_graph_type_and_folder_path_from_file_path(file_path)
            if current_graph_type != "all":
                if inferred_type != current_graph_type:
                    continue
            else:
                if inferred_type not in {"server", "client"}:
                    continue

            # 文件夹树点击：需要支持“子树”过滤
            if sanitized_current_folder:
                if inferred_folder != sanitized_current_folder and not inferred_folder.startswith(folder_prefix):
                    continue

            is_shared = graph_id in shared_graph_ids
            if current_folder_scope == "shared" and not is_shared:
                continue
            if current_folder_scope == "package" and is_shared:
                continue

            fast_graph_entries.append(
                {
                    "graph_id": graph_id,
                    "graph_type": inferred_type,
                    "folder_path": inferred_folder,
                    "file_path": file_path,
                    "is_shared": is_shared,
                }
            )

        graph_data_list = []
        pending_metadata_ids: List[str] = []
        for entry in fast_graph_entries:
            graph_id = entry["graph_id"]
            is_shared = bool(entry.get("is_shared"))
            folder_path = str(entry.get("folder_path", "") or "")
            graph_type = str(entry.get("graph_type", "") or "")
            file_path = entry.get("file_path")

            metadata = self._graph_metadata_cache.get(graph_id)
            if isinstance(metadata, dict):
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
                    "graph_id": metadata.get("graph_id") or graph_id,
                    "name": metadata.get("name") or graph_id,
                    "graph_type": metadata.get("graph_type") or graph_type or "server",
                    "folder_path": metadata.get("folder_path") or folder_path,
                    "description": metadata.get("description") or "",
                    "last_modified": time_str,
                    "last_modified_ts": timestamp_value,
                    "node_count": node_count,
                    "edge_count": edge_count,
                    "is_corrupted": False,
                    "is_shared": is_shared,
                }
            else:
                # 先构建“占位卡片”：展示文件名/mtime 等快信息，避免切目录卡顿。
                inferred_name = graph_id
                last_modified_ts = 0.0
                last_modified_text = "未知"
                is_corrupted = False
                if isinstance(file_path, Path):
                    inferred_name = file_path.stem or graph_id
                    if file_path.exists():
                        last_modified_ts = float(file_path.stat().st_mtime)
                        last_modified_text = datetime.fromtimestamp(last_modified_ts).strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        is_corrupted = True
                else:
                    is_corrupted = True

                graph_data = {
                    "graph_id": graph_id,
                    "name": f"⚠️ {graph_id} (缺失)" if is_corrupted else inferred_name,
                    "graph_type": graph_type or ("server" if current_graph_type == "all" else current_graph_type),
                    "folder_path": folder_path,
                    "description": "节点图文件缺失或索引异常，请检查资源库" if is_corrupted else "",
                    "last_modified": last_modified_text,
                    "last_modified_ts": last_modified_ts,
                    "node_count": 0,
                    "edge_count": 0,
                    "is_corrupted": bool(is_corrupted),
                    "is_shared": is_shared,
                }
                if not is_corrupted:
                    pending_metadata_ids.append(graph_id)

            ref_count = self.reference_tracker.get_reference_count(graph_id)
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
        elif self.selected_graph_id:
            # 刷新后原选中图已不在当前列表中（例如源文件被外部删除/视图范围切换导致不可见）：
            # 清空选中并通知上层面板更新为空状态，避免右侧仍加载旧 graph_id 后提示“源文件不存在”。
            self.selected_graph_id = None
            self.graph_selected.emit("")
            if hasattr(self, "notify_selection_state"):
                self.notify_selection_state(False, context={"source": "graph"})

        # 后台补全：只对“未命中内存缓存”的条目读取 docstring 元数据（可能触发 AST 解析，放到线程中）。
        if pending_metadata_ids:
            self._set_graph_list_loading_visible(
                True,
                text=f"正在加载 {len(pending_metadata_ids)} 个节点图的元信息…（大图首次加载可能稍慢）",
            )
            thread = GraphMetadataLoadThread(
                resource_manager=self.resource_manager,
                graph_ids=list(pending_metadata_ids),
                parent=self if isinstance(self, QtCore.QObject) else None,
            )
            setattr(self, "_async_graph_metadata_thread", thread)

            def _apply_loaded(graph_id: str, metadata_obj: object) -> None:
                if int(getattr(self, "_async_graph_list_generation", 0) or 0) != int(generation):
                    return
                card = self.graph_cards.get(graph_id)
                if not card:
                    return
                ref_count_value = self.reference_tracker.get_reference_count(graph_id)
                has_error = self.error_tracker.has_error(graph_id)
                if isinstance(metadata_obj, dict):
                    self._graph_metadata_cache[graph_id] = metadata_obj
                    modified_time = metadata_obj.get("modified_time", "")
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
                    graph_data = {
                        "graph_id": metadata_obj.get("graph_id") or graph_id,
                        "name": metadata_obj.get("name") or graph_id,
                        "graph_type": metadata_obj.get("graph_type") or card.graph_data.get("graph_type") or "server",
                        "folder_path": metadata_obj.get("folder_path") or card.graph_data.get("folder_path") or "",
                        "description": metadata_obj.get("description") or "",
                        "last_modified": time_str,
                        "last_modified_ts": timestamp_value,
                        "node_count": int(metadata_obj.get("node_count") or 0),
                        "edge_count": int(metadata_obj.get("edge_count") or 0),
                        "is_corrupted": False,
                        "is_shared": bool(card.graph_data.get("is_shared")),
                    }
                else:
                    graph_data = dict(card.graph_data)
                    graph_data["name"] = f"⚠️ {graph_id} (损坏)"
                    graph_data["description"] = "节点图文件损坏或无法解析，请检查代码文件"
                    graph_data["is_corrupted"] = True

                snapshot_entry = self._build_graph_snapshot_entry(graph_data, ref_count_value, has_error)
                current_snapshot = getattr(self, "__graph_snapshot", {}) or {}
                if current_snapshot.get(graph_id) != snapshot_entry:
                    card.update_graph_info(graph_data, ref_count_value, has_error)
                    current_snapshot = dict(current_snapshot)
                    current_snapshot[graph_id] = snapshot_entry
                    setattr(self, "__graph_snapshot", current_snapshot)

            thread.metadata_loaded.connect(_apply_loaded)

            def _on_done() -> None:
                current_thread = getattr(self, "_async_graph_metadata_thread", None)
                if current_thread is thread:
                    setattr(self, "_async_graph_metadata_thread", None)
                if int(getattr(self, "_async_graph_list_generation", 0) or 0) != int(generation):
                    return
                self._set_graph_list_loading_visible(False)
                # 若当前排序依赖名称/节点数，则在元数据补全后重新排序一次，确保结果准确。
                if str(getattr(self, "current_sort_by", "") or "") in {"name", "nodes"}:
                    self._resort_current_graph_cards()

            thread.finished.connect(_on_done)
            thread.finished.connect(thread.deleteLater)
            thread.start()
        else:
            self._set_graph_list_loading_visible(False)

    def _sort_graphs(self, graph_list: List[dict]) -> List[dict]:
        """根据当前排序方式对节点图列表排序"""
        sorters: Dict[str, Callable[[dict], object]] = {
            "modified": lambda item: item["data"].get("last_modified_ts", 0),
            "name": lambda item: item["data"].get("name", "").lower(),
            "nodes": lambda item: item["data"].get("node_count", 0),
            "references": lambda item: item["ref_count"],
        }
        sorter = sorters.get(self.current_sort_by)
        if not sorter:
            return graph_list

        # 约定：无论选择何种排序规则，都要保证“当前项目资源优先、共享资源靠后”。
        # 即：先按 is_shared 分组，再在各自分组内应用当前排序规则。
        reverse_flag = self.current_sort_by in {"modified", "nodes", "references"}

        project_graphs = [
            item for item in graph_list if not bool((item.get("data") or {}).get("is_shared"))
        ]
        shared_graphs = [
            item for item in graph_list if bool((item.get("data") or {}).get("is_shared"))
        ]

        return (
            sorted(project_graphs, key=sorter, reverse=reverse_flag)
            + sorted(shared_graphs, key=sorter, reverse=reverse_flag)
        )

    def _on_graph_card_clicked(self, graph_id: str) -> None:
        """卡片点击"""
        if self.selected_graph_id and self.selected_graph_id in self.graph_cards:
            self.graph_cards[self.selected_graph_id].set_selected(False)
        self.selected_graph_id = graph_id
        if graph_id in self.graph_cards:
            self.graph_cards[graph_id].set_selected(True)
        self.graph_selected.emit(graph_id)

    def _ensure_graph_resource_async_loader(self) -> GraphResourceAsyncLoader:
        loader = getattr(self, "_graph_resource_async_loader", None)
        if isinstance(loader, GraphResourceAsyncLoader):
            return loader
        loader = GraphResourceAsyncLoader(parent=self)
        setattr(self, "_graph_resource_async_loader", loader)
        loader.graph_loaded.connect(self._on_graph_resource_loaded)
        loader.graph_load_failed.connect(self._on_graph_resource_load_failed)
        return loader

    def _on_graph_resource_loaded(self, graph_id: str, graph_data: dict) -> None:
        self.graph_double_clicked.emit(str(graph_id or ""), graph_data)

    def _on_graph_resource_load_failed(self, graph_id: str) -> None:
        graph_id_text = str(graph_id or "").strip()
        if not graph_id_text:
            return
        self.show_warning(
            "加载失败",
            f"无法加载节点图 '{graph_id_text}'。\n\n可能的原因：\n"
            "• 文件不存在、已被移动/删除或已损坏\n"
            "• 节点图无法通过校验（请检查节点图逻辑并修正后再加载）\n\n"
            "建议：\n"
            "• 查看控制台输出中的详细错误信息\n"
            "• 运行节点图校验：python -X utf8 -m app.cli.graph_tools validate-graphs --all（或 validate-file <图文件路径>）",
        )

    def _on_graph_card_double_clicked(self, graph_id: str) -> None:
        """卡片双击 - 打开编辑"""
        # selection_mode（例如 GraphSelectionDialog）：双击仅代表“选择该 graph_id”，不应触发重度解析加载。
        if bool(getattr(self, "selection_mode", False)):
            self.graph_double_clicked.emit(str(graph_id or ""), {})
            return

        graph_id_text = str(graph_id or "").strip()
        if not graph_id_text:
            return

        # 轻量检查：若无法读取 docstring 元数据，通常意味着文件缺失或已损坏（不进入加载线程）
        metadata = self.resource_manager.load_graph_metadata(graph_id_text)
        if not metadata:
            self.show_error(
                "无法打开节点图",
                f"节点图 '{graph_id_text}' 已损坏或无法解析，无法打开编辑。\n\n可能的原因：\n"
                "• 代码文件包含语法错误\n"
                "• 使用了不存在的节点类型\n"
                "• 文件被手动修改导致格式错误\n"
                "• 文件已被移动/删除\n\n"
                "建议：\n"
                "• 检查资源库中的代码文件\n"
                "• 查看控制台输出中的详细错误信息\n"
                "• 如果有备份，尝试从备份恢复",
            )
            return

        # 后台加载：避免 load_resource(ResourceType.GRAPH, ...) 在 UI 线程阻塞（解析/布局/缓存命中等可能很重）
        loader = self._ensure_graph_resource_async_loader()
        loader.request_load(resource_manager=self.resource_manager, graph_id=graph_id_text)

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
                    "请在 assets/资源库/项目存档/<项目存档名>/节点图 或 assets/资源库/共享/节点图 下通过 Python 文件定义新图。",
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
        write_root_dir = self._resolve_graph_write_root_dir()
        saved = self.resource_manager.save_resource(
            ResourceType.GRAPH,
            graph_id,
            graph_config.serialize(),
            resource_root_dir=write_root_dir,
        )
        if not saved:
            self.show_error("新建失败", f"新建节点图 '{name}' 失败：保存被取消（往返校验未通过或存在保存冲突）。")
            return

        # 新建资源：失效 PackageIndex 派生缓存，确保当前视图能立即看到新图
        current_package = getattr(self, "current_package", None)
        if isinstance(current_package, PackageView):
            invalidate_cache = getattr(self.package_index_manager, "invalidate_package_index_cache", None)
            if callable(invalidate_cache):
                invalidate_cache(current_package.package_id)

        self._force_invalidate_graph_list_refresh_signature(self)
        self._invalidate_graph_metadata(graph_id)
        self._refresh_graph_list()
        self.selected_graph_id = graph_id
        if graph_id in self.graph_cards:
            self.graph_cards[graph_id].set_selected(True)
            self.graph_selected.emit(graph_id)

    def _duplicate_selected_graph(self) -> None:
        """复制当前选中的节点图（生成新 graph_id）。"""
        if getattr(self, "graph_library_read_only", False):
            if hasattr(self, "show_warning"):
                self.show_warning(
                    "只读模式",
                    "当前节点图库为只读模式，不能在 UI 中复制节点图；请在资源库中手动复制对应文件。",
                )
            return
        graph_id = str(getattr(self, "selected_graph_id", "") or "").strip()
        if not graph_id:
            self.show_warning("提示", "请先选择要复制的节点图")
            return

        graph_data = self.resource_manager.load_resource(ResourceType.GRAPH, graph_id)
        if not graph_data:
            self.show_warning("警告", "无法加载节点图数据")
            return

        graph_config = GraphConfig.deserialize(graph_data)
        new_graph_id = generate_prefixed_id("graph")
        new_name = f"{graph_config.name} - 副本"

        new_data = copy.deepcopy(graph_config.data) if isinstance(graph_config.data, dict) else {}
        if isinstance(new_data, dict):
            new_data["graph_id"] = new_graph_id
            new_data["graph_name"] = new_name
            metadata = new_data.get("metadata")
            if isinstance(metadata, dict):
                metadata.setdefault("graph_type", graph_config.graph_type)

        new_graph_config = GraphConfig(
            graph_id=new_graph_id,
            name=new_name,
            graph_type=graph_config.graph_type,
            folder_path=str(getattr(graph_config, "folder_path", "") or ""),
            data=new_data,
        )
        new_graph_config.update_timestamp()

        write_root_dir = self._resolve_graph_write_root_dir()
        saved = self.resource_manager.save_resource(
            ResourceType.GRAPH,
            new_graph_id,
            new_graph_config.serialize(),
            resource_root_dir=write_root_dir,
        )
        if not saved:
            self.show_error("复制失败", f"复制节点图 '{graph_config.name}' 失败：保存被取消（往返校验未通过或存在保存冲突）。")
            return

        current_package = getattr(self, "current_package", None)
        if isinstance(current_package, PackageView):
            invalidate_cache = getattr(self.package_index_manager, "invalidate_package_index_cache", None)
            if callable(invalidate_cache):
                invalidate_cache(current_package.package_id)

        self._force_invalidate_graph_list_refresh_signature(self)
        self._invalidate_graph_metadata(new_graph_id)
        self._refresh_graph_list()
        self.select_graph_by_id(new_graph_id, open_editor=False, sync_folder_filter=False)
        ToastNotification.show_message(
            QtWidgets.QApplication.activeWindow(),
            f"已复制节点图：{new_name}",
            "info",
        )

    def _rename_selected_graph(self) -> None:
        """重命名当前选中的节点图（仅修改 name 字段）。"""
        if getattr(self, "graph_library_read_only", False):
            if hasattr(self, "show_warning"):
                self.show_warning(
                    "只读模式",
                    "当前节点图库为只读模式，不能在 UI 中重命名节点图；请在资源库中修改对应文件。",
                )
            return
        graph_id = str(getattr(self, "selected_graph_id", "") or "").strip()
        if not graph_id:
            self.show_warning("提示", "请先选择要重命名的节点图")
            return

        graph_data = self.resource_manager.load_resource(ResourceType.GRAPH, graph_id)
        if not graph_data:
            self.show_warning("警告", "无法加载节点图数据")
            return

        graph_config = GraphConfig.deserialize(graph_data)
        old_name = str(getattr(graph_config, "name", "") or "").strip() or graph_id
        new_name = input_dialogs.prompt_text(
            self,
            "重命名节点图",
            "请输入新的节点图名称:",
            text=old_name,
        )
        if not new_name:
            return
        new_name = str(new_name).strip()
        if not new_name or new_name == old_name:
            return

        graph_config.name = new_name
        if isinstance(graph_config.data, dict):
            graph_config.data["graph_name"] = new_name
        graph_config.update_timestamp()
        saved = self.resource_manager.save_resource(ResourceType.GRAPH, graph_id, graph_config.serialize())
        if not saved:
            self.show_error("重命名失败", f"重命名节点图 '{old_name}' 失败：保存被取消（往返校验未通过或存在保存冲突）。")
            return

        self._force_invalidate_graph_list_refresh_signature(self)
        self._invalidate_graph_metadata(graph_id)
        self._refresh_graph_list()
        self.select_graph_by_id(graph_id, open_editor=False, sync_folder_filter=False)
        ToastNotification.show_message(
            QtWidgets.QApplication.activeWindow(),
            f"已重命名节点图：{new_name}",
            "info",
        )

    def _locate_issues_for_selected_graph(self) -> None:
        """打开验证页面并定位到与当前节点图相关的问题（若存在）。"""
        graph_id = str(getattr(self, "selected_graph_id", "") or "").strip()
        if not graph_id:
            self.show_warning("提示", "请先选择要定位问题的节点图")
            return
        window = getattr(self, "window", None)
        host = window() if callable(window) else window
        locate = getattr(host, "_locate_issues_for_resource_id", None) if host is not None else None
        if callable(locate):
            locate(graph_id)

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
        self._force_invalidate_graph_list_refresh_signature(self)
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
        folders = self.resource_manager.get_all_graph_folders(
            resource_roots=self.resource_manager.get_current_resource_roots()
        )
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
        saved = self.resource_manager.save_resource(ResourceType.GRAPH, graph_id, graph_config.serialize())
        if not saved:
            self.show_error("移动失败", f"移动节点图 '{graph_config.name}' 失败：保存被取消（往返校验未通过或存在保存冲突）。")
            return

        self._force_invalidate_graph_list_refresh_signature(self)
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
            # 右键也应视为一次“选中”，确保菜单动作作用于当前卡片。
            self._on_graph_card_clicked(graph_id)
            if read_only:
                builder.add_action("查看节点图", lambda: self._on_graph_card_double_clicked(graph_id))
                builder.add_separator()
                builder.add_action("查看详情", lambda: self._show_graph_detail_by_id(graph_id))
            else:
                primary_shortcut = getattr(self, "_primary_shortcut", None)
                shortcut_dup = (
                    str(primary_shortcut("library.duplicate") or "") if callable(primary_shortcut) else "Ctrl+D"
                )
                shortcut_rename = (
                    str(primary_shortcut("library.rename") or "") if callable(primary_shortcut) else "F2"
                )
                shortcut_move = (
                    str(primary_shortcut("library.move") or "") if callable(primary_shortcut) else ""
                )
                shortcut_delete = (
                    str(primary_shortcut("library.delete") or "") if callable(primary_shortcut) else ""
                )

                builder.add_action("编辑节点图", lambda: self._on_graph_card_double_clicked(graph_id))
                builder.add_separator()
                builder.add_action("复制", self._duplicate_selected_graph, shortcut=(shortcut_dup or None))
                builder.add_action("重命名", self._rename_selected_graph, shortcut=(shortcut_rename or None))
                builder.add_action("移动到文件夹", self._move_graph, shortcut=(shortcut_move or None))
                builder.add_separator()
                builder.add_action("查看详情", lambda: self._show_graph_detail_by_id(graph_id))
                builder.add_separator()
                builder.add_action("删除", lambda: self._delete_graph_by_id(graph_id), shortcut=(shortcut_delete or None))
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

    def select_graph_by_id(
        self,
        graph_id: str,
        open_editor: bool = False,
        *,
        sync_folder_filter: bool = True,
    ) -> None:
        """程序化选择并（可选）打开指定ID的节点图。

        参数：
        - sync_folder_filter:
            - True：同步切换左侧目录筛选（current_folder），让中间列表聚焦到目标节点图所在文件夹子树；
            - False：仅保证类型切换与卡片选中，不改变当前目录筛选（用于启动恢复等场景，避免“列表看起来只剩少量图”）。
        """
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

        if sync_folder_filter:
            target_folder = metadata.get("folder_path", "") or ""
            self.current_folder = target_folder
            # 同步 folder_scope：避免选中共享图时仍停留在“当前存档”分支导致目录高亮与列表 scope 不一致。
            owner_root_id = ""
            package_index_manager = getattr(self, "package_index_manager", None)
            get_owner = getattr(package_index_manager, "get_resource_owner_root_id", None)
            if callable(get_owner):
                owner_root_id = str(
                    get_owner(resource_type="graph", resource_id=graph_id)  # type: ignore[call-arg]
                    or ""
                ).strip()
            if owner_root_id == "shared":
                inferred_scope = "shared"
            elif owner_root_id:
                inferred_scope = "package"
            else:
                inferred_scope = "all"
            setattr(self, "current_folder_scope", inferred_scope)
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

        # layout 顶部可能存在“加载中提示”等固定 widget（例如 _graph_list_loading_label）。
        # 这些 widget 不属于卡片序列，应保持在卡片之前，避免 reorder 把卡片插到提示之上。
        base_index = 0
        loading_label = getattr(self, "_graph_list_loading_label", None)
        if isinstance(loading_label, QtWidgets.QWidget):
            label_index = layout.indexOf(loading_label)
            if label_index != -1:
                base_index = label_index + 1
        for order_index, graph_id in enumerate(ordered_ids):
            card = self.graph_cards.get(graph_id)
            if not card:
                continue
            current_index = layout.indexOf(card)
            target_index = min(base_index + order_index, spacer_index)
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


