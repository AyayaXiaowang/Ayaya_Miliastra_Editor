from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class CompositeWritebackArtifacts:
    node_def_wrappers: List[Dict[str, Any]]
    composite_graph_objs: List[Dict[str, Any]]
    record_id_by_node_type_id_and_inparam_index: Dict[int, Dict[int, int]]


__all__ = ["CompositeWritebackArtifacts"]

