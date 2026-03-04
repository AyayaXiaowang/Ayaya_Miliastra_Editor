from __future__ import annotations

from typing import Any, Dict, Optional

from ugc_file_tools.scope_utils import normalize_scope_or_default, normalize_scope_or_raise


def _infer_scope_from_graph_id_int(graph_id_int: int) -> Optional[str]:
    mask = int(graph_id_int) & 0xFF800000
    if int(mask) == 0x40000000:
        return "server"
    if int(mask) == 0x40800000:
        return "client"
    return None


def _infer_scope_from_graph_json_object(*, graph_json_object: Dict[str, Any], default_scope: str) -> str:
    default_norm = normalize_scope_or_default(default_scope, default_scope="server")
    meta = graph_json_object.get("metadata")
    if isinstance(meta, dict):
        t = str(meta.get("graph_type") or meta.get("graph_scope") or "").strip()
        if t:
            return normalize_scope_or_raise(t)
    t2 = str(graph_json_object.get("graph_type") or graph_json_object.get("graph_scope") or "").strip()
    if t2:
        return normalize_scope_or_raise(t2)
    return str(default_norm)

