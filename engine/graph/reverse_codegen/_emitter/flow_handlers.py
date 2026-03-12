from __future__ import annotations

import keyword
from typing import Dict, List, Optional, Tuple

from engine.graph.common import LOOP_NODE_NAMES
from engine.graph.models import NodeModel
from engine.utils.name_utils import make_valid_identifier

from engine.graph.reverse_codegen._common import (
    ReverseGraphCodeError,
    _try_resolve_node_def,
)
from engine.graph.reverse_codegen._emitter.call_args import _render_node_call_args


class _StructuredEventEmitterFlowHandlers:
    """提供控制流节点（if/match/loop/复合多出口）的发射处理器。"""

    def _emit_flow_node_and_get_next(
        self,
        *,
        out_lines: List[str],
        node_id: str,
        node: NodeModel,
        stop_node_id: Optional[str],
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
        loop_stack: List[str],
        visited_flow: set[str],
    ) -> Optional[str]:
        """发射单个流程节点并返回下一流程节点 id。"""
        title = str(getattr(node, "title", "") or "").strip()

        if title == "跳出循环":
            self._emit_break_from_break_node(
                out_lines=out_lines,
                node_id=node_id,
                indent=indent,
                loop_stack=loop_stack,
            )
            return None

        if title == "双分支":
            return self._emit_if_node_and_get_next(
                out_lines=out_lines,
                node_id=node_id,
                stop_node_id=stop_node_id,
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                indent=indent,
                loop_stack=loop_stack,
                visited_flow=visited_flow,
            )

        if title == "多分支":
            return self._emit_match_node_and_get_next(
                out_lines=out_lines,
                node_id=node_id,
                node=node,
                stop_node_id=stop_node_id,
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                indent=indent,
                loop_stack=loop_stack,
                visited_flow=visited_flow,
            )

        node_def = _try_resolve_node_def(node=node, node_library=self.node_library)  # type: ignore[attr-defined]
        if node_def is not None and bool(getattr(node_def, "is_composite", False)):
            handled, next_id = self._try_emit_composite_match_and_get_next(
                out_lines=out_lines,
                node_id=node_id,
                node=node,
                node_def=node_def,
                stop_node_id=stop_node_id,
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                indent=indent,
                loop_stack=loop_stack,
                visited_flow=visited_flow,
            )
            if handled:
                return next_id

        if title in LOOP_NODE_NAMES:
            return self._emit_loop_node_and_get_next(
                out_lines=out_lines,
                node_id=node_id,
                node=node,
                stop_node_id=stop_node_id,
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                indent=indent,
                loop_stack=loop_stack,
            )

        return self._emit_regular_node_and_get_next(
            out_lines=out_lines,
            node_id=node_id,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent,
            loop_stack=loop_stack,
        )

    def _emit_break_from_break_node(
        self,
        *,
        out_lines: List[str],
        node_id: str,
        indent: str,
        loop_stack: List[str],
    ) -> None:
        """将跳出循环节点还原为语句级 break 并终止当前序列。"""
        next_flow = self._pick_single_flow_successor(node_id)  # type: ignore[attr-defined]
        if next_flow is None:
            raise ReverseGraphCodeError("【跳出循环】节点缺少流程后继，无法反向生成 break")
        next_node, next_port = next_flow
        if next_port != "跳出循环":
            raise ReverseGraphCodeError("【跳出循环】节点的流程后继必须连到循环节点输入【跳出循环】")
        self._assert_break_target(loop_stack=loop_stack, target_node_id=next_node)
        self.emitted_nodes.add(str(node_id))  # type: ignore[attr-defined]
        out_lines.append(f"{indent}break")

    def _assert_break_target(self, *, loop_stack: List[str], target_node_id: str) -> None:
        """校验跳出循环连线目标是否为当前最内层循环节点。"""
        if not loop_stack:
            raise ReverseGraphCodeError("发现跳出循环语义，但当前不在循环体内")
        if str(target_node_id) != str(loop_stack[-1]):
            raise ReverseGraphCodeError("跳出循环连线的目标不是当前最内层循环")

    def _advance_to_next_flow_or_break(
        self,
        *,
        out_lines: List[str],
        current_node_id: str,
        indent: str,
        loop_stack: List[str],
    ) -> Optional[str]:
        """推进到唯一流程后继并在遇到跳出循环端口时发射 break。"""
        next_flow = self._pick_single_flow_successor(current_node_id)  # type: ignore[attr-defined]
        if next_flow is None:
            return None
        next_node, next_port = next_flow
        if next_port == "跳出循环":
            self._assert_break_target(loop_stack=loop_stack, target_node_id=next_node)
            out_lines.append(f"{indent}break")
            return None
        return str(next_node)

    def _emit_node_as_non_structured_and_get_next(
        self,
        *,
        out_lines: List[str],
        node_id: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
        loop_stack: List[str],
    ) -> Optional[str]:
        """将节点按普通调用发射并返回其流程后继。"""
        self._emit_node_statement(  # type: ignore[attr-defined]
            out_lines=out_lines,
            node_id=node_id,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent,
        )
        return self._advance_to_next_flow_or_break(
            out_lines=out_lines,
            current_node_id=node_id,
            indent=indent,
            loop_stack=loop_stack,
        )

    def _emit_if_node_and_get_next(
        self,
        *,
        out_lines: List[str],
        node_id: str,
        stop_node_id: Optional[str],
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
        loop_stack: List[str],
        visited_flow: set[str],
    ) -> Optional[str]:
        """发射双分支节点为 if/else 或退化为普通节点调用。"""
        true_target = self._flow_target(node_id, "是")  # type: ignore[attr-defined]
        false_target = self._flow_target(node_id, "否")  # type: ignore[attr-defined]
        if true_target is None and false_target is None:
            return self._emit_node_as_non_structured_and_get_next(
                out_lines=out_lines,
                node_id=node_id,
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                indent=indent,
                loop_stack=loop_stack,
            )

        self.emitted_nodes.add(str(node_id))  # type: ignore[attr-defined]
        join = self._find_join_for_branches(  # type: ignore[attr-defined]
            branch_starts=[true_target, false_target],
            stop_node_id=stop_node_id,
        )
        join = self._weak_join_via_stop_if_needed(
            join_node_id=join,
            stop_node_id=stop_node_id,
            branch_targets=[true_target, false_target],
        )

        self._emit_shared_data_sources_for_branches(  # type: ignore[attr-defined]
            out_lines=out_lines,
            indent=indent,
            branch_targets=[true_target, false_target],
            join_node_id=join,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
        )

        cond_expr = self._expr_for_required_data_input(  # type: ignore[attr-defined]
            node_id=node_id,
            port_name="条件",
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            out_lines=out_lines,
            indent=indent,
            loop_stack=loop_stack,
        )
        out_lines.append(f"{indent}if {cond_expr}:")
        self._emit_branch_body(  # type: ignore[attr-defined]
            out_lines=out_lines,
            branch_target=true_target,
            join_node_id=join,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent + "    ",
            loop_stack=loop_stack,
            visited_flow=set(visited_flow),
        )
        out_lines.append(f"{indent}else:")
        self._emit_branch_body(  # type: ignore[attr-defined]
            out_lines=out_lines,
            branch_target=false_target,
            join_node_id=join,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent + "    ",
            loop_stack=loop_stack,
            visited_flow=set(visited_flow),
        )

        return str(join) if join else None

    def _weak_join_via_stop_if_needed(
        self,
        *,
        join_node_id: Optional[str],
        stop_node_id: Optional[str],
        branch_targets: List[Optional[Tuple[str, str]]],
    ) -> Optional[str]:
        """在缺少 join 时尝试用外层 stop_node_id 作为弱 join 兜底。"""
        if join_node_id or (not stop_node_id):
            return join_node_id
        stop = str(stop_node_id)
        for target in branch_targets:
            if target is None:
                continue
            node_id, dst_port = target
            if dst_port == "跳出循环":
                continue
            if node_id and self._can_reach(str(node_id), stop):  # type: ignore[attr-defined]
                return stop
        return None

    def _emit_match_node_and_get_next(
        self,
        *,
        out_lines: List[str],
        node_id: str,
        node: NodeModel,
        stop_node_id: Optional[str],
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
        loop_stack: List[str],
        visited_flow: set[str],
    ) -> Optional[str]:
        """发射多分支节点为 match/case 或退化为普通节点调用。"""
        has_any_branch_edge = bool(self.flow_out.get(str(node_id), []) or [])  # type: ignore[attr-defined]
        if not has_any_branch_edge:
            return self._emit_node_as_non_structured_and_get_next(
                out_lines=out_lines,
                node_id=node_id,
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                indent=indent,
                loop_stack=loop_stack,
            )

        self.emitted_nodes.add(str(node_id))  # type: ignore[attr-defined]
        control_expr = self._expr_for_required_match_subject(  # type: ignore[attr-defined]
            node_id=node_id,
            port_name="控制表达式",
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            out_lines=out_lines,
            indent=indent,
            loop_stack=loop_stack,
        )

        flow_out_ports = [
            str(getattr(p, "name", "") or "")
            for p in (getattr(node, "outputs", None) or [])
            if str(getattr(p, "name", "") or "")
        ]
        if not flow_out_ports:
            raise ReverseGraphCodeError("多分支节点缺少输出端口")

        branch_targets = [self._flow_target(node_id, port) for port in flow_out_ports]  # type: ignore[attr-defined]
        join = self._find_join_for_branches(  # type: ignore[attr-defined]
            branch_starts=branch_targets,
            stop_node_id=stop_node_id,
        )
        join = self._weak_join_via_stop_if_needed(
            join_node_id=join,
            stop_node_id=stop_node_id,
            branch_targets=branch_targets,
        )

        self._emit_shared_data_sources_for_branches(  # type: ignore[attr-defined]
            out_lines=out_lines,
            indent=indent,
            branch_targets=branch_targets,
            join_node_id=join,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
        )

        out_lines.append(f"{indent}match {control_expr}:")
        ordered_ports = list(flow_out_ports)
        if join:
            ordered_ports = self._order_match_ports_by_reachability(
                node_id=node_id,
                ports=ordered_ports,
                join_node_id=str(join),
            )

        for port_name in ordered_ports:
            pattern = self._render_match_case_pattern(port_name)  # type: ignore[attr-defined]
            out_lines.append(f"{indent}    case {pattern}:")
            self._emit_branch_body(  # type: ignore[attr-defined]
                out_lines=out_lines,
                branch_target=self._flow_target(node_id, port_name),  # type: ignore[attr-defined]
                join_node_id=join,
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                indent=indent + "        ",
                loop_stack=loop_stack,
                visited_flow=set(visited_flow),
            )

        return str(join) if join else None

    def _order_match_ports_by_reachability(self, *, node_id: str, ports: List[str], join_node_id: str) -> List[str]:
        """对 match/case 端口按是否可达 join 做稳定重排。"""
        reachable_ports: List[str] = []
        unreachable_ports: List[str] = []
        for port_name in ports:
            target = self._flow_target(node_id, port_name)  # type: ignore[attr-defined]
            if target is None or target[1] == "跳出循环":
                unreachable_ports.append(port_name)
                continue
            start_id = str(target[0])
            if start_id == join_node_id or self._can_reach(start_id, join_node_id):  # type: ignore[attr-defined]
                reachable_ports.append(port_name)
            else:
                unreachable_ports.append(port_name)
        return unreachable_ports + reachable_ports

    def _try_emit_composite_match_and_get_next(
        self,
        *,
        out_lines: List[str],
        node_id: str,
        node: NodeModel,
        node_def: object,
        stop_node_id: Optional[str],
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
        loop_stack: List[str],
        visited_flow: set[str],
    ) -> Tuple[bool, Optional[str]]:
        """在复合节点存在多流程出口时发射 match self.<实例>.<入口>(...) 结构。"""
        flow_outputs_in_order = [
            str(getattr(p, "name", "") or "")
            for p in (getattr(node, "outputs", None) or [])
            if str(getattr(p, "name", "") or "")
            and self._is_flow_port(node, str(getattr(p, "name", "") or ""), True)  # type: ignore[attr-defined]
        ]
        connected_flow_outputs = [name for name in flow_outputs_in_order if self._flow_target(node_id, name) is not None]  # type: ignore[attr-defined]

        needs_match = False
        if len(connected_flow_outputs) > 1:
            needs_match = True
        elif (
            len(connected_flow_outputs) == 1
            and len(flow_outputs_in_order) > 1
            and connected_flow_outputs[0] != flow_outputs_in_order[0]
        ):
            needs_match = True

        if not needs_match:
            return (False, None)

        self._assert_composite_match_has_no_used_data_outputs(node_id=node_id, node=node)
        self._ensure_composite_call_data_sources_emitted(
            out_lines=out_lines,
            node=node,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent,
        )

        subject_expr = self._build_composite_match_subject_expr(
            node=node,
            node_def=node_def,
            var_mapping=var_mapping,
        )
        branch_targets = [self._flow_target(node_id, port) for port in connected_flow_outputs]  # type: ignore[attr-defined]
        join = self._find_join_for_branches(  # type: ignore[attr-defined]
            branch_starts=branch_targets,
            stop_node_id=stop_node_id,
        )

        self._emit_shared_data_sources_for_branches(  # type: ignore[attr-defined]
            out_lines=out_lines,
            indent=indent,
            branch_targets=branch_targets,
            join_node_id=join,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
        )

        out_lines.append(f"{indent}match {subject_expr}:")
        for port_name in connected_flow_outputs:
            pattern = "_" if port_name == "默认" else repr(port_name)
            out_lines.append(f"{indent}    case {pattern}:")
            self._emit_branch_body(  # type: ignore[attr-defined]
                out_lines=out_lines,
                branch_target=self._flow_target(node_id, port_name),  # type: ignore[attr-defined]
                join_node_id=join,
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                indent=indent + "        ",
                loop_stack=loop_stack,
                visited_flow=set(visited_flow),
            )

        self.emitted_nodes.add(str(node_id))  # type: ignore[attr-defined]
        return (True, str(join) if join else None)

    def _assert_composite_match_has_no_used_data_outputs(self, *, node_id: str, node: NodeModel) -> None:
        """校验复合节点在多出口 match 语法下不存在被下游引用的数据输出端口。"""
        for (_dst_node, _dst_port), (src_node_id, src_port) in list(self.data_in_edge.items()):  # type: ignore[attr-defined]
            if str(src_node_id) != str(node_id):
                continue
            if not self._is_flow_port(node, str(src_port), True):  # type: ignore[attr-defined]
                raise ReverseGraphCodeError(
                    f"复合节点 {node.title} 的数据输出端口 {src_port!r} 被下游引用，但该节点又存在多流程出口；"
                    "当前版本无法同时表达“多流程出口 + 数据输出”语义，请拆分图结构或减少对该数据输出的依赖。"
                )

    def _ensure_composite_call_data_sources_emitted(
        self,
        *,
        out_lines: List[str],
        node: NodeModel,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
    ) -> None:
        """确保复合节点调用所需的数据来源节点已被发出（仅允许纯数据节点）。"""
        for port in (getattr(node, "inputs", None) or []):
            pname = str(getattr(port, "name", "") or "")
            if not pname or self._is_flow_port(node, pname, False):  # type: ignore[attr-defined]
                continue
            source = self.data_in_edge.get((str(node.id), pname))  # type: ignore[attr-defined]
            if source is None:
                continue
            src_node_id, _src_port = source
            if src_node_id not in self.emitted_nodes:  # type: ignore[attr-defined]
                self._ensure_data_node_emitted(  # type: ignore[attr-defined]
                    out_lines=out_lines,
                    node_id=str(src_node_id),
                    var_mapping=var_mapping,
                    used_var_names=used_var_names,
                    indent=indent,
                )

    def _build_composite_match_subject_expr(
        self,
        *,
        node: NodeModel,
        node_def: object,
        var_mapping: Dict[Tuple[str, str], str],
    ) -> str:
        """构造复合节点多出口 match 的 subject 表达式字符串。"""
        composite_id = str(getattr(node_def, "composite_id", "") or "").strip() or str(
            getattr(node, "composite_id", "") or ""
        ).strip()
        if not composite_id:
            composite_id = str(getattr(node_def, "name", "") or getattr(node, "title", "") or "").strip()
        alias = self.composite_alias_by_id.get(composite_id) or (  # type: ignore[attr-defined]
            make_valid_identifier(str(getattr(node_def, "name", "") or getattr(node, "title", "") or "")) or "复合实例"
        )
        if not alias.isidentifier() or keyword.iskeyword(alias):
            raise ReverseGraphCodeError(f"复合节点实例名不可作为 self 属性：{alias!r}")

        call_args = _render_node_call_args(
            node=node,
            node_def=node_def,  # type: ignore[arg-type]
            node_library=self.node_library,  # type: ignore[attr-defined]
            data_in_edge=self.data_in_edge,  # type: ignore[attr-defined]
            var_mapping=var_mapping,
        )
        if call_args:
            return f"self.{alias}.{self._composite_entry_method_name}({', '.join(call_args)})"  # type: ignore[attr-defined]
        return f"self.{alias}.{self._composite_entry_method_name}()"  # type: ignore[attr-defined]

    def _emit_loop_node_and_get_next(
        self,
        *,
        out_lines: List[str],
        node_id: str,
        node: NodeModel,
        stop_node_id: Optional[str],
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
        loop_stack: List[str],
    ) -> Optional[str]:
        """发射循环节点为 for 结构并返回循环完成后的接续节点。"""
        self._lift_data_sources_needed_after_loop(
            out_lines=out_lines,
            loop_node_id=node_id,
            stop_node_id=stop_node_id,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent,
        )
        self._emit_loop_header_and_bind_var(
            out_lines=out_lines,
            loop_node_id=node_id,
            loop_title=str(getattr(node, "title", "") or "").strip(),
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent,
            loop_stack=loop_stack,
        )
        self.emitted_nodes.add(str(node_id))  # type: ignore[attr-defined]
        self._emit_loop_body(
            out_lines=out_lines,
            loop_node_id=node_id,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent,
            loop_stack=loop_stack,
        )
        return self._next_after_loop(loop_node_id=node_id)

    def _lift_data_sources_needed_after_loop(
        self,
        *,
        out_lines: List[str],
        loop_node_id: str,
        stop_node_id: Optional[str],
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
    ) -> None:
        """在循环前提升循环后续区域依赖的纯数据节点以避免变量映射缺失。"""
        next_target_preview = self._flow_target(loop_node_id, "循环完成")  # type: ignore[attr-defined]
        if next_target_preview is None or next_target_preview[1] == "跳出循环":
            return

        after_region = self._collect_flow_nodes_in_region(  # type: ignore[attr-defined]
            start_node_id=next_target_preview[0],
            stop_node_id=stop_node_id,
        )
        after_sources = self._collect_direct_data_sources_into_nodes(after_region)  # type: ignore[attr-defined]
        for src_id in sorted(after_sources):
            if src_id in self.emitted_nodes:  # type: ignore[attr-defined]
                continue
            src_node = self.model.nodes.get(src_id)  # type: ignore[attr-defined]
            if src_node is None:
                continue
            if self._node_has_any_flow_port(src_node):  # type: ignore[attr-defined]
                continue
            if not self._can_emit_data_node_without_unbound_flow_sources(  # type: ignore[attr-defined]
                node_id=str(src_id),
                var_mapping=var_mapping,
                visiting=set(),
            ):
                continue
            self._ensure_data_node_emitted(  # type: ignore[attr-defined]
                out_lines=out_lines,
                node_id=src_id,
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                indent=indent,
            )

    def _emit_loop_header_and_bind_var(
        self,
        *,
        out_lines: List[str],
        loop_node_id: str,
        loop_title: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
        loop_stack: List[str],
    ) -> None:
        """发射 for 头并绑定循环节点的数据输出变量映射。"""
        if loop_title == "有限循环":
            loop_var = self._unique_var_name("当前循环值", used_var_names)  # type: ignore[attr-defined]
            var_mapping[(loop_node_id, "当前循环值")] = loop_var
            start_expr = self._expr_for_optional_data_input(  # type: ignore[attr-defined]
                node_id=loop_node_id,
                port_name="循环起始值",
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                out_lines=out_lines,
                indent=indent,
                loop_stack=loop_stack,
            )
            end_expr = self._expr_for_optional_data_input(  # type: ignore[attr-defined]
                node_id=loop_node_id,
                port_name="循环终止值",
                var_mapping=var_mapping,
                used_var_names=used_var_names,
                out_lines=out_lines,
                indent=indent,
                loop_stack=loop_stack,
            )
            if not end_expr:
                raise ReverseGraphCodeError("有限循环缺少 循环终止值（必须有数据来源或常量）")
            range_expr = f"range({start_expr}, {end_expr})" if start_expr and start_expr != "0" else f"range({end_expr})"
            out_lines.append(f"{indent}for {loop_var} in {range_expr}:")
            return

        loop_var = self._unique_var_name("迭代值", used_var_names)  # type: ignore[attr-defined]
        var_mapping[(loop_node_id, "迭代值")] = loop_var
        iter_expr = self._expr_for_required_match_subject(  # type: ignore[attr-defined]
            node_id=loop_node_id,
            port_name="迭代列表",
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            out_lines=out_lines,
            indent=indent,
            loop_stack=loop_stack,
        )
        out_lines.append(f"{indent}for {loop_var} in {iter_expr}:")

    def _emit_loop_body(
        self,
        *,
        out_lines: List[str],
        loop_node_id: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
        loop_stack: List[str],
    ) -> None:
        """发射循环体并以循环节点入栈建立 break 语义上下文。"""
        body_target = self._flow_target(loop_node_id, "循环体")  # type: ignore[attr-defined]
        if body_target is None:
            out_lines.append(f"{indent}    pass")
            return
        if body_target[1] == "跳出循环":
            raise ReverseGraphCodeError("循环体出口不应直接连到跳出循环端口")
        self._emit_flow_sequence(  # type: ignore[attr-defined]
            out_lines=out_lines,
            start_node_id=body_target[0],
            stop_node_id=None,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent + "    ",
            loop_stack=loop_stack + [loop_node_id],
            visited_flow=set(),
        )

    def _next_after_loop(self, *, loop_node_id: str) -> Optional[str]:
        """返回循环完成出口的接续节点 id 并在不合法连线时 fail-fast。"""
        next_target = self._flow_target(loop_node_id, "循环完成")  # type: ignore[attr-defined]
        if next_target is None:
            return None
        if next_target[1] == "跳出循环":
            raise ReverseGraphCodeError("循环完成出口不应连到跳出循环端口")
        return str(next_target[0])

    def _emit_regular_node_and_get_next(
        self,
        *,
        out_lines: List[str],
        node_id: str,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: set[str],
        indent: str,
        loop_stack: List[str],
    ) -> Optional[str]:
        """发射普通节点调用并返回其唯一流程后继。"""
        self._emit_node_statement(  # type: ignore[attr-defined]
            out_lines=out_lines,
            node_id=node_id,
            var_mapping=var_mapping,
            used_var_names=used_var_names,
            indent=indent,
        )
        return self._advance_to_next_flow_or_break(
            out_lines=out_lines,
            current_node_id=node_id,
            indent=indent,
            loop_stack=loop_stack,
        )

