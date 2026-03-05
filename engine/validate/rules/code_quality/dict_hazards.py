"""字典相关的执行器语义风险提示/约束规则。"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

from engine.utils.graph.graph_utils import is_flow_port_name

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import infer_graph_scope
from ..node_index import callable_node_defs_by_name
from .graph_model_utils import (
    _build_flow_next_index,
    _build_incoming_data_edge_index,
    _canonicalize_node_id,
    _collect_downstream_flow_nodes,
    _get_or_parse_graph_model,
    _span_for_graph_nodes,
)


def _is_explicit_dict_output_port(
    node_defs_by_name: Dict[str, object],
    *,
    node_title: str,
    output_port_name: str,
) -> bool:
    """判断某节点的指定输出端口是否为“字典类型输出”（节点定义层明确声明）。"""
    node_def = node_defs_by_name.get(str(node_title))
    if node_def is None:
        return False
    output_types = getattr(node_def, "output_types", {}) or {}
    port_type = output_types.get(str(output_port_name), "")
    return isinstance(port_type, str) and ("字典" in port_type)


def _collect_explicit_dict_output_ports(
    node_defs_by_name: Dict[str, object],
    *,
    node_title: str,
) -> Set[str]:
    """收集某节点“明确声明为字典类型”的输出端口名集合。"""
    node_def = node_defs_by_name.get(str(node_title))
    if node_def is None:
        return set()
    output_types = getattr(node_def, "output_types", {}) or {}
    output_names = getattr(node_def, "outputs", []) or []
    dict_ports: Set[str] = set()
    for output_port_name in list(output_names):
        port_type = output_types.get(output_port_name, "")
        if isinstance(port_type, str) and ("字典" in port_type):
            dict_ports.add(str(output_port_name))
    return dict_ports


class DictComputeMultiUseHazardRule(ValidationRule):
    """字典来自“计算节点”且被多处消费时的风险提示（warning）。

    背景：
    - 一些离线/简化执行器采用 pull 语义：下游需要数据时可能会回溯并重复求值上游计算节点；
    - 若字典来源于“计算节点的字典输出”，并被多个下游节点消费，则在无缓存的 pull 执行器中，
      可能导致每次使用到的 dict 不是同一个引用。

    说明：
    - 这在“只读使用”场景下通常不会改变语义，但一旦对该字典做原地修改并期望后续继续使用，
      就会出现“写回无效”的问题；
    - 局部变量禁止字典类型，无法作为缓存承载；若需要稳定引用/写回语义，应改为节点图变量。
    """

    rule_id = "engine_code_dict_compute_multi_use_hazard"
    category = "代码规范"
    default_level = "warning"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        graph_model = _get_or_parse_graph_model(ctx)
        if graph_model is None:
            return []

        scope = infer_graph_scope(ctx)
        node_defs_by_name = callable_node_defs_by_name(ctx.workspace_path, scope)

        dict_ports_by_title: Dict[str, Set[str]] = {}
        consumers_by_source: Dict[Tuple[str, str], Set[str]] = {}

        for edge in graph_model.edges.values():
            dst_port = str(getattr(edge, "dst_port", "") or "")
            if is_flow_port_name(dst_port):
                continue

            raw_src_node_id = str(getattr(edge, "src_node", "") or "")
            src_port = str(getattr(edge, "src_port", "") or "")
            raw_dst_node_id = str(getattr(edge, "dst_node", "") or "")
            if not raw_src_node_id or not raw_dst_node_id or not src_port:
                continue

            src_node_id = _canonicalize_node_id(graph_model, raw_src_node_id)
            src_node = graph_model.nodes.get(src_node_id)
            if src_node is None:
                continue
            src_category = str(getattr(src_node, "category", "") or "")
            if ("查询" not in src_category) and ("运算" not in src_category):
                continue

            src_title = str(getattr(src_node, "title", "") or "")
            dict_ports = dict_ports_by_title.get(src_title)
            if dict_ports is None:
                dict_ports = _collect_explicit_dict_output_ports(node_defs_by_name, node_title=src_title)
                dict_ports_by_title[src_title] = dict_ports
            if src_port not in dict_ports:
                continue

            dst_node_id = _canonicalize_node_id(graph_model, raw_dst_node_id)
            consumers_by_source.setdefault((src_node_id, src_port), set()).add(dst_node_id)

        issues: List[EngineIssue] = []
        for (src_node_id, src_port), consumer_node_ids in consumers_by_source.items():
            if len(consumer_node_ids) < 2:
                continue

            src_node = graph_model.nodes.get(src_node_id)
            if src_node is None:
                continue

            consumer_titles: List[str] = []
            for consumer_id in sorted(consumer_node_ids):
                consumer_node = graph_model.nodes.get(consumer_id)
                consumer_titles.append(consumer_node.title if consumer_node else consumer_id)
            consumer_display = "、".join(consumer_titles[:6])
            if len(consumer_titles) > 6:
                consumer_display += "…"

            span = _span_for_graph_nodes(
                graph_model,
                [src_node_id, *list(sorted(consumer_node_ids))[:2]],
            )

            issues.append(
                EngineIssue(
                    level=self.default_level,
                    category=self.category,
                    code="CODE_DICT_COMPUTE_MULTI_USE",
                    message=(
                        "检测到字典来源于计算节点的字典输出并被多处使用；在无缓存的拉取式执行器中可能发生重复求值，"
                        "导致每次使用到的 dict 不是同一个引用，从而无法实现“原地修改后继续使用”的写回语义。\n"
                        f"- 字典来源: {src_node.title}.{src_port}\n"
                        f"- 消费节点: {consumer_display}\n"
                        "建议：若需要稳定引用/写回语义，请将该字典改为【节点图变量】承载（GRAPH_VARIABLES + 设置/获取节点图变量）；"
                        "局部变量禁止字典类型，无法用于缓存。"
                    ),
                    file=str(ctx.file_path),
                    line_span=span,
                    detail={
                        "dict_source_node_id": src_node_id,
                        "dict_source_port": src_port,
                        "consumer_node_ids": list(sorted(consumer_node_ids)),
                    },
                )
            )

        return issues


class DictMutationRequiresGraphVarRule(ValidationRule):
    """字典“写回/可变引用”语义约束（error）。

    背景：
    - 字典构造类运算节点（例如【拼装字典】/【建立字典】）返回的是一个新的 Python dict；
    - 在当前节点图生成与部分执行器语义下，运算节点输出可能被重复求值或被复制为多个数据节点副本；
      若对该字典进行原地修改后仍在后续流程中继续使用“同一字典来源”，则容易出现：
        - 写回无效：后续读取到的是重新构造的初始字典，而非已修改结果。

    约束：
    - 【获取局部变量】明确禁止字典类型（含别名字典与泛型字典），无法作为缓存/落盘手段；
    - 若确实需要“修改后被后续继续使用”的字典，应使用【节点图变量】承载（或其他可持久化容器）。
    """

    rule_id = "engine_code_dict_mutation_requires_graph_var"
    category = "代码规范"
    default_level = "error"

    _DICT_MUTATION_NODE_TITLES: Set[str] = {
        "对字典设置或新增键值对",
        "以键对字典移除键值对",
        "清空字典",
    }

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        graph_model = _get_or_parse_graph_model(ctx)
        if graph_model is None:
            return []

        scope = infer_graph_scope(ctx)
        node_defs_by_name = callable_node_defs_by_name(ctx.workspace_path, scope)

        # 快速失败：没有“字典修改执行节点”则无需分析
        if not any(n.title in self._DICT_MUTATION_NODE_TITLES for n in graph_model.nodes.values()):
            return []

        incoming_data_edges = _build_incoming_data_edge_index(graph_model)
        flow_next_map = _build_flow_next_index(graph_model)
        data_closure_cache: Dict[str, Set[str]] = {}

        def _collect_data_upstream(node_id: str) -> Set[str]:
            cached = data_closure_cache.get(node_id)
            if cached is not None:
                return cached
            raw_visited: Set[str] = set()
            canonical_visited: Set[str] = set()
            stack: List[str] = [node_id]
            while stack:
                current = stack.pop()
                incoming = incoming_data_edges.get(current, {})
                for edge in incoming.values():
                    src_node = str(getattr(edge, "src_node", "") or "")
                    if not src_node or src_node in raw_visited:
                        continue
                    raw_visited.add(src_node)
                    canonical_visited.add(_canonicalize_node_id(graph_model, src_node))
                    stack.append(src_node)
            data_closure_cache[node_id] = canonical_visited
            return canonical_visited

        issues: List[EngineIssue] = []

        for mutation_node in graph_model.nodes.values():
            if mutation_node.title not in self._DICT_MUTATION_NODE_TITLES:
                continue

            dict_edge = incoming_data_edges.get(mutation_node.id, {}).get("字典")
            if dict_edge is None:
                continue

            raw_src_node_id = str(getattr(dict_edge, "src_node", "") or "")
            if not raw_src_node_id:
                continue
            dict_source_output_port = str(getattr(dict_edge, "src_port", "") or "")
            if not dict_source_output_port:
                continue

            dict_source_node_id = _canonicalize_node_id(graph_model, raw_src_node_id)
            dict_source_node = graph_model.nodes.get(dict_source_node_id)
            if dict_source_node is None:
                continue

            # 仅处理“节点定义层明确声明为字典类型输出”的来源，避免把泛型输出（如节点图变量/自定义变量）
            # 误判为“每次返回新 dict”的计算结果来源。
            if not _is_explicit_dict_output_port(
                node_defs_by_name,
                node_title=dict_source_node.title,
                output_port_name=dict_source_output_port,
            ):
                continue

            downstream_flow_nodes = _collect_downstream_flow_nodes(flow_next_map, mutation_node.id)
            if not downstream_flow_nodes:
                continue

            affected_downstream: List[str] = []
            for flow_node_id in downstream_flow_nodes:
                deps = _collect_data_upstream(flow_node_id)
                if dict_source_node_id in deps:
                    affected_downstream.append(flow_node_id)

            if not affected_downstream:
                continue

            downstream_titles: List[str] = []
            for node_id in affected_downstream:
                node = graph_model.nodes.get(node_id)
                title = node.title if node else node_id
                if title not in downstream_titles:
                    downstream_titles.append(title)
            downstream_titles_display = "、".join(downstream_titles[:6])
            if len(downstream_titles) > 6:
                downstream_titles_display += "…"

            span = _span_for_graph_nodes(
                graph_model,
                [mutation_node.id, dict_source_node_id, *affected_downstream[:3]],
            )
            issues.append(
                EngineIssue(
                    level=self.default_level,
                    category=self.category,
                    code="CODE_DICT_MUTATION_REQUIRES_GRAPH_VAR",
                    message=(
                        "检测到字典被『原地修改后仍在后续流程中继续使用』，但该字典来源于运算节点产生的计算结果，"
                        "无法保证引用写回语义。\n"
                        f"- 修改节点: {mutation_node.title}\n"
                        f"- 字典来源: {dict_source_node.title}.{dict_source_output_port}\n"
                        f"- 可能受影响的后续流程节点: {downstream_titles_display}\n"
                        "原因：该字典来源于计算节点的字典输出；在当前节点图生成/执行语义下，后续使用可能会重复求值并返回新的 dict，"
                        "从而导致写回无效。\n"
                        "修复建议：局部变量禁止字典类型，无法用【获取局部变量】缓存；请将该字典改为【节点图变量】："
                        "在 GRAPH_VARIABLES 中声明字典变量，用【设置节点图变量】保存初始值/更新，"
                        "并用【获取节点图变量】读取后再进行字典修改。"
                    ),
                    file=str(ctx.file_path),
                    line_span=span,
                    detail={
                        "mutation_node_id": mutation_node.id,
                        "dict_source_node_id": dict_source_node_id,
                        "affected_flow_node_ids": list(affected_downstream),
                    },
                )
            )

        return issues













