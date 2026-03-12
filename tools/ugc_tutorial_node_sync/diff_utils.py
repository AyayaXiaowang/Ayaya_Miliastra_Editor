from __future__ import annotations

"""对上游 DocNodeSpec 与本地节点索引做 diff 的工具函数。"""

from typing import Any, Dict, List, Tuple


FLOW_PORT_TYPE = "流程"


def is_flow_port(port_name: str, port_type: str) -> bool:
    # Return whether a port is treated as a flow-control port.
    return str(port_type or "") == FLOW_PORT_TYPE or str(port_name or "").startswith("流程")


def compute_diff(
    *,
    upstream: List[Any],
    local_map: Dict[Tuple[str, str, str], Dict[str, Any]],
    subset_mode: bool,
) -> Dict[str, Any]:
    # Compute missing/extra/changed_ports between upstream specs and local node @node_spec tables.
    upstream_map: Dict[Tuple[str, str, str], Any] = {}
    for s in upstream:
        upstream_map[(str(s.scope), str(s.category), str(s.name))] = s

    local_keys = set(local_map.keys())
    upstream_keys = set(upstream_map.keys())

    missing_locally = sorted(list(upstream_keys - local_keys))
    extra_locally = [] if subset_mode else sorted(list(local_keys - upstream_keys))

    changed: List[Dict[str, Any]] = []
    for k in sorted(list(upstream_keys & local_keys)):
        up = upstream_map[k]
        lo = local_map[k]

        def _to_port_pairs(raw: Any, where: str) -> List[Tuple[str, str]]:
            # Convert local index raw port lists into stable (name, type) pairs.
            if not isinstance(raw, list):
                raise ValueError(f"local.{where} is not a list")
            out_pairs: List[Tuple[str, str]] = []
            for it in raw:
                if isinstance(it, (list, tuple)) and len(it) == 2:
                    out_pairs.append((str(it[0]), str(it[1])))
                    continue
                raise ValueError(f"local.{where} item is not a [name, type] pair: {it!r}")
            return out_pairs

        local_inputs_pairs = _to_port_pairs(lo.get("inputs") or [], "inputs")
        local_outputs_pairs = _to_port_pairs(lo.get("outputs") or [], "outputs")

        local_data_inputs = [(n, t) for (n, t) in local_inputs_pairs if not is_flow_port(n, t)]
        local_data_outputs = [(n, t) for (n, t) in local_outputs_pairs if not is_flow_port(n, t)]

        if local_data_inputs != list(getattr(up, "inputs")) or local_data_outputs != list(getattr(up, "outputs")):
            changed.append(
                {
                    "key": {"scope": k[0], "category": k[1], "name": k[2]},
                    "source_path_id": str(getattr(up, "source_path_id")),
                    "local_file_path": str(lo.get("file_path") or ""),
                    "local_data_inputs": local_data_inputs,
                    "doc_data_inputs": list(getattr(up, "inputs")),
                    "local_data_outputs": local_data_outputs,
                    "doc_data_outputs": list(getattr(up, "outputs")),
                }
            )

    return {
        "summary": {
            "missing_locally": len(missing_locally),
            "extra_locally": len(extra_locally),
            "changed_ports": len(changed),
        },
        "missing_locally": [{"scope": s, "category": c, "name": n} for (s, c, n) in missing_locally],
        "extra_locally": (
            []
            if subset_mode
            else [
                {"scope": s, "category": c, "name": n, "file_path": str(local_map[(s, c, n)].get("file_path") or "")}
                for (s, c, n) in extra_locally
            ]
        ),
        "changed_ports": changed,
    }

