from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def list_gil_node_graphs(*, input_gil_file_path: Path, dtype_path: Path) -> List[Dict[str, Any]]:
    """
    读取 `.gil` 并列出其中的“节点图定义”清单（不落盘）。

    返回元素形如：
    - graph_id_int: int
    - graph_name: str
    - source_pyugc_path: str
    """
    input_gil = Path(input_gil_file_path).resolve()
    dtype = Path(dtype_path).resolve()
    if not input_gil.is_file():
        raise FileNotFoundError(str(input_gil))
    if not dtype.is_file():
        raise FileNotFoundError(str(dtype))

    from .pyugc_decode import _decode_gil_with_pyugc
    from .node_graph_raw_exporter import list_pyugc_node_graphs

    _header, pyugc_object = _decode_gil_with_pyugc(input_gil, dtype)
    graphs = list_pyugc_node_graphs(pyugc_object)
    graphs.sort(key=lambda it: int(it.get("graph_id_int", 0) or 0))
    return graphs


__all__ = [
    "list_gil_node_graphs",
]

