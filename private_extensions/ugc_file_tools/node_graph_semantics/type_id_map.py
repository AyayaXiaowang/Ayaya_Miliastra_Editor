from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable

from ugc_file_tools.scope_utils import normalize_scope_or_raise


def _build_node_name_to_type_id(*, mapping_path: Path, scope: str) -> Dict[str, int]:
    """
    将 `node_type_semantic_map.json` 规约为 {Graph_Generater NodeDef.name: type_id_int}。

    说明：
    - 映射表以人类可维护的 `graph_generater_node_name` 为准，因此 key 为 NodeDef.name（而不是 canonical key）。
    - 该函数会为 name 衍生常见别名（仅影响查找，不改变 type_id），用于对齐 Graph Code/导出链路的命名变体。
    """
    scope_norm = normalize_scope_or_raise(scope)
    mapping_object = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
    if not isinstance(mapping_object, dict):
        raise TypeError("node_type_semantic_map.json must be dict")

    name_to_id: Dict[str, int] = {}

    def iter_name_aliases(name: str) -> Iterable[str]:
        n = str(name or "").strip()
        if n == "":
            return
        yield n
        if "/" in n:
            # 常见别名：去掉分隔符 / 用中文或 / 用下划线
            yield n.replace("/", "")
            yield n.replace("/", "或")
            yield n.replace("/", "_")

    for type_id_str, entry in mapping_object.items():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("scope") or "").strip().lower() != str(scope_norm):
            continue
        name = str(entry.get("graph_generater_node_name") or "").strip()
        if name == "":
            continue
        if not str(type_id_str).isdigit():
            continue
        type_id_int = int(type_id_str)
        for alias in iter_name_aliases(name):
            name_to_id.setdefault(alias, type_id_int)

    return name_to_id


def _build_node_def_key_to_type_id(
    *,
    mapping_path: Path,
    scope: str,
    graph_generater_root: Path,
) -> Dict[str, int]:
    """
    将 `node_type_semantic_map.json` 规约为 {NodeDef canonical key: type_id_int}。

    约定：
    - GraphModel(JSON) 已携带 `node_def_ref`（builtin 的 key 即 canonical key）。
    - 导出/写回链路不得通过 node.title 反查 type_id。
    - 映射表仍以 NodeDef.name 作为人类可维护字段，因此需要在此处通过节点库把 name → canonical key 规约一次。
    """
    scope_norm = normalize_scope_or_raise(scope)
    name_to_id = _build_node_name_to_type_id(mapping_path=Path(mapping_path), scope=str(scope_norm))

    from .graph_generater import ensure_graph_generater_sys_path as _ensure_graph_generater_sys_path

    _ensure_graph_generater_sys_path(Path(graph_generater_root).resolve())
    from engine.nodes.node_registry import get_node_registry  # type: ignore[import-not-found]
    from engine.nodes import get_canonical_node_def_key  # type: ignore[import-not-found]

    registry = get_node_registry(Path(graph_generater_root).resolve(), include_composite=True)
    node_library = registry.get_library()

    key_to_id: Dict[str, int] = {}
    for _, node_def in node_library.items():
        if node_def is None:
            continue
        if not bool(getattr(node_def, "is_available_in_scope", None)):
            continue
        if not node_def.is_available_in_scope(str(scope_norm)):
            continue

        node_name = str(getattr(node_def, "name", "") or "").strip()
        if node_name == "":
            continue
        mapped = name_to_id.get(node_name)
        if not isinstance(mapped, int) or int(mapped) <= 0:
            continue

        canonical_key = get_canonical_node_def_key(node_def)
        if canonical_key and canonical_key not in key_to_id:
            key_to_id[canonical_key] = int(mapped)

    return key_to_id


def build_node_name_to_type_id(*, mapping_path: Path, scope: str) -> Dict[str, int]:
    return _build_node_name_to_type_id(mapping_path=Path(mapping_path), scope=str(scope))


def build_node_def_key_to_type_id(*, mapping_path: Path, scope: str, graph_generater_root: Path) -> Dict[str, int]:
    return _build_node_def_key_to_type_id(
        mapping_path=Path(mapping_path),
        scope=str(scope),
        graph_generater_root=Path(graph_generater_root),
    )


__all__ = [
    "build_node_name_to_type_id",
    "build_node_def_key_to_type_id",
]

