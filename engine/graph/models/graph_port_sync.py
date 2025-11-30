"""节点图端口同步模块

负责节点端口的动态同步操作，主要用于复合节点引脚更新后的自动同步
"""
from __future__ import annotations
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from engine.graph.models.graph_model import GraphModel, NodeModel


def sync_ports_from_def(node: "NodeModel", node_def) -> bool:
    """从节点定义同步端口信息（用于复合节点引脚更新）
    
    Args:
        node: 节点模型实例
        node_def: NodeDef对象
        
    Returns:
        是否发生了变化
    """
    old_input_names = [port.name for port in node.inputs]
    old_output_names = [port.name for port in node.outputs]
    
    new_input_names = node_def.inputs
    new_output_names = node_def.outputs
    
    # 检查是否有变化
    if old_input_names == new_input_names and old_output_names == new_output_names:
        return False
    
    # 更新端口
    from engine.graph.models.graph_model import PortModel
    node.inputs = [PortModel(name=name, is_input=True) for name in new_input_names]
    node.outputs = [PortModel(name=name, is_input=False) for name in new_output_names]
    node._rebuild_port_maps()
    
    return True


def sync_composite_nodes_from_library(graph: "GraphModel", node_library: Dict) -> int:
    """从节点库同步所有复合节点的端口定义
    
    当复合节点的虚拟引脚被修改后，调用此方法更新节点图中的实例。
    
    Args:
        graph: 节点图模型
        node_library: 节点库字典 {key: NodeDef}
        
    Returns:
        同步更新的节点数量
    """
    if not node_library:
        return 0
    
    updated_count = 0
    for node in graph.nodes.values():
        # 只处理复合节点
        if node.category != "复合节点":
            continue
        
        # 优先使用 composite_id 查找节点定义（稳定标识符，不受改名影响）
        node_def = None
        if node.composite_id:
            # 尝试通过 composite_id 查找（精确匹配）
            for key, candidate_def in node_library.items():
                if hasattr(candidate_def, 'composite_id') and candidate_def.composite_id == node.composite_id:
                    node_def = candidate_def
                    break
        
        # 退化方案：使用 "类别/标题" 查找（可能受改名影响）
        if not node_def:
            node_key = f"{node.category}/{node.title}"
            node_def = node_library.get(node_key)
        
        if node_def:
            # 记录旧端口名称
            old_input_names = [port.name for port in node.inputs]
            old_output_names = [port.name for port in node.outputs]
            
            # 同步端口
            if sync_ports_from_def(node, node_def):
                updated_count += 1
                
                # 建立端口名称映射（旧名称 -> 新名称）
                new_input_names = [port.name for port in node.inputs]
                new_output_names = [port.name for port in node.outputs]
                
                # 更新连接到该节点的所有连线
                _update_edges_after_port_sync(
                    graph,
                    node.id,
                    old_input_names,
                    new_input_names,
                    old_output_names,
                    new_output_names
                )
    
    return updated_count


def _update_edges_after_port_sync(
    graph: "GraphModel",
    node_id: str,
    old_inputs: List[str],
    new_inputs: List[str],
    old_outputs: List[str],
    new_outputs: List[str]
) -> None:
    """更新端口同步后的连线引用
    
    当节点的端口列表改变时（例如复合节点的引脚被修改），
    需要更新所有连接到该节点的连线的端口名称引用。
    
    Args:
        graph: 节点图模型
        node_id: 节点ID
        old_inputs: 旧的输入端口名称列表
        new_inputs: 新的输入端口名称列表
        old_outputs: 旧的输出端口名称列表
        new_outputs: 新的输出端口名称列表
    """
    # 建立端口映射（按位置索引）
    input_mapping = {}
    for i, old_name in enumerate(old_inputs):
        if i < len(new_inputs):
            input_mapping[old_name] = new_inputs[i]
    
    output_mapping = {}
    for i, old_name in enumerate(old_outputs):
        if i < len(new_outputs):
            output_mapping[old_name] = new_outputs[i]
    
    # 更新所有相关的连线
    for edge in graph.edges.values():
        # 更新源端口（输出端口）
        if edge.src_node == node_id and edge.src_port in output_mapping:
            old_port = edge.src_port
            new_port = output_mapping[old_port]
            if old_port != new_port:
                edge.src_port = new_port
        
        # 更新目标端口（输入端口）
        if edge.dst_node == node_id and edge.dst_port in input_mapping:
            old_port = edge.dst_port
            new_port = input_mapping[old_port]
            if old_port != new_port:
                edge.dst_port = new_port


