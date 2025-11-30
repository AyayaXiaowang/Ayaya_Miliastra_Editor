"""节点图数据处理工具函数

提供统一的节点图数据格式处理、端口提取、常量判断等工具函数，
避免在多个模块中重复相同的逻辑。
"""

from typing import List, Dict, Any, Set, Union
import re
import json
import hashlib


def _normalize_graph_collection(collection: Union[Dict, List]) -> List[Dict]:
    """将节点或边集合统一转换为列表格式，避免在多处重复判定类型。"""
    if isinstance(collection, dict):
        return list(collection.values())
    if isinstance(collection, list):
        return collection
    return collection if collection else []


def normalize_graph_nodes(nodes_data: Union[Dict, List]) -> List[Dict]:
    """统一处理字典/列表格式的节点数据
    
    节点图数据支持两种格式：
    - 字典格式：{node_id: node_data, ...}
    - 列表格式：[node_data, node_data, ...]
    
    Args:
        nodes_data: 节点数据（字典或列表）
        
    Returns:
        统一的列表格式
        
    Example:
        >>> nodes = normalize_graph_nodes(graph_data.get("nodes", []))
        >>> for node in nodes:
        ...     process_node(node)
    """
    return _normalize_graph_collection(nodes_data)


def normalize_graph_edges(edges_data: Union[Dict, List]) -> List[Dict]:
    """统一处理字典/列表格式的边数据
    
    边数据支持两种格式：
    - 字典格式：{edge_id: edge_data, ...}
    - 列表格式：[edge_data, edge_data, ...]
    
    Args:
        edges_data: 边数据（字典或列表）
        
    Returns:
        统一的列表格式
        
    Example:
        >>> edges = normalize_graph_edges(graph_data.get("edges", []))
        >>> for edge in edges:
        ...     process_edge(edge)
    """
    return _normalize_graph_collection(edges_data)


def extract_port_names(ports: List[Union[str, Dict]]) -> Set[str]:
    """从端口列表提取端口名称集合
    
    端口可以是字符串列表或字典列表（包含name字段）
    
    Args:
        ports: 端口列表，元素可以是字符串或字典
        
    Returns:
        端口名称的集合
        
    Example:
        >>> ports = ["流程入", {"name": "参数A"}, {"name": "参数B"}]
        >>> names = extract_port_names(ports)
        >>> print(names)
        {'流程入', '参数A', '参数B'}
    """
    port_names = set()
    for port in ports:
        if isinstance(port, str):
            port_names.add(port)
        elif isinstance(port, dict):
            name = port.get("name", "")
            if name:
                port_names.add(name)
    return port_names


def is_reasonable_constant(param_name: str, param_value: Any) -> bool:
    """判断是否为合理的常量值
    
    某些常量值是合理的固定值，不应被标记为硬编码：
    - 布尔值（True/False）
    - 空值（空字符串、0、0.0）
    - 全零向量（[0,0,0] 等）
    - 标识性参数（变量名、定时器名称等）
    
    Args:
        param_name: 参数名称
        param_value: 参数值
        
    Returns:
        True 表示这是合理的常量值，False 表示可能需要改为变量
        
    Example:
        >>> is_reasonable_constant("启用", "True")
        True
        >>> is_reasonable_constant("速度", "100")
        False
    """
    # 标识性参数：名称类参数通常是硬编码的，这是合理的
    identifier_params = {
        "变量名", "运动器名称", "字符串", "标签名", 
        "定时器名称", "名称", "ID", "标识符"
    }
    
    if param_name in identifier_params:
        return True
    
    # 合理的固定值
    reasonable_values = {
        "True", "False",  # 布尔值
        "", "0", "0.0",   # 空值和零
        "[0.0, 0.0, 0.0]", "[0, 0, 0]",  # 全零向量
        "(0, 0, 0)", "(0.0, 0.0, 0.0)",   # 全零元组
        "None", "null"    # 空引用
    }
    
    value_str = str(param_value).strip()
    return value_str in reasonable_values


