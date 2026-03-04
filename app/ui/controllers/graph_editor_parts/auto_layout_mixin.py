"""GraphEditorController 的自动排版相关 mixin。

- 自动排版前重解析（清缓存→从 .py 重新解析→重载）
- 设置变更后按需重建显示层（不改变 baseline/dirty）
- 自动排版完成后刷新持久化缓存
"""

from __future__ import annotations

from PyQt6 import QtCore

from app.ui.controllers.graph_editor_flow import GraphAutoLayoutReparseThread, GraphEditorLoadRequest


class GraphEditorAutoLayoutMixin:
    def schedule_reparse_on_next_auto_layout(self) -> None:
        """安排在下一次自动排版前强制从 .py 重新解析当前图（忽略持久化缓存）。"""
        self._force_reparse_on_next_auto_layout = True

    def prepare_for_auto_layout(self) -> bool:
        """在自动排版前按需（一次性标记）重建模型：清缓存→从 .py 解析→替换到场景。

        说明：
        - 默认不重载，避免打断当前视图缩放/中心导致“居中偏移”的体验问题。
        - 当设置页面触发一次性标记（例如 DATA_NODE_CROSS_BLOCK_COPY 从 True→False）时，
          才进行清缓存与重载；重载前后会保存并恢复视图缩放与中心点，保持画面稳定。
        - 重解析与后续重载均走“打开节点图”同款非阻塞链路（按阈值切换），避免点击自动排版卡住 UI。

        返回：
        - True：本次触发了“重解析+重载（异步）”，自动排版应延后到加载完成后再执行
        - False：未触发重载，可立即继续自动排版
        """
        if not self.current_graph_id:
            self._force_reparse_on_next_auto_layout = False
            self._cancel_pending_auto_layout_reparse()
            return False

        graph_id = str(self.current_graph_id)

        # 仅当被安排“下一次自动排版前强制重解析”时才执行重载
        should_reparse = bool(self._force_reparse_on_next_auto_layout)
        if not should_reparse:
            return False

        # 先清除一次性标记，避免“重载完成后自动触发排版”再次走重解析
        self._force_reparse_on_next_auto_layout = False

        # 保存当前视图的缩放与中心（场景坐标系下的中心点），在加载完成后恢复
        prev_center_xy: tuple[float, float] | None = None
        prev_scale = 1.0
        if self.view is not None:
            viewport_center = self.view.viewport().rect().center()
            prev_center_scene = self.view.mapToScene(viewport_center)
            prev_center_xy = (float(prev_center_scene.x()), float(prev_center_scene.y()))
            prev_scale = float(self.view.transform().m11())

        # 取消旧任务并启动新一轮重解析（后台线程）。
        self._cancel_pending_auto_layout_reparse()
        generation = int(self._auto_layout_reparse_generation)
        container = self.current_graph_container
        self._pending_auto_layout_after_reparse_graph_id = None
        self._pending_view_restore_after_reparse = None

        if self.view is not None and hasattr(self.view, "show_loading_overlay"):
            self.view.show_loading_overlay(
                title=f"正在重解析节点图：{graph_id}",
                detail="清缓存并从 .py 重新解析…",
                progress_value=None,
                progress_max=None,
            )

        thread = GraphAutoLayoutReparseThread(
            prepare_service=self._auto_layout_prepare_service,
            resource_manager=self.resource_manager,
            graph_id=graph_id,
            parent=self,
        )
        self._auto_layout_reparse_thread = thread

        def _on_finished() -> None:
            self._on_auto_layout_reparse_finished(
                generation=generation,
                expected_graph_id=graph_id,
                container=container,
                prev_center_xy=prev_center_xy,
                prev_scale=float(prev_scale),
                thread=thread,
            )

        thread.finished.connect(_on_finished)
        thread.start()
        return True

    def _on_auto_layout_reparse_finished(
        self,
        *,
        generation: int,
        expected_graph_id: str,
        container: object | None,
        prev_center_xy: tuple[float, float] | None,
        prev_scale: float,
        thread: GraphAutoLayoutReparseThread,
    ) -> None:
        if int(generation) != int(getattr(self, "_auto_layout_reparse_generation", 0)):
            return

        self._auto_layout_reparse_thread = None

        result = getattr(thread, "result", None)
        if result is None:
            raise RuntimeError("自动排版重解析线程失败：未返回 result（详见控制台 traceback）")

        graph_id = str(getattr(result, "graph_id", "") or expected_graph_id or "")
        if graph_id != str(expected_graph_id or ""):
            return

        # 用户可能在重解析期间切换到其它图：此时直接丢弃结果，避免旧图回写覆盖当前编辑上下文。
        if str(getattr(self, "current_graph_id", "") or "") != str(graph_id or ""):
            if self.view is not None and hasattr(self.view, "hide_loading_overlay"):
                self.view.hide_loading_overlay()
            return

        graph_data = result.graph_data if isinstance(result.graph_data, dict) else None
        # 通知主窗口统一失效 GraphDataService / 图属性面板等上层缓存，避免仍拿到旧数据。
        self.graph_runtime_cache_updated.emit(graph_id)

        if not graph_data:
            self._pending_auto_layout_after_reparse_graph_id = None
            self._pending_view_restore_after_reparse = None
            if self.view is not None and hasattr(self.view, "hide_loading_overlay"):
                self.view.hide_loading_overlay()
            return

        # 标记：加载完成后自动恢复视图 + 自动排版
        self._pending_auto_layout_after_reparse_graph_id = str(graph_id)
        self._pending_view_restore_after_reparse = {
            "graph_id": str(graph_id),
            "center": prev_center_xy,
            "scale": float(prev_scale),
        }

        # 与“打开节点图”一致：超大图走非阻塞管线，避免重建图元卡住 UI。
        if self._should_use_non_blocking_load(graph_data):
            self.load_graph_non_blocking(graph_id, graph_data, container=container)
        else:
            self.load_graph(graph_id, graph_data, container=container)

    def _cancel_pending_auto_layout_reparse(self) -> None:
        """取消自动排版前的后台重解析任务（若存在）。"""
        self._auto_layout_reparse_generation += 1
        thread = getattr(self, "_auto_layout_reparse_thread", None)
        if thread is not None and thread.isRunning():
            thread.requestInterruption()
        self._auto_layout_reparse_thread = None

    def rebuild_scene_for_settings_change(self, *, preserve_view: bool = True) -> None:
        """基于当前模型重建 GraphScene 与图元，用于设置变更后立即生效。

        设计目标：
        - **不改变会话状态机的 baseline/dirty/save_status**（避免把“未保存修改”误判为已保存）；
        - 主要用于“画布性能相关开关”切换后，需要重新构建图元才能生效的场景：
          fast_preview_mode、行内常量控件虚拟化、批量边层等。

        注意：
        - 该方法不会触发 `graph_loaded` 信号；它属于“重建显示层”，不是重新加载另一张图。
        """
        # 设置变更可能影响 GraphScene/图元结构：清空运行期 scene 缓存，避免复用旧渲染策略
        self._clear_scene_lru_cache()
        if not self.current_graph_id:
            return
        if self.model is None or self.scene is None or self.view is None:
            return

        # 保存视图状态（缩放 + 视口中心的场景坐标），用于重建后恢复。
        prev_transform = None
        prev_center_scene = None
        if preserve_view:
            prev_transform = self.view.transform()
            viewport_center = self.view.viewport().rect().center()
            prev_center_scene = self.view.mapToScene(viewport_center)

        # 保存会话状态机关键字段（重建不应影响 dirty 判定）
        state_machine = self._session_state_machine
        prev_graph_id = state_machine.current_graph_id
        prev_baseline_hash = state_machine.baseline_content_hash

        graph_data = self.model.serialize()
        if not isinstance(graph_data, dict) or not graph_data:
            return

        load_result = self._load_service.load(
            request=GraphEditorLoadRequest(
                graph_id=str(self.current_graph_id),
                graph_data=graph_data,
                container=self.current_graph_container,
            ),
            current_scene=self.scene,
            view=self.view,
            node_library=self.node_library,
            edit_session_capabilities=state_machine.capabilities,
            base_scene_extra_options=self._scene_extra_options,
            get_current_package=self.get_current_package,
            main_window=self.parent(),
            on_graph_modified=self._on_graph_modified,
        )

        # 更新引用：后续行为必须基于新的 model/scene
        self.model = load_result.model
        self.scene = load_result.scene
        self._apply_edit_session_capabilities_to_view_and_scene()

        # 恢复会话状态机（保持 baseline 不变）
        state_machine.current_graph_id = prev_graph_id
        state_machine.baseline_content_hash = prev_baseline_hash

        # 重新派生 save_status（避免状态机与新 model 分叉）
        current_hash = self.model.get_content_hash() if self.model is not None else None
        if not state_machine.capabilities.can_persist:
            state_machine.save_status = "readonly"
        else:
            if prev_graph_id is None:
                state_machine.save_status = "saved"
            elif prev_baseline_hash is None or current_hash is None:
                state_machine.save_status = "unsaved"
            else:
                state_machine.save_status = (
                    "saved" if str(current_hash) == str(prev_baseline_hash) else "unsaved"
                )
        self.save_status_changed.emit(state_machine.save_status)

        # 恢复视图状态（尽量保持画面稳定）
        if preserve_view and prev_transform is not None:
            self.view.setTransform(prev_transform)
        if preserve_view and prev_center_scene is not None:
            self.view.centerOn(prev_center_scene)

    def refresh_persistent_cache_after_layout(self) -> None:
        """将当前模型写入持久化缓存（用于自动排版后覆盖缓存）。

        位置变化不落盘，但希望下次打开时直接使用最新位置，
        因此在自动排版完成后，将当前 GraphModel 序列化并写入 app/runtime/cache/graph_cache。
        """
        if not self.current_graph_id or not self.model:
            return
        graph_id = str(self.current_graph_id)
        self.resource_manager.update_persistent_graph_cache_from_model(
            graph_id,
            self.model,
            layout_changed=True,
        )
        from engine.configs.settings import settings as _settings_ui

        if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
            print(f"[缓存] 已刷新持久化缓存（自动排版后）: {graph_id}")

        # 通知主窗口统一失效 GraphDataService / 图属性面板等上层缓存，避免“显示不一致/回退”。
        self.graph_runtime_cache_updated.emit(graph_id)
        # 自动排版完成后默认不强制改变镜头；
        # 若用户显式开启“自动适配全图（压缩视图）”，则恢复旧行为。
        if bool(getattr(_settings_ui, "GRAPH_AUTO_FIT_ALL_ENABLED", False)) and self.view is not None:
            QtCore.QTimer.singleShot(100, lambda: self.view and self.view.fit_all(use_animation=False))

