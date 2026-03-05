"""自动排版控制器

负责节点图的自动排版逻辑（验证、克隆布局、差异合并、同步）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6 import QtCore, QtWidgets, sip
from app.ui.foundation.toast_notification import ToastNotification

from engine.graph import validate_graph_model
from engine.validate import validate_files
from engine.utils.workspace import ensure_settings_workspace_root, get_injected_workspace_root_or_none

if TYPE_CHECKING:
    from app.ui.graph.graph_view import GraphView


class AutoLayoutController:
    """自动排版控制器
    
    管理自动排版的完整流程：
    1. 排版前回调（可选重载）
    2. 验证节点图
    3. 克隆模型并执行就地布局
    4. 差异合并（新增/删除节点与连线）
    5. 同步坐标与基本块
    6. 更新图形项
    7. 排版完成回调
    """

    @classmethod
    def run(cls, view: "GraphView") -> None:
        """执行自动排版"""
        scene = view.scene()
        if scene is None:
            return

        # 防止重入：自动排版属于“长任务”，重复点击只会放大卡顿与状态错乱风险
        if bool(getattr(view, "_auto_layout_running", False)):
            return

        # 排版前回调（例如：按当前设置强制重载 .py → 模型，清理旧副本/缓存）
        # 约定：若回调返回 True，表示触发了“重解析/重载”，自动排版应延后到加载完成后执行。
        if getattr(view, "on_before_auto_layout", None):
            should_defer = bool(view.on_before_auto_layout())
            if should_defer:
                return

        # 回调可能替换 scene/model（例如重载），这里重新获取一次
        scene = view.scene()
        if scene is None:
            return

        # AutoLayoutController 完整流程要求 scene 为真实 QGraphicsScene（GraphScene）。
        # 测试/桩场景允许只验证“清理 edge_items 不触碰已删除对象”：
        # - 直接清空 edge_items/_edges_by_node_id（不调用 removeItem），避免访问已释放对象导致崩溃。
        if not isinstance(scene, QtWidgets.QGraphicsScene):
            edge_items = getattr(scene, "edge_items", None)
            if isinstance(edge_items, dict):
                edge_items.clear()
            edges_by_node = getattr(scene, "_edges_by_node_id", None)
            if isinstance(edges_by_node, dict):
                edges_by_node.clear()
            return

        # 防御性清理：edge_items/_edges_by_node_id 可能残留已被 Qt 释放的悬空对象。
        # 这类对象一旦被触碰（removeItem/访问属性）可能触发进程级崩溃：
        # - `wrapped C/C++ object ... has been deleted`
        # 自动排版属于长任务，提前清理可避免后续流程（线程回调/分帧 apply）踩雷。
        edge_items = getattr(scene, "edge_items", None)
        if isinstance(edge_items, dict) and edge_items:
            for edge_id, edge_item in list(edge_items.items()):
                if edge_item is None or sip.isdeleted(edge_item):
                    edge_items.pop(edge_id, None)

        edges_by_node = getattr(scene, "_edges_by_node_id", None)
        if isinstance(edges_by_node, dict) and edges_by_node:
            for node_id, items in list(edges_by_node.items()):
                if not isinstance(items, set):
                    continue
                alive_items = {it for it in items if it is not None and (not sip.isdeleted(it))}
                if alive_items:
                    edges_by_node[node_id] = alive_items
                else:
                    edges_by_node.pop(node_id, None)

        setattr(view, "_auto_layout_running", True)
        if hasattr(view, "auto_layout_button") and getattr(view, "auto_layout_button", None) is not None:
            view.auto_layout_button.setEnabled(False)

        workspace_path = cls._resolve_workspace_path(getattr(scene, "model", None))

        # 如果是复合节点编辑器，构建虚拟引脚映射
        virtual_pin_mappings = {}
        if hasattr(scene, 'is_composite_editor') and scene.is_composite_editor:
            composite_id = scene.composite_edit_context.get('composite_id')
            manager = scene.composite_edit_context.get('manager')
            if composite_id and manager:
                composite = manager.get_composite_node(composite_id)
                if composite:
                    for vpin in composite.virtual_pins:
                        for mapped_port in vpin.mapped_ports:
                            virtual_pin_mappings[(mapped_port.node_id, mapped_port.port_name)] = mapped_port.is_input
        if hasattr(view, "show_loading_overlay"):
            view.show_loading_overlay(
                title="正在自动排版…",
                detail="验证/布局计算（后台）…",
                progress_value=None,
                progress_max=None,
            )

        generation = int(getattr(view, "_auto_layout_generation", 0) or 0) + 1
        setattr(view, "_auto_layout_generation", generation)

        thread = _AutoLayoutComputeThread(
            model=scene.model,
            node_library=getattr(scene, "node_library", None),
            virtual_pin_mappings=dict(virtual_pin_mappings),
            workspace_path=workspace_path,
            parent=view,
        )
        setattr(view, "_auto_layout_compute_thread", thread)

        def _on_thread_finished() -> None:
            cls._on_compute_thread_finished(
                view=view,
                expected_scene=scene,
                generation=generation,
                thread=thread,
            )

        thread.finished.connect(_on_thread_finished)
        thread.start()
        return

    @classmethod
    def _on_compute_thread_finished(
        cls,
        *,
        view: "GraphView",
        expected_scene: object,
        generation: int,
        thread: "_AutoLayoutComputeThread",
    ) -> None:
        # generation 不一致：丢弃旧任务
        if int(getattr(view, "_auto_layout_generation", 0) or 0) != int(generation):
            return

        current_scene = view.scene()
        if current_scene is None or current_scene is not expected_scene:
            setattr(view, "_auto_layout_running", False)
            if hasattr(view, "auto_layout_button") and getattr(view, "auto_layout_button", None) is not None:
                view.auto_layout_button.setEnabled(True)
            if hasattr(view, "hide_loading_overlay"):
                view.hide_loading_overlay()
            return

        thread_result = getattr(thread, "result", None)
        if thread_result is None:
            raise RuntimeError("自动排版线程失败：未返回 result（详见控制台 traceback）")

        errors = list(thread_result.errors or [])
        if errors:
            from engine.configs.settings import settings as _settings_ui

            if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
                print("\n" + "=" * 80)
                print("【自动布局】节点图存在错误，无法自动排版")
                print("=" * 80)
                for error in errors:
                    print(f"  • {error}")
                print("=" * 80 + "\n")

            first_error = errors[0]
            max_message_length = 180
            if len(first_error) > max_message_length:
                first_error = first_error[: max_message_length - 3] + "..."
            toast_message = (
                f"自动排版失败：节点图存在 {len(errors)} 个错误，"
                f"例如：{first_error}。在设置>自动排版中开启“图编辑器详细日志”可查看完整原因。"
            )
            if isinstance(view, QtWidgets.QWidget):
                ToastNotification.show_message(view, toast_message, "warning")

            setattr(view, "_auto_layout_running", False)
            if hasattr(view, "auto_layout_button") and getattr(view, "auto_layout_button", None) is not None:
                view.auto_layout_button.setEnabled(True)
            if hasattr(view, "hide_loading_overlay"):
                view.hide_loading_overlay()
            return

        layout_result = thread_result.layout_result
        if layout_result is None:
            raise RuntimeError("自动排版线程返回空 layout_result")

        scene = current_scene

        # 应用增强布局差分合并（在主线程修改 GraphModel）
        from engine.layout.utils.augmented_layout_merge import apply_augmented_layout_merge

        old_edge_ids = list((getattr(scene.model, "edges", None) or {}).keys())
        merge_delta = apply_augmented_layout_merge(
            scene.model,
            layout_result,
            allow_fallback_without_augmented=False,
        )
        if not merge_delta.used_augmented_model:
            setattr(view, "_auto_layout_running", False)
            if hasattr(view, "auto_layout_button") and getattr(view, "auto_layout_button", None) is not None:
                view.auto_layout_button.setEnabled(True)
            if hasattr(view, "hide_loading_overlay"):
                view.hide_loading_overlay()
            return

        # 反馈：当启用“长连线自动生成局部变量中转节点”时，提示本次实际插入数量
        from engine.configs.settings import settings as _settings_ui
        if bool(getattr(_settings_ui, "LAYOUT_AUTO_INSERT_LOCAL_VAR_RELAY", False)):
            from engine.layout.utils.local_variable_relay_inserter import is_local_var_relay_node_id

            added_node_ids = getattr(merge_delta, "added_node_ids", None) or set()
            relay_added_count = sum(1 for node_id in added_node_ids if is_local_var_relay_node_id(node_id))
            if relay_added_count > 0:
                threshold = int(getattr(_settings_ui, "LAYOUT_LOCAL_VAR_RELAY_MAX_BLOCK_DISTANCE", 5) or 5)
                ToastNotification.show_message(
                    view,
                    f"自动排版：已插入 {relay_added_count} 个局部变量中转节点（阈值={threshold}）",
                    "success",
                )
            elif bool(getattr(_settings_ui, "GRAPH_UI_VERBOSE", False)):
                threshold = int(getattr(_settings_ui, "LAYOUT_LOCAL_VAR_RELAY_MAX_BLOCK_DISTANCE", 5) or 5)
                print(
                    f"[自动排版] 局部变量中转已启用，但本次未插入 relay 节点（阈值={threshold}）。",
                    flush=True,
                )

        if hasattr(view, "update_loading_overlay_detail"):
            view.update_loading_overlay_detail("应用布局并重建图元…")

        apply_job = _AutoLayoutApplyJob(
            view=view,
            scene=scene,
            old_edge_ids=old_edge_ids,
            removed_copy_node_ids=sorted(getattr(merge_delta, "removed_copy_node_ids", set()) or set()),
            generation=generation,
            parent=view,
        )
        setattr(view, "_auto_layout_apply_job", apply_job)

        def _on_apply_finished() -> None:
            if int(getattr(view, "_auto_layout_generation", 0) or 0) != int(generation):
                return
            setattr(view, "_auto_layout_running", False)
            if hasattr(view, "auto_layout_button") and getattr(view, "auto_layout_button", None) is not None:
                view.auto_layout_button.setEnabled(True)
            if hasattr(view, "hide_loading_overlay"):
                view.hide_loading_overlay()

        apply_job.finished.connect(_on_apply_finished)
        apply_job.start()
        return

    @classmethod
    def _collect_validation_errors(
        cls,
        view: "GraphView",
        virtual_pin_mappings: dict[tuple[str, str], bool],
        workspace_path: Path | None = None,
    ) -> list[str]:
        scene = view.scene()
        if scene is None:
            return []
        model = getattr(scene, "model", None)
        if model is None:
            return []
        resolved_workspace_path = (
            workspace_path if workspace_path is not None else cls._resolve_workspace_path(model)
        )
        source_path = (
            cls._resolve_source_file(model, resolved_workspace_path)
            if not virtual_pin_mappings
            else None
        )
        if source_path:
            report = validate_files([source_path], resolved_workspace_path)
            return [issue.message for issue in report.issues if issue.level == "error"]
        return validate_graph_model(
            model,
            virtual_pin_mappings,
            workspace_path=resolved_workspace_path,
        )

    @classmethod
    def _resolve_source_file(cls, model, workspace_path: Path) -> Path | None:
        metadata = getattr(model, "metadata", None) or {}
        source_rel = metadata.get("source_file")
        if not source_rel:
            return None
        candidate = Path(source_rel)
        if not candidate.is_absolute():
            candidate = workspace_path / candidate
        return candidate if candidate.exists() else None

    @classmethod
    def _resolve_workspace_path(cls, _model) -> Path:
        """获取 workspace_root（单一真源：优先 settings 注入；未注入则统一走引擎推断并注入）。"""
        injected_root = get_injected_workspace_root_or_none()
        if injected_root is not None:
            return injected_root
        return ensure_settings_workspace_root(
            start_paths=[Path(__file__).resolve()],
            load_user_settings=False,
        )


@dataclass(frozen=True, slots=True)
class _AutoLayoutComputeThreadResult:
    errors: list[str]
    layout_result: object | None


class _AutoLayoutComputeThread(QtCore.QThread):
    """后台线程：验证 + compute_layout（避免阻塞 UI 线程）。"""

    def __init__(
        self,
        *,
        model: object,
        node_library: object,
        virtual_pin_mappings: dict[tuple[str, str], bool],
        workspace_path: Path,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("AutoLayoutComputeThread")
        self._model = model
        self._node_library = node_library
        self._virtual_pin_mappings = virtual_pin_mappings
        self._workspace_path = workspace_path
        self.result: _AutoLayoutComputeThreadResult | None = None

    def run(self) -> None:
        model = self._model
        mappings = dict(self._virtual_pin_mappings or {})
        workspace_path = self._workspace_path

        # 验证：复合节点编辑器（virtual_pin_mappings 非空）走模型验证；普通节点图优先 validate_files
        source_path = (
            AutoLayoutController._resolve_source_file(model, workspace_path)  # type: ignore[arg-type]
            if not mappings
            else None
        )
        if source_path:
            report = validate_files([source_path], workspace_path)
            errors = [issue.message for issue in report.issues if issue.level == "error"]
            if errors:
                self.result = _AutoLayoutComputeThreadResult(errors=list(errors), layout_result=None)
                return
        else:
            errors = validate_graph_model(
                model,
                mappings,
                workspace_path=workspace_path,
            )
            if errors:
                self.result = _AutoLayoutComputeThreadResult(errors=list(errors), layout_result=None)
                return

        from engine.layout import LayoutService

        node_lib = self._node_library if isinstance(self._node_library, dict) else None
        layout_result = LayoutService.compute_layout(
            model,  # type: ignore[arg-type]
            node_library=node_lib,
            include_augmented_model=True,
            workspace_path=workspace_path,
        )
        self.result = _AutoLayoutComputeThreadResult(errors=[], layout_result=layout_result)


class _AutoLayoutApplyJob(QtCore.QObject):
    """主线程分帧应用自动排版结果（重建连线/同步坐标），避免阻塞 UI。"""

    finished = QtCore.pyqtSignal()

    def __init__(
        self,
        *,
        view: QtWidgets.QWidget,
        scene: QtWidgets.QGraphicsScene,
        old_edge_ids: list[str],
        removed_copy_node_ids: list[str],
        generation: int,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._view = view
        self._scene = scene
        self._generation = int(generation)

        self._phase: str = "clear_edges"
        self._time_budget_s: float = 0.010

        self._edge_ids = [str(eid) for eid in (getattr(scene, "edge_items", {}) or {}).keys()]
        self._edge_index = 0
        self._old_batched_edge_ids = [str(eid) for eid in (old_edge_ids or []) if str(eid or "")]
        self._batched_edge_index = 0

        self._node_items_snapshot = list(getattr(scene, "node_items", {}).items() or [])
        self._node_snapshot_index = 0

        self._removed_copy_node_ids = [str(nid) for nid in (removed_copy_node_ids or []) if str(nid or "")]
        self._removed_copy_index = 0

        self._new_node_ids: list[str] = []
        self._new_node_index = 0

        self._pos_sync_items: list[tuple[str, object]] = []
        self._pos_sync_index = 0

        self._edge_models: list[object] = []
        self._edge_model_index = 0

        # 批量更新优化：暂时关闭 viewport 更新、回调与索引，并开启 bulk 标记以延迟端口重排
        self._prev_bulk_adding = bool(getattr(scene, "is_bulk_adding_items", False))
        if hasattr(scene, "is_bulk_adding_items"):
            scene.is_bulk_adding_items = True

        viewport = getattr(view, "viewport", None)() if hasattr(view, "viewport") else None
        self._viewport = viewport
        self._prev_viewport_updates = bool(viewport.updatesEnabled()) if viewport is not None else True
        if viewport is not None:
            viewport.setUpdatesEnabled(False)

        self._old_on_change_cb = getattr(getattr(scene, "undo_manager", None), "on_change_callback", None)
        self._old_on_data_changed = getattr(scene, "on_data_changed", None)
        if hasattr(scene, "undo_manager") and getattr(scene, "undo_manager", None) is not None:
            scene.undo_manager.on_change_callback = None
        setattr(scene, "on_data_changed", None)

        self._old_index_method = scene.itemIndexMethod()
        scene.setItemIndexMethod(QtWidgets.QGraphicsScene.ItemIndexMethod.NoIndex)

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._on_tick)

    def start(self) -> None:
        self._timer.start()

    def _restore_scene_state(self) -> None:
        scene = self._scene
        scene.setItemIndexMethod(self._old_index_method)
        if hasattr(scene, "undo_manager") and getattr(scene, "undo_manager", None) is not None:
            scene.undo_manager.on_change_callback = self._old_on_change_cb
        setattr(scene, "on_data_changed", self._old_on_data_changed)
        if hasattr(scene, "is_bulk_adding_items"):
            scene.is_bulk_adding_items = bool(self._prev_bulk_adding)
        if self._viewport is not None:
            self._viewport.setUpdatesEnabled(bool(self._prev_viewport_updates))
            self._viewport.update()

    def _stop_timer(self) -> None:
        if self._timer.isActive():
            self._timer.stop()

    def _finish(self) -> None:
        self._stop_timer()
        self._restore_scene_state()
        self.finished.emit()

    def _on_tick(self) -> None:
        view = self._view
        if int(getattr(view, "_auto_layout_generation", 0) or 0) != int(self._generation):
            self._finish()
            return

        scene = self._scene
        budget_s = float(self._time_budget_s)
        t0 = time.perf_counter()

        # phase 1: clear edge items + adjacency + batched edge layer
        if self._phase == "clear_edges":
            edge_items = getattr(scene, "edge_items", None)
            while self._edge_index < len(self._edge_ids):
                edge_id = self._edge_ids[self._edge_index]
                self._edge_index += 1
                edge_item = edge_items.pop(edge_id, None) if isinstance(edge_items, dict) else None
                if edge_item is not None:
                    if sip.isdeleted(edge_item):
                        continue
                    if hasattr(scene, "_unregister_edge_for_nodes"):
                        scene._unregister_edge_for_nodes(edge_item)  # type: ignore[arg-type]  # noqa: SLF001
                    scene.removeItem(edge_item)
                if budget_s > 0.0 and (time.perf_counter() - float(t0)) >= budget_s:
                    return

            # batched edges: remove old edges from layer，避免残留绘制（fast_preview_mode）
            remove_batched = getattr(scene, "remove_batched_edge", None)
            if callable(remove_batched):
                while self._batched_edge_index < len(self._old_batched_edge_ids):
                    edge_id = self._old_batched_edge_ids[self._batched_edge_index]
                    self._batched_edge_index += 1
                    remove_batched(edge_id)
                    if budget_s > 0.0 and (time.perf_counter() - float(t0)) >= budget_s:
                        return

            edges_by_node = getattr(scene, "_edges_by_node_id", None)
            if isinstance(edges_by_node, dict):
                edges_by_node.clear()

            self._phase = "prune_deleted_nodes"
            self._node_items_snapshot = list(getattr(scene, "node_items", {}).items() or [])
            self._node_snapshot_index = 0

        # phase 2: prune deleted node_items
        if self._phase == "prune_deleted_nodes":
            node_items = getattr(scene, "node_items", None)
            while self._node_snapshot_index < len(self._node_items_snapshot):
                node_id, node_item = self._node_items_snapshot[self._node_snapshot_index]
                self._node_snapshot_index += 1
                if node_item is None:
                    if isinstance(node_items, dict):
                        node_items.pop(node_id, None)
                    continue
                if sip.isdeleted(node_item):
                    if isinstance(node_items, dict):
                        node_items.pop(node_id, None)
                if budget_s > 0.0 and (time.perf_counter() - float(t0)) >= budget_s:
                    return
            self._phase = "remove_removed_copy_nodes"

        # phase 3: remove removed copy nodes
        if self._phase == "remove_removed_copy_nodes":
            node_items = getattr(scene, "node_items", None)
            while self._removed_copy_index < len(self._removed_copy_node_ids):
                node_id = self._removed_copy_node_ids[self._removed_copy_index]
                self._removed_copy_index += 1
                node_item = node_items.pop(node_id, None) if isinstance(node_items, dict) else None
                if node_item is not None and (not sip.isdeleted(node_item)):
                    scene.removeItem(node_item)
                if budget_s > 0.0 and (time.perf_counter() - float(t0)) >= budget_s:
                    return

            model_node_ids = set((getattr(getattr(scene, "model", None), "nodes", {}) or {}).keys())
            scene_node_ids = set((getattr(scene, "node_items", {}) or {}).keys())
            self._new_node_ids = sorted(model_node_ids - scene_node_ids)
            self._new_node_index = 0
            self._phase = "add_new_nodes"

        # phase 4: add new nodes
        if self._phase == "add_new_nodes":
            while self._new_node_index < len(self._new_node_ids):
                node_id = self._new_node_ids[self._new_node_index]
                self._new_node_index += 1
                node = scene.model.nodes[node_id]
                scene.add_node_item(node)
                if budget_s > 0.0 and (time.perf_counter() - float(t0)) >= budget_s:
                    return
            self._pos_sync_items = list(getattr(scene, "node_items", {}).items() or [])
            self._pos_sync_index = 0
            self._phase = "sync_positions"

        # phase 5: sync positions
        if self._phase == "sync_positions":
            node_items = getattr(scene, "node_items", None)
            model_nodes = getattr(getattr(scene, "model", None), "nodes", {}) or {}
            while self._pos_sync_index < len(self._pos_sync_items):
                node_id, node_item = self._pos_sync_items[self._pos_sync_index]
                self._pos_sync_index += 1
                if node_item is None:
                    if isinstance(node_items, dict):
                        node_items.pop(node_id, None)
                    continue
                if sip.isdeleted(node_item):
                    if isinstance(node_items, dict):
                        node_items.pop(node_id, None)
                    continue
                node_obj = model_nodes.get(node_id) if isinstance(model_nodes, dict) else None
                if node_obj is None:
                    scene.removeItem(node_item)
                    if isinstance(node_items, dict):
                        node_items.pop(node_id, None)
                    continue
                model_pos = getattr(node_obj, "pos", (0.0, 0.0)) or (0.0, 0.0)
                node_item.setPos(model_pos[0], model_pos[1])
                if budget_s > 0.0 and (time.perf_counter() - float(t0)) >= budget_s:
                    return
            self._edge_models = list((getattr(getattr(scene, "model", None), "edges", {}) or {}).values())
            self._edge_model_index = 0
            self._phase = "add_edges"

        # phase 6: add edges
        if self._phase == "add_edges":
            while self._edge_model_index < len(self._edge_models):
                edge = self._edge_models[self._edge_model_index]
                self._edge_model_index += 1
                scene.add_edge_item(edge)
                if budget_s > 0.0 and (time.perf_counter() - float(t0)) >= budget_s:
                    return
            self._phase = "finalize"

        # phase 7: finalize
        if self._phase == "finalize":
            flush_deferred = getattr(scene, "flush_deferred_port_layouts", None)
            if callable(flush_deferred):
                flush_deferred()

            invalidate_blocks = getattr(scene, "invalidate_basic_block_rect_cache", None)
            if callable(invalidate_blocks):
                invalidate_blocks()

            rebuild_rect_and_minimap = getattr(scene, "rebuild_scene_rect_and_minimap", None)
            if callable(rebuild_rect_and_minimap):
                rebuild_rect_and_minimap()
            else:
                update_scene_rect = getattr(scene, "_update_scene_rect", None)
                if callable(update_scene_rect):
                    update_scene_rect()
                mini_map_widget = getattr(view, "mini_map", None)
                if mini_map_widget is not None:
                    reset_cached = getattr(mini_map_widget, "reset_cached_rect", None)
                    if callable(reset_cached):
                        reset_cached()
                    else:
                        mini_map_widget.update()

            # 恢复 UI 状态后再触发回调（回调可能包含 fit_all/刷新缓存等）
            self._stop_timer()
            self._restore_scene_state()

            scene.update()
            if getattr(view, "on_auto_layout_completed", None):
                view.on_auto_layout_completed()
            self.finished.emit()

