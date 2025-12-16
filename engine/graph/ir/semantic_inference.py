from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Set

from engine.graph.models import GraphModel, NodeModel
from engine.graph.common import (
    SIGNAL_SEND_NODE_TITLE,
    SIGNAL_NAME_PORT_NAME,
    STRUCT_BUILD_NODE_TITLE,
    STRUCT_MODIFY_NODE_TITLE,
    STRUCT_SPLIT_NODE_TITLE,
    STRUCT_BUILD_STATIC_INPUTS,
    STRUCT_MODIFY_STATIC_INPUTS,
    STRUCT_NAME_PORT_NAME,
)
from .node_factory import FactoryContext


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _resolve_signal_id_from_literal(ctx: FactoryContext, literal: str) -> str:
    """将“信号名/信号ID 字面量”解析为稳定的 signal_id；失败则返回原文。"""
    text = _safe_text(literal)
    if not text:
        return text
    repo = getattr(ctx, "signal_repo", None)
    if repo is None:
        return text
    payload = repo.get_payload(text)
    if isinstance(payload, dict) and payload:
        return text
    resolved_by_name = repo.resolve_id_by_name(text)
    if resolved_by_name:
        return str(resolved_by_name)
    return text


def _try_infer_struct_id_and_fields(
    ctx: FactoryContext,
    *,
    struct_name: str,
    used_field_names: List[str],
) -> Optional[Dict[str, Any]]:
    """根据结构体名与使用字段列表推导 struct_bindings payload。"""
    name_text = _safe_text(struct_name)
    if not name_text:
        return None

    name_to_id = getattr(ctx, "struct_name_to_id", None)
    if not isinstance(name_to_id, dict) or not name_to_id:
        return None

    struct_id = name_to_id.get(name_text)
    if not struct_id:
        return None

    binding: Dict[str, Any] = {
        "struct_id": str(struct_id),
        "struct_name": name_text,
    }

    # 若提供字段列表，则按结构体定义过滤并保持出现顺序去重
    fields_by_id = getattr(ctx, "struct_fields_by_id", None)
    defined_fields: Set[str] = set()
    if isinstance(fields_by_id, dict):
        defined_list = fields_by_id.get(str(struct_id)) or []
        if isinstance(defined_list, list):
            for entry in defined_list:
                if isinstance(entry, str) and entry:
                    defined_fields.add(entry)

    if used_field_names:
        filtered: List[str] = []
        for name in used_field_names:
            name_text = _safe_text(name)
            if not name_text:
                continue
            if defined_fields and name_text not in defined_fields:
                continue
            if name_text not in filtered:
                filtered.append(name_text)
        if filtered:
            binding["field_names"] = filtered

    return binding


def apply_call_semantics(
    *,
    node: NodeModel,
    call_expr: ast.Call,
    graph_model: GraphModel,
    ctx: FactoryContext,
    assigned_names: Optional[List[str]] = None,
) -> None:
    """在“节点已确认要纳入图模型”后，推导并写入 GraphModel.metadata 的语义绑定。

    注意：本函数不会覆盖 UI/外部工具已经写入的绑定记录。
    """
    node_title = _safe_text(getattr(node, "title", ""))
    node_id = _safe_text(getattr(node, "id", ""))
    if not node_id or not node_title:
        return

    # 1) 发送信号节点：推导 signal_bindings（若未绑定）
    if node_title == SIGNAL_SEND_NODE_TITLE:
        existing_signal_id = graph_model.get_node_signal_id(node_id)
        if not existing_signal_id:
            literal = _safe_text((node.input_constants or {}).get(SIGNAL_NAME_PORT_NAME))
            resolved_id = _resolve_signal_id_from_literal(ctx, literal)
            if resolved_id and getattr(ctx, "signal_repo", None) is not None:
                payload = ctx.signal_repo.get_payload(resolved_id)
                if isinstance(payload, dict) and payload:
                    graph_model.set_node_signal_binding(node_id, resolved_id)
        return

    # 2) 结构体节点：推导 struct_bindings（若未绑定）
    if node_title not in (STRUCT_BUILD_NODE_TITLE, STRUCT_MODIFY_NODE_TITLE, STRUCT_SPLIT_NODE_TITLE):
        return

    existing_struct_binding = graph_model.get_node_struct_binding(node_id)
    if isinstance(existing_struct_binding, dict):
        return

    struct_name = _safe_text((node.input_constants or {}).get(STRUCT_NAME_PORT_NAME))
    used_fields: List[str] = []

    if node_title in (STRUCT_BUILD_NODE_TITLE, STRUCT_MODIFY_NODE_TITLE):
        static_inputs = (
            set(STRUCT_BUILD_STATIC_INPUTS)
            if node_title == STRUCT_BUILD_NODE_TITLE
            else set(STRUCT_MODIFY_STATIC_INPUTS)
        )
        for keyword in getattr(call_expr, "keywords", []) or []:
            key_name = keyword.arg
            if not isinstance(key_name, str) or not key_name:
                continue
            if key_name in static_inputs:
                continue
            if key_name not in used_fields:
                used_fields.append(key_name)
    elif node_title == STRUCT_SPLIT_NODE_TITLE:
        for name in assigned_names or []:
            if isinstance(name, str) and name.strip() and name.strip() not in used_fields:
                used_fields.append(name.strip())

    binding_payload = _try_infer_struct_id_and_fields(
        ctx,
        struct_name=struct_name,
        used_field_names=used_fields,
    )
    if binding_payload is not None:
        graph_model.set_node_struct_binding(node_id, binding_payload)


__all__ = ["apply_call_semantics"]


