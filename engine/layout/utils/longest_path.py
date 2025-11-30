from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Set, Tuple, TypeVar
import heapq


T = TypeVar("T")

OptionalWeightProvider = Callable[[T, T], float] | None
OptionalOrderKey = Callable[[T], Any] | None


def assign_longest_path_levels(
    nodes: Iterable[T],
    adjacency_provider: Callable[[T], Iterable[T]],
    *,
    weight_provider: OptionalWeightProvider[T] = None,
    order_key: OptionalOrderKey[T] = None,
) -> Tuple[Dict[T, float], Set[T]]:
    node_list: List[T] = list(nodes)
    node_lookup: Set[T] = set(node_list)
    adjacency_map: Dict[T, List[T]] = {}
    in_degree: Dict[T, int] = {node: 0 for node in node_list}

    for node in node_list:
        raw_children = adjacency_provider(node) or []
        unique_children: List[T] = []
        seen: Set[T] = set()
        for child in raw_children:
            if child not in node_lookup:
                continue
            if child in seen:
                continue
            seen.add(child)
            unique_children.append(child)
        adjacency_map[node] = unique_children
        for child in unique_children:
            in_degree[child] = in_degree.get(child, 0) + 1

    queue: List[Tuple[Any, int, T]] = []
    sequence = 0

    def push(node: T) -> None:
        nonlocal sequence
        key = order_key(node) if order_key is not None else sequence
        heapq.heappush(queue, (key, sequence, node))
        sequence += 1

    for node in node_list:
        if in_degree.get(node, 0) == 0:
            push(node)

    levels: Dict[T, float] = {node: 0.0 for node in node_list}
    processed: Set[T] = set()

    while queue:
        _, _, node = heapq.heappop(queue)
        if node in processed:
            continue
        processed.add(node)
        base_level = levels.get(node, 0.0)
        for child in adjacency_map.get(node, ()):
            weight = weight_provider(node, child) if weight_provider is not None else 1.0
            candidate = base_level + float(weight)
            if candidate > levels.get(child, float("-inf")):
                levels[child] = candidate
            in_degree[child] -= 1
            if in_degree[child] == 0:
                push(child)

    leftover = {node for node in node_list if node not in processed}
    return levels, leftover


def resolve_levels_with_parents(
    nodes: Iterable[T],
    adjacency_provider: Callable[[T], Iterable[T]],
    parent_provider: Callable[[T], Iterable[T]] | None = None,
    *,
    weight_provider: OptionalWeightProvider[T] = None,
    order_key: OptionalOrderKey[T] = None,
    default_level: float = 0.0,
) -> Dict[T, float]:
    """
    在 `assign_longest_path_levels` 的基础上，结合父集合对残余节点进行回退处理。

    - 先运行标准的最长路径拓扑排序，获得大部分节点的层级
    - 对剩余（存在环或缺失入度信息）的节点，根据所有父节点的层级+权重进行补偿
    - 若节点无父节点，则保持默认层级
    """

    node_list: List[T] = list(nodes)
    base_levels, leftovers = assign_longest_path_levels(
        node_list,
        adjacency_provider,
        weight_provider=weight_provider,
        order_key=order_key,
    )

    resolved: Dict[T, float] = {node: float(base_levels.get(node, default_level)) for node in node_list}
    if not leftovers:
        return resolved

    def _iter_parents(item: T) -> Iterable[T]:
        if parent_provider is None:
            return ()
        parents = parent_provider(item)
        return parents or ()

    def _weight(src: T, dst: T) -> float:
        if weight_provider is None:
            return 1.0
        return float(weight_provider(src, dst))

    def _order_value(item: T) -> Any:
        if order_key is None:
            return 0
        return order_key(item)

    for node in sorted(leftovers, key=_order_value):
        parents = list(_iter_parents(node))
        if parents:
            candidate_level = max(resolved.get(parent, default_level) + _weight(parent, node) for parent in parents)
            if candidate_level > resolved.get(node, default_level):
                resolved[node] = float(candidate_level)
        else:
            resolved.setdefault(node, float(default_level))

    return resolved
