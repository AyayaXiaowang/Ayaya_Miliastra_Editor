# -*- coding: utf-8 -*-
"""
Todo 预览控制器

职责：
- 加载节点图到右侧预览（只读模式）
- 根据任务类型执行高亮、灰化与镜头聚焦动画
- 管理快速切换任务时的版本控制，避免动画/高亮冲突

说明：
- 不负责详情HTML渲染与树勾选逻辑
- 不涉及真实执行（由 ExecutionRunner 负责）
"""

from __future__ import annotations
from typing import Tuple, List, Optional, Dict, Any, Callable
from pathlib import Path

import time
from functools import partial

from PyQt6 import QtCore

from engine.configs.settings import settings
from app.models import TodoItem
from engine.graph.models.graph_model import GraphModel
from app.ui.graph.graph_io import deserialize_model
from app.ui.graph.graph_scene import GraphScene
from app.ui.graph.graph_view import GraphView
from app.ui.graph.scene_builder import populate_scene_from_model
from app.ui.todo.todo_config import TodoStyles, StepTypeRules
from app.models.todo_detail_info_accessors import get_detail_type
from engine.nodes.port_type_system import is_flow_port_with_context
from engine.nodes.composite_node_manager import get_composite_node_manager
from app.ui.todo import todo_preview_handlers
from app.models.edit_session_capabilities import EditSessionCapabilities


