from __future__ import annotations

from typing import Any, Dict, List

from ugc_file_tools.graph.model_ir import (
    normalize_edges_list as _normalize_edges_list_public,
    normalize_graph_model_payload as _normalize_graph_model_payload_public,
    normalize_nodes_list as _normalize_nodes_list_public,
)


def _normalize_graph_model_payload(graph_json_object: Dict[str, Any]) -> Dict[str, Any]:
    # 兼容 wrapper：内部实现已上移到 ugc_file_tools.graph.model_ir（稳定公共口径）。
    return _normalize_graph_model_payload_public(graph_json_object)


def _normalize_nodes_list(graph_model: Dict[str, Any]) -> List[Dict[str, Any]]:
    # 兼容 wrapper：内部实现已上移到 ugc_file_tools.graph.model_ir（稳定公共口径）。
    return _normalize_nodes_list_public(graph_model)


def _normalize_edges_list(graph_model: Dict[str, Any]) -> List[Dict[str, Any]]:
    # 兼容 wrapper：内部实现已上移到 ugc_file_tools.graph.model_ir（稳定公共口径）。
    return _normalize_edges_list_public(graph_model)


# ---------------------------------------------------------------------------
# Public API (no leading underscores)
#
# Import policy: cross-module imports must not import underscored private names.
# Keep underscored wrappers for compatibility, but expose stable public names.


def normalize_graph_model_payload(graph_json_object: Dict[str, Any]) -> Dict[str, Any]:
    return _normalize_graph_model_payload(graph_json_object)


def normalize_nodes_list(graph_model: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _normalize_nodes_list(graph_model)


def normalize_edges_list(graph_model: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _normalize_edges_list(graph_model)
