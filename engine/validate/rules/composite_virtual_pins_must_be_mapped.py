from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from engine.graph import deserialize_graph
from engine.graph.composite_code_parser import CompositeCodeParser
from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.node_registry import get_node_registry
from engine.utils.graph.graph_utils import is_flow_port_name

from ..context import ValidationContext
from ..issue import EngineIssue
from ..pipeline import ValidationRule


def _get_or_parse_composite_config(
    ctx: ValidationContext,
    *,
    node_library: Dict[str, NodeDef],
) -> Any:
    cached = getattr(ctx, "composite_config", None)
    if cached is not None:
        return cached
    if ctx.file_path is None:
        return None
    parser = CompositeCodeParser(
        node_library=node_library,
        verbose=False,
        workspace_path=ctx.workspace_path,
    )
    composite = parser.parse_file(ctx.file_path)
    ctx.composite_config = composite
    return composite


def _mapped_nodes_for_pin(pin: object) -> Set[str]:
    out: Set[str] = set()
    for mapped in list(getattr(pin, "mapped_ports", []) or []):
        node_id = str(getattr(mapped, "node_id", "") or "").strip()
        if node_id:
            out.add(node_id)
    return out


def _flow_adjacency_from_edges(edges: Iterable[object]) -> Dict[str, List[str]]:
    next_map: Dict[str, List[str]] = {}
    for edge in list(edges or []):
        src_node = str(getattr(edge, "src_node", "") or "").strip()
        dst_node = str(getattr(edge, "dst_node", "") or "").strip()
        dst_port = str(getattr(edge, "dst_port", "") or "").strip()
        if not src_node or not dst_node:
            continue
        if not is_flow_port_name(dst_port):
            continue
        next_map.setdefault(src_node, []).append(dst_node)
    return next_map


def _reachable_nodes(flow_next: Dict[str, List[str]], start_nodes: Sequence[str]) -> Set[str]:
    visited: Set[str] = set()
    queue: deque[str] = deque()
    for node_id in start_nodes:
        n = str(node_id or "").strip()
        if not n or n in visited:
            continue
        visited.add(n)
        queue.append(n)
    while queue:
        current = queue.popleft()
        for nxt in flow_next.get(current, []):
            if nxt in visited:
                continue
            visited.add(nxt)
            queue.append(nxt)
    return visited


class CompositeVirtualPinsMustBeMappedRule(ValidationRule):
    """复合节点：虚拟引脚必须可映射到子图端口（禁止“声明了但未使用”的悬空引脚）。"""

    rule_id = "engine_composite_virtual_pins_must_be_mapped"
    category = "复合节点"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if (not ctx.is_composite) or ctx.file_path is None:
            return []

        node_library = getattr(ctx, "node_library", None)
        if not isinstance(node_library, dict) or not node_library:
            registry = get_node_registry(ctx.workspace_path, include_composite=True)
            node_library = registry.get_library()
            ctx.node_library = node_library

        composite = _get_or_parse_composite_config(ctx, node_library=dict(node_library))
        if composite is None:
            return []

        file_text = str(Path(ctx.file_path).resolve())
        composite_id = str(getattr(composite, "composite_id", "") or "").strip()
        node_name = str(getattr(composite, "node_name", "") or "").strip()
        issues: List[EngineIssue] = []
        for pin in list(getattr(composite, "virtual_pins", []) or []):
            mapped_ports = list(getattr(pin, "mapped_ports", []) or [])
            allow_unmapped = bool(getattr(pin, "allow_unmapped", False))
            if mapped_ports or allow_unmapped:
                continue
            pin_name = str(getattr(pin, "pin_name", "") or "").strip()
            pin_type = str(getattr(pin, "pin_type", "") or "").strip()
            direction = "输入" if bool(getattr(pin, "is_input", False)) else "输出"
            kind = "流程" if bool(getattr(pin, "is_flow", False)) else "数据"
            pin_index = getattr(pin, "pin_index", "?")
            issues.append(
                EngineIssue(
                    level=self.default_level,
                    category=self.category,
                    code="COMPOSITE_VIRTUAL_PIN_UNMAPPED",
                    message=(
                        "复合节点虚拟引脚未映射到任何子图端口（mapped_ports=0）。\n"
                        f"- 复合节点：composite_id={composite_id!r} node_name={node_name!r}\n"
                        f"- 引脚：{direction}{kind} pin_index={pin_index} name={pin_name!r} type={pin_type!r}\n"
                        "这通常表示该形参/返回值在方法体内从未被节点消费（或被 IR 裁剪），导致 UI/导出/写回侧看起来“缺引脚”。\n"
                        "修复建议：让该引脚参与至少一个节点调用/赋值（形成可建模的数据/流程依赖），"
                        "或显式移除该引脚声明；若确实仅用于控制流条件，请设置 allow_unmapped=True 并确保有对应控制流证据。"
                    ),
                    file=file_text,
                    detail={
                        "composite_id": composite_id,
                        "node_name": node_name,
                        "pin_index": pin_index,
                        "pin_name": pin_name,
                        "pin_type": pin_type,
                        "pin_direction": direction,
                        "pin_kind": kind,
                    },
                )
            )
        return issues


