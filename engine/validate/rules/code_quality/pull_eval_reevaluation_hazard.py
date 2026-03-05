"""拉取式执行器的“重复求值风险”提示规则（warning）。"""

from __future__ import annotations

from typing import Dict, List, Set

from engine.graph.common import TARGET_ENTITY_PORT_NAME, VARIABLE_NAME_PORT_NAME
from engine.validate.node_semantics import SEMANTIC_CUSTOM_VAR_GET, SEMANTIC_CUSTOM_VAR_SET

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import infer_graph_scope
from ..node_index import callable_node_defs_by_name
from .graph_model_utils import (
    _build_incoming_data_edge_index,
    _build_flow_next_index,
    _canonicalize_node_id,
    _collect_downstream_flow_nodes,
    _custom_var_key,
    _describe_input_source,
    _get_or_parse_graph_model,
    _span_for_graph_nodes,
)


class PullEvalReevaluationHazardRule(ValidationRule):
    """拉取式执行器的“重复求值风险”提示（warning）。

    背景：
    - 一些离线/简化执行器采用 pull 语义：当某个节点需要数据输入时，会沿数据边回溯求值上游节点；
    - 若同一个【获取自定义变量】节点实例同时参与“读-改-写”，并在写入后仍被后续流程节点间接依赖，
      则在无 memoization 的 pull 执行器中可能出现：
        1) 条件/数值偏移（典型：条件用到了“写入后的新值再 +1”的结果）
        2) 非确定性（随机/时间类读取被重复触发）

    本规则专注于最常见、最可静态识别的坑：
    - 【设置自定义变量】在写入某个 (目标实体, 变量名) 之前，其“变量值”数据链路中读取了同一个
      (目标实体, 变量名) 的【获取自定义变量】；
    - 且写入之后沿流程边可达的后续流程节点仍然依赖这同一个【获取自定义变量】节点实例（node_id 相同）。

    说明：
    - 这是 warning：更推荐从“执行器语义”层面提供节点输出缓存（同一 node_id 在单次事件流内只计算一次），
      但在缓存尚未就绪时，本规则可以提前提醒作者规避。
    """

    rule_id = "engine_code_pull_eval_reevaluation_hazard"
    category = "代码规范"
    default_level = "warning"

    _CUSTOM_VAR_READ_SEMANTIC_ID = SEMANTIC_CUSTOM_VAR_GET
    _CUSTOM_VAR_WRITE_SEMANTIC_ID = SEMANTIC_CUSTOM_VAR_SET

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        graph_model = _get_or_parse_graph_model(ctx)
        if graph_model is None:
            return []

        scope = infer_graph_scope(ctx)
        node_defs_by_name = callable_node_defs_by_name(ctx.workspace_path, scope, include_composite=False)

        def _is_custom_var_read_node_title(node_title: str) -> bool:
            node_def = node_defs_by_name.get(str(node_title or ""))
            return str(getattr(node_def, "semantic_id", "") or "").strip() == self._CUSTOM_VAR_READ_SEMANTIC_ID

        def _is_custom_var_write_node_title(node_title: str) -> bool:
            node_def = node_defs_by_name.get(str(node_title or ""))
            return str(getattr(node_def, "semantic_id", "") or "").strip() == self._CUSTOM_VAR_WRITE_SEMANTIC_ID

        # 快速失败：没有“设置自定义变量”则无需分析
        if not any(_is_custom_var_write_node_title(n.title) for n in graph_model.nodes.values()):
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

        for write_node in graph_model.nodes.values():
            if not _is_custom_var_write_node_title(write_node.title):
                continue

            write_key = _custom_var_key(graph_model, incoming_data_edges, write_node.id)
            if write_key is None:
                continue

            # 识别“读-改-写同一变量”的读取节点实例（必须出现在写入节点的数据依赖闭包中）
            read_node_ids: List[str] = []
            for upstream_node_id in _collect_data_upstream(write_node.id):
                upstream_node = graph_model.nodes.get(upstream_node_id)
                if upstream_node is None:
                    continue
                if not _is_custom_var_read_node_title(upstream_node.title):
                    continue
                read_key = _custom_var_key(graph_model, incoming_data_edges, upstream_node_id)
                if read_key is None:
                    continue
                if read_key == write_key:
                    read_node_ids.append(upstream_node_id)

            if not read_node_ids:
                continue

            downstream_flow_nodes = _collect_downstream_flow_nodes(flow_next_map, write_node.id)
            if not downstream_flow_nodes:
                continue

            hazard_pairs: Dict[str, List[str]] = {}
            for flow_node_id in downstream_flow_nodes:
                data_dependencies = _collect_data_upstream(flow_node_id)
                for read_id in read_node_ids:
                    if read_id in data_dependencies:
                        hazard_pairs.setdefault(read_id, []).append(flow_node_id)

            if not hazard_pairs:
                continue

            # 描述目标实体/变量名的数据来源，便于定位
            entity_desc, _ = _describe_input_source(graph_model, incoming_data_edges, write_node.id, TARGET_ENTITY_PORT_NAME)
            var_desc, _ = _describe_input_source(graph_model, incoming_data_edges, write_node.id, VARIABLE_NAME_PORT_NAME)

            read_titles: List[str] = []
            for read_id in sorted(hazard_pairs.keys()):
                read_node = graph_model.nodes.get(read_id)
                read_titles.append(f"{read_node.title if read_node else read_id}")

            downstream_titles: List[str] = []
            for read_id in sorted(hazard_pairs.keys()):
                dst_ids = hazard_pairs.get(read_id, [])
                for dst_id in dst_ids:
                    dst_node = graph_model.nodes.get(dst_id)
                    dst_title = dst_node.title if dst_node else dst_id
                    if dst_title not in downstream_titles:
                        downstream_titles.append(dst_title)
            downstream_titles_display = "、".join(downstream_titles[:6])
            if len(downstream_titles) > 6:
                downstream_titles_display += "…"

            span = _span_for_graph_nodes(graph_model, [write_node.id, *hazard_pairs.keys()])
            issues.append(
                EngineIssue(
                    level=self.default_level,
                    category=self.category,
                    code="CODE_PULL_EVAL_REEVAL_AFTER_WRITE",
                    message=(
                        "检测到『读-改-写同一自定义变量』后，后续流程节点仍依赖同一个【获取自定义变量】节点实例；"
                        "在无缓存的拉取式执行器中可能发生重复求值，导致条件/数值偏移。\n"
                        f"- 写入节点: {write_node.title}\n"
                        f"- 目标实体来源: {entity_desc}\n"
                        f"- 变量名来源: {var_desc}\n"
                        f"- 复用读取节点: {'、'.join(read_titles)}\n"
                        f"- 可能受影响的后续流程节点: {downstream_titles_display}\n"
                        "建议：为该读取链路做显式缓存（【获取局部变量】中继/拆分读取节点），"
                        "或在图结构上采用“先判定分支、再写入变量”的顺序；更推荐在执行器层实现"
                        "『同一 node_id 在单次事件流内只求值一次』的输出缓存语义。"
                    ),
                    file=str(ctx.file_path),
                    line_span=span,
                    detail={
                        "write_node_id": write_node.id,
                        "read_node_ids": list(sorted(hazard_pairs.keys())),
                        "downstream_flow_node_ids": list(sorted({i for ids in hazard_pairs.values() for i in ids})),
                        "entity_source": entity_desc,
                        "var_name_source": var_desc,
                    },
                )
            )

        return issues













