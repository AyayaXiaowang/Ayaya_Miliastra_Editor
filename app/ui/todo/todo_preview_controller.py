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

from PyQt6 import QtCore

from app.common.graph_data_cache import resolve_graph_data, store_graph_data
from engine.configs.settings import settings
from app.models import TodoItem
from engine.graph.models.graph_model import GraphModel
from ui.graph.graph_io import deserialize_model
from ui.graph.graph_scene import GraphScene
from ui.graph.graph_view import GraphView
from ui.graph.scene_builder import populate_scene_from_model
from ui.todo.todo_config import TodoStyles, StepTypeRules
from engine.nodes.port_type_system import is_flow_port_with_context
from engine.nodes.port_name_rules import get_dynamic_port_type
from engine.nodes.composite_node_manager import get_composite_node_manager
from engine.resources.resource_manager import ResourceType
from engine.graph.models.graph_config import GraphConfig


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
        self.register_handler("graph_create_node", self._handle_graph_create_node)
        self.register_handler("graph_config_node", self._handle_graph_config_node)
        self.register_handler("graph_config_node_merged", self._handle_graph_config_node_merged)
        self.register_handler("graph_set_port_types_merged", self._handle_graph_set_port_types_merged)
        self.register_handler("graph_create_and_connect", self._handle_graph_create_and_connect)
        self.register_handler("graph_create_and_connect_reverse", self._handle_graph_create_and_connect_reverse)
        self.register_handler("graph_create_and_connect_data", self._handle_graph_create_and_connect_data)
        self.register_handler("graph_create_branch_node", self._handle_graph_create_branch_node)
        self.register_handler("graph_connect", self._handle_graph_connect)
        self.register_handler("graph_connect_merged", self._handle_graph_connect_merged)
        self.register_handler("template_graph_root", self._handle_template_graph_root)
        self.register_handler("event_flow_root", self._handle_event_flow_root)
        self.register_handler("graph_signals_overview", self._handle_graph_signals_overview)
        self.register_handler("graph_bind_signal", self._handle_graph_bind_signal)

        dynamic_port_types = (
            "graph_add_variadic_inputs",
            "graph_add_dict_pairs",
            "graph_add_branch_outputs",
            "graph_config_branch_outputs",
        )
        for detail_type in dynamic_port_types:
            self.register_handler(detail_type, self._handle_dynamic_port_step)

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

        # 任务清单右侧预览使用只读场景
        scene = GraphScene(model, read_only=True)
        populate_scene_from_model(scene, enable_batch_mode=True)

        # 替换视图的场景
        self.view.setScene(scene)
        # 视图层也开启只读，禁用删除/复制/粘贴等快捷键与右键菜单
        if hasattr(self.view, 'read_only'):
            self.view.read_only = True

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
    def focus_and_highlight_task(self, todo: TodoItem) -> None:
        """根据任务类型执行高亮与聚焦。"""
        # 版本递增，失效旧的延迟操作
        self._focus_operation_version += 1
        current_version = self._focus_operation_version

        # 停止正在进行的动画
        if hasattr(self.view, 'transform_animation') and self.view.transform_animation:
            if self.view.transform_animation.is_running:
                self.view.transform_animation.timer.stop()
                self.view.transform_animation.is_running = False

        # 停止浮窗动画
        if hasattr(self.view, 'overlay_manager') and self.view.overlay_manager:
            self.view.overlay_manager.stop_all_animations()

        detail_type = todo.detail_info.get("type", "")

        # 批处理更新，避免闪烁
        self._prepare_for_focus()

        handler = self._detail_type_handlers.get(detail_type)
        if handler is not None:
            handler(todo, current_version)
        else:
            # 未注册类型：仅恢复视图更新状态，保持“清空高亮+还原透明度”的基线视图
            self._hide_overlay()
            self._finalize_updates()

    # === 内部 handler 实现（按任务类型拆分） ===
    def _handle_graph_create_node(self, todo: TodoItem, current_version: int) -> None:
        node_id = todo.detail_info.get("node_id")
        # 创建节点：仅高亮新节点，不灰显其他元素
        self._highlight_single_node_and_focus(
            node_id=node_id,
            current_version=current_version,
            dim_unrelated=False,
            hide_overlay=True,
        )

    def _handle_graph_config_node(self, todo: TodoItem, current_version: int) -> None:
        detail = todo.detail_info
        node_id = detail.get("node_id")
        param_name = detail.get("param_name")

        def extra_highlighting(node_identifier: str) -> None:
            if param_name:
                self.view.highlight_port(node_identifier, param_name, is_input=True)

        self._highlight_single_node_and_focus(
            node_id=node_id,
            current_version=current_version,
            dim_unrelated=True,
            hide_overlay=True,
            extra_highlighting=extra_highlighting if param_name else None,
        )

    def _handle_graph_config_node_merged(self, todo: TodoItem, current_version: int) -> None:
        detail = todo.detail_info
        node_id = detail.get("node_id")
        params = detail.get("params", []) or []

        def extra_highlighting(node_identifier: str) -> None:
            for param_info in params:
                param_name = param_info.get("param_name")
                if param_name:
                    self.view.highlight_port(node_identifier, param_name, is_input=True)

        self._highlight_single_node_and_focus(
            node_id=node_id,
            current_version=current_version,
            dim_unrelated=True,
            hide_overlay=True,
            extra_highlighting=extra_highlighting if params else None,
        )

    def _handle_graph_set_port_types_merged(self, todo: TodoItem, current_version: int) -> None:
        node_id = todo.detail_info.get("node_id")
        if not node_id:
            self._hide_overlay()
            self._finalize_updates()
            return

        self.view.highlight_node(node_id)
        # 高亮需要设置类型的端口：仅高亮类型为“泛型家族”（泛型/泛型*）的数据端口
        scene = self.view.scene()
        if scene and hasattr(scene, 'model') and scene.model and node_id in scene.model.nodes:
            node_obj = scene.model.nodes.get(node_id)
            # 获取节点定义以判断端口声明类型
            node_def = None
            if hasattr(scene, 'get_node_def') and callable(getattr(scene, 'get_node_def')):
                node_def = scene.get_node_def(node_obj)  # 依赖 scene.node_library

            # 判定：是否为“泛型家族”类型名
            def _is_generic_type_name(type_name: object) -> bool:
                if not isinstance(type_name, str):
                    return False
                type_name_stripped = type_name.strip()
                return bool(type_name_stripped == "泛型" or type_name_stripped.startswith("泛型"))

            # 安全获取端口声明类型（支持 0~99 等范围占位）
            def _get_declared_port_type(definition, port_name: str, is_input: bool) -> Optional[str]:
                if definition is None:
                    return None
                types_dict = getattr(definition, 'input_types', {}) if is_input else getattr(definition, 'output_types', {})
                dynamic_type = getattr(definition, 'dynamic_port_type', "") or ""
                return get_dynamic_port_type(str(port_name), dict(types_dict), str(dynamic_type))

            # 输入侧：仅高亮声明为泛型家族的端口（排除流程端口）
            inputs = list(getattr(node_obj, 'inputs', []) or [])
            for port in inputs:
                port_name = getattr(port, 'name', None)
                if isinstance(port_name, str) and port_name and (not is_flow_port_with_context(node_obj, port_name, False)):
                    declared = _get_declared_port_type(node_def, port_name, is_input=True)
                    if _is_generic_type_name(declared):
                        self.view.highlight_port(node_id, port_name, is_input=True)

            # 输出侧：仅高亮声明为泛型家族的端口（排除流程端口）
            outputs = list(getattr(node_obj, 'outputs', []) or [])
            for port in outputs:
                port_name = getattr(port, 'name', None)
                if isinstance(port_name, str) and port_name and (not is_flow_port_with_context(node_obj, port_name, True)):
                    declared = _get_declared_port_type(node_def, port_name, is_input=False)
                    if _is_generic_type_name(declared):
                        self.view.highlight_port(node_id, port_name, is_input=False)

        self._dim_unrelated([node_id], [])
        self._hide_overlay()
        self._finalize_updates()

        self._schedule_focus(
            current_version,
            lambda use_animation, nid=node_id: self.view.focus_on_node(
                nid,
                use_animation=use_animation,
            ),
        )

    def _handle_graph_create_and_connect(self, todo: TodoItem, current_version: int) -> None:
        detail = todo.detail_info
        prev_node_id = detail.get("prev_node_id")
        node_id = detail.get("node_id")
        src_port = detail.get("src_port")
        dst_port = detail.get("dst_port")
        edge_id_from_detail = detail.get("edge_id")

        if not (prev_node_id and node_id and self.view.scene()):
            self._finalize_updates()
            return

        edge_id = self._maybe_resolve_edge_id_from_model(
            fallback_edge_id=edge_id_from_detail,
            src_node_id=prev_node_id,
            src_port=src_port,
            dst_node_id=node_id,
            dst_port=dst_port,
        )

        self.view.highlight_nodes_and_edge(prev_node_id, node_id, edge_id, src_port, dst_port)  # type: ignore[arg-type]
        focused_edge_ids: List[Optional[str]] = [edge_id] if edge_id else []
        focused_node_ids = [prev_node_id, node_id]
        self._dim_unrelated(focused_node_ids, focused_edge_ids)
        self._finalize_updates()

        self._schedule_focus(
            current_version,
            lambda use_animation, pnid=prev_node_id, nid=node_id, eid=edge_id, s_port=src_port, d_port=dst_port: self._overlay_and_focus(
                pnid,
                nid,
                eid,
                s_port,
                d_port,
                use_animation=use_animation,
            ),
        )

    def _handle_graph_create_and_connect_reverse(self, todo: TodoItem, current_version: int) -> None:
        detail = todo.detail_info
        successor_node_id = detail.get("successor_node_id")
        node_id = detail.get("node_id")
        node_port = detail.get("node_port")
        successor_port = detail.get("successor_port")
        edge_id_from_detail = detail.get("edge_id")

        if not (successor_node_id and node_id and self.view.scene()):
            self._finalize_updates()
            return

        edge_id = self._maybe_resolve_edge_id_from_model(
            fallback_edge_id=edge_id_from_detail,
            src_node_id=node_id,
            src_port=node_port,
            dst_node_id=successor_node_id,
            dst_port=successor_port,
        )

        self.view.highlight_nodes_and_edge(node_id, successor_node_id, edge_id, node_port, successor_port)  # type: ignore[arg-type]
        focused_edge_ids: List[Optional[str]] = [edge_id] if edge_id else []
        focused_node_ids = [node_id, successor_node_id]
        self._dim_unrelated(focused_node_ids, focused_edge_ids)
        self._finalize_updates()

        self._schedule_focus(
            current_version,
            lambda use_animation, snid=successor_node_id, nid=node_id, eid=edge_id, n_port=node_port, s_port=successor_port: self._overlay_and_focus(
                snid,
                nid,
                eid,
                n_port,
                s_port,
                order='dst-src',
                use_animation=use_animation,
            ),
        )

    def _handle_graph_create_and_connect_data(self, todo: TodoItem, current_version: int) -> None:
        detail = todo.detail_info
        target_node_id = detail.get("target_node_id")
        data_node_id = detail.get("data_node_id")
        edge_identifier = detail.get("edge_id")

        if not (target_node_id and data_node_id and self.view.scene()):
            self._finalize_updates()
            return

        self.view.highlight_nodes_and_edge(
            data_node_id,
            target_node_id,
            edge_identifier,
        )
        focused_edge_ids: List[Optional[str]] = [edge_identifier] if edge_identifier else []
        focused_node_ids = [data_node_id, target_node_id]
        self._dim_unrelated(focused_node_ids, focused_edge_ids)
        self._finalize_updates()

        self._schedule_focus(
            current_version,
            lambda use_animation, data_id=data_node_id, target_id=target_node_id, edge_id_value=edge_identifier: self._overlay_and_focus(
                data_id,
                target_id,
                edge_id_value,
                None,
                None,
                use_animation=use_animation,
            ),
        )

    def _handle_graph_create_branch_node(self, todo: TodoItem, current_version: int) -> None:
        detail = todo.detail_info
        branch_node_id = detail.get("branch_node_id")
        node_id = detail.get("node_id")
        branch_name = detail.get("branch_name")

        if not (branch_node_id and node_id and self.view.scene()):
            self._finalize_updates()
            return

        self.view.highlight_node(branch_node_id)
        self.view.highlight_node(node_id)

        edge_id: Optional[str] = None
        scene = self.view.scene()
        if scene and hasattr(scene, 'model') and scene.model:
            for candidate_edge_id, edge in scene.model.edges.items():
                if edge.src_node == branch_node_id and edge.dst_node == node_id and edge.src_port == branch_name:
                    edge_id = candidate_edge_id
                    break

        if edge_id:
            self.view.highlight_edge(edge_id, is_flow_edge=True)

        focused_edge_ids: List[Optional[str]] = [edge_id] if edge_id else []
        focused_node_ids = [branch_node_id, node_id]
        self._dim_unrelated(focused_node_ids, focused_edge_ids)
        self._finalize_updates()

        self._schedule_focus(
            current_version,
            lambda use_animation, b_id=branch_node_id, nid=node_id, eid=edge_id, b_port=branch_name: self._overlay_and_focus(
                b_id,
                nid,
                eid,
                b_port,
                "流程入",
                use_animation=use_animation,
            ),
        )

    def _handle_graph_connect(self, todo: TodoItem, current_version: int) -> None:
        detail = todo.detail_info
        src_node_id = detail.get("src_node")
        dst_node_id = detail.get("dst_node")
        edge_id = detail.get("edge_id")
        src_port = detail.get("src_port")
        dst_port = detail.get("dst_port")

        if not (src_node_id and dst_node_id):
            self._finalize_updates()
            return

        is_flow_edge = self._is_flow_edge_between(src_node_id, src_port, dst_node_id, dst_port)
        self.view.highlight_edge(edge_id, is_flow_edge=is_flow_edge)

        scene = self.view.scene()
        if scene and edge_id and hasattr(scene, 'edge_items') and edge_id in scene.edge_items:
            focused_edge_ids: List[Optional[str]] = [edge_id]
        else:
            focused_edge_ids = []
        focused_node_ids = [src_node_id, dst_node_id]
        self._dim_unrelated(focused_node_ids, focused_edge_ids)
        self._finalize_updates()

        self._schedule_focus(
            current_version,
            lambda use_animation, s_node=src_node_id, d_node=dst_node_id, eid=edge_id, s_port=src_port, d_port=dst_port: self._overlay_and_focus(
                s_node,
                d_node,
                eid,
                s_port,
                d_port,
                use_animation=use_animation,
            ),
        )

    def _handle_graph_connect_merged(self, todo: TodoItem, current_version: int) -> None:
        detail = todo.detail_info
        node1_id = detail.get("node1_id")
        node2_id = detail.get("node2_id")
        edges_info = detail.get("edges", []) or []

        if not (node1_id and node2_id and edges_info):
            self._finalize_updates()
            return

        focused_edge_ids: List[str] = []
        for edge_info in edges_info:
            edge_id_in_group = edge_info.get("edge_id")
            src_port = edge_info.get("src_port")
            dst_port = edge_info.get("dst_port")
            if not edge_id_in_group:
                continue

            is_flow_edge = self._is_flow_edge_between(node1_id, src_port, node2_id, dst_port)
            self.view.highlight_edge(edge_id_in_group, is_flow_edge=is_flow_edge)
            focused_edge_ids.append(edge_id_in_group)

            if src_port:
                self.view.highlight_port(node1_id, src_port, is_input=False)
            if dst_port:
                self.view.highlight_port(node2_id, dst_port, is_input=True)

        self._dim_unrelated([node1_id, node2_id], focused_edge_ids)
        self._finalize_updates()

        def _merged_focus(use_animation: bool) -> None:
            if self.view.overlay_manager and edges_info:
                first_src = edges_info[0].get("src_port")
                first_dst = edges_info[0].get("dst_port")
                self.view.overlay_manager.show_node_pair(node1_id, node2_id, first_src, first_dst)
            first_edge_id = edges_info[0].get("edge_id") if edges_info else None
            self.view.focus_on_nodes_and_edge(node1_id, node2_id, first_edge_id, use_animation=use_animation)

        self._schedule_focus(current_version, _merged_focus)

    def _handle_template_graph_root(self, todo: TodoItem, current_version: int) -> None:
        self._hide_overlay()
        self._finalize_updates()

        self._schedule_focus(
            current_version,
            lambda use_animation: self.view.fit_all(use_animation=use_animation),
        )

    def _handle_event_flow_root(self, todo: TodoItem, current_version: int) -> None:
        # 事件流根：调用分组聚焦
        # 具体节点集合由外层在调用前准备并通过 detail_info 传入或由外层辅助函数计算
        node_ids = todo.detail_info.get("_flow_node_ids", []) or []
        if node_ids:
            for node_identifier in node_ids:
                self.view.highlight_node(node_identifier)
            self._dim_unrelated(node_ids, [])
            self._hide_overlay()
            self._finalize_updates()

            self._schedule_focus(
                current_version,
                lambda use_animation, nids=list(node_ids): self._focus_on_node_group(nids, use_animation=use_animation),
            )
        else:
            self._hide_overlay()
            self._finalize_updates()

            self._schedule_focus(
                current_version,
                lambda use_animation: self.view.fit_all(use_animation=use_animation),
            )

    def _handle_dynamic_port_step(self, todo: TodoItem, current_version: int) -> None:
        # 动态端口添加：高亮目标节点并聚焦（与创建/配置类体验一致）
        node_id = todo.detail_info.get("node_id")
        self._highlight_single_node_and_focus(
            node_id=node_id,
            current_version=current_version,
            dim_unrelated=True,
            hide_overlay=True,
        )

    def _handle_graph_signals_overview(self, todo: TodoItem, current_version: int) -> None:
        # 高亮本图中所有使用信号的节点，并聚焦到这些节点所在区域
        signals = todo.detail_info.get("signals", []) or []
        node_ids: List[str] = []
        for signal_entry in signals:
            nodes_info = signal_entry.get("nodes") or []
            for node_info in nodes_info:
                node_id = node_info.get("node_id")
                if node_id and node_id not in node_ids:
                    node_ids.append(node_id)

        if node_ids:
            for node_identifier in node_ids:
                self.view.highlight_node(node_identifier)
            self._dim_unrelated(node_ids, [])
            self._hide_overlay()
            self._finalize_updates()

            self._schedule_focus(
                current_version,
                lambda use_animation, nids=list(node_ids): self._focus_on_node_group(nids, use_animation=use_animation),
            )
        else:
            self._hide_overlay()
            self._finalize_updates()

            self._schedule_focus(
                current_version,
                lambda use_animation: self.view.fit_all(use_animation=use_animation),
            )

    def _handle_graph_bind_signal(self, todo: TodoItem, current_version: int) -> None:
        node_id = todo.detail_info.get("node_id")
        self._highlight_single_node_and_focus(
            node_id=node_id,
            current_version=current_version,
            dim_unrelated=True,
            hide_overlay=True,
        )

    # === 工具 ===
    def focus_on_node_group(self, node_ids: List[str], *, use_animation: Optional[bool] = None) -> None:
        """对外公开的分组聚焦接口。"""
        self._focus_on_node_group(node_ids, use_animation=use_animation)

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

    # === 预览上下文解析（从 Todo 推导 graph_data / graph_id / 容器对象） ===
    def get_graph_data_id_and_container(
        self,
        todo: TodoItem,
        todo_map: Dict[str, TodoItem],
        main_window: Any,
        tree_manager: Any = None,
    ) -> Tuple[Optional[dict], Optional[str], Optional[object]]:
        """解析给定 Todo 所属图的 graph_data / graph_id 以及预览容器对象。

        优先级：
        1. 若提供了 tree_manager，则：
           - 对模板图根/事件流根直接通过 tree_manager.load_graph_data_for_root 加载；
           - 对叶子步骤先回溯到模板图根，再按图根加载；
        2. 回退到基于 detail_info 的 graph_id / graph_data 解析；
        3. 若仍缺失且 main_window.resource_manager 可用，则按 graph_id 走 ResourceManager + GraphConfig 加载，
           并通过 graph_data_cache 写回缓存 key。
        """
        graph_id: Optional[str] = None
        graph_data: Optional[dict] = None

        # 1) 优先使用 TodoTreeManager/TodoTreeGraphSupport 提供的图根加载逻辑
        root_todo_for_tree: Optional[TodoItem] = None
        detail_type = (todo.detail_info or {}).get("type", "")
        if tree_manager is not None:
            if StepTypeRules.is_graph_root(detail_type):
                root_todo_for_tree = todo
            else:
                find_root = getattr(tree_manager, "find_template_graph_root_for_todo", None)
                if callable(find_root):
                    root_todo_for_tree = find_root(todo.todo_id)
            if root_todo_for_tree is not None:
                root_info = root_todo_for_tree.detail_info or {}
                graph_id_candidate = root_info.get("graph_id")
                if isinstance(graph_id_candidate, str) and graph_id_candidate:
                    graph_id = graph_id_candidate
                if hasattr(tree_manager, "load_graph_data_for_root") and callable(
                    getattr(tree_manager, "load_graph_data_for_root")
                ):
                    loaded = tree_manager.load_graph_data_for_root(root_todo_for_tree)
                    if isinstance(loaded, dict) and ("nodes" in loaded or "edges" in loaded):
                        graph_data = loaded

        # 2) 回退到基于 detail_info / graph_data_key 的解析
        if graph_id is None:
            graph_id = self._resolve_graph_id(todo, todo_map)
        if graph_data is None:
            graph_data = self._resolve_graph_data(todo, todo_map)

        # 3) 最终兜底：直接按 graph_id 使用 ResourceManager + GraphConfig 加载，并写回缓存 key
        if (not graph_data) and main_window and hasattr(main_window, 'resource_manager') and graph_id:
            res_mgr = getattr(main_window, 'resource_manager')
            data = res_mgr.load_resource(ResourceType.GRAPH, graph_id)
            if data and isinstance(data, dict):
                graph_config = GraphConfig.deserialize(data)
                graph_data = graph_config.data
                detail = dict(todo.detail_info or {})
                cache_key = store_graph_data(todo.todo_id, graph_id, graph_data)
                detail["graph_data_key"] = cache_key
                detail.pop("graph_data", None)
                todo.detail_info = detail
        container_obj = self._resolve_template_or_instance(todo, todo_map, main_window)
        return graph_data, graph_id, container_obj

    def _resolve_graph_data(self, todo: TodoItem, todo_map: Dict[str, TodoItem]) -> Optional[dict]:
        # 优先从当前任务
        current_info = todo.detail_info or {}
        data = resolve_graph_data(current_info)
        if isinstance(data, dict) and ("nodes" in data or "edges" in data):
            if settings.PREVIEW_VERBOSE:
                print("[PREVIEW] graph_data 来自当前任务(detail_info)")
            return data
        # 向上查找
        current_id = todo.todo_id
        depth = 0
        while current_id and depth < 10:
            current = todo_map.get(current_id)
            if not current:
                break
            detail_type = (current.detail_info or {}).get("type")
            # 仅在“模板图根”处尝试读取/复用图数据；
            # 事件流根自身不持有 graph_data_key，应继续向上查找到对应的模板图根。
            if StepTypeRules.is_template_graph_root(detail_type):
                data = resolve_graph_data(current.detail_info or {})
                if isinstance(data, dict) and ("nodes" in data or "edges" in data):
                    if settings.PREVIEW_VERBOSE:
                        print(f"[PREVIEW] graph_data 来自父任务(模板图根): {detail_type}")
                    return data
                return None
            current_id = current.parent_id
            depth += 1
        if settings.PREVIEW_VERBOSE:
            print("[PREVIEW] 未找到 graph_data")
        return None

    def _resolve_graph_id(self, todo: TodoItem, todo_map: Dict[str, TodoItem]) -> Optional[str]:
        # 当前任务
        gid = todo.detail_info.get("graph_id")
        if gid:
            if settings.PREVIEW_VERBOSE:
                print(f"[PREVIEW] graph_id 来自当前任务: {gid}")
            return gid
        # 向上查找
        current_id = todo.parent_id
        depth = 0
        while current_id and depth < 10:
            current = todo_map.get(current_id)
            if not current:
                break
            gid = current.detail_info.get("graph_id")
            if gid:
                if settings.PREVIEW_VERBOSE:
                    print(f"[PREVIEW] graph_id 来自父任务: {gid}")
                return gid
            current_id = current.parent_id
            depth += 1
        if settings.PREVIEW_VERBOSE:
            print("[PREVIEW] 未找到 graph_id")
        return None

    def _resolve_template_or_instance(self, todo: TodoItem, todo_map: Dict[str, TodoItem], main_window: Any) -> Optional[object]:
        if not main_window or not hasattr(main_window, 'package_controller'):
            if settings.PREVIEW_VERBOSE:
                print("[PREVIEW] 无 main_window.package_controller，预览上下文不可用")
            return None
        current_package = main_window.package_controller.current_package
        if not current_package:
            if settings.PREVIEW_VERBOSE:
                print("[PREVIEW] 当前没有加载存档，预览上下文不可用")
            return None
        # 当前任务
        detail = todo.detail_info
        template_id = detail.get("template_id")
        instance_id = detail.get("instance_id")
        if not template_id and "template:" in detail.get("target_id", ""):
            template_id = detail["target_id"].split("template:")[-1]
        if template_id:
            obj = current_package.get_template(template_id)
            if settings.PREVIEW_VERBOSE:
                print(f"[PREVIEW] 预览容器: template_id={template_id}, found={bool(obj)}")
            return obj
        if instance_id:
            obj = current_package.get_instance(instance_id)
            if settings.PREVIEW_VERBOSE:
                print(f"[PREVIEW] 预览容器: instance_id={instance_id}, found={bool(obj)}")
            return obj
        # 向上查找
        current_id = todo.parent_id
        depth = 0
        while current_id and depth < 10:
            current = todo_map.get(current_id)
            if not current:
                break
            detail = current.detail_info
            template_id = detail.get("template_id")
            instance_id = detail.get("instance_id")
            if not template_id and "template:" in detail.get("target_id", ""):
                template_id = detail["target_id"].split("template:")[-1]
            if template_id:
                obj = current_package.get_template(template_id)
                if settings.PREVIEW_VERBOSE:
                    print(f"[PREVIEW] 预览容器(父任务): template_id={template_id}, found={bool(obj)}")
                return obj
            if instance_id:
                obj = current_package.get_instance(instance_id)
                if settings.PREVIEW_VERBOSE:
                    print(f"[PREVIEW] 预览容器(父任务): instance_id={instance_id}, found={bool(obj)}")
                return obj
            current_id = current.parent_id
            depth += 1
        return None

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
        # 批处理，避免闪烁
        self.view.setUpdatesEnabled(False)
        self.view.clear_highlights()
        self.view.restore_all_opacity()

        detail_type = todo.detail_info.get("type", "")
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
            self.view.setUpdatesEnabled(True)

            def _focus_group() -> None:
                if nodes_to_focus:
                    self.focus_on_node_group(nodes_to_focus)
                else:
                    self.view.fit_all()
            QtCore.QTimer.singleShot(TodoStyles.ANIMATION_DELAY, _focus_group)
            return

        # 默认适应全图
        self.view.setUpdatesEnabled(True)
        QtCore.QTimer.singleShot(TodoStyles.ANIMATION_DELAY, self.view.fit_all)

    # === 内部小工具 ===
    def _schedule(self, version: int, fn) -> None:
        def _wrapped() -> None:
            if self._focus_operation_version == version:
                fn()
        QtCore.QTimer.singleShot(TodoStyles.ANIMATION_DELAY, _wrapped)

    def _schedule_focus(self, version: int, fn: Callable[[bool], None]) -> None:
        use_animation = self._should_use_focus_animation()

        def _wrapped() -> None:
            if self._focus_operation_version == version:
                fn(use_animation)
        QtCore.QTimer.singleShot(TodoStyles.ANIMATION_DELAY, _wrapped)

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
        self.view.restore_all_opacity()

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
            if hide_overlay:
                self._hide_overlay()
            self._finalize_updates()
            return

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


