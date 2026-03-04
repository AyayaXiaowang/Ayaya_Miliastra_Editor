from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def resolve_default_node_data_index_path() -> Path:
    """
    默认指向本仓库内置的节点静态数据索引：
    `ugc_file_tools/node_data/index.json`
    """
    return (
        Path(__file__).resolve().parent
        / "node_data"
        / "index.json"
    )


def load_node_data_document(index_path: Path) -> Dict[str, Any]:
    index_path = Path(index_path).resolve()
    if not index_path.is_file():
        raise FileNotFoundError(f"node_data index.json not found: {str(index_path)!r}")
    doc = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("node_data index.json is not a dict document")
    return doc


def _build_entry_by_id_map(entries: Any) -> Dict[int, Dict[str, Any]]:
    if not isinstance(entries, list):
        return {}
    result: Dict[int, Dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get("ID")
        if not isinstance(entry_id, int):
            continue
        result[int(entry_id)] = dict(entry)
    return result


def load_node_entry_by_id_map(index_path: Path) -> Dict[int, Dict[str, Any]]:
    doc = load_node_data_document(index_path)
    return _build_entry_by_id_map(doc.get("NodesList"))


def load_type_entry_by_id_map(index_path: Path) -> Dict[int, Dict[str, Any]]:
    doc = load_node_data_document(index_path)
    return _build_entry_by_id_map(doc.get("TypesList"))


def load_node_name_by_id_if_exists(index_path: Optional[Path] = None) -> Dict[int, str]:
    """
    若 index.json 存在则返回 node_id_int -> safe_name；否则返回空 dict。
    用途：为 `export_graph_ir_from_package.py` 提供一个“尽力而为”的节点名提示来源。
    """
    resolved_path = Path(index_path).resolve() if index_path is not None else resolve_default_node_data_index_path()
    if not resolved_path.is_file():
        return {}
    node_entry_by_id = load_node_entry_by_id_map(resolved_path)
    result: Dict[int, str] = {}
    for node_id_int, entry in node_entry_by_id.items():
        name = str(entry.get("Name") or "").strip()
        if name == "":
            continue
        result[int(node_id_int)] = name
    return result


