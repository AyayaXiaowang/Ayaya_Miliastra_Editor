"""
布局上下文模块

提供只读布局上下文，一次性构建端口与连线的索引缓存。
"""

from __future__ import annotations
from typing import Dict, Set, List, Optional, Tuple
import hashlib
from engine.graph.models import GraphModel
from engine.utils.graph.graph_utils import is_flow_port_name
from ..utils.graph_query_utils import (
    estimate_node_height_ui_exact_for_model,
    is_pure_data_node as graph_query_is_pure_data_node,
    build_edge_indices,
)


class LayoutContext:
    """
    只读布局上下文：一次性构建端口与连线的索引缓存，便于在布局/树打印过程中 O(1) 查询。
    不改变 GraphModel；所有集合/映射均视为只读视图。
    """

    def __init__(self, model: GraphModel):
        self.model: GraphModel = model
        self.graph_signature = self._compute_graph_signature(model)

        # 节点级别缓存
        self.virtualPinNodeIds: Set[str] = {
            node_id for node_id, node in model.nodes.items() if getattr(node, "is_virtual_pin", False)
        }
        self.portIndexByNodeOut: Dict[str, Dict[str, int]] = {}
        self.portIndexByNodeIn: Dict[str, Dict[str, int]] = {}
        self.portMapByNodeIn: Dict[str, Dict[str, object]] = {}
        self.portMapByNodeOut: Dict[str, Dict[str, object]] = {}
        self.flowCapableNodeIds: Set[str] = set()
        self.eventMetadataByNode: Dict[str, Tuple[Optional[str], Optional[str]]] = {}

        # 边级别缓存（按"目标端口是否为流程口"划分流/数）
        self.flowOutByNode: Dict[str, List[object]] = {}
        self.flowInByNode: Dict[str, List[object]] = {}
        self.dataOutByNode: Dict[str, List[object]] = {}
        self.dataInByNode: Dict[str, List[object]] = {}
        self._pure_data_node_cache: Dict[str, bool] = {}

        self._build_node_port_caches()
        self._build_edge_caches()

    def _build_node_port_caches(self) -> None:
        """构建节点端口缓存"""
        for node_id, node in self.model.nodes.items():
            # 端口索引与映射
            self.portIndexByNodeOut[node_id] = {port.name: index for index, port in enumerate(node.outputs)}
            self.portIndexByNodeIn[node_id] = {port.name: index for index, port in enumerate(node.inputs)}
            self.portMapByNodeIn[node_id] = {port.name: port for port in node.inputs}
            self.portMapByNodeOut[node_id] = {port.name: port for port in node.outputs}

            has_flow_port = False
            for port in node.inputs:
                if is_flow_port_name(port.name):
                    has_flow_port = True
                    break
            if not has_flow_port:
                for port in node.outputs:
                    if is_flow_port_name(port.name):
                        has_flow_port = True
                        break
            if has_flow_port:
                self.flowCapableNodeIds.add(node_id)

    def _build_edge_caches(self) -> None:
        """构建边缓存"""
        (
            self.flowOutByNode,
            self.flowInByNode,
            self.dataOutByNode,
            self.dataInByNode,
        ) = build_edge_indices(self.model)

    def is_pure_data_node(self, node_id: str) -> bool:
        """
        判断节点是否为纯数据节点（无流程端口）
        
        Args:
            node_id: 节点ID
            
        Returns:
            True 如果节点是纯数据节点
        """
        cached = self._pure_data_node_cache.get(node_id)
        if cached is not None:
            return cached
        resolved = graph_query_is_pure_data_node(node_id, self.model)
        self._pure_data_node_cache[node_id] = resolved
        return resolved

    def get_out_flow_edges(self, node_id: str) -> List[object]:
        """获取节点的流程输出边（只读视图，调用方勿修改）"""
        return self.flowOutByNode.get(node_id, [])

    def get_in_flow_edges(self, node_id: str) -> List[object]:
        """获取节点的流程输入边（只读视图，调用方勿修改）"""
        return self.flowInByNode.get(node_id, [])

    def get_out_data_edges(self, node_id: str) -> List[object]:
        """获取节点的数据输出边（只读视图，调用方勿修改）"""
        return self.dataOutByNode.get(node_id, [])

    def get_in_data_edges(self, node_id: str) -> List[object]:
        """获取节点的数据输入边（只读视图，调用方勿修改）"""
        return self.dataInByNode.get(node_id, [])

    def get_input_port_index(self, node_id: str, port_name: str) -> int:
        """获取输入端口索引（默认极大值）"""
        return self.portIndexByNodeIn.get(node_id, {}).get(port_name, 10**6)

    def get_output_port_index(self, node_id: str, port_name: str) -> int:
        """获取输出端口索引（默认最大999）"""
        return self.portIndexByNodeOut.get(node_id, {}).get(port_name, 999)

    def set_event_metadata(self, metadata: Dict[str, Tuple[Optional[str], Optional[str]]]) -> None:
        """缓存事件 ID → (事件根ID, 标题) 映射。"""
        self.eventMetadataByNode = dict(metadata or {})

    def get_event_metadata(self, node_id: str) -> Optional[Tuple[Optional[str], Optional[str]]]:
        return self.eventMetadataByNode.get(node_id)

    def clone_for_model(self, model: GraphModel) -> "LayoutContext":
        """
        基于当前缓存快速复制一份 LayoutContext，重定向到新的 GraphModel。

        Notes:
            - 仅针对克隆模型返回的 GraphModel（节点/边结构保持一致）；
            - 端口/边对象会从目标模型重新查找，确保引用指向调用方模型。
        """
        cloned = object.__new__(LayoutContext)
        cloned.model = model
        cloned.graph_signature = self._compute_graph_signature(model)

        existing_node_ids = set(model.nodes.keys())

        def _copy_port_index(source: Dict[str, Dict[str, int]]) -> Dict[str, Dict[str, int]]:
            return {node_id: dict(index_map) for node_id, index_map in source.items() if node_id in existing_node_ids}

        cloned.virtualPinNodeIds = set(self.virtualPinNodeIds) & existing_node_ids
        cloned.portIndexByNodeOut = _copy_port_index(self.portIndexByNodeOut)
        cloned.portIndexByNodeIn = _copy_port_index(self.portIndexByNodeIn)

        def _rebuild_port_map(node_id: str, is_output: bool) -> Dict[str, object]:
            node = model.nodes.get(node_id)
            if not node:
                return {}
            ports = node.outputs if is_output else node.inputs
            return {port.name: port for port in ports}

        cloned.portMapByNodeIn = {node_id: _rebuild_port_map(node_id, False) for node_id in cloned.portIndexByNodeIn}
        cloned.portMapByNodeOut = {node_id: _rebuild_port_map(node_id, True) for node_id in cloned.portIndexByNodeOut}

        cloned.flowCapableNodeIds = set(self.flowCapableNodeIds) & existing_node_ids
        cloned.eventMetadataByNode = dict(self.eventMetadataByNode)

        def _relink_edges(source: Dict[str, List[object]]) -> Dict[str, List[object]]:
            if not source:
                return {}
            remapped: Dict[str, List[object]] = {}
            for node_id, edges in source.items():
                target_bucket: List[object] = []
                for edge in edges or []:
                    edge_id = getattr(edge, "id", None)
                    if edge_id is None:
                        continue
                    target_edge = model.edges.get(edge_id)
                    if target_edge is not None:
                        target_bucket.append(target_edge)
                if target_bucket:
                    remapped[node_id] = target_bucket
            return remapped

        cloned.flowOutByNode = _relink_edges(self.flowOutByNode)
        cloned.flowInByNode = _relink_edges(self.flowInByNode)
        cloned.dataOutByNode = _relink_edges(self.dataOutByNode)
        cloned.dataInByNode = _relink_edges(self.dataInByNode)

        cloned._pure_data_node_cache = {
            node_id: flag for node_id, flag in self._pure_data_node_cache.items() if node_id in existing_node_ids
        }

        return cloned

    @staticmethod
    def _compute_graph_signature(model: GraphModel) -> Tuple[Optional[int], Optional[int], str, str]:
        """基于节点/边集合生成稳定签名。"""
        node_hasher = hashlib.sha1()
        edge_hasher = hashlib.sha1()

        nodes_dict = getattr(model, "nodes", {}) or {}
        for node_id in sorted(nodes_dict.keys()):
            node_hasher.update(str(node_id).encode("utf-8"))
            node_hasher.update(b"\x00")

        edges_dict = getattr(model, "edges", {}) or {}
        for edge_id in sorted(edges_dict.keys()):
            edge = edges_dict.get(edge_id)
            edge_hasher.update(str(edge_id).encode("utf-8"))
            edge_hasher.update(b"|")
            if edge is not None:
                edge_hasher.update(str(getattr(edge, "src_node", "") or "").encode("utf-8"))
                edge_hasher.update(b"->")
                edge_hasher.update(str(getattr(edge, "dst_node", "") or "").encode("utf-8"))
                edge_hasher.update(b":")
                edge_hasher.update(str(getattr(edge, "src_port", "") or "").encode("utf-8"))
                edge_hasher.update(b"/")
                edge_hasher.update(str(getattr(edge, "dst_port", "") or "").encode("utf-8"))
            edge_hasher.update(b"\x00")

        return (
            getattr(model, "graph_revision", None),
            getattr(model, "version", None),
            node_hasher.hexdigest(),
            edge_hasher.hexdigest(),
        )

    @classmethod
    def compute_signature_for_model(cls, model: GraphModel) -> Tuple[Optional[int], Optional[int], int, int]:
        """对外暴露的签名计算入口，便于无需实例化即可比较。"""
        return cls._compute_graph_signature(model)



