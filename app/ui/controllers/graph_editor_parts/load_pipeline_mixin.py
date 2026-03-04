"""GraphEditorController 的加载管线 mixin（同步/非阻塞/复合节点子图）。"""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from engine.graph.models.graph_model import GraphModel
from engine.layout import LayoutService
from app.ui.controllers.graph_editor_flow import GraphEditorLoadRequest, GraphPrepareThread
from app.ui.controllers.graph_editor_parts.scene_cache_mixin import _GraphSceneCacheEntry
from app.ui.graph.scene_builder import IncrementalScenePopulateJob


class GraphEditorLoadPipelineMixin:
    def load_graph_for_composite(
        self,
        composite_id: str,
        graph_data: dict,
        *,
        composite_edit_context: dict,
    ) -> None:
        """加载复合节点子图到编辑器（含预排版与复合上下文注入）。

        设计目标：
        - 由控制器统一负责对子图做一次预排版（LayoutService.compute_layout）；
        - 将复合节点专用的 composite_edit_context 通过 scene_extra_options 注入 GraphScene；
        - UI 层仅关心“当前选中的复合节点 ID 与其子图数据”，不再手动构造场景与批量 add_node/add_edge。
        """
        if not graph_data or not isinstance(graph_data, dict):
            raise ValueError("复合节点子图数据为空或类型错误")

        # 1) 在当前进程内对复合节点子图做一次事件区域预排版（不落盘，仅调整位置语义）。
        pre_layout_model = GraphModel.deserialize(graph_data)

        # 1.1) 复合节点子图的端口类型展示需要“有效类型快照”（effective_input_types/effective_output_types）。
        # 普通节点图加载由资源层 GraphLoader 在写 graph_cache 时补齐；但复合节点预览页直接加载 sub_graph，
        # 因此必须在此处补齐：
        # - 将虚拟引脚上声明的具体类型写入 metadata.port_type_overrides（按 mapped_ports 定位到内部端口）；
        # - 再对整张子图执行一次“有效端口类型推断 → 快照写回”，避免 UI 长期显示为“泛型”。
        manager = composite_edit_context.get("manager") if isinstance(composite_edit_context, dict) else None
        if manager is not None and composite_id:
            load_subgraph_if_needed = getattr(manager, "load_subgraph_if_needed", None)
            if callable(load_subgraph_if_needed):
                load_subgraph_if_needed(str(composite_id))
            get_composite_node = getattr(manager, "get_composite_node", None)
            composite_config = get_composite_node(str(composite_id)) if callable(get_composite_node) else None
            virtual_pins = (
                list(getattr(composite_config, "virtual_pins", []) or [])
                if composite_config is not None
                else []
            )
            if virtual_pins:
                meta = getattr(pre_layout_model, "metadata", None)
                if not isinstance(meta, dict):
                    meta = {}
                    pre_layout_model.metadata = meta
                overrides = meta.get("port_type_overrides")
                if not isinstance(overrides, dict):
                    overrides = {}
                    meta["port_type_overrides"] = overrides
                for vpin in virtual_pins:
                    if bool(getattr(vpin, "is_flow", False)):
                        continue
                    pin_type_text = str(getattr(vpin, "pin_type", "") or "").strip()
                    if not pin_type_text or pin_type_text == "泛型":
                        continue
                    for mapped in (getattr(vpin, "mapped_ports", None) or []):
                        if bool(getattr(mapped, "is_flow", False)):
                            continue
                        node_id = str(getattr(mapped, "node_id", "") or "").strip()
                        port_name = str(getattr(mapped, "port_name", "") or "").strip()
                        if not node_id or not port_name:
                            continue
                        per_node = overrides.get(node_id)
                        if not isinstance(per_node, dict):
                            per_node = {}
                            overrides[node_id] = per_node
                        per_node[port_name] = pin_type_text

        LayoutService.compute_layout(
            pre_layout_model,
            node_library=self.node_library,
            clone_model=False,
        )

        from engine.resources.graph_loader import GraphLoader

        GraphLoader._apply_port_type_snapshots(  # type: ignore[attr-defined]
            pre_layout_model,
            node_library=self.node_library,
        )
        layouted_graph_data = pre_layout_model.serialize()

        # 2) 注入复合节点编辑上下文（仅对本次加载生效）：由 GraphScene 消费，用于端口同步与虚拟引脚回调。
        # 注意：不写入控制器全局 `_scene_extra_options`，避免污染后续普通图加载。
        scene_extra_options_override = {
            "composite_edit_context": dict(composite_edit_context or {}),
        }

        # 3) 复用通用加载管线，确保布局/场景装配/小地图等行为与普通图一致。
        effective_graph_id = composite_id or "composite_graph"
        self._load_graph_pipeline(
            GraphEditorLoadRequest(
                graph_id=effective_graph_id,
                graph_data=layouted_graph_data,
                container=None,
                scene_extra_options_override=scene_extra_options_override,
            ),
        )

    def load_graph(self, graph_id: str, graph_data: dict, container=None) -> None:
        """加载节点图

        Args:
            graph_id: 节点图ID
            graph_data: 节点图数据
            container: 容器对象（模板或实例）
        """
        self._load_graph_pipeline(
            GraphEditorLoadRequest(graph_id=graph_id, graph_data=graph_data, container=container)
        )

    def load_graph_non_blocking(
        self,
        graph_id: str,
        graph_data: dict,
        container=None,
        *,
        scene_extra_options_override: dict | None = None,
    ) -> None:
        """非阻塞加载节点图（后台准备模型 + 主线程分帧装配图元）。

        注意：该入口主要用于“用户显式打开超大图”的场景；
        对内部重载/重建显示层等需要同步完成的链路，仍应使用 `load_graph()`（同步）。
        """
        self._load_graph_pipeline_non_blocking(
            GraphEditorLoadRequest(
                graph_id=str(graph_id),
                graph_data=graph_data,
                container=container,
                scene_extra_options_override=scene_extra_options_override,
            )
        )

    def _estimate_graph_size_from_data(self, graph_data: dict) -> tuple[int, int]:
        """从序列化 dict 估算节点/连线数量（用于选择加载策略）。"""
        if not isinstance(graph_data, dict):
            return 0, 0
        nodes_value = graph_data.get("nodes")
        edges_value = graph_data.get("edges")

        # GraphModel.serialize 的唯一格式：nodes/edges 为 list[dict]
        # 但为兼容旧缓存/工具链输入，这里同时兼容 dict（id->payload）形式。
        if isinstance(nodes_value, list):
            node_count = int(len(nodes_value))
        elif isinstance(nodes_value, dict):
            node_count = int(len(nodes_value))
        else:
            node_count = 0

        if isinstance(edges_value, list):
            edge_count = int(len(edges_value))
        elif isinstance(edges_value, dict):
            edge_count = int(len(edges_value))
        else:
            edge_count = 0
        return node_count, edge_count

    def _should_use_non_blocking_load(self, graph_data: dict) -> bool:
        """是否对当前图启用“非阻塞加载”。

        约定：
        - 阈值走 settings（缺省值足够保守），便于后续按体验调参而不改代码；
        - 只作为“打开图”的 UI 体验策略，不影响其它内部管线。
        """
        from engine.configs.settings import settings as _settings_ui

        node_count, edge_count = self._estimate_graph_size_from_data(graph_data)
        node_threshold = int(getattr(_settings_ui, "GRAPH_ASYNC_LOAD_NODE_THRESHOLD", 300) or 300)
        edge_threshold = int(getattr(_settings_ui, "GRAPH_ASYNC_LOAD_EDGE_THRESHOLD", 600) or 600)
        return bool(node_count >= node_threshold or edge_count >= edge_threshold)

    def _cancel_pending_non_blocking_load(self) -> None:
        job = getattr(self, "_async_populate_job", None)
        if job is not None:
            job.cancel()
        self._async_populate_job = None

        thread = getattr(self, "_async_prepare_thread", None)
        if thread is not None and thread.isRunning():
            thread.requestInterruption()
        self._async_prepare_thread = None

        self._async_batch_build_context = None

    def _load_graph_pipeline_non_blocking(self, load_request: GraphEditorLoadRequest) -> None:
        """非阻塞节点图加载管线（后台准备模型 + 主线程分帧装配）。"""
        graph_id = str(load_request.graph_id)
        container = load_request.container

        self._async_load_generation += 1
        generation = int(self._async_load_generation)

        # 取消上一轮未完成任务（若存在）
        self._cancel_pending_non_blocking_load()
        # 若存在“自动排版前重解析”后台任务，也一并取消，避免旧任务完成后回写当前会话。
        self._cancel_pending_auto_layout_reparse()

        # 运行期 GraphScene LRU 缓存：若目标图仍在内存中且兼容，则直接秒切回（无需后台准备/分帧装配）
        cached_entry: _GraphSceneCacheEntry | None = None
        current_graph_id = str(self.current_graph_id or "").strip()
        if graph_id and graph_id != current_graph_id:
            cached_entry = self._pop_scene_from_cache_if_compatible(
                graph_id=str(graph_id),
                expected_capabilities=self._session_state_machine.capabilities,
            )

        # 切图：将当前图作为“非激活缓存”存入 LRU（若符合条件）
        cached_source = self._cache_current_scene_as_inactive(next_graph_id=str(graph_id))
        # 后续 attach 新场景时是否清空旧场景：若旧场景已缓存则必须跳过 clear
        self._async_clear_old_scene_on_attach = not bool(cached_source)

        if cached_entry is not None:
            if self.view is not None and hasattr(self.view, "hide_loading_overlay"):
                self.view.hide_loading_overlay()
            self._restore_graph_from_scene_cache_entry(entry=cached_entry, request=load_request)
            return

        from engine.configs.settings import settings as _settings

        if getattr(_settings, "GRAPH_UI_VERBOSE", False):
            print(f"[加载] 开始加载节点图（非阻塞）: {graph_id}")
        if self.view is not None and hasattr(self.view, "show_loading_overlay"):
            self.view.show_loading_overlay(
                title=f"正在加载节点图：{graph_id}",
                detail="准备模型（反序列化/语义对齐）…",
                progress_value=None,
                progress_max=None,
            )

        thread = GraphPrepareThread(
            graph_id=str(graph_id),
            graph_data=load_request.graph_data,
            node_library=self.node_library,
            parent=self,
        )
        self._async_prepare_thread = thread

        def _on_finished() -> None:
            self._on_non_blocking_prepare_finished(
                generation=generation,
                thread=thread,
                container=container,
                scene_extra_options_override=load_request.scene_extra_options_override,
            )

        thread.finished.connect(_on_finished)
        thread.start()

    def _on_non_blocking_prepare_finished(
        self,
        *,
        generation: int,
        thread: GraphPrepareThread,
        container: object | None,
        scene_extra_options_override: dict | None,
    ) -> None:
        if int(generation) != int(getattr(self, "_async_load_generation", 0)):
            return

        result = getattr(thread, "result", None)
        if result is None:
            raise RuntimeError("GraphPrepareThread 失败：未返回 result（详见控制台 traceback）")

        graph_id = str(result.graph_id)
        model = result.model
        baseline_hash = str(result.baseline_content_hash)

        # 清空旧场景以释放图元；随后会替换为新 GraphScene。
        # 若旧场景已被 LRU 缓存（切图秒切回），则必须跳过 clear，避免把缓存图元清掉。
        should_clear_old = bool(getattr(self, "_async_clear_old_scene_on_attach", True))
        if should_clear_old and self.scene is not None:
            self.scene.clear()

        edit_caps = self._session_state_machine.capabilities
        new_scene = self._load_service.create_scene_for_load(
            model=model,
            node_library=self.node_library,
            edit_session_capabilities=edit_caps,
            base_scene_extra_options=self._scene_extra_options,
            scene_extra_options_override=scene_extra_options_override,
            get_current_package=self.get_current_package,
            main_window=self.parent(),
            on_graph_modified=self._on_graph_modified,
        )
        self._load_service.attach_scene_to_view_for_load(
            scene=new_scene,
            view=self.view,
            node_library=self.node_library,
        )

        # 更新引用：后续行为必须基于新的 model/scene
        self.model = model
        self.scene = new_scene

        # 会话能力同步到 view/scene（含 read_only 与“添加节点”入口）
        self._apply_edit_session_capabilities_to_view_and_scene()

        # 分帧装配图元：关闭 viewport 更新 + 关闭回调 + NoIndex
        viewport = self.view.viewport()
        prev_viewport_updates = bool(viewport.updatesEnabled())
        old_on_change_cb = new_scene.undo_manager.on_change_callback
        old_on_data_changed = new_scene.on_data_changed

        viewport.setUpdatesEnabled(False)
        new_scene.undo_manager.on_change_callback = None
        new_scene.on_data_changed = None
        new_scene.setItemIndexMethod(QtWidgets.QGraphicsScene.ItemIndexMethod.NoIndex)

        self._async_batch_build_context = {
            "graph_id": graph_id,
            "container": container,
            "baseline_hash": baseline_hash,
            "prev_viewport_updates": prev_viewport_updates,
            "old_on_change_cb": old_on_change_cb,
            "old_on_data_changed": old_on_data_changed,
        }

        job = IncrementalScenePopulateJob(
            new_scene,
            enable_batch_mode=True,
            time_budget_ms=10,
            parent=self,
        )
        self._async_populate_job = job

        total = int(job.nodes_total + job.edges_total)
        if self.view is not None and hasattr(self.view, "update_loading_overlay_progress"):
            self.view.update_loading_overlay_progress(
                progress_value=0, progress_max=total if total > 0 else None
            )
            self.view.update_loading_overlay_detail("装配图元…")

        def _on_progress(nodes_done: int, nodes_total: int, edges_done: int, edges_total: int) -> None:
            if int(generation) != int(getattr(self, "_async_load_generation", 0)):
                return
            # 分帧装配除了节点/连线，还包含“批量装配收尾”的延迟端口重排（flush_deferred_port_layouts）。
            # 该阶段若不纳入进度条，会出现 100% 卡住但仍在忙的错觉（尤其是超大图）。
            flush_done = int(getattr(job, "flush_done", 0) or 0)
            flush_total = int(getattr(job, "flush_total", 0) or 0)

            done = int(nodes_done) + int(edges_done) + int(flush_done)
            all_total = int(nodes_total) + int(edges_total) + int(flush_total)
            if self.view is not None and hasattr(self.view, "update_loading_overlay_progress"):
                self.view.update_loading_overlay_progress(
                    progress_value=done,
                    progress_max=all_total if all_total > 0 else None,
                )
                phase = str(getattr(job, "phase", "") or "")
                if phase == "flush_ports":
                    self.view.update_loading_overlay_detail(
                        f"整理端口布局… {int(flush_done)}/{int(flush_total)}"
                    )
                elif phase in {"finalize", "finished"}:
                    self.view.update_loading_overlay_detail("收尾中…")
                else:
                    self.view.update_loading_overlay_detail(
                        f"节点 {int(nodes_done)}/{int(nodes_total)}  连线 {int(edges_done)}/{int(edges_total)}"
                    )

        def _on_finished() -> None:
            self._on_non_blocking_populate_finished(generation=generation)

        job.progress.connect(_on_progress)
        job.finished.connect(_on_finished)
        job.start()

    def _on_non_blocking_populate_finished(self, *, generation: int) -> None:
        if int(generation) != int(getattr(self, "_async_load_generation", 0)):
            return

        ctx = getattr(self, "_async_batch_build_context", None)
        if not isinstance(ctx, dict):
            raise RuntimeError("非阻塞加载：缺少 batch_build_context")

        graph_id = str(ctx.get("graph_id") or "")
        container = ctx.get("container")
        baseline_hash = str(ctx.get("baseline_hash") or "")
        prev_viewport_updates = bool(ctx.get("prev_viewport_updates", True))
        old_on_change_cb = ctx.get("old_on_change_cb", None)
        old_on_data_changed = ctx.get("old_on_data_changed", None)

        # 加载后按需同步信号节点端口（仍保持 viewport 更新关闭，避免中途重绘）
        self._load_service.sync_signals_after_load_if_needed(
            scene=self.scene,
            model=self.model,
            get_current_package=self.get_current_package,
        )

        # 恢复索引/回调/更新
        self.scene.setItemIndexMethod(QtWidgets.QGraphicsScene.ItemIndexMethod.BspTreeIndex)
        self.scene.undo_manager.on_change_callback = old_on_change_cb
        self.scene.on_data_changed = old_on_data_changed

        viewport = self.view.viewport()
        viewport.setUpdatesEnabled(bool(prev_viewport_updates))
        viewport.update()
        self._load_service._refresh_mini_map_after_batch_build(view=self.view)  # noqa: SLF001

        if self.view is not None and hasattr(self.view, "hide_loading_overlay"):
            self.view.hide_loading_overlay()

        self._async_populate_job = None
        self._async_prepare_thread = None
        self._async_batch_build_context = None

        # 收尾：状态、验证与通知信号
        self._finalize_after_graph_loaded(
            graph_id=str(graph_id),
            container=container,
            baseline_hash=str(baseline_hash),
        )

    def _load_graph_pipeline(self, load_request: GraphEditorLoadRequest) -> None:
        """统一的节点图加载管线。

        说明：
        - 公共入口 `load_graph` 与复合入口 `load_graph_for_composite` 统一走此处，减少“改一点牵一片”。
        - `scene_extra_options_override` 为“单次加载 override”，不写入控制器全局 `_scene_extra_options`。
        """
        graph_id = str(load_request.graph_id)
        container = load_request.container

        # 若此前存在非阻塞加载任务：提升 generation + 取消，避免旧任务完成后覆盖本次同步加载结果
        self._async_load_generation += 1
        self._cancel_pending_non_blocking_load()
        # 同步加载同样会替换会话上下文：取消自动排版前的后台重解析任务，避免旧结果回写。
        self._cancel_pending_auto_layout_reparse()
        if self.view is not None and hasattr(self.view, "hide_loading_overlay"):
            self.view.hide_loading_overlay()

        # 运行期 GraphScene LRU 缓存：切图时优先秒切回（避免重建 QGraphicsItem）
        cached_entry: _GraphSceneCacheEntry | None = None
        current_graph_id = str(self.current_graph_id or "").strip()
        if graph_id and graph_id != current_graph_id:
            cached_entry = self._pop_scene_from_cache_if_compatible(
                graph_id=str(graph_id),
                expected_capabilities=self._session_state_machine.capabilities,
            )

        cached_source = self._cache_current_scene_as_inactive(next_graph_id=str(graph_id))
        if cached_entry is not None:
            from engine.configs.settings import settings as _settings_ui

            if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
                print(f"[缓存][scene] 命中，秒切回: {graph_id}")
            self._restore_graph_from_scene_cache_entry(entry=cached_entry, request=load_request)
            return

        from engine.configs.settings import settings as _settings_ui

        if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
            print(f"[加载] 开始加载节点图: {graph_id}")

        load_result = self._load_service.load(
            request=load_request,
            current_scene=self.scene,
            clear_current_scene=not bool(cached_source),
            view=self.view,
            node_library=self.node_library,
            edit_session_capabilities=self._session_state_machine.capabilities,
            base_scene_extra_options=self._scene_extra_options,
            get_current_package=self.get_current_package,
            main_window=self.parent(),
            on_graph_modified=self._on_graph_modified,
        )

        # 更新引用：后续行为必须基于新的 model/scene
        self.model = load_result.model
        self.scene = load_result.scene

        # 会话能力同步到 view/scene（含 read_only 与“添加节点”入口）
        self._apply_edit_session_capabilities_to_view_and_scene()

        # 收尾：状态、验证与通知信号
        self._finalize_after_graph_loaded(
            graph_id=load_result.graph_id,
            container=container,
            baseline_hash=load_result.baseline_content_hash,
        )

    def _finalize_after_graph_loaded(
        self,
        *,
        graph_id: str,
        container: object | None,
        baseline_hash: str,
    ) -> None:
        # 更新当前图状态
        new_status = self._session_state_machine.on_graph_loaded(
            graph_id=str(graph_id),
            baseline_content_hash=str(baseline_hash),
        )
        self.current_graph_container = container

        self.save_status_changed.emit(new_status)

        from engine.configs.settings import settings as _settings_ui

        if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
            print(f"[加载] 完成，加载了 {len(self.scene.node_items)} 个节点")

        # 加载完成后清除错误状态（如果有的话）
        self.error_tracker.clear_error(graph_id)

        # 加载完成后触发验证（需显式允许 can_validate）
        if self._session_state_machine.capabilities.can_validate and self._session_state_machine.capabilities.can_persist:
            self.validate_current_graph()

        # 发送加载完成信号
        self.graph_loaded.emit(graph_id)

        # 用户显式打开图：在“加载完成”后再应用镜头策略（避免超大图同步 fit_all/sceneRect 计算卡顿）。
        pending_graph_id = str(getattr(self, "_pending_post_load_camera_graph_id", "") or "")
        if pending_graph_id and pending_graph_id == str(graph_id or ""):
            self._pending_post_load_camera_graph_id = None
            from engine.configs.settings import settings as _settings_ui

            if bool(getattr(_settings_ui, "GRAPH_AUTO_FIT_ALL_ENABLED", False)):
                # 延迟一帧，确保视口尺寸有效
                QtCore.QTimer.singleShot(
                    100, lambda: self.view and self.view.fit_all(use_animation=False)
                )
            else:
                # 不改变缩放，仅轻量居中
                QtCore.QTimer.singleShot(
                    0,
                    lambda gid=str(graph_id): self._center_view_after_graph_loaded(gid),
                )

        # 自动排版前的“重解析+重载”：恢复视图中心/缩放（保持画面稳定）
        pending_restore = getattr(self, "_pending_view_restore_after_reparse", None)
        if (
            isinstance(pending_restore, dict)
            and str(pending_restore.get("graph_id") or "") == str(graph_id or "")
        ):
            self._pending_view_restore_after_reparse = None
            if self.view is not None:
                center = pending_restore.get("center", None)
                scale = float(pending_restore.get("scale", 1.0) or 1.0)
                if isinstance(center, (list, tuple)) and len(center) >= 2:
                    self.view.resetTransform()
                    self.view.scale(float(scale), float(scale))
                    self.view.centerOn(QtCore.QPointF(float(center[0]), float(center[1])))

        # 若本次加载来自“自动排版前重解析”，则在加载完成后自动触发一次自动排版
        pending_auto_layout_graph_id = str(
            getattr(self, "_pending_auto_layout_after_reparse_graph_id", "") or ""
        )
        if pending_auto_layout_graph_id and pending_auto_layout_graph_id == str(graph_id or ""):
            self._pending_auto_layout_after_reparse_graph_id = None
            if self.view is not None:
                from app.ui.graph.graph_view.auto_layout.auto_layout_controller import AutoLayoutController

                QtCore.QTimer.singleShot(0, lambda v=self.view: AutoLayoutController.run(v))

    def _center_view_after_graph_loaded(self, expected_graph_id: str) -> None:
        """加载完成后将视图轻量居中到当前场景内容中心（不改变缩放）。"""
        if str(getattr(self, "current_graph_id", "") or "") != str(expected_graph_id or ""):
            return
        view = getattr(self, "view", None)
        scene = getattr(self, "scene", None)
        if view is None or scene is None:
            return
        scene_rect = scene.sceneRect() if hasattr(scene, "sceneRect") else None
        if scene_rect is None or scene_rect.isEmpty():
            return
        # 若当前缩放极小（常见于从 Todo 预览页借回共享画布后，预览侧曾执行 fit_all），
        # 则将缩放恢复到默认比例，避免“打开即压缩”的体验。
        current_scale = float(getattr(view.transform(), "m11", lambda: 1.0)())
        if current_scale < 0.12:
            view.resetTransform()
        view.centerOn(scene_rect.center())

