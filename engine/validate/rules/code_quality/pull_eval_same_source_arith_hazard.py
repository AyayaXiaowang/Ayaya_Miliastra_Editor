"""拉取式执行器的“同源算术运算风险”提示规则（warning）。

背景：
- 一些离线/简化执行器采用 pull 语义：下游需要数据时会回溯求值上游节点；
- 若同一自定义变量的读取（同目标实体+同变量名）在同一算术节点中被读取两次并分别接到“左值/右值”，
  则在无 memoization 的 pull 执行器中很容易退化为“同一时刻读取两次当前值”，表现为 X-X=0、
  或其它看似“同源运算”的异常。

本规则只做最常见、最可静态识别的提示：
- 算术节点：加减乘除（左值/右值）；
- 左/右输入各来自一个【获取自定义变量】节点；
- 两个读取节点指向同一个 (目标实体来源, 变量名来源)。

说明：
- 这是 warning：严格语义应由执行器提供“同一 node_id 单次事件流只求值一次”的输出缓存；
  在缓存尚未就绪时，本规则可以提前提醒作者规避该结构。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from engine.graph.common import TARGET_ENTITY_PORT_NAME, VARIABLE_NAME_PORT_NAME
from engine.validate.node_semantics import SEMANTIC_CUSTOM_VAR_GET

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import infer_graph_scope
from ..node_index import callable_node_defs_by_name
from .graph_model_utils import (
    _build_incoming_data_edge_index,
    _canonicalize_node_id,
    _custom_var_key,
    _describe_input_source,
    _get_or_parse_graph_model,
    _span_for_graph_nodes,
)


class PullEvalSameSourceArithmeticHazardRule(ValidationRule):
    """拉取式执行器的“同源算术运算风险”提示（warning）。"""

    rule_id = "engine_code_pull_eval_same_source_arith_hazard"
    category = "代码规范"
    default_level = "warning"

    _CUSTOM_VAR_READ_SEMANTIC_ID = SEMANTIC_CUSTOM_VAR_GET

    # 仅覆盖最常见的二元算术节点（统一端口名：左值/右值）
    _ARITH_NODE_TITLES: Set[str] = {"加法运算", "减法运算", "乘法运算", "除法运算"}
    _LEFT_PORT: str = "左值"
    _RIGHT_PORT: str = "右值"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        graph_model = _get_or_parse_graph_model(ctx)
        if graph_model is None:
            return []

        # 快速失败：没有算术节点则无需分析
        if not any(str(getattr(n, "title", "") or "") in self._ARITH_NODE_TITLES for n in graph_model.nodes.values()):
            return []

        scope = infer_graph_scope(ctx)
        node_defs_by_name = callable_node_defs_by_name(ctx.workspace_path, scope, include_composite=False)

        def _is_custom_var_read_node_title(node_title: str) -> bool:
            node_def = node_defs_by_name.get(str(node_title or ""))
            return str(getattr(node_def, "semantic_id", "") or "").strip() == self._CUSTOM_VAR_READ_SEMANTIC_ID

        incoming_data_edges = _build_incoming_data_edge_index(graph_model)

        issues: List[EngineIssue] = []

        for arith_node in graph_model.nodes.values():
            if str(getattr(arith_node, "title", "") or "") not in self._ARITH_NODE_TITLES:
                continue

            left_edge = incoming_data_edges.get(arith_node.id, {}).get(self._LEFT_PORT)
            right_edge = incoming_data_edges.get(arith_node.id, {}).get(self._RIGHT_PORT)
            if left_edge is None or right_edge is None:
                continue

            raw_left_src = str(getattr(left_edge, "src_node", "") or "")
            raw_right_src = str(getattr(right_edge, "src_node", "") or "")
            if not raw_left_src or not raw_right_src:
                continue

            left_src_id = _canonicalize_node_id(graph_model, raw_left_src)
            right_src_id = _canonicalize_node_id(graph_model, raw_right_src)

            left_src = graph_model.nodes.get(left_src_id)
            right_src = graph_model.nodes.get(right_src_id)
            if left_src is None or right_src is None:
                continue

            if not _is_custom_var_read_node_title(str(getattr(left_src, "title", "") or "")):
                continue
            if not _is_custom_var_read_node_title(str(getattr(right_src, "title", "") or "")):
                continue

            left_key = _custom_var_key(graph_model, incoming_data_edges, left_src_id)
            right_key = _custom_var_key(graph_model, incoming_data_edges, right_src_id)
            if left_key is None or right_key is None:
                continue
            if left_key != right_key:
                continue

            # 描述读节点的(目标实体, 变量名)来源，便于定位
            entity_desc, _ = _describe_input_source(
                graph_model, incoming_data_edges, left_src_id, TARGET_ENTITY_PORT_NAME
            )
            var_desc, _ = _describe_input_source(
                graph_model, incoming_data_edges, left_src_id, VARIABLE_NAME_PORT_NAME
            )

            span = _span_for_graph_nodes(graph_model, [arith_node.id, left_src_id, right_src_id])
            issues.append(
                EngineIssue(
                    level=self.default_level,
                    category=self.category,
                    code="CODE_PULL_EVAL_SAME_SOURCE_ARITH",
                    message=(
                        "检测到同一自定义变量读取被同时接入同一个算术节点的左右输入；在无缓存的拉取式执行器中可能退化为“同源运算”(例如 X-X=0)。\n"
                        f"- 算术节点: {arith_node.title}\n"
                        f"- 目标实体来源: {entity_desc}\n"
                        f"- 变量名来源: {var_desc}\n"
                        "建议：对读取结果做显式快照（例如使用【获取局部变量】中继并在后续复用快照值），"
                        "或直接按业务规则计算 delta（避免依赖两次读取相减）。更推荐在执行器层实现"
                        "『同一 node_id 在单次事件流内只求值一次』的输出缓存语义。"
                    ),
                    file=str(ctx.file_path),
                    line_span=span,
                    detail={
                        "arith_node_id": arith_node.id,
                        "left_read_node_id": left_src_id,
                        "right_read_node_id": right_src_id,
                        "entity_source": entity_desc,
                        "var_name_source": var_desc,
                    },
                )
            )

        return issues