def get_node_display_info(node: Dict) -> tuple[str, str, str]:
    """获取节点的显示信息（ID、名称、类别）
    
    统一处理节点数据中可能存在的不同字段名称：
    - 名称：title 或 name
    - 类别：category
    - ID：id
    
    Args:
        node: 节点数据字典
        
    Returns:
        (node_id, node_name, node_category) 元组
        
    Example:
        >>> node_id, node_name, category = get_node_display_info(node)
        >>> print(f"节点 {node_name} (ID: {node_id}, 类别: {category})")
    """
    node_id = node.get("id", "")
    node_name = node.get("title", node.get("name", ""))
    node_category = node.get("category", "")
    return node_id, node_name, node_category


def build_node_map(nodes: List[Dict]) -> Dict[str, Dict]:
    """构建节点ID到节点数据的映射
    
    Args:
        nodes: 节点列表
        
    Returns:
        {node_id: node_data} 字典
        
    Example:
        >>> nodes = normalize_graph_nodes(graph_data.get("nodes", []))
        >>> node_map = build_node_map(nodes)
        >>> node = node_map.get(node_id)
    """
    return {node.get("id"): node for node in nodes if node.get("id")}


def build_connection_map(connections: List[Dict]) -> Dict[tuple, tuple]:
    """构建连接映射：每个节点的每个输入端口连接到哪个节点的哪个输出端口
    
    Args:
        connections: 连接列表
        
    Returns:
        {(to_node, to_input): (from_node, from_output)} 字典
        
    Example:
        >>> connections = graph_data.get("connections", [])
        >>> conn_map = build_connection_map(connections)
        >>> source = conn_map.get((node_id, "参数A"))
        >>> if source:
        ...     from_node, from_output = source
    """
    connection_map = {}
    for conn in connections:
        from_node = conn.get("from_node")
        from_output = conn.get("from_output")
        to_node = conn.get("to_node")
        to_input = conn.get("to_input")
        
        if from_node and to_node and from_output and to_input:
            connection_map[(to_node, to_input)] = (from_node, from_output)
    
    return connection_map


def is_flow_port_name(port_name: str) -> bool:
    """判断端口名称是否为流程端口
    
    流程端口包括：
    - 包含"流程"关键字的端口
    - 命名的流程端口：是、否、默认、循环体、循环完成等
    - 流程入口：流程入、跳出循环
    - 多分支节点的动态端口：分支_0, 分支_1 等
    
    Args:
        port_name: 端口名称
        
    Returns:
        True 表示是流程端口
        
    Example:
        >>> is_flow_port_name("流程入")
        True
        >>> is_flow_port_name("参数A")
        False
        >>> is_flow_port_name("分支_0")
        True
    """
    port_name_lower = port_name.lower()
    flow_out_ports = {'流程出', '是', '否', '默认', '循环体', '循环完成'}
    flow_in_ports = {'流程入', '跳出循环'}
    
    # 检查是否包含流程关键字或在预定义集合中（兼容英文关键字 'flow'）
    if ('流程' in port_name_lower or 
        port_name_lower == 'flow' or 
        port_name in flow_out_ports or 
        port_name in flow_in_ports):
        return True
    
    # 提示：多分支节点的动态端口（如“分支_0/分支-0/分支0/0/1/...”) 在验证阶段结合上下文判断，
    # 此处不对纯数字或“分支_*”名称做全局判定，避免将数据节点（如拼装列表的数字输入端）误识别为流程端口。
    
    return False


def compute_stable_md5_from_data(data: Any) -> str:
    """对任意可序列化数据计算稳定的 MD5 值。
    
    规则：
    - 使用 json.dumps进行序列化，开启 sort_keys=True，确保字典键顺序稳定
    - ensure_ascii=False 保留中文
    - separators=(",", ":") 去除多余空格，保证结果稳定
    """
    serialized = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.md5(serialized.encode("utf-8")).hexdigest()


