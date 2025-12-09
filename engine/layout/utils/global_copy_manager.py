"""
全局跨块数据节点复制管理器

负责在所有块识别完成后，统一分析跨块共享的数据节点，
批量创建副本并重定向边，取代原有的"边识别边复制"逻辑。

调用时机：所有块的流程节点识别完成后、数据节点放置前

复制规则：
1. 同一个块里的数据节点不需要复制
2. 复制后，原始节点到非owner块的边要断开，改为副本连接
3. 同一个块内的多个消费者共用一个副本
"""

from __future__ import annotations
from dataclasses import dataclass, field, replace
from typing import Dict, List, Set, Optional, Tuple, TYPE_CHECKING
import uuid

from engine.graph.models import GraphModel, NodeModel, EdgeModel, PortModel

if TYPE_CHECKING:
    from ..core.layout_models import LayoutBlock
    from ..core.layout_context import LayoutContext


@dataclass
class BlockDataDependency:
    """块的数据依赖信息"""
    block_id: str
    block_index: int
    flow_node_ids: Set[str]
    # 直接被流程节点消费的数据节点
    direct_data_consumers: Set[str] = field(default_factory=set)
    # 包含上游闭包的完整数据依赖
    full_data_closure: Set[str] = field(default_factory=set)


@dataclass
class CopyPlan:
    """复制计划：描述一个数据节点需要在哪些块创建副本"""
    original_node_id: str
    # 首个使用该节点的块（保留原始节点）
    owner_block_id: str
    owner_block_index: int
    # 需要创建副本的块列表（块ID -> 副本ID）
    copy_targets: Dict[str, str] = field(default_factory=dict)


