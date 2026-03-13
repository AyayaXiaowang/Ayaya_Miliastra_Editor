from __future__ import annotations

from collections import deque
from typing import Dict, List, Mapping, Optional, Tuple

from engine.graph.port_type_effective_resolver import (
    EffectivePortTypeResolver,
    build_port_type_overrides,
)
from engine.graph.models import GraphModel, NodeModel
from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.port_type_system import is_flow_port_with_context

from engine.graph.reverse_codegen._common import (
    ReverseGraphCodeError,
    ReverseGraphCodeOptions,
    _COPY_MARKER,
    _is_data_node_copy,
    _is_local_var_relay_node_id,
    _resolve_node_def,
    _strip_copy_suffix,
)
from engine.graph.reverse_codegen._emitter.constants import (
    INF_BFS_DISTANCE,
    MAX_DATA_SOURCE_RESOLVE_DEPTH,
    MIN_BRANCHES_FOR_JOIN,
)


def _join_candidate_sort_key(
    node_id: str,
    *,
    reach_count: Mapping[str, int],
    dist_maps: List[Dict[str, int]],
) -> Tuple[int, int, int, str]:
    """为 join 候选节点计算稳定排序键。"""
    counts = reach_count.get(node_id, 0)
    dists = [dm.get(node_id, INF_BFS_DISTANCE) for dm in dist_maps]
    return (-counts, max(dists), sum(dists), node_id)