class CompositeFlowPinReachabilityRule(ValidationRule):
    """复合节点：存在流程入/流程出时，流程出必须从某个流程入可达（支持分支/循环）。"""

    rule_id = "engine_composite_flow_pin_reachability"
    category = "复合节点"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if (not ctx.is_composite) or ctx.file_path is None:
            return []

        node_library = getattr(ctx, "node_library", None)
        if not isinstance(node_library, dict) or not node_library:
            registry = get_node_registry(ctx.workspace_path, include_composite=True)
            node_library = registry.get_library()
            ctx.node_library = node_library

        composite = _get_or_parse_composite_config(ctx, node_library=dict(node_library))
        if composite is None:
            return []

        composite_id = str(getattr(composite, "composite_id", "") or "").strip()
        node_name = str(getattr(composite, "node_name", "") or "").strip()
        sub_graph = getattr(composite, "sub_graph", None)
        if not isinstance(sub_graph, dict):
            return []
        model = deserialize_graph(sub_graph)

        flow_in_nodes: Set[str] = set()
        flow_out_nodes: Set[str] = set()
        for pin in list(getattr(composite, "virtual_pins", []) or []):
            if not bool(getattr(pin, "is_flow", False)):
                continue
            nodes = _mapped_nodes_for_pin(pin)
            if not nodes:
                continue
            if bool(getattr(pin, "is_input", False)):
                flow_in_nodes |= nodes
            else:
                flow_out_nodes |= nodes

        if (not flow_in_nodes) or (not flow_out_nodes):
            return []

        flow_next = _flow_adjacency_from_edges(list(getattr(model, "edges", {}).values() if hasattr(model, "edges") else []))
        reachable = _reachable_nodes(flow_next, sorted(flow_in_nodes))
        unreachable_out = sorted([n for n in flow_out_nodes if n not in reachable], key=lambda s: s.casefold())
        if not unreachable_out:
            return []

        file_text = str(Path(ctx.file_path).resolve())
        return [
            EngineIssue(
                level=self.default_level,
                category=self.category,
                code="COMPOSITE_FLOW_OUT_NOT_REACHABLE",
                message=(
                    "复合节点流程连通性校验失败：存在流程出引脚，但从任一流程入引脚出发不可达。\n"
                    f"- 复合节点：composite_id={composite_id!r} node_name={node_name!r}\n"
                    f"- 不可达的流程出锚点节点数：{len(unreachable_out)}\n"
                    "这通常意味着：方法体虽然声明了流程入/流程出，但内部流程边未正确连接（包括分支/循环合流错误）。\n"
                    "修复建议：确保流程从入口节点可通过流程边到达每个流程出口；"
                    "必要时在分支/循环末尾补齐合流/继续节点，避免出现“孤立出口”。"
                ),
                file=file_text,
                detail={
                    "composite_id": composite_id,
                    "node_name": node_name,
                    "unreachable_flow_out_nodes": unreachable_out,
                },
            )
        ]


__all__ = [
    "CompositeVirtualPinsMustBeMappedRule",
    "CompositeFlowPinReachabilityRule",
]