class GlobalCopyManager:
    """全局跨块数据节点复制管理器
    
    职责：
    1. 分析所有块的数据依赖，识别跨块共享的数据节点
    2. 生成复制计划
    3. 统一创建所有需要的副本
    4. 统一执行边重定向（断开旧边，创建新边）
    
    使用方式：
        manager = GlobalCopyManager(model, layout_blocks, layout_context)
        manager.analyze_dependencies()
        manager.execute_copy_plan()
    """
    
    def __init__(
        self,
        model: GraphModel,
        layout_blocks: List["LayoutBlock"],
        layout_context: Optional["LayoutContext"] = None,
    ):
        self.model = model
        self.layout_blocks = layout_blocks
        self.layout_context = layout_context
        
        # 分析结果
        self.block_dependencies: Dict[str, BlockDataDependency] = {}
        # 数据节点 -> 使用它的块ID列表（按块序号排序）
        self.data_node_consumers: Dict[str, List[str]] = {}
        # 复制计划
        self.copy_plans: Dict[str, CopyPlan] = {}
        # 已创建的副本映射：(原始ID, 块ID) -> 副本ID
        self.created_copies: Dict[Tuple[str, str], str] = {}
        # 流程节点所属块的映射：流程节点ID -> 块ID
        self._flow_to_block: Dict[str, str] = {}
        
        # 边索引（用于高效查询）
        self._data_in_edges_by_dst: Dict[str, List] = {}
        self._data_out_edges_by_src: Dict[str, List] = {}
        self._build_edge_indices()
    
    def _build_edge_indices(self) -> None:
        """构建边索引"""
        if self.layout_context is not None:
            # 复制索引（避免修改原始数据）
            for key, edges in self.layout_context.dataInByNode.items():
                self._data_in_edges_by_dst[key] = list(edges)
            for key, edges in self.layout_context.dataOutByNode.items():
                self._data_out_edges_by_src[key] = list(edges)
            return
        
        # 回退：手动构建索引
        for edge in self.model.edges.values():
            src_node = self.model.nodes.get(edge.src_node)
            dst_node = self.model.nodes.get(edge.dst_node)
            if not src_node or not dst_node:
                continue
            
            # 判断是否为数据边（非流程边）
            if self._is_data_edge(edge, src_node, dst_node):
                self._data_in_edges_by_dst.setdefault(edge.dst_node, []).append(edge)
                self._data_out_edges_by_src.setdefault(edge.src_node, []).append(edge)
    
    def _is_data_edge(self, edge: EdgeModel, src_node: NodeModel, dst_node: NodeModel) -> bool:
        """判断边是否为数据边"""
        from engine.utils.graph.graph_utils import is_flow_port_name
        
        # 源端口或目标端口是流程端口则为流程边
        if is_flow_port_name(edge.src_port) or is_flow_port_name(edge.dst_port):
            return False
        return True
    
    def _is_pure_data_node(self, node_id: str) -> bool:
        """判断是否为纯数据节点"""
        if self.layout_context is not None:
            return self.layout_context.is_pure_data_node(node_id)
        
        node = self.model.nodes.get(node_id)
        if not node:
            return False
        
        from engine.utils.graph.graph_utils import is_flow_port_name
        
        # 检查是否有流程端口
        for port in node.inputs:
            if is_flow_port_name(port.name):
                return False
        for port in node.outputs:
            if is_flow_port_name(port.name):
                return False
        return True
    
    def analyze_dependencies(self) -> None:
        """分析所有块的数据依赖"""
        # 步骤1：构建流程节点到块的映射
        self._build_flow_to_block_mapping()
        
        # 步骤2：收集每个块直接消费的数据节点
        self._collect_direct_consumers()
        
        # 步骤3：扩展到完整的上游闭包
        self._expand_to_full_closure()
        
        # 步骤4：识别跨块共享的数据节点
        self._identify_shared_nodes()
        
        # 步骤5：生成复制计划
        self._generate_copy_plans()
    
    def _build_flow_to_block_mapping(self) -> None:
        """构建流程节点到块的映射"""
        for block in self.layout_blocks:
            block_id = f"block_{block.order_index}"
            for flow_id in block.flow_nodes:
                self._flow_to_block[flow_id] = block_id
    
    def _collect_direct_consumers(self) -> None:
        """收集每个块直接消费的数据节点"""
        for block in self.layout_blocks:
            block_id = f"block_{block.order_index}"
            flow_ids = set(block.flow_nodes)
            
            dependency = BlockDataDependency(
                block_id=block_id,
                block_index=block.order_index,
                flow_node_ids=flow_ids,
            )
            
            # 遍历流程节点的输入边，找到直接消费的数据节点
            for flow_id in flow_ids:
                in_edges = self._data_in_edges_by_dst.get(flow_id, [])
                for edge in in_edges:
                    src_id = edge.src_node
                    if self._is_pure_data_node(src_id):
                        dependency.direct_data_consumers.add(src_id)
            
            self.block_dependencies[block_id] = dependency
    
    def _expand_to_full_closure(self) -> None:
        """将直接消费扩展到完整的上游闭包"""
        for block_id, dependency in self.block_dependencies.items():
            visited: Set[str] = set()
            queue = list(dependency.direct_data_consumers)
            
            while queue:
                current_id = queue.pop(0)
                if current_id in visited:
                    continue
                visited.add(current_id)
                
                if not self._is_pure_data_node(current_id):
                    continue
                
                dependency.full_data_closure.add(current_id)
                
                # 添加上游数据节点
                in_edges = self._data_in_edges_by_dst.get(current_id, [])
                for edge in in_edges:
                    src_id = edge.src_node
                    if self._is_pure_data_node(src_id) and src_id not in visited:
                        queue.append(src_id)
    
    def _identify_shared_nodes(self) -> None:
        """识别被多个块使用的数据节点"""
        # 收集每个数据节点被哪些块使用
        for block_id, dependency in self.block_dependencies.items():
            for data_id in dependency.full_data_closure:
                if data_id not in self.data_node_consumers:
                    self.data_node_consumers[data_id] = []
                if block_id not in self.data_node_consumers[data_id]:
                    self.data_node_consumers[data_id].append(block_id)
        
        # 按块序号排序（首个块保留原始节点）
        for data_id, block_ids in self.data_node_consumers.items():
            block_ids.sort(key=lambda bid: self.block_dependencies[bid].block_index)
    
    def _generate_copy_plans(self) -> None:
        """生成复制计划"""
        for data_id, block_ids in self.data_node_consumers.items():
            if len(block_ids) <= 1:
                # 只被一个块使用，不需要复制
                continue
            
            # 首个块保留原始节点
            owner_block_id = block_ids[0]
            owner_index = self.block_dependencies[owner_block_id].block_index
            
            plan = CopyPlan(
                original_node_id=data_id,
                owner_block_id=owner_block_id,
                owner_block_index=owner_index,
            )
            
            # 其他块需要创建副本（每个块只创建一个副本）
            for block_id in block_ids[1:]:
                copy_id = f"{data_id}_copy_{block_id}_1"
                plan.copy_targets[block_id] = copy_id
            
            self.copy_plans[data_id] = plan
    
    def execute_copy_plan(self) -> None:
        """执行复制计划：创建副本并重定向边"""
        if not self.copy_plans:
            return
        
        # 步骤1：批量创建所有副本
        self._create_all_copies()
        
        # 步骤2：重定向边（断开旧边，创建新边）
        self._redirect_all_edges()
        
        # 步骤3：去重边（防止重复边）
        self._dedupe_edges()
    
    def _create_all_copies(self) -> None:
        """批量创建所有副本节点"""
        for original_id, plan in self.copy_plans.items():
            source_node = self.model.nodes.get(original_id)
            if not source_node:
                continue
            
            for block_id, copy_id in plan.copy_targets.items():
                copy_node = self._create_copy_node(source_node, copy_id, block_id)
                self.model.nodes[copy_id] = copy_node
                self.created_copies[(original_id, block_id)] = copy_id
    
    def _create_copy_node(
        self,
        source_node: NodeModel,
        copy_id: str,
        block_id: str,
    ) -> NodeModel:
        """创建副本节点"""
        # 解析根原始节点ID
        original_id = source_node.original_node_id if source_node.original_node_id else source_node.id
        
        copy_node = replace(
            source_node,
            id=copy_id,
            is_data_node_copy=True,
            original_node_id=original_id,
            copy_block_id=block_id,
            # 深拷贝端口列表
            inputs=[PortModel(name=port.name, is_input=True) for port in source_node.inputs],
            outputs=[PortModel(name=port.name, is_input=False) for port in source_node.outputs],
            # 深拷贝常量
            input_constants=dict(source_node.input_constants) if source_node.input_constants else {},
        )
        copy_node._rebuild_port_maps()
        return copy_node
    
    def _redirect_all_edges(self) -> None:
        """重定向所有边：断开旧边，创建新边"""
        edges_to_remove: List[str] = []
        edges_to_create: List[EdgeModel] = []
        
        for original_id, plan in self.copy_plans.items():
            # 获取原始节点的所有输出边
            out_edges = self._data_out_edges_by_src.get(original_id, [])
            
            for edge in out_edges:
                dst_id = edge.dst_node
                
                # 判断目标节点所属的块
                dst_block_id = self._get_node_block(dst_id)
                if not dst_block_id:
                    continue
                
                # 如果目标在owner块，保留原始边
                if dst_block_id == plan.owner_block_id:
                    continue
                
                # 如果目标在需要副本的块，断开旧边，创建新边
                if dst_block_id in plan.copy_targets:
                    copy_id = plan.copy_targets[dst_block_id]
                    
                    # 标记旧边待删除
                    edges_to_remove.append(edge.id)
                    
                    # 检查目标是否也有副本
                    dst_copy_id = self.created_copies.get((dst_id, dst_block_id))
                    actual_dst = dst_copy_id if dst_copy_id else dst_id
                    
                    # 创建新边：副本 -> 目标
                    new_edge = EdgeModel(
                        id=f"edge_{uuid.uuid4().hex[:8]}",
                        src_node=copy_id,
                        src_port=edge.src_port,
                        dst_node=actual_dst,
                        dst_port=edge.dst_port,
                    )
                    edges_to_create.append(new_edge)
            
            # 处理副本的输入边
            in_edges = self._data_in_edges_by_dst.get(original_id, [])
            for block_id, copy_id in plan.copy_targets.items():
                for edge in in_edges:
                    # 检查源节点是否也有副本在这个块
                    src_copy_id = self.created_copies.get((edge.src_node, block_id))
                    actual_src = src_copy_id if src_copy_id else edge.src_node
                    
                    # 为副本创建输入边
                    new_edge = EdgeModel(
                        id=f"edge_{uuid.uuid4().hex[:8]}",
                        src_node=actual_src,
                        src_port=edge.src_port,
                        dst_node=copy_id,
                        dst_port=edge.dst_port,
                    )
                    edges_to_create.append(new_edge)
        
        # 删除旧边
        for edge_id in edges_to_remove:
            if edge_id in self.model.edges:
                del self.model.edges[edge_id]
        
        # 添加新边
        for edge in edges_to_create:
            self.model.edges[edge.id] = edge
    
    def _get_node_block(self, node_id: str) -> Optional[str]:
        """获取节点所属的块ID"""
        # 流程节点
        if node_id in self._flow_to_block:
            return self._flow_to_block[node_id]
        
        # 数据节点：检查它被哪个块消费
        # 这里需要根据消费者来判断
        out_edges = self._data_out_edges_by_src.get(node_id, [])
        for edge in out_edges:
            dst_id = edge.dst_node
            if dst_id in self._flow_to_block:
                return self._flow_to_block[dst_id]
        
        # 如果没有直接消费者，检查它属于哪个块的闭包
        for block_id, dependency in self.block_dependencies.items():
            if node_id in dependency.full_data_closure:
                return block_id
        
        return None
    
    def _dedupe_edges(self) -> None:
        """去除重复边"""
        seen_edges: Dict[Tuple[str, str, str, str], str] = {}
        edges_to_remove: List[str] = []
        
        for edge_id, edge in self.model.edges.items():
            key = (edge.src_node, edge.src_port, edge.dst_node, edge.dst_port)
            if key in seen_edges:
                edges_to_remove.append(edge_id)
            else:
                seen_edges[key] = edge_id
        
        for edge_id in edges_to_remove:
            del self.model.edges[edge_id]
    
    def get_block_copy_mapping(self, block_id: str) -> Dict[str, str]:
        """获取指定块的副本映射：原始ID -> 副本ID"""
        mapping: Dict[str, str] = {}
        for (original_id, bid), copy_id in self.created_copies.items():
            if bid == block_id:
                mapping[original_id] = copy_id
        return mapping
    
    def get_block_owned_nodes(self, block_id: str) -> Set[str]:
        """获取指定块"拥有"的数据节点（原始节点，非副本）"""
        owned: Set[str] = set()
        for original_id, plan in self.copy_plans.items():
            if plan.owner_block_id == block_id:
                owned.add(original_id)
        
        # 加上只被这个块使用的节点
        dependency = self.block_dependencies.get(block_id)
        if dependency:
            for data_id in dependency.full_data_closure:
                if data_id not in self.copy_plans:
                    owned.add(data_id)
        
        return owned
    
    def get_block_data_nodes(self, block_id: str) -> Set[str]:
        """获取指定块应该放置的所有数据节点ID
        
        包括：拥有的原始节点 + 该块的副本节点
        """
        result: Set[str] = set()
        
        # 该块拥有的原始节点
        result.update(self.get_block_owned_nodes(block_id))
        
        # 该块的副本节点
        for (original_id, bid), copy_id in self.created_copies.items():
            if bid == block_id:
                result.add(copy_id)
        
        return result
