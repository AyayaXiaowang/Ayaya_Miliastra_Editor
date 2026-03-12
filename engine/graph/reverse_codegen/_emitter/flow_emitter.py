from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from engine.graph.models import NodeModel

from engine.graph.reverse_codegen._common import (
    ReverseGraphCodeError,
    _is_layout_artifact_node_id,
)
from engine.graph.reverse_codegen._emitter.constants import (
    MAX_GRAPH_END_NODE_IDS_IN_ERROR,
    MIN_BRANCH_USAGE_FOR_LIFT,
)


class _StructuredEventEmitterFlowEmitter:
    """提供事件体入口组织、分支体与共享数据源提升等结构化发射能力。"""

    def emit_event_body(
        self,
        *,
        out_lines: List[str],
        event_node: NodeModel,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
    ) -> Optional[str]:
        """发射单个事件方法体并在需要时返回 return 表达式。"""
        visited_flow: set[str] = set()
        self._emit_event_entry_sequence(
            out_lines=out_lines,
            event_node=event_node,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent,
            visited_flow=visited_flow,
        )
        self._emit_additional_flow_entry_sequences(
            out_lines=out_lines,
            event_node=event_node,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent,
            visited_flow=visited_flow,
        )
        return_expr = self._maybe_build_return_expr_from_graph_end(
            out_lines=out_lines,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent,
        )
        self._assert_no_unemitted_nodes_in_event(event_node=event_node)
        return return_expr

    def _emit_event_entry_sequence(
        self,
        *,
        out_lines: List[str],
        event_node: NodeModel,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
        visited_flow: set[str],
    ) -> None:
        """发射事件主入口从“流程出”开始的流程序列。"""
        entry = self.flow_out_by_port.get((str(event_node.id), "流程出"))  # type: ignore[attr-defined]
        if entry is None:
            return
        start_node, start_port = entry
        if start_port == "跳出循环":
            raise ReverseGraphCodeError("事件入口不应直接连到循环的跳出循环端口")
        self._emit_flow_sequence(
            out_lines=out_lines,
            start_node_id=start_node,
            stop_node_id=None,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent,
            loop_stack=[],
            visited_flow=visited_flow,
        )

    def _emit_additional_flow_entry_sequences(
        self,
        *,
        out_lines: List[str],
        event_node: NodeModel,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
        visited_flow: set[str],
    ) -> None:
        """发射事件内与主入口不连通但无流程入的额外流程入口序列。"""
        extra_roots = self._collect_extra_flow_roots(event_node=event_node)
        for root_id in extra_roots:
            self._emit_flow_sequence(
                out_lines=out_lines,
                start_node_id=root_id,
                stop_node_id=None,
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                indent=indent,
                loop_stack=[],
                visited_flow=visited_flow,
            )

    def _collect_extra_flow_roots(self, *, event_node: NodeModel) -> List[str]:
        """收集 member_set 中满足“无流程入且有流程出”的额外流程入口节点。"""
        extra_roots: List[str] = []
        event_id = str(getattr(event_node, "id", "") or "")
        for node_id in sorted(self.member_set):  # type: ignore[attr-defined]
            if str(node_id) == event_id:
                continue
            if node_id in self.emitted_nodes:  # type: ignore[attr-defined]
                continue
            node = self.model.nodes.get(str(node_id))  # type: ignore[attr-defined]
            if node is None:
                continue
            if str(getattr(node, "category", "") or "") == "事件节点":
                continue
            if self._is_flow_entry_node(node):
                extra_roots.append(str(node_id))
        return extra_roots

    def _is_flow_entry_node(self, node: NodeModel) -> bool:
        """判断节点是否为“无流程入且有流程出”的流程入口节点。"""
        has_flow_out = any(
            (str(getattr(p, "name", "") or "") and self._is_flow_port(node, str(getattr(p, "name", "") or ""), True))  # type: ignore[attr-defined]
            for p in (getattr(node, "outputs", None) or [])
        )
        has_flow_in = any(
            (str(getattr(p, "name", "") or "") and self._is_flow_port(node, str(getattr(p, "name", "") or ""), False))  # type: ignore[attr-defined]
            for p in (getattr(node, "inputs", None) or [])
        )
        return bool(has_flow_out and (not has_flow_in))

    def _maybe_build_return_expr_from_graph_end(
        self,
        *,
        out_lines: List[str],
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
    ) -> Optional[str]:
        """从 graph_end 节点补发数据节点并返回其结果表达式。"""
        graph_end_nodes = self._collect_graph_end_nodes()
        if not graph_end_nodes:
            return None
        if len(graph_end_nodes) > 1:
            raise ReverseGraphCodeError(
                "同一事件内存在多个节点图结束（graph_end）节点，无法稳定反向生成 return："
                + ", ".join(str(getattr(n, "id", "") or "") for n in graph_end_nodes[:MAX_GRAPH_END_NODE_IDS_IN_ERROR])
                + ("..." if len(graph_end_nodes) > MAX_GRAPH_END_NODE_IDS_IN_ERROR else "")
            )
        end_node = graph_end_nodes[0]
        expr = self._expr_for_optional_data_input(
            node_id=str(end_node.id),
            port_name="结果",
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            out_lines=out_lines,
            indent=indent,
            loop_stack=[],
        )
        if not str(expr or "").strip():
            raise ReverseGraphCodeError("节点图结束（graph_end）缺少结果数据来源，无法生成 return 表达式")
        return str(expr)

    def _collect_graph_end_nodes(self) -> List[NodeModel]:
        """收集事件 member_set 内代表节点图结束的 graph_end 节点集合。"""
        graph_end_nodes: List[NodeModel] = []
        for nid in self.member_set:  # type: ignore[attr-defined]
            node = self.model.nodes.get(str(nid))  # type: ignore[attr-defined]
            if node is None:
                continue
            if _is_layout_artifact_node_id(node_id=str(nid), node=node):
                continue
            if str(getattr(node, "id", "") or "").startswith("graph_end_"):
                graph_end_nodes.append(node)
                continue
            if str(getattr(node, "title", "") or "").strip().startswith("节点图结束"):
                graph_end_nodes.append(node)
        return graph_end_nodes

    def _assert_no_unemitted_nodes_in_event(self, *, event_node: NodeModel) -> None:
        """校验事件 member_set 内不存在无法稳定发射的剩余节点。"""
        remaining: List[str] = []
        event_id = str(getattr(event_node, "id", "") or "")
        for nid in self.member_set:  # type: ignore[attr-defined]
            nid_str = str(nid)
            if nid_str == event_id:
                continue
            if nid_str.startswith("graph_end_"):
                continue
            if nid_str in self.emitted_nodes:  # type: ignore[attr-defined]
                continue
            node = self.model.nodes.get(nid_str)  # type: ignore[attr-defined]
            if node is None:
                continue
            if _is_layout_artifact_node_id(node_id=nid_str, node=node):
                continue
            if str(getattr(node, "title", "") or "").strip().startswith("节点图结束"):
                continue
            remaining.append(nid_str)

        if remaining:
            node = self.model.nodes.get(remaining[0])  # type: ignore[attr-defined]
            title = f"{getattr(node, 'category', '')}/{getattr(node, 'title', '')}" if node is not None else "<missing>"
            raise ReverseGraphCodeError(
                "事件内存在无法稳定反向生成的节点（可能是无流程入但也非流程入口，或存在多入口 join 等结构）："
                + f"{remaining[0]} ({title})"
            )

    def _emit_flow_sequence(
        self,
        *,
        out_lines: List[str],
        start_node_id: Optional[str],
        stop_node_id: Optional[str],
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
        loop_stack: List[str],
        visited_flow: set[str],
    ) -> None:
        """沿流程边从 start 发射到 stop 之前的顺序语句序列。"""
        current = str(start_node_id) if start_node_id else ""
        stop = str(stop_node_id or "")
        while current and current != stop:
            if current in visited_flow:
                return
            visited_flow.add(current)

            node = self.model.nodes.get(current)  # type: ignore[attr-defined]
            if node is None:
                return

            next_node_id = self._emit_flow_node_and_get_next(  # type: ignore[attr-defined]
                out_lines=out_lines,
                node_id=current,
                node=node,
                stop_node_id=stop_node_id,
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                indent=indent,
                loop_stack=loop_stack,
                visited_flow=visited_flow,
            )
            if not next_node_id:
                return
            current = str(next_node_id)

    def _emit_branch_body(
        self,
        *,
        out_lines: List[str],
        branch_target: Optional[Tuple[str, str]],
        join_node_id: Optional[str],
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
        loop_stack: List[str],
        visited_flow: set[str],
    ) -> None:
        """发射单个分支体并在不可达 join 时注入 return。"""
        if branch_target is not None and branch_target[1] == "跳出循环":
            if not loop_stack or branch_target[0] != loop_stack[-1]:
                raise ReverseGraphCodeError("break 分支不在正确的循环上下文内")
            out_lines.append(f"{indent}break")
            return

        if branch_target is None or (join_node_id and branch_target[0] == join_node_id):
            out_lines.append(f"{indent}pass")
            return

        self._emit_flow_sequence(
            out_lines=out_lines,
            start_node_id=branch_target[0],
            stop_node_id=join_node_id,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent,
            loop_stack=loop_stack,
            visited_flow=visited_flow,
        )

        if join_node_id and (not self._can_reach(branch_target[0], join_node_id)):  # type: ignore[attr-defined]
            out_lines.append(f"{indent}return")

    def _emit_shared_data_sources_for_branches(
        self,
        *,
        out_lines: List[str],
        indent: str,
        branch_targets: List[Optional[Tuple[str, str]]],
        join_node_id: Optional[str],
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
    ) -> None:
        """将被多个分支共同依赖的纯数据节点提升到控制流语句之前。"""
        branch_flow_nodes: List[set[str]] = []
        for target in branch_targets:
            if target is None:
                branch_flow_nodes.append(set())
                continue
            node_id, dst_port = target
            if dst_port == "跳出循环":
                branch_flow_nodes.append(set())
                continue
            branch_flow_nodes.append(
                self._collect_flow_nodes_in_region(start_node_id=node_id, stop_node_id=join_node_id)  # type: ignore[attr-defined]
            )

        src_count: Dict[str, int] = {}
        for flow_nodes in branch_flow_nodes:
            srcs = self._collect_direct_data_sources_into_nodes(flow_nodes)  # type: ignore[attr-defined]
            for src in srcs:
                src_count[src] = src_count.get(src, 0) + 1

        shared_sources = [node_id for node_id, count in src_count.items() if count >= MIN_BRANCH_USAGE_FOR_LIFT]
        join_sources: set[str] = set()
        if join_node_id:
            join_sources = self._collect_direct_data_sources_into_nodes({str(join_node_id)})  # type: ignore[attr-defined]

        lifted_sources = set(shared_sources) | set(join_sources)
        for node_id in sorted(lifted_sources):
            if node_id in self.emitted_nodes:  # type: ignore[attr-defined]
                continue
            if not self._can_emit_data_node_without_unbound_flow_sources(  # type: ignore[attr-defined]
                node_id=str(node_id),
                var_mapping=var_mapping,
                visiting=set(),
            ):
                continue
            self._ensure_data_node_emitted(  # type: ignore[attr-defined]
                out_lines=out_lines,
                node_id=node_id,
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                indent=indent,
            )

