"""节点图任务生成器 - 为节点图生成详细的实施步骤"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from engine.graph.models import GraphModel
from engine.nodes.advanced_node_features import build_signal_definitions_from_package
from engine.signal import get_default_signal_binding_service

from app.runtime.services.graph_data_service import get_shared_graph_data_service
from app.models.todo_item import TodoItem
from app.models.todo_graph_tasks import (
    CompositeTaskBuilder,
    EventFlowTaskBuilder,
    build_edge_lookup,
)
from app.models.todo_node_type_helper import NodeTypeHelper
from app.models.todo_structure_helpers import ensure_child_reference

if TYPE_CHECKING:
    from engine.resources.package_interfaces import PackageLike


@dataclass
class _GraphTaskProgressState:
    """节点图任务生成进度状态（跨子图/复合节点递归复用）。

    说明：
    - completed_units / total_units 用于 UI 百分比进度条：percent = completed / total。
    - 该状态只在一次“展开模板图根”生成过程中存在，结束后会被清理。
    """

    # 进度条需要一个稳定的初始总量，避免在“总量尚未可知”时因 completed > total
    # 直接跳到 100%。后续会按事件流/复合节点动态补齐 total_units。
    completed_units: int = 0
    total_units: int = 100
    last_reported_units: int = 0
    last_reported_stage: str = ""
@dataclass(frozen=True)
class _ParentContext:
    template_ctx_id: str
    instance_ctx_id: str
    target_id: str


def _resolve_parent_context(parent_id: str, graph_id: str) -> _ParentContext:
    if isinstance(parent_id, str):
        if parent_id.startswith("template:"):
            ctx_id = parent_id.split("template:", 1)[-1]
            return _ParentContext(template_ctx_id=ctx_id, instance_ctx_id="", target_id=ctx_id)
        if parent_id.startswith("instance:"):
            ctx_id = parent_id.split("instance:", 1)[-1]
            return _ParentContext(template_ctx_id="", instance_ctx_id=ctx_id, target_id=ctx_id)
    return _ParentContext(template_ctx_id="", instance_ctx_id="", target_id=graph_id)


class TodoGraphTaskGenerator:
    """节点图任务生成器 - 专门负责为节点图生成详细的实施步骤"""

    def __init__(
        self,
        *,
        type_helper: NodeTypeHelper,
        resource_manager=None,
        add_todo_callback: Optional[Callable[[TodoItem], None]] = None,
        todo_map: Optional[Dict[str, TodoItem]] = None,
        package: Optional["PackageLike"] = None,
    ) -> None:
        self.type_helper = type_helper
        self.resource_manager = resource_manager
        self.add_todo_callback = add_todo_callback
        self.todo_map = todo_map if todo_map is not None else {}
        self.package = package
        self._signal_param_types_by_id: Dict[str, Dict[str, str]] = {}
        self._signal_binding_service = get_default_signal_binding_service()
        self._graph_data_service = get_shared_graph_data_service(resource_manager, None)
        if package is not None:
            self._init_signal_param_types(package)
        self._composite_builder = CompositeTaskBuilder(
            add_todo=self._add_todo,
            resource_manager=resource_manager,
            generate_graph_tasks=self._generate_sub_graph_tasks,
        )
        self._event_flow_builder = EventFlowTaskBuilder(
            type_helper=type_helper,
            add_todo=self._add_todo,
            todo_map=self.todo_map,
        )
        # 进度回调：仅在 UI 懒加载“展开模板图根”时由上层注入。
        self._progress_callback: Optional[Callable[[str, int, int], None]] = None
        self._progress_state: Optional[_GraphTaskProgressState] = None

    def _advance_progress(
        self,
        stage: str,
        completed_delta: int = 0,
        total_delta: int = 0,
    ) -> None:
        """推进进度并向上层回调（若存在）。

        参数语义：
        - completed_delta: 本次新增完成的单位数量（>=0）
        - total_delta: 本次新增总量的单位数量（>=0），用于“分批得知总量”的场景
        """
        state = self._progress_state
        callback = self._progress_callback
        if state is None or callback is None:
            return

        safe_completed_delta = int(completed_delta) if int(completed_delta) > 0 else 0
        safe_total_delta = int(total_delta) if int(total_delta) > 0 else 0

        if safe_total_delta:
            state.total_units += safe_total_delta
        if safe_completed_delta:
            state.completed_units += safe_completed_delta
        if state.completed_units > state.total_units:
            state.total_units = state.completed_units

        normalized_stage = str(stage or "")
        should_report = False
        if normalized_stage and normalized_stage != state.last_reported_stage:
            should_report = True
        if state.completed_units - state.last_reported_units >= 20:
            should_report = True

        if should_report:
            callback(normalized_stage, int(state.completed_units), int(state.total_units))
            state.last_reported_stage = normalized_stage
            state.last_reported_units = int(state.completed_units)

    def create_graph_root_todo(
        self,
        parent_id: str,
        graph_id: str,
        graph_name: str,
        target_id: str,
        template_ctx_id: str = "",
        instance_ctx_id: str = "",
        preview_template_id: str = "",
        suppress_auto_jump: bool = False,
        task_type: str = "",
    ) -> TodoItem:
        """构建节点图根任务，供懒加载和即时展开复用"""
        graph_root_id = f"{parent_id}:graph:{graph_id}"
        resolved_task_type = task_type or self._resolve_task_type(template_ctx_id, instance_ctx_id)
        detail_root: Dict[str, Any] = {
            "type": "template_graph_root",
            "graph_id": graph_id,
            "graph_name": graph_name,
            "template_id": template_ctx_id or None,
            "instance_id": instance_ctx_id or None,
            "task_type": resolved_task_type,
        }
        detail_root = self._build_graph_root_detail(
            existing_detail=detail_root,
            graph_id=graph_id,
            graph_name=graph_name,
            template_ctx_id=template_ctx_id,
            instance_ctx_id=instance_ctx_id,
            preview_template_id=preview_template_id,
            suppress_auto_jump=suppress_auto_jump,
        )

        return TodoItem(
            todo_id=graph_root_id,
            title=f"配置节点图：{graph_name}",
            description="请在编辑器中打开此节点图进行配置",
            level=3,
            parent_id=parent_id,
            children=[],
            task_type=resolved_task_type,
            target_id=target_id,
            detail_info=detail_root,
        )

    def generate_graph_tasks(
        self,
        parent_id: str,
        graph_id: str,
        graph_name: str,
        graph_data: dict,
        preview_template_id: str = "",
        suppress_auto_jump: bool = False,
        existing_root: Optional[TodoItem] = None,
        attach_root: bool = True,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> List[str]:
        # 若上层提供进度回调：在“最外层图”初始化进度状态，并允许复合节点子图复用同一状态。
        is_root_progress_owner = False
        if progress_callback is not None:
            self._progress_callback = progress_callback
            if self._progress_state is None:
                self._progress_state = _GraphTaskProgressState()
                is_root_progress_owner = True
            self._advance_progress(f"准备生成：{graph_name}", 0, 0)

        try:
            model = GraphModel.deserialize(graph_data)
            edge_lookup = build_edge_lookup(model)
            self._advance_progress("解析节点图模型", 5, 0)

            context = _resolve_parent_context(parent_id, graph_id)
            template_ctx_id = context.template_ctx_id
            instance_ctx_id = context.instance_ctx_id
            target_id = context.target_id
            task_type = self._resolve_task_type(template_ctx_id, instance_ctx_id)

            composite_step_ids: List[str] = []
            used_composites: Dict[str, str] = {}
            composite_nodes_map: Dict[str, List[Any]] = {}
            for node in model.nodes.values():
                composite_id = getattr(node, "composite_id", "")
                if not composite_id:
                    continue
                composite_nodes_map.setdefault(composite_id, []).append(node)
                if composite_id not in used_composites:
                    used_composites[composite_id] = node.title or composite_id

            if used_composites:
                # 复合节点指引整体占用较小：按复合节点数量给一个轻量总量，避免进度长期停留在 0%。
                self._advance_progress("生成复合节点指引", 0, len(used_composites) * 10)

            for composite_id, composite_name in used_composites.items():
                comp_ids = self._composite_builder.build_composite_steps(
                    parent_id=parent_id,
                    graph_id=graph_id,
                    graph_name=graph_name,
                    composite_id=composite_id,
                    composite_name=composite_name,
                    template_ctx_id=template_ctx_id,
                    instance_ctx_id=instance_ctx_id,
                    composite_nodes=composite_nodes_map.get(composite_id, []),
                )
                composite_step_ids.extend(comp_ids)
                self._advance_progress("生成复合节点指引", 10, 0)

            expected_root_id = f"{parent_id}:graph:{graph_id}"
            graph_root: Optional[TodoItem] = None
            if existing_root is not None and existing_root.todo_id == expected_root_id:
                graph_root = existing_root
            if graph_root is None:
                graph_root = self.create_graph_root_todo(
                    parent_id=parent_id,
                    graph_id=graph_id,
                    graph_name=graph_name,
                    target_id=target_id,
                    template_ctx_id=template_ctx_id,
                    instance_ctx_id=instance_ctx_id,
                    preview_template_id=preview_template_id,
                    suppress_auto_jump=suppress_auto_jump,
                    task_type=task_type,
                )
            self._register_graph_root(graph_root, attach_root=attach_root)
            graph_root.children = []
            self._refresh_graph_root_detail(
                graph_root=graph_root,
                graph_id=graph_id,
                graph_name=graph_name,
                template_ctx_id=template_ctx_id,
                instance_ctx_id=instance_ctx_id,
                preview_template_id=preview_template_id,
                suppress_auto_jump=suppress_auto_jump,
                graph_data=graph_data,
            )
            graph_root_todo_id = graph_root.todo_id

            if model.graph_variables:
                vars_id = f"{graph_root_todo_id}:variables"
                vars_todo = TodoItem(
                    todo_id=vars_id,
                    title="配置节点图变量",
                    description="设置本图的局部变量",
                    level=4,
                    parent_id=graph_root_todo_id,
                    children=[],
                    task_type="template",
                    target_id=graph_id,
                    detail_info={
                        "type": "graph_variables_table",
                        "variables": model.graph_variables,
                    },
                )
                self._add_todo(vars_todo)
                ensure_child_reference(graph_root, vars_id)
                self._advance_progress("生成节点图变量步骤", 2, 0)

            signal_usage_payload = self._collect_signal_usage_for_graph(model)
            if signal_usage_payload:
                signals_id = f"{graph_root_todo_id}:signals"
                signals_detail: Dict[str, Any] = {
                    "type": "graph_signals_overview",
                    "graph_id": graph_id,
                    "graph_name": graph_name,
                    "signals": signal_usage_payload,
                    "template_id": template_ctx_id or None,
                    "instance_id": instance_ctx_id or None,
                }
                signals_todo = TodoItem(
                    todo_id=signals_id,
                    title="检查本图使用的信号",
                    description="查看并确认本图中使用到的信号定义与绑定节点",
                    level=4,
                    parent_id=graph_root_todo_id,
                    children=[],
                    task_type=task_type,
                    target_id=graph_id,
                    detail_info=signals_detail,
                )
                self._add_todo(signals_todo)
                ensure_child_reference(graph_root, signals_id)
                self._advance_progress("生成信号概览步骤", 2, 0)

            signal_param_types_by_node = self._build_signal_param_types_for_graph(model)

            self._event_flow_builder.build_event_flows(
                graph_root_id=graph_root_todo_id,
                graph_id=graph_id,
                model=model,
                edge_lookup=edge_lookup,
                template_ctx_id=template_ctx_id,
                instance_ctx_id=instance_ctx_id,
                suppress_auto_jump=suppress_auto_jump,
                preview_template_id=preview_template_id,
                graph_root=graph_root,
                task_type=task_type,
                signal_param_types_by_node=signal_param_types_by_node,
                progress_advance=self._advance_progress,
            )

            self._advance_progress("完成", 0, 0)
            return composite_step_ids + [graph_root_todo_id]
        finally:
            if is_root_progress_owner:
                state = self._progress_state
                if state is not None:
                    remaining = int(state.total_units) - int(state.completed_units)
                    if remaining > 0:
                        self._advance_progress("完成", remaining, 0)
                    if self._progress_callback is not None:
                        self._progress_callback(
                            "完成",
                            int(state.total_units),
                            int(state.total_units),
                        )
                self._progress_callback = None
                self._progress_state = None

    def _generate_sub_graph_tasks(
        self,
        parent_id: str,
        graph_id: str,
        graph_name: str,
        graph_data: dict,
        preview_template_id: str,
        suppress_auto_jump: bool,
        existing_root: Optional[TodoItem] = None,
        attach_root: bool = True,
    ) -> List[str]:
        return self.generate_graph_tasks(
            parent_id=parent_id,
            graph_id=graph_id,
            graph_name=graph_name,
                graph_data=graph_data,
            preview_template_id=preview_template_id,
            suppress_auto_jump=suppress_auto_jump,
            existing_root=existing_root,
            attach_root=attach_root,
        )

    def _add_todo(self, todo: TodoItem) -> None:
        existing = self.todo_map.get(todo.todo_id)
        if existing:
            self._copy_todo(existing, todo)
            return
        if self.add_todo_callback:
            self.add_todo_callback(todo)
        self.todo_map[todo.todo_id] = todo

    def _register_graph_root(self, graph_root: TodoItem, *, attach_root: bool) -> None:
        already_registered = graph_root.todo_id in self.todo_map
        if already_registered:
            return
        if attach_root:
            self._add_todo(graph_root)
        else:
            self.todo_map[graph_root.todo_id] = graph_root

    def _refresh_graph_root_detail(
        self,
        *,
        graph_root: TodoItem,
        graph_id: str,
        graph_name: str,
        template_ctx_id: str,
        instance_ctx_id: str,
        preview_template_id: str,
        suppress_auto_jump: bool,
        graph_data: dict,
    ) -> None:
        self._graph_data_service.drop_payload_for_root(graph_root.todo_id)
        detail_info = self._build_graph_root_detail(
            existing_detail=graph_root.detail_info,
            graph_id=graph_id,
            graph_name=graph_name,
            template_ctx_id=template_ctx_id,
            instance_ctx_id=instance_ctx_id,
            preview_template_id=preview_template_id,
            suppress_auto_jump=suppress_auto_jump,
        )
        cache_key = self._graph_data_service.store_payload_graph_data(graph_root.todo_id, graph_id, graph_data)
        detail_info["graph_data_key"] = cache_key
        graph_root.detail_info = detail_info

    def _build_graph_root_detail(
        self,
        *,
        existing_detail: Optional[Dict[str, Any]],
        graph_id: str,
        graph_name: str,
        template_ctx_id: str,
        instance_ctx_id: str,
        preview_template_id: str,
        suppress_auto_jump: bool,
    ) -> Dict[str, Any]:
        detail_info = dict(existing_detail or {})
        detail_info["graph_id"] = graph_id
        detail_info["graph_name"] = graph_name
        detail_info["template_id"] = preview_template_id or template_ctx_id or None
        detail_info["instance_id"] = instance_ctx_id or None
        if "task_type" not in detail_info:
            detail_info["task_type"] = self._resolve_task_type(template_ctx_id, instance_ctx_id)
        detail_info.pop("graph_data", None)
        if suppress_auto_jump:
            detail_info["no_auto_jump"] = True
        else:
            detail_info.pop("no_auto_jump", None)
        return detail_info

    def _resolve_task_type(self, template_ctx_id: str, instance_ctx_id: str) -> str:
        if template_ctx_id:
            return "template"
        if instance_ctx_id:
            return "instance"
        return "graph"

    def _copy_todo(self, target: TodoItem, source: TodoItem) -> None:
        target.title = source.title
        target.description = source.description
        target.level = source.level
        target.parent_id = source.parent_id
        target.children = list(source.children)
        target.task_type = source.task_type
        target.target_id = source.target_id
        target.detail_info = dict(source.detail_info or {})

    def _init_signal_param_types(self, package: "PackageLike") -> None:
        """从包级视图的 `signals` 字段预构建 signal_id -> {param_name: param_type} 映射。"""
        signal_definitions = build_signal_definitions_from_package(package)
        mapping: Dict[str, Dict[str, str]] = {}
        for signal_id, signal_def in signal_definitions.items():
            param_map: Dict[str, str] = {}
            for param in signal_def.parameters:
                param_map[param.param_name] = param.param_type
            mapping[signal_id] = param_map
        self._signal_param_types_by_id = mapping

    def _build_signal_param_types_for_graph(self, model: GraphModel) -> Dict[str, Dict[str, str]]:
        """为当前图中的信号节点构建 node_id -> {param_name: expected_type} 映射。"""
        if not self._signal_param_types_by_id:
            return {}
        bindings_raw = model.metadata.get("signal_bindings")
        if not isinstance(bindings_raw, dict):
            return {}
        result: Dict[str, Dict[str, str]] = {}
        for node_id, binding in bindings_raw.items():
            if not isinstance(binding, dict):
                continue
            signal_id_raw = binding.get("signal_id")
            if not signal_id_raw:
                continue
            signal_id = str(signal_id_raw)
            param_map = self._signal_param_types_by_id.get(signal_id)
            if not param_map:
                continue
            result[str(node_id)] = dict(param_map)
        return result

    def _collect_signal_usage_for_graph(self, model: GraphModel) -> List[Dict[str, Any]]:
        """收集当前图中已绑定信号的节点使用情况，供“信号概览”步骤使用。"""
        return self._signal_binding_service.collect_graph_usage(
            model,
            signal_param_types_by_id=self._signal_param_types_by_id or None,
        )
