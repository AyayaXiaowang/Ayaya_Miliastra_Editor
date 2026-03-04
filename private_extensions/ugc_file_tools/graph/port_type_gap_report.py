from __future__ import annotations

"""
GraphModel payload 的“端口类型缺口”报告（纯逻辑）。

定位：
- 供 `.gia` 导出与 `.gil` 写回等链路在落盘前输出诊断信息；
- 报告仅描述“哪些端口仍为泛型/证据不足”，不做 I/O，不参与具体写回策略。
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from engine.graph.port_type_effective_resolver import is_generic_type_name
from engine.type_registry import parse_typed_dict_alias


@dataclass(frozen=True, slots=True)
class PortTypeGapItem:
    severity: str  # "error" | "warn"
    node_id: str
    node_title: str
    node_category: str
    node_def_ref: Dict[str, str] | None
    event_mapping: Dict[str, str] | None
    port_name: str
    is_input: bool
    declared_type_text: str
    effective_type_text: str
    evidence_source: str  # "port_types"
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": str(self.severity),
            "node_id": str(self.node_id),
            "node_title": str(self.node_title),
            "node_category": str(self.node_category),
            "node_def_ref": dict(self.node_def_ref) if isinstance(self.node_def_ref, dict) else None,
            "event_mapping": dict(self.event_mapping) if isinstance(self.event_mapping, dict) else None,
            "port_name": str(self.port_name),
            "is_input": bool(self.is_input),
            "declared_type_text": str(self.declared_type_text),
            "effective_type_text": str(self.effective_type_text),
            "evidence_source": str(self.evidence_source),
            "reason": str(self.reason),
        }


def _get_type_text(
    node_payload: Mapping[str, Any],
    port_name: str,
    *,
    is_input: bool,
    prefer_effective: bool,
) -> str:
    key = ("input_port_types" if bool(is_input) else "output_port_types") if bool(prefer_effective) else (
        "input_port_declared_types" if bool(is_input) else "output_port_declared_types"
    )
    mapping = node_payload.get(key)
    if isinstance(mapping, Mapping):
        raw = mapping.get(str(port_name))
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


def build_port_type_gap_report(
    *,
    graph_model_payload: Mapping[str, Any],
    graph_scope: str,
    graph_name: str,
    graph_id_int: int | None,
) -> Dict[str, Any]:
    """
    生成 GraphModel payload 的“端口类型缺口”报告。

    约定：
    - 只依赖 payload 内的 `input_port_types/output_port_types` 与 `*_declared_types`；
    - 主要输出“仍为泛型家族”的端口；并对少量高风险节点给出 error 分级。
    """
    scope = str(graph_scope or "").strip().lower() or "server"
    name = str(graph_name or "").strip()
    gid = int(graph_id_int) if isinstance(graph_id_int, int) else None

    nodes = graph_model_payload.get("nodes")
    if not isinstance(nodes, list):
        nodes = []

    # fail-fast 分级：字典原地修改节点的 “字典/键/值” 必须能解析出别名字典(K/V)。
    dict_mutation_titles = {
        "对字典设置或新增键值对",
        "以键对字典移除键值对",
        "清空字典",
        "对字典修改键值对",
    }

    items: List[PortTypeGapItem] = []
    for node in list(nodes):
        if not isinstance(node, Mapping):
            continue
        node_id = str(node.get("id") or "").strip()
        title = str(node.get("title") or "").strip()
        category = str(node.get("category") or "").strip()
        node_def_ref = node.get("node_def_ref")
        node_def_ref_dict: Optional[Dict[str, str]] = None
        if isinstance(node_def_ref, Mapping):
            kind = str(node_def_ref.get("kind") or "").strip()
            key = str(node_def_ref.get("key") or "").strip()
            if kind and key:
                node_def_ref_dict = {"kind": kind, "key": key}
        event_mapping: Optional[Dict[str, str]] = None
        if node_def_ref_dict is not None and str(node_def_ref_dict.get("kind") or "") == "event":
            mapped_builtin_key = f"{category}/{title}" if (category and title) else ""
            event_mapping = {
                "event_key": str(node_def_ref_dict.get("key") or ""),
                "mapped_builtin_key": str(mapped_builtin_key),
            }

        # inputs
        for port in list(node.get("inputs") if isinstance(node.get("inputs"), list) else []):
            port_name = str(port or "").strip()
            if not port_name:
                continue
            declared = _get_type_text(node, port_name, is_input=True, prefer_effective=False)
            effective = _get_type_text(node, port_name, is_input=True, prefer_effective=True)
            if effective == "":
                continue
            if effective == "流程":
                continue
            if not is_generic_type_name(effective):
                continue
            severity = "warn"
            evidence_source = "port_types"
            reason = "effective_type_is_generic_family"
            # 高风险：字典原地修改节点的 字典/键/值 不能停留在泛型/泛型字典
            if title in dict_mutation_titles and port_name in {"字典", "键", "值"}:
                if port_name == "字典":
                    ok, _k, _v = parse_typed_dict_alias(str(effective))
                    if not bool(ok):
                        severity = "error"
                        reason = "dict_mutation_requires_typed_dict_alias"
                else:
                    severity = "error"
                    reason = "dict_mutation_requires_resolved_kv_ports"
            # 高风险：节点图变量 Get/Set 的 变量值 若仍为泛型家族，导出/写回很容易退化为字符串
            if title in {"获取节点图变量", "设置节点图变量"} and port_name == "变量值":
                severity = "error"
                reason = "graph_variable_value_requires_concrete_type"
            items.append(
                PortTypeGapItem(
                    severity=severity,
                    node_id=node_id,
                    node_title=title,
                    node_category=category,
                    node_def_ref=node_def_ref_dict,
                    event_mapping=event_mapping,
                    port_name=port_name,
                    is_input=True,
                    declared_type_text=str(declared),
                    effective_type_text=str(effective),
                    evidence_source=str(evidence_source),
                    reason=str(reason),
                )
            )

        # outputs
        for port in list(node.get("outputs") if isinstance(node.get("outputs"), list) else []):
            port_name = str(port or "").strip()
            if not port_name:
                continue
            declared = _get_type_text(node, port_name, is_input=False, prefer_effective=False)
            effective = _get_type_text(node, port_name, is_input=False, prefer_effective=True)
            if effective == "":
                continue
            if effective == "流程":
                continue
            if not is_generic_type_name(effective):
                continue
            severity = "warn"
            evidence_source = "port_types"
            reason = "effective_type_is_generic_family"
            if title in {"获取节点图变量", "设置节点图变量"} and port_name == "变量值":
                severity = "error"
                reason = "graph_variable_value_requires_concrete_type"
            items.append(
                PortTypeGapItem(
                    severity=severity,
                    node_id=node_id,
                    node_title=title,
                    node_category=category,
                    node_def_ref=node_def_ref_dict,
                    event_mapping=event_mapping,
                    port_name=port_name,
                    is_input=False,
                    declared_type_text=str(declared),
                    effective_type_text=str(effective),
                    evidence_source=str(evidence_source),
                    reason=str(reason),
                )
            )

    error_count = sum(1 for x in items if x.severity == "error")
    warn_count = sum(1 for x in items if x.severity == "warn")

    return {
        "schema": "ugc.port_type_gap_report.v1",
        "graph_scope": scope,
        "graph_name": name,
        "graph_id_int": gid,
        "counts": {"errors": int(error_count), "warnings": int(warn_count), "total": int(len(items))},
        "items": [it.to_dict() for it in items],
    }


__all__ = [
    "PortTypeGapItem",
    "build_port_type_gap_report",
]

