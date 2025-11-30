"""节点图哈希计算模块

负责计算节点图内容的哈希值，用于判断节点图是否真正发生变化
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.graph.models.graph_model import GraphModel


def get_content_hash(graph: "GraphModel") -> str:
    """计算节点图内容的哈希值（不包含位置信息）
    
    用于判断节点图是否真正发生变化。
    只计算有意义的数据：节点结构、连线、常量、变量、注释等，不包含节点位置。
    
    Args:
        graph: 节点图模型
    
    Returns:
        内容的MD5哈希值
    """
    from engine.utils.graph.graph_utils import compute_stable_md5_from_data
    
    # 序列化数据，但排除位置信息
    content_data = {
        "graph_id": graph.graph_id,
        "graph_name": graph.graph_name,
        "description": graph.description,
        "nodes": [
            {
                "id": node.id,
                "title": node.title,
                "category": node.category,
                "composite_id": node.composite_id,  # 复合节点ID
                # 不包含 pos - 这是关键
                "inputs": [port.name for port in node.inputs],
                "outputs": [port.name for port in node.outputs],
                "input_constants": node.input_constants,
                # 虚拟引脚相关字段
                "is_virtual_pin": node.is_virtual_pin,
                "virtual_pin_index": node.virtual_pin_index,
                "virtual_pin_type": node.virtual_pin_type,
                "is_virtual_pin_input": node.is_virtual_pin_input,
                # 用户自定义信息
                "custom_var_names": node.custom_var_names,
                "custom_comment": node.custom_comment,
                "inline_comment": node.inline_comment,
            }
            for node in sorted(graph.nodes.values(), key=lambda x: x.id)  # 排序确保稳定性
        ],
        "edges": [
            {
                "src_node": edge.src_node,
                "src_port": edge.src_port,
                "dst_node": edge.dst_node,
                "dst_port": edge.dst_port,
            }
            for edge in sorted(graph.edges.values(), key=lambda x: x.id)  # 排序确保稳定性
        ],
        "graph_variables": graph.graph_variables,
        "event_flow_comments": graph.event_flow_comments,
    }
    return compute_stable_md5_from_data(content_data)


