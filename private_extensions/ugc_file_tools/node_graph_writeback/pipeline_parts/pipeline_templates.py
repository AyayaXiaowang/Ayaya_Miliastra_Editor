from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..gil_dump import _dump_gil_to_raw_json_object, _ensure_list, _find_graph_entry, _get_payload_root


@dataclass(frozen=True)
class _TemplateGraphSample:
    template_raw_dump_object: Dict[str, Any]
    template_payload_root: Dict[str, Any]
    template_section: Dict[str, Any]
    template_group: Dict[str, Any]
    template_entry: Dict[str, Any]
    template_nodes: List[Dict[str, Any]]
    template_node_id_set: set[int]


def _load_template_graph_sample_or_raise(
    *,
    template_gil_path: Path,
    template_graph_id_int: int,
) -> _TemplateGraphSample:
    template_raw_dump_object = _dump_gil_to_raw_json_object(Path(template_gil_path))
    template_payload_root = _get_payload_root(template_raw_dump_object)

    template_section = template_payload_root.get("10")
    if not isinstance(template_section, dict):
        raise ValueError("template_gil 缺少节点图段 payload['10']")

    template_groups_list = _ensure_list(template_section, "1")
    template_group_dicts = [g for g in template_groups_list if isinstance(g, dict)]
    if not template_group_dicts:
        raise ValueError("template_gil 的 payload['10']['1'] 为空，无法克隆 group wrapper 元数据")
    template_group = template_group_dicts[0]

    template_entry = _find_graph_entry(template_payload_root, int(template_graph_id_int))
    template_nodes_value = template_entry.get("3")
    if not isinstance(template_nodes_value, list):
        raise ValueError("模板图缺少 nodes 列表 entry['3']")
    template_nodes = [n for n in template_nodes_value if isinstance(n, dict)]
    if not template_nodes:
        raise ValueError("模板图 nodes 为空")

    template_node_id_set: set[int] = set()
    for node in template_nodes:
        node_id_value = node.get("1")
        if isinstance(node_id_value, list) and node_id_value and isinstance(node_id_value[0], int):
            template_node_id_set.add(int(node_id_value[0]))

    return _TemplateGraphSample(
        template_raw_dump_object=dict(template_raw_dump_object),
        template_payload_root=dict(template_payload_root),
        template_section=dict(template_section),
        template_group=dict(template_group),
        template_entry=dict(template_entry),
        template_nodes=list(template_nodes),
        template_node_id_set=set(template_node_id_set),
    )


def _load_base_gil_payload_root(
    *,
    base_gil_path: Optional[Path],
    template_gil_path: Path,
) -> Tuple[Path, Dict[str, Any], Dict[str, Any]]:
    effective_base_gil_path = Path(base_gil_path).resolve() if base_gil_path is not None else Path(template_gil_path).resolve()
    base_raw_dump_object = _dump_gil_to_raw_json_object(effective_base_gil_path)
    payload_root = _get_payload_root(base_raw_dump_object)
    return Path(effective_base_gil_path), dict(base_raw_dump_object), dict(payload_root)