class _StructuredEventEmitterCore:
    """提供结构化发射所需的边索引、可达性与基础工具方法。"""

    def __init__(
        self,
        *,
        model: GraphModel,
        member_set: set[str],
        node_library: Dict[str, NodeDef],
        node_name_index: Dict[str, str],
        call_name_candidates_by_identity: Dict[int, List[str]],
        composite_alias_by_id: Dict[str, str],
        options: ReverseGraphCodeOptions,
    ) -> None:
        """初始化结构化事件体发射器并构建边索引。"""
        self.model = model
        self.member_set = set(member_set)
        self.node_library = node_library
        self.node_name_index = node_name_index
        self.call_name_candidates_by_identity = call_name_candidates_by_identity
        self.composite_alias_by_id = dict(composite_alias_by_id or {})
        self._composite_entry_method_name: str = "执行"
        self.options = options

        self._port_type_resolver = EffectivePortTypeResolver(
            self.model,
            node_def_resolver=lambda node_obj: _resolve_node_def(node=node_obj, node_library=self.node_library),
            port_type_overrides=build_port_type_overrides(self.model),
        )

        # (dst_node, dst_port) -> (src_node, src_port)
        self.data_in_edge: Dict[Tuple[str, str], Tuple[str, str]] = {}
        # src_node -> [(src_port, dst_node, dst_port), ...]（仅流程边）
        self.flow_out: Dict[str, List[Tuple[str, str, str]]] = {}
        # (src_node, src_port) -> (dst_node, dst_port)
        self.flow_out_by_port: Dict[Tuple[str, str], Tuple[str, str]] = {}

        self._build_edge_indices()
        self.emitted_nodes: set[str] = set()

    def _is_flow_port(self, node: NodeModel, port_name: str, is_source: bool) -> bool:
        """判断给定端口是否为流程端口（context-aware）。"""
        return is_flow_port_with_context(node, port_name, is_source, self.node_library)

    def _resolve_data_source(
        self,
        src_node_id: str,
        src_port: str,
        *,
        raw_data_in_edge: Mapping[Tuple[str, str], Tuple[str, str]],
        depth: int = 0,
    ) -> Tuple[str, str]:
        """对 data edge 的源端做归一化以透传 copy/relay 影响。"""
        if depth > MAX_DATA_SOURCE_RESOLVE_DEPTH:
            return str(src_node_id), str(src_port)

        src_id = str(src_node_id)
        port = str(src_port)
        node = self.model.nodes.get(src_id)
        if node is not None:
            if _is_data_node_copy(node) or (_COPY_MARKER in src_id):
                candidate = str(getattr(node, "original_node_id", "") or "") or src_id
                canonical = _strip_copy_suffix(candidate)
                if canonical and canonical != src_id:
                    return self._resolve_data_source(
                        canonical,
                        port,
                        raw_data_in_edge=raw_data_in_edge,
                        depth=depth + 1,
                    )

        if _is_local_var_relay_node_id(src_id) and port == "值":
            upstream = raw_data_in_edge.get((src_id, "初始值"))
            if upstream is not None:
                return self._resolve_data_source(
                    upstream[0],
                    upstream[1],
                    raw_data_in_edge=raw_data_in_edge,
                    depth=depth + 1,
                )

        return src_id, port

    def _build_edge_indices(self) -> None:
        """构建流程/数据边索引并对数据来源做归一化。"""
        raw_data_in_edge: Dict[Tuple[str, str], Tuple[str, str]] = {}
        for edge in (getattr(self.model, "edges", None) or {}).values():
            if edge.dst_node not in self.member_set:
                continue
            if edge.src_node not in self.member_set:
                continue
            dst_node = self.model.nodes.get(edge.dst_node)
            src_node = self.model.nodes.get(edge.src_node)
            if dst_node is None or src_node is None:
                continue

            src_is_flow = self._is_flow_port(src_node, str(edge.src_port), True)
            dst_is_flow = self._is_flow_port(dst_node, str(edge.dst_port), False)

            if src_is_flow and dst_is_flow:
                self.flow_out.setdefault(edge.src_node, []).append(
                    (str(edge.src_port), str(edge.dst_node), str(edge.dst_port))
                )
                key = (str(edge.src_node), str(edge.src_port))
                if key in self.flow_out_by_port:
                    raise ReverseGraphCodeError(
                        f"同一流程输出端口存在多条流程连线：{src_node.title}.{edge.src_port}"
                    )
                self.flow_out_by_port[key] = (str(edge.dst_node), str(edge.dst_port))
                continue

            if (not src_is_flow) and (not dst_is_flow):
                key2 = (str(edge.dst_node), str(edge.dst_port))
                if key2 in raw_data_in_edge:
                    raise ReverseGraphCodeError(
                        f"输入端口存在多条数据连线：{dst_node.title}.{edge.dst_port}"
                    )
                raw_data_in_edge[key2] = (str(edge.src_node), str(edge.src_port))

        for (dst_node_id, dst_port), (src_node_id, src_port) in raw_data_in_edge.items():
            resolved_src = self._resolve_data_source(
                str(src_node_id),
                str(src_port),
                raw_data_in_edge=raw_data_in_edge,
            )
            self.data_in_edge[(str(dst_node_id), str(dst_port))] = resolved_src

    def _flow_target(self, src_node_id: str, src_port: str) -> Optional[Tuple[str, str]]:
        """返回指定流程输出端口的唯一后继（若不存在则为 None）。"""
        return self.flow_out_by_port.get((str(src_node_id), str(src_port)))

    def _pick_single_flow_successor(self, node_id: str) -> Optional[Tuple[str, str]]:
        """选择普通节点的唯一流程后继并在多出边时 fail-fast。"""
        outs = list(self.flow_out.get(str(node_id), []) or [])
        if not outs:
            return None
        if len(outs) != 1:
            node = self.model.nodes.get(node_id)
            title = getattr(node, "title", "") if node is not None else node_id
            raise ReverseGraphCodeError(f"节点存在多条流程出边但不是结构化控制流节点：{title}")
        _src_port, dst_node, dst_port = outs[0]
        return dst_node, dst_port

    def _can_reach(self, start: str, target: str) -> bool:
        """判断沿流程边从 start 是否可达 target。"""
        return target in self._bfs_distances(start)

    def _bfs_distances(self, start: str) -> Dict[str, int]:
        """计算从 start 出发沿流程边可达节点到 start 的距离表。"""
        start_id = str(start)
        dist: Dict[str, int] = {}
        q = deque([(start_id, 0)])
        while q:
            node_id, d = q.popleft()
            if node_id in dist:
                continue
            dist[node_id] = d
            for _src_port, dst_node, dst_port in self.flow_out.get(node_id, []) or []:
                if dst_port == "跳出循环":
                    continue
                if dst_node not in self.member_set:
                    continue
                q.append((dst_node, d + 1))
        return dist

    def _find_join_for_branches(
        self,
        *,
        branch_starts: List[Optional[Tuple[str, str]]],
        stop_node_id: Optional[str],
    ) -> Optional[str]:
        """为分支集合选择一个稳定的 join 节点作为接续点。"""
        starts: List[str] = []
        for item in branch_starts:
            if item is None:
                continue
            node_id, dst_port = item
            if dst_port == "跳出循环":
                continue
            if stop_node_id and node_id == stop_node_id:
                continue
            starts.append(str(node_id))
        if len(starts) < MIN_BRANCHES_FOR_JOIN:
            return None

        dist_maps = [self._bfs_distances(s) for s in starts]
        reach_count: Dict[str, int] = {}
        for dm in dist_maps:
            for node_id in dm.keys():
                reach_count[node_id] = reach_count.get(node_id, 0) + 1

        candidates = [node_id for node_id, c in reach_count.items() if c >= MIN_BRANCHES_FOR_JOIN]
        if not candidates:
            return None

        return sorted(
            candidates,
            key=lambda nid: _join_candidate_sort_key(nid, reach_count=reach_count, dist_maps=dist_maps),
        )[0]

    def _collect_flow_nodes_in_region(self, *, start_node_id: str, stop_node_id: Optional[str]) -> set[str]:
        """收集从 start 出发沿流程边可达且在 stop 之前的流程节点集合。"""
        visited: set[str] = set()
        q = deque([str(start_node_id)])
        stop = str(stop_node_id) if stop_node_id else ""
        while q:
            node_id = q.popleft()
            if not node_id or node_id in visited:
                continue
            if stop and node_id == stop:
                continue
            visited.add(node_id)
            for _src_port, dst_node, dst_port in self.flow_out.get(node_id, []) or []:
                if dst_port == "跳出循环":
                    continue
                if dst_node not in self.member_set:
                    continue
                q.append(dst_node)
        return visited

    def _node_has_any_flow_port(self, node: NodeModel) -> bool:
        """判断节点是否存在任一流程端口。"""
        for port in (getattr(node, "outputs", None) or []):
            pname = str(getattr(port, "name", "") or "")
            if pname and self._is_flow_port(node, pname, True):
                return True
        for port in (getattr(node, "inputs", None) or []):
            pname = str(getattr(port, "name", "") or "")
            if pname and self._is_flow_port(node, pname, False):
                return True
        return False

