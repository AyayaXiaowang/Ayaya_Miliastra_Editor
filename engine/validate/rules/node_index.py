from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Set, Tuple

from engine.nodes.node_registry import get_node_registry


def _expand_aliases(names: Set[str]) -> Set[str]:
    if not names:
        return set()
    alias: Set[str] = set(names)
    for name in list(names):
        if "/" in name:
            alias.add(name.replace("/", ""))
    return alias


@lru_cache(maxsize=8)
def node_function_names(workspace: Path) -> Set[str]:
    registry = get_node_registry(workspace, include_composite=True)
    lib = registry.get_library()
    base_names: Set[str] = {nd.name for _, nd in lib.items()}
    return _expand_aliases(base_names)


@lru_cache(maxsize=8)
def boolean_node_names(workspace: Path) -> Set[str]:
    registry = get_node_registry(workspace, include_composite=True)
    return _expand_aliases(set(registry.get_boolean_node_names()))


@lru_cache(maxsize=8)
def flow_node_names(workspace: Path) -> Set[str]:
    registry = get_node_registry(workspace, include_composite=True)
    return _expand_aliases(set(registry.get_flow_node_names()))


@lru_cache(maxsize=8)
def data_query_node_names(workspace: Path) -> Set[str]:
    registry = get_node_registry(workspace, include_composite=True)
    return _expand_aliases(set(registry.get_data_query_node_names()))


@lru_cache(maxsize=8)
def event_node_names(workspace: Path) -> Set[str]:
    """返回所有事件节点的名称集合（按节点库中的“事件节点”类别收集）。

    说明：
    - 仅依赖引擎侧节点库，不访问 assets 或 UI；
    - 结果用于代码层校验 register_event_handler 注册的事件名是否存在。
    """
    registry = get_node_registry(workspace, include_composite=True)
    lib = registry.get_library()
    names: Set[str] = set()
    for _, node_def in lib.items():
        category = getattr(node_def, "category", "") or ""
        if isinstance(category, str) and ("事件" in category):
            names.add(node_def.name)
    return _expand_aliases(names)


@lru_cache(maxsize=8)
def variadic_min_args(workspace: Path) -> Dict[str, int]:
    registry = get_node_registry(workspace, include_composite=True)
    return dict(registry.get_variadic_min_args())


@lru_cache(maxsize=8)
def input_types_by_func(workspace: Path) -> Dict[str, Dict[str, str]]:
    registry = get_node_registry(workspace, include_composite=True)
    lib = registry.get_library()
    result: Dict[str, Dict[str, str]] = {}
    for _, nd in lib.items():
        result[nd.name] = dict(nd.input_types)
    return result


@lru_cache(maxsize=8)
def input_generic_constraints_by_func(workspace: Path) -> Dict[str, Dict[str, List[str]]]:
    registry = get_node_registry(workspace, include_composite=True)
    lib = registry.get_library()
    result: Dict[str, Dict[str, List[str]]] = {}
    for _, nd in lib.items():
        constraints = getattr(nd, "input_generic_constraints", {}) or {}
        if constraints:
            result[nd.name] = {port: list(allowed or []) for port, allowed in constraints.items()}
    return result


@lru_cache(maxsize=8)
def output_types_by_func(workspace: Path) -> Dict[str, List[str]]:
    registry = get_node_registry(workspace, include_composite=True)
    lib = registry.get_library()
    result: Dict[str, List[str]] = {}
    for _, nd in lib.items():
        outs: List[str] = []
        for out_name in nd.outputs:
            outs.append(nd.output_types.get(out_name, ""))
        result[nd.name] = outs
    return result


@lru_cache(maxsize=8)
def output_generic_constraints_by_func(workspace: Path) -> Dict[str, Dict[str, List[str]]]:
    registry = get_node_registry(workspace, include_composite=True)
    lib = registry.get_library()
    result: Dict[str, Dict[str, List[str]]] = {}
    for _, nd in lib.items():
        constraints = getattr(nd, "output_generic_constraints", {}) or {}
        if constraints:
            result[nd.name] = {port: list(allowed or []) for port, allowed in constraints.items()}
    return result


def clear_node_index_caches() -> None:
    node_function_names.cache_clear()
    boolean_node_names.cache_clear()
    flow_node_names.cache_clear()
    data_query_node_names.cache_clear()
    event_node_names.cache_clear()
    variadic_min_args.cache_clear()
    input_types_by_func.cache_clear()
    input_generic_constraints_by_func.cache_clear()
    output_types_by_func.cache_clear()
    output_generic_constraints_by_func.cache_clear()