class TodoPreviewController:
    """任务清单右侧预览的控制器。

    提供：
    - load_graph_preview(graph_data)
    - focus_and_highlight_task(todo)
    """

    def __init__(self, view: GraphView) -> None:
        self.view = view
        self._focus_operation_version: int = 0
        self._last_focus_request_ts: float = 0.0
        # detail_type -> handler(todo, current_version)
        self._detail_type_handlers: Dict[str, Callable[[TodoItem, int], None]] = {}
        self._register_default_handlers()

    # === 任务类型 handler 注册 ===
    def _register_default_handlers(self) -> None:
        """初始化内置任务类型到 handler 的映射。"""
        self.register_handler(
            "graph_create_node",
            partial(todo_preview_handlers.handle_graph_create_node, self),
        )
        self.register_handler(
            "graph_config_node",
            partial(todo_preview_handlers.handle_graph_config_node, self),
        )
        self.register_handler(
            "graph_config_node_merged",
            partial(todo_preview_handlers.handle_graph_config_node_merged, self),
        )
        self.register_handler(
            "graph_set_port_types_merged",
            partial(todo_preview_handlers.handle_graph_set_port_types_merged, self),
        )
        self.register_handler(
            "graph_create_and_connect",
            partial(todo_preview_handlers.handle_graph_create_and_connect, self),
        )
        self.register_handler(
            "graph_create_and_connect_reverse",
            partial(todo_preview_handlers.handle_graph_create_and_connect_reverse, self),
        )
        self.register_handler(
            "graph_create_and_connect_data",
            partial(todo_preview_handlers.handle_graph_create_and_connect_data, self),
        )
        self.register_handler(
            "graph_create_branch_node",
            partial(todo_preview_handlers.handle_graph_create_branch_node, self),
        )
        self.register_handler(
            "graph_connect",
            partial(todo_preview_handlers.handle_graph_connect, self),
        )
        self.register_handler(
            "graph_connect_merged",
            partial(todo_preview_handlers.handle_graph_connect_merged, self),
        )
        self.register_handler(
            "template_graph_root",
            partial(todo_preview_handlers.handle_template_graph_root, self),
        )
        self.register_handler("event_flow_root", self._handle_event_flow_root)
        self.register_handler(
            "graph_signals_overview",
            partial(todo_preview_handlers.handle_graph_signals_overview, self),
        )
        self.register_handler(
            "graph_bind_signal",
            partial(todo_preview_handlers.handle_graph_bind_signal, self),
        )
        self.register_handler(
            "graph_bind_struct",
            partial(todo_preview_handlers.handle_graph_bind_struct, self),
        )

        dynamic_port_types = (
            "graph_add_variadic_inputs",
            "graph_add_dict_pairs",
            "graph_add_branch_outputs",
            "graph_config_branch_outputs",
        )
        for detail_type in dynamic_port_types:
            self.register_handler(
                detail_type,
                partial(todo_preview_handlers.handle_dynamic_port_step, self),
            )

    def register_handler(self, detail_type: str, handler: Callable[[TodoItem, int], None]) -> None:
        """注册或覆盖任务类型对应的预览 handler。"""
        self._detail_type_handlers[detail_type] = handler

    # === 图加载 ===
    def load_graph_preview(self, graph_data: dict) -> Tuple[GraphModel, GraphScene]:
        """将图数据加载到视图（返回新建的 model 与 scene）。

        说明：
        - 图数据已由 ResourceManager 在首次加载时执行过布局计算，
          此处直接使用已布局的数据，确保与节点图编辑器/节点图库看到一致的排版。
        """
        model = deserialize_model(graph_data)

        # 任务清单右侧预览使用只读能力（统一注入，避免 view/scene 各自拼 read_only）
        preview_capabilities = EditSessionCapabilities.read_only_preview()
        scene = GraphScene(
            model,
            read_only=True,
            edit_session_capabilities=preview_capabilities,
        )
        populate_scene_from_model(scene, enable_batch_mode=True)

        # 替换视图的场景
        self.view.setScene(scene)
        self.view.set_edit_session_capabilities(preview_capabilities)

        # 禁用常量编辑控件的交互（文本与ProxyWidget）
        # 说明：不使用try/except，逐项检查方法是否存在再调用
        for _, node_item in scene.node_items.items():
            constant_map = getattr(node_item, '_constant_edits', {}) or {}
            for edit in constant_map.values():
                # QGraphicsTextItem: 关闭文本交互
                if hasattr(edit, 'setTextInteractionFlags'):
                    from PyQt6 import QtCore as _QtCore
                    edit.setTextInteractionFlags(_QtCore.Qt.TextInteractionFlag.NoTextInteraction)
                # QGraphicsProxyWidget: 禁用内部控件
                if hasattr(edit, 'widget') and callable(getattr(edit, 'widget')):
                    embedded_widget = edit.widget()
                    if embedded_widget is not None and hasattr(embedded_widget, 'setEnabled'):
                        embedded_widget.setEnabled(False)
        if settings.PREVIEW_VERBOSE:
            print(f"[PREVIEW] 已加载图到预览: nodes={len(model.nodes)}, edges={len(model.edges)}")

        return model, scene

    # === 高亮与聚焦 ===
    def focus_and_highlight_task(
        self,
        todo: TodoItem,
        *,
        event_flow_node_ids: Optional[List[str]] = None,
    ) -> None:
        """根据任务类型执行高亮与聚焦。"""
        # 版本递增，失效旧的延迟操作
        self._focus_operation_version += 1
        current_version = self._focus_operation_version

        # 停止正在进行的动画
        if hasattr(self.view, "transform_animation") and self.view.transform_animation:
            self.view.transform_animation.stop()

        # 停止浮窗动画
        if hasattr(self.view, 'overlay_manager') and self.view.overlay_manager:
            self.view.overlay_manager.stop_all_animations()

        detail_type = get_detail_type(todo)

        # 批处理更新，避免闪烁
        # 重要：预览 handler 可能在异常/边界数据下抛错；Qt 会打印异常但不会让进程立刻退出，
        # 若此处不做 finally 兜底，view 会永久停留在 updatesDisabled 状态，造成“怎么选都没反应”的假死观感。
        self.view.setUpdatesEnabled(False)
        try:
            self.view.clear_highlights()
            # 不在此处无条件 restore_all_opacity：连续高亮/聚焦场景下会造成全量遍历卡顿；
            # 需要恢复透明度的分支由具体 handler 明确调用。

            # 事件流根：若外层已给出节点集合，则优先使用显式参数（避免通过 detail_info 增加额外字段）
            if StepTypeRules.is_event_flow_root(detail_type) and event_flow_node_ids is not None:
                self._handle_event_flow_root_with_node_ids(
                    current_version=current_version,
                    node_ids=event_flow_node_ids,
                )
                return

            handler = self._detail_type_handlers.get(detail_type)
            if handler is not None:
                handler(todo, current_version)
            else:
                # 未注册类型：仅恢复视图更新状态，保持“清空高亮+还原透明度”的基线视图
                self.view.restore_all_opacity()
                self._hide_overlay()
                self._finalize_updates()
        finally:
            # 兜底恢复：不吞异常，只保证 UI 不会因一次 handler 异常进入“永久不刷新”的状态。
            self.view.setUpdatesEnabled(True)

    # === 内部 handler 实现（按任务类型拆分） ===
    # 大多数 handler 已拆分到 `ui.todo.todo_preview_handlers`，通过 `_register_default_handlers` 注册。

    def _handle_event_flow_root(self, todo: TodoItem, current_version: int) -> None:
        # 事件流根：调用分组聚焦
        self._handle_event_flow_root_with_node_ids(
            current_version=current_version,
            node_ids=[],
        )

    def _handle_event_flow_root_with_node_ids(
        self,
        *,
        current_version: int,
        node_ids: List[str],
    ) -> None:
        if node_ids:
            for node_identifier in node_ids:
                self.view.highlight_node(node_identifier)
            self._dim_unrelated(node_ids, [])
            self._hide_overlay()
            self._finalize_updates()

            self._schedule_focus(
                current_version,
                lambda use_animation, nids=list(node_ids): self._focus_on_node_group(
                    nids, use_animation=use_animation
                ),
            )
            return

        # 无显式节点集合：恢复透明度并回退到适应全图
        self.view.restore_all_opacity()
        self._hide_overlay()
        self._finalize_updates()
        self._schedule_focus(
            current_version,
            lambda use_animation: self.fit_all_or_center(use_animation=use_animation),
        )

    # === 工具 ===
    def focus_on_node_group(self, node_ids: List[str], *, use_animation: Optional[bool] = None) -> None:
        """对外公开的分组聚焦接口。"""
        self._focus_on_node_group(node_ids, use_animation=use_animation)

    def fit_all_or_center(self, *, use_animation: Optional[bool] = None) -> None:
        """按设置决定“适配全图（压缩视图）”还是仅居中（不改变缩放）。

        说明：
        - 当 `settings.GRAPH_AUTO_FIT_ALL_ENABLED=True` 时，执行 `GraphView.fit_all()`；
        - 默认关闭时不自动缩放，仅居中到场景内容中心，避免预览侧把共享画布拉到极小缩放。
        """
        from engine.configs.settings import settings as _settings_ui

        if bool(getattr(_settings_ui, "GRAPH_AUTO_FIT_ALL_ENABLED", False)):
            self.view.fit_all(use_animation=use_animation)
            return

        scene = self.view.scene()
        if scene is None:
            return
        rect = scene.sceneRect()
        if rect.isEmpty():
            return
        self.view.centerOn(rect.center())

    # === handlers 公共 API（供 `todo_preview_handlers.py` 使用）===
    # 说明：
    # - handlers 属于独立模块，不应通过 `controller._xxx()` 形式调用私有方法作为跨模块协议
    # - 这里提供稳定的公开方法名，内部仍可复用现有私有实现

    def highlight_single_node_and_focus(
        self,
        *,
        node_id: Optional[str],
        current_version: int,
        dim_unrelated: bool,
        hide_overlay: bool,
        extra_highlighting: Optional[Callable[[str], None]] = None,
    ) -> None:
        """单节点高亮 + 可选端口高亮 + 灰显 + 聚焦 的组合模板（handlers 公共入口）。"""
        self._highlight_single_node_and_focus(
            node_id=node_id,
            current_version=current_version,
            dim_unrelated=dim_unrelated,
            hide_overlay=hide_overlay,
            extra_highlighting=extra_highlighting,
        )

    def hide_overlay(self) -> None:
        """隐藏预览浮窗（handlers 公共入口）。"""
        self._hide_overlay()

    def finalize_updates(self) -> None:
        """结束批处理更新（handlers 公共入口）。"""
        self._finalize_updates()

    def dim_unrelated(self, node_ids: List[str], edge_ids: List[Optional[str]]) -> None:
        """灰显无关节点/边（handlers 公共入口）。"""
        self._dim_unrelated(node_ids, edge_ids)

    def schedule_focus(self, version: int, fn: Callable[[bool], None]) -> None:
        """按版本节流/失效机制调度聚焦（handlers 公共入口）。"""
        self._schedule_focus(version, fn)

    def overlay_and_focus(
        self,
        src_node: str,
        dst_node: str,
        edge_id: Optional[str],
        src_port: Optional[str],
        dst_port: Optional[str],
        *,
        order: str = "src-dst",
        use_animation: Optional[bool] = None,
    ) -> None:
        """显示节点对浮窗并聚焦（handlers 公共入口）。"""
        self._overlay_and_focus(
            src_node,
            dst_node,
            edge_id,
            src_port,
            dst_port,
            order=order,
            use_animation=use_animation,
        )

    def is_flow_edge_between(
        self,
        src_node_id: Optional[str],
        src_port: Optional[str],
        dst_node_id: Optional[str],
        dst_port: Optional[str],
    ) -> bool:
        """根据节点与端口推断是否为流程连线（handlers 公共入口）。"""
        return self._is_flow_edge_between(src_node_id, src_port, dst_node_id, dst_port)

    def maybe_resolve_edge_id_from_model(
        self,
        *,
        fallback_edge_id: Optional[str],
        src_node_id: Optional[str],
        src_port: Optional[str],
        dst_node_id: Optional[str],
        dst_port: Optional[str],
    ) -> Optional[str]:
        """优先使用 detail_info 中的 edge_id，必要时在模型中按端口信息反查（handlers 公共入口）。"""
        return self._maybe_resolve_edge_id_from_model(
            fallback_edge_id=fallback_edge_id,
            src_node_id=src_node_id,
            src_port=src_port,
            dst_node_id=dst_node_id,
            dst_port=dst_port,
        )

    def _focus_on_node_group(self, node_ids: List[str], *, use_animation: Optional[bool] = None) -> None:
        if not node_ids or not self.view.scene():
            return
        rects = []
        for node_id in node_ids:
            if node_id in self.view.scene().node_items:
                node_item = self.view.scene().node_items[node_id]
                rects.append(node_item.sceneBoundingRect())
        if not rects:
            return
        total_rect = rects[0]
        for rect in rects[1:]:
            total_rect = total_rect.united(rect)
        total_rect.adjust(-TodoStyles.FOCUS_MARGIN, -TodoStyles.FOCUS_MARGIN,
                          TodoStyles.FOCUS_MARGIN, TodoStyles.FOCUS_MARGIN)
        if hasattr(self.view, "_execute_focus_on_rect"):
            self.view._execute_focus_on_rect(total_rect, use_animation=use_animation)
        else:
            # 回退：直接使用 Qt 内建的 fitInView（无动画控制）
            self.view.fitInView(total_rect, QtCore.Qt.AspectRatioMode.KeepAspectRatio)

    # === 复合节点：内部子图加载与步骤高亮 ===
    def load_composite_internal_graph(self, composite_id: str, workspace_path: Path):
        manager = get_composite_node_manager(workspace_path)
        manager.load_subgraph_if_needed(composite_id)
        composite = manager.get_composite_node(composite_id)
        if not composite:
            return None, None
        return composite.sub_graph, composite

    def focus_composite_task(self, todo: TodoItem, composite_obj) -> None:
        if not composite_obj or not self.view or not self.view.scene():
            return
        # 批处理，避免闪烁（同样需要 finally 兜底恢复 updatesEnabled）
        self.view.setUpdatesEnabled(False)
        try:
            self.view.clear_highlights()

            detail_type = get_detail_type(todo)
            nodes_to_focus: List[str] = []

            if detail_type == "composite_set_pins":
                expected_inputs = {p.get("name", ""): p for p in (todo.detail_info.get("inputs", []) or [])}
                expected_outputs = {p.get("name", ""): p for p in (todo.detail_info.get("outputs", []) or [])}
                for vp in composite_obj.virtual_pins:
                    name = vp.pin_name
                    is_expected = (vp.is_input and name in expected_inputs) or ((not vp.is_input) and name in expected_outputs)
                    if not is_expected:
                        continue
                    for mp in vp.mapped_ports:
                        self.view.highlight_node(mp.node_id)
                        self.view.highlight_port(mp.node_id, mp.port_name, is_input=mp.is_input)
                        if mp.node_id not in nodes_to_focus:
                            nodes_to_focus.append(mp.node_id)
                self.view.dim_unrelated_items(nodes_to_focus, [])

                def _focus_group() -> None:
                    if nodes_to_focus:
                        self.focus_on_node_group(nodes_to_focus)
                    else:
                        self.fit_all_or_center()

                QtCore.QTimer.singleShot(TodoStyles.ANIMATION_DELAY, _focus_group)
                return

            # 默认适应全图
            self.view.restore_all_opacity()
            QtCore.QTimer.singleShot(
                TodoStyles.ANIMATION_DELAY,
                lambda: self.fit_all_or_center(),
            )
        finally:
            self.view.setUpdatesEnabled(True)

    # === 内部小工具 ===
    def _schedule(self, version: int, fn) -> None:
        def _wrapped() -> None:
            if self._focus_operation_version == version:
                fn()
        QtCore.QTimer.singleShot(TodoStyles.ANIMATION_DELAY, _wrapped)

    def _schedule_focus(self, version: int, fn: Callable[[bool], None]) -> None:
        use_animation = self._should_use_focus_animation()

        # 关键：GraphView 的聚焦底层会在 viewport 尺寸为 0 时直接 return（见 ViewportNavigator.execute_focus_on_rect）。
        # 当预览页刚切换/共享画布刚 re-parent/分割器尺寸抖动时，偶发出现“选中项已变但画板不动”，
        # 本质是聚焦触发得太早导致被短路且没有重试。
        #
        # 这里做一次“视图就绪”短重试：仅在当前 version 仍有效时继续，避免旧步骤残留定时器干扰。
        retry_state = {"attempts": 0}
        max_attempts = 60  # ~1s（16ms * 60），足以覆盖一次布局/切页的稳定期
        retry_delay_ms = 16

        def _attempt_focus() -> None:
            if self._focus_operation_version != version:
                return

            viewport = self.view.viewport() if self.view is not None else None
            if viewport is None:
                return

            size = viewport.size()
            if size.width() <= 0 or size.height() <= 0:
                retry_state["attempts"] += 1
                if int(retry_state["attempts"]) >= int(max_attempts):
                    return
                QtCore.QTimer.singleShot(retry_delay_ms, _attempt_focus)
                return

            fn(use_animation)

        QtCore.QTimer.singleShot(TodoStyles.ANIMATION_DELAY, _attempt_focus)

    def _should_use_focus_animation(self) -> bool:
        if not getattr(self.view, 'enable_smooth_transition', False):
            return False
        threshold = getattr(TodoStyles, 'PREVIEW_FOCUS_MIN_INTERVAL_MS', 0)
        now = time.perf_counter()
        last_ts = self._last_focus_request_ts
        self._last_focus_request_ts = now
        if threshold <= 0 or last_ts <= 0.0:
            return True
        elapsed_ms = (now - last_ts) * 1000.0
        return elapsed_ms >= threshold

    def _overlay_and_focus(self, src_node: str, dst_node: str, edge_id: Optional[str], src_port: Optional[str], dst_port: Optional[str], order: str = 'src-dst', *, use_animation: Optional[bool] = None) -> None:
        if self.view.overlay_manager:
            if order == 'dst-src':
                self.view.overlay_manager.show_node_pair(src_node, dst_node, src_port, dst_port)  # 参数名仍为src/dst
            else:
                self.view.overlay_manager.show_node_pair(src_node, dst_node, src_port, dst_port)
        self.view.focus_on_nodes_and_edge(src_node, dst_node, edge_id, use_animation=use_animation)

    # === 模板化辅助（减少重复序列） ===
    def _prepare_for_focus(self) -> None:
        self.view.setUpdatesEnabled(False)
        self.view.clear_highlights()
        # 不在此处无条件 restore_all_opacity：连续高亮/聚焦场景下会造成全量遍历卡顿；
        # 需要恢复透明度的分支由具体 handler 明确调用。

    def _hide_overlay(self) -> None:
        if hasattr(self.view, 'overlay_manager') and self.view.overlay_manager:
            self.view.overlay_manager.hide()

    def _finalize_updates(self) -> None:
        self.view.setUpdatesEnabled(True)

    def _dim_unrelated(self, node_ids: List[str], edge_ids: List[Optional[str]]) -> None:
        valid_edge_ids = [eid for eid in edge_ids if eid]
        self.view.dim_unrelated_items(node_ids, valid_edge_ids)

    def _highlight_single_node_and_focus(
        self,
        *,
        node_id: Optional[str],
        current_version: int,
        dim_unrelated: bool,
        hide_overlay: bool,
        extra_highlighting: Optional[Callable[[str], None]] = None,
    ) -> None:
        """单节点高亮 + 可选端口高亮 + 灰显 + 聚焦 的组合模板。"""
        if not node_id:
            # 无可高亮节点时，恢复透明度以保持基线视图
            self.view.restore_all_opacity()
            if hide_overlay:
                self._hide_overlay()
            self._finalize_updates()
            return

        if not dim_unrelated:
            # “仅高亮，不灰显”场景需要清除上一次的灰显状态
            self.view.restore_all_opacity()

        self.view.highlight_node(node_id)
        if extra_highlighting is not None:
            extra_highlighting(node_id)
        if dim_unrelated:
            self._dim_unrelated([node_id], [])
        if hide_overlay:
            self._hide_overlay()
        self._finalize_updates()

        self._schedule_focus(
            current_version,
            lambda use_animation, nid=node_id: self.view.focus_on_node(
                nid,
                use_animation=use_animation,
            ),
        )

    def _is_flow_edge_between(
        self,
        src_node_id: Optional[str],
        src_port: Optional[str],
        dst_node_id: Optional[str],
        dst_port: Optional[str],
    ) -> bool:
        """根据节点与端口推断是否为流程连线。"""
        scene = self.view.scene()
        if not (scene and hasattr(scene, 'model') and scene.model and src_node_id and dst_node_id):
            return False
        src_node_obj = scene.model.nodes.get(src_node_id)
        dst_node_obj = scene.model.nodes.get(dst_node_id)
        if not (src_node_obj and dst_node_obj):
            return False
        return bool(
            is_flow_port_with_context(src_node_obj, str(src_port), True)
            and is_flow_port_with_context(dst_node_obj, str(dst_port), False)
        )

    def _maybe_resolve_edge_id_from_model(
        self,
        *,
        fallback_edge_id: Optional[str],
        src_node_id: Optional[str],
        src_port: Optional[str],
        dst_node_id: Optional[str],
        dst_port: Optional[str],
    ) -> Optional[str]:
        """优先使用 detail_info 中的 edge_id，必要时在模型中按端口信息反查。"""
        edge_id = fallback_edge_id
        scene = self.view.scene()
        if not (scene and hasattr(scene, 'model') and scene.model and src_node_id and dst_node_id and src_port and dst_port):
            return edge_id

        for candidate_edge_id, edge in scene.model.edges.items():
            if (
                edge.src_node == src_node_id
                and edge.dst_node == dst_node_id
                and edge.src_port == src_port
                and edge.dst_port == dst_port
            ):
                edge_id = candidate_edge_id
                break
        return edge_id


