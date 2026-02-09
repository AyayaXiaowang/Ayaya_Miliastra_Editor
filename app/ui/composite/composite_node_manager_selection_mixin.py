"""CompositeNodeManagerWidget 的选择/预览加载/图编辑器复位 mixin。"""

from __future__ import annotations

from typing import Optional

from PyQt6 import QtCore

from engine.graph.models.graph_model import GraphModel
from app.ui.foundation.dialog_utils import ask_choice_dialog, show_warning_dialog
from app.ui.graph.graph_scene import GraphScene


class CompositeNodeManagerSelectionMixin:
    def _clear_current_composite_context(self) -> None:
        """清空当前复合节点上下文，并重置图编辑器状态以避免脏状态残留。"""
        self.current_composite = None
        self.current_composite_id = ""
        self._composite_meta_dirty = False
        self._reset_graph_editor_to_empty()
        self.composite_selected.emit("")

    def _reset_graph_editor_to_empty(self) -> None:
        """将内部 GraphEditorController 复位到空图，以清除 is_dirty 与旧场景引用。"""
        if self.graph_editor_controller is None or self.graph_view is None:
            if self.graph_view is not None:
                self.graph_view.setScene(None)
            self.graph_model = None
            self.graph_scene = None
            return

        empty_graph_data = {"nodes": [], "edges": [], "graph_variables": []}
        composite_edit_context = {
            "composite_id": "",
            "manager": self.manager,
            "on_virtual_pins_changed": self._on_virtual_pins_changed,
            "can_persist": self.can_persist_composite,
        }
        self.graph_editor_controller.load_graph_for_composite(
            "composite_graph",
            empty_graph_data,
            composite_edit_context=composite_edit_context,
        )
        self.graph_editor_controller.mark_as_saved()
        self.graph_model = self.graph_editor_controller.get_current_model()
        self.graph_scene = self.graph_editor_controller.get_current_scene()

    def _select_composite(self, composite_id: str, *, open_preview: bool) -> bool:
        """选中复合节点；仅在 open_preview=True 时进入预览页并加载子图。"""
        normalized_id = str(composite_id or "")
        if not normalized_id:
            return False

        if self.current_composite_id and self.current_composite_id != normalized_id:
            if not self._confirm_leave_current_composite():
                # 回滚列表选中
                self._try_select_composite_in_list(self.current_composite_id, trigger_selection=False)
                return False
            self._reset_graph_editor_to_empty()

        composite_config = self._service.load_composite(normalized_id, ensure_subgraph=True)
        if composite_config is None:
            show_warning_dialog(self, "错误", "无法加载复合节点")
            return False

        self.current_composite = composite_config
        self.current_composite_id = normalized_id
        self._composite_meta_dirty = False

        print(f"[复合节点] 选中节点: {composite_config.node_name} (ID: {normalized_id})")
        self.composite_selected.emit(normalized_id)

        if open_preview:
            self._show_preview_page()
            self._load_graph(composite_config.sub_graph)
        else:
            self._show_browse_page()
        return True

    def _has_unsaved_changes(self) -> bool:
        """判断当前复合节点是否存在未保存的修改。"""
        graph_dirty = False
        if self.graph_editor_controller is not None:
            graph_dirty = bool(self.graph_editor_controller.is_dirty)
        return graph_dirty or self._composite_meta_dirty

    def _confirm_leave_current_composite(self) -> bool:
        """切换复合节点前确认：仅在有脏改动时询问是否保存/放弃/取消切换。"""
        if not self.current_composite or not self.current_composite_id:
            return True
        if not self._has_unsaved_changes():
            return True

        # 只读模式：不允许保存，直接询问是否放弃修改（修改理论上不应产生，但仍防御 UI 误触发）。
        if not self.can_persist_composite:
            choice_key = ask_choice_dialog(
                self,
                "未保存修改",
                (
                    f"复合节点“{self.current_composite.node_name}”存在未保存的修改。\n"
                    f"只读模式下无法保存，切换将丢失这些修改。"
                ),
                icon="warning",
                choices=[
                    ("discard", "放弃修改", "destructive"),
                    ("cancel", "取消", "reject"),
                ],
                default_choice_key="cancel",
                escape_choice_key="cancel",
            )
            return choice_key == "discard"

        choice_key = ask_choice_dialog(
            self,
            "未保存修改",
            f"复合节点“{self.current_composite.node_name}”有未保存的修改。\n是否在切换前保存？",
            icon="question",
            choices=[
                ("save", "保存", "accept"),
                ("discard", "不保存", "destructive"),
                ("cancel", "取消", "reject"),
            ],
            default_choice_key="save",
            escape_choice_key="cancel",
        )
        if choice_key == "cancel":
            return False
        if choice_key == "save":
            self._save_current_composite()
            return True
        return True

    def _load_graph(self, graph_data: dict) -> None:
        """加载子图到编辑器（优先复用 GraphEditorController）。"""
        if not graph_data:
            return

        if self.graph_editor_controller is not None and self.graph_view is not None:
            composite_edit_context = {
                "composite_id": self.current_composite_id,
                "manager": self.manager,
                "on_virtual_pins_changed": self._on_virtual_pins_changed,
                "can_persist": self.can_persist_composite,
            }
            self.graph_editor_controller.load_graph_for_composite(
                self.current_composite_id or "composite_graph",
                graph_data,
                composite_edit_context=composite_edit_context,
            )
            self.graph_model = self.graph_editor_controller.get_current_model()
            self.graph_scene = self.graph_editor_controller.get_current_scene()
        else:
            # 回退：在未注入 ResourceManager 时仍构造独立场景。
            self.graph_model = GraphModel.deserialize(graph_data)
            if self.node_library:
                updated_count = self.graph_model.sync_composite_nodes_from_library(self.node_library)
                if updated_count > 0:
                    print(f"  [复合节点编辑器] 同步了 {updated_count} 个复合节点的端口定义")
            self.graph_scene = GraphScene(
                self.graph_model,
                node_library=self.node_library,
                composite_edit_context={
                    "composite_id": self.current_composite_id,
                    "manager": self.manager,
                    "on_virtual_pins_changed": self._on_virtual_pins_changed,
                    "can_persist": self.can_persist_composite,
                },
                edit_session_capabilities=self._edit_session_capabilities,
            )
            if self.graph_view is not None:
                self.graph_view.setScene(self.graph_scene)
            if self.graph_scene is not None:
                for node_model in self.graph_model.nodes.values():
                    self.graph_scene.add_node_item(node_model)
                for edge_model in self.graph_model.edges.values():
                    self.graph_scene.add_edge_item(edge_model)

        if self.graph_view is not None:
            QtCore.QTimer.singleShot(100, self.graph_view.fit_all)

    def _on_virtual_pins_changed(self) -> None:
        """虚拟引脚被修改后的回调（节点删除导致引脚清理时触发）。"""
        print("[复合节点管理器] 虚拟引脚已更新，触发刷新")
        if self.current_composite_id:
            self.composite_selected.emit(self.current_composite_id)

    # ------------------------------------------------------------------ 外部选择接口

    def select_composite_by_id(self, composite_id: str) -> bool:
        """通过 composite_id 选中复合节点（供外部跳转使用）。

        说明：
        - composite_id 是稳定标识符，不受改名影响；优先于按名称选择。
        - 即使当前存档上下文过滤导致列表未展示该节点，也允许直接打开其预览页用于定位。
        """
        target_id = str(composite_id or "")
        if not target_id:
            return False

        composite_config = self._service.load_composite(target_id, ensure_subgraph=True)
        if composite_config is None:
            return False

        folder_path = str(composite_config.folder_path or "")
        normalized_folder = self._normalize_folder_path(folder_path)
        shared_composite_ids = self._get_shared_composite_ids()
        self._current_folder_scope = self._resolve_composite_scope(target_id, shared_composite_ids=shared_composite_ids)
        self._current_folder_path = normalized_folder
        self._refresh_composite_list()
        self._try_select_composite_in_list(target_id, trigger_selection=False)
        # 外部导航：默认直接打开预览
        return self._select_composite(target_id, open_preview=True)

    def select_composite_by_name(self, composite_name: str) -> bool:
        """通过名称选中复合节点（供外部导航使用）。"""
        target_name = str(composite_name or "")
        if not target_name:
            return False
        # 直接从 manager 中查找，避免依赖 UI 树结构
        target_composite: Optional[object] = None
        for composite in self.manager.list_composite_nodes():
            if composite is not None and composite.node_name == target_name:
                target_composite = composite
                break
        if target_composite is None:
            return False

        folder_path = str(target_composite.folder_path or "")
        normalized_folder = self._normalize_folder_path(folder_path)
        shared_composite_ids = self._get_shared_composite_ids()
        self._current_folder_scope = self._resolve_composite_scope(
            target_composite.composite_id,
            shared_composite_ids=shared_composite_ids,
        )
        self._current_folder_path = normalized_folder
        self._refresh_composite_list()
        self._try_select_composite_in_list(target_composite.composite_id, trigger_selection=False)
        # 外部导航：默认直接打开预览
        return self._select_composite(target_composite.composite_id, open_preview=True)



