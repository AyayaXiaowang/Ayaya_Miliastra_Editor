"""节点图序列化与反序列化模块

负责节点图数据结构的序列化和反序列化操作
"""
from __future__ import annotations
from typing import Dict, List, TYPE_CHECKING, Tuple, Any

if TYPE_CHECKING:
    from engine.graph.models.graph_model import GraphModel, NodeModel, EdgeModel, PortModel, BasicBlock


def _parse_string_list(value: Any, *, field_name: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError(f"节点图序列化格式错误：字段 '{field_name}' 必须为 list[str]")
    result: List[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"节点图序列化格式错误：字段 '{field_name}' 必须为 list[str]")
        result.append(item)
    return result


def _parse_int_to_str_dict(value: Any, *, field_name: str) -> Dict[int, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError(f"节点图序列化格式错误：字段 '{field_name}' 必须为 dict[int, str]")
    result: Dict[int, str] = {}
    for raw_key, raw_value in value.items():
        if isinstance(raw_key, int):
            key = raw_key
        elif isinstance(raw_key, str) and raw_key.isdigit():
            key = int(raw_key)
        else:
            raise TypeError(
                f"节点图序列化格式错误：字段 '{field_name}' 的 key 必须为 int 或数字字符串"
            )
        if isinstance(raw_value, str):
            result[key] = raw_value
        else:
            result[key] = str(raw_value)
    return result


def _parse_port_list(ports_data: Any, is_input: bool) -> List["PortModel"]:
    """解析端口列表（唯一格式：list[str]）。"""
    from engine.graph.models.graph_model import PortModel
    names = _parse_string_list(ports_data, field_name="inputs/outputs")
    return [PortModel(name=name, is_input=is_input) for name in names]


def serialize_graph(graph: "GraphModel") -> dict:
    """序列化节点图为字典
    
    Args:
        graph: 节点图模型
        
    Returns:
        序列化后的字典
    """
    # 按 ID 稳定排序，减少文件 diff 噪音
    sorted_nodes = sorted(graph.nodes.values(), key=lambda n: n.id)
    sorted_edges = sorted(graph.edges.values(), key=lambda e: e.id)
    
    return {
        "graph_id": graph.graph_id,
        "graph_name": graph.graph_name,
        "description": graph.description,
        # 事件流顺序（用于稳定布局与编号）
        "event_flow_order": list(graph.event_flow_order or []),
        # 事件标题顺序（用于缺失source_lineno或ID映射时的稳定回退）
        "event_flow_titles": list(graph.event_flow_titles or []),
        "nodes": [
            {
                "id": node.id,
                "title": node.title,
                "category": node.category,
                "composite_id": node.composite_id,  # 复合节点ID（用于精确引用）
                "pos": list(node.pos),
                "inputs": [port.name for port in node.inputs],
                "outputs": [port.name for port in node.outputs],
                "input_constants": node.input_constants,
                # 源代码行范围（用于UI错误定位与布局稳定排序；可选字段）
                "source_lineno": node.source_lineno,
                "source_end_lineno": node.source_end_lineno,
                # 虚拟引脚相关字段（仅在is_virtual_pin=True时有意义）
                "is_virtual_pin": node.is_virtual_pin,
                "virtual_pin_index": node.virtual_pin_index,
                "virtual_pin_type": node.virtual_pin_type,
                "is_virtual_pin_input": node.is_virtual_pin_input,
                # 双向无痛编辑：用户自定义信息
                "custom_var_names": node.custom_var_names,
                "custom_comment": node.custom_comment,
                "inline_comment": node.inline_comment,
                # 数据节点副本元信息（跨块复制）
                "is_data_node_copy": bool(node.is_data_node_copy),
                "original_node_id": node.original_node_id,
                "copy_block_id": node.copy_block_id,
            }
            for node in sorted_nodes
        ],
        "edges": [
            {
                "id": edge.id,
                "src_node": edge.src_node,
                "src_port": edge.src_port,
                "dst_node": edge.dst_node,
                "dst_port": edge.dst_port,
            }
            for edge in sorted_edges
        ],
        "graph_variables": graph.graph_variables,
        "metadata": graph.metadata,
        # 双向无痛编辑：用户自定义信息
        "event_flow_comments": graph.event_flow_comments,
        "preserve_formatting": graph.preserve_formatting,
        # 基本块（用于UI可视化与避免二次计算）
        "basic_blocks": [
            {
                "nodes": basic_block.nodes,
                "color": basic_block.color,
                "alpha": basic_block.alpha,
            }
            for basic_block in (graph.basic_blocks or [])
        ],
    }


def deserialize_graph(data: dict) -> "GraphModel":
    """从字典反序列化节点图
    
    Args:
        data: 序列化的字典数据
        
    Returns:
        节点图模型实例
    """
    from engine.graph.models.graph_model import GraphModel, NodeModel, EdgeModel, BasicBlock
    
    graph = GraphModel(
        graph_id=data.get("graph_id", ""),
        graph_name=data.get("graph_name", ""),
        description=data.get("description", "")
    )
    graph.metadata = data.get("metadata", {})
    
    # 事件流顺序（用于稳定事件布局顺序）
    if "event_flow_order" in data:
        graph.event_flow_order = _parse_string_list(
            data.get("event_flow_order"),
            field_name="event_flow_order",
        )
    
    # 事件标题顺序（用于ID缺失时的稳定回退）
    if "event_flow_titles" in data:
        graph.event_flow_titles = _parse_string_list(
            data.get("event_flow_titles"),
            field_name="event_flow_titles",
        )
    
    # 双向无痛编辑：加载用户自定义信息
    graph.event_flow_comments = _parse_int_to_str_dict(
        data.get("event_flow_comments", {}),
        field_name="event_flow_comments",
    )
    graph.preserve_formatting = data.get("preserve_formatting", True)
    
    nodes_data = data.get("nodes", [])
    if not isinstance(nodes_data, list):
        raise TypeError("节点图序列化格式错误：字段 'nodes' 必须为 list[dict]")

    for node_data in nodes_data:
        if not isinstance(node_data, dict):
            raise TypeError("节点图序列化格式错误：字段 'nodes' 必须为 list[dict]")
        node = NodeModel(
            id=node_data["id"],
            title=node_data.get("title", ""),
            category=node_data.get("category", ""),
            composite_id=node_data.get("composite_id", ""),  # 加载复合节点ID
            pos=tuple(node_data.get("pos", [0.0, 0.0])),
        )
        
        # 使用辅助函数解析端口列表，支持三种格式
        node.inputs = _parse_port_list(node_data.get("inputs", []), is_input=True)
        node.outputs = _parse_port_list(node_data.get("outputs", []), is_input=False)
        
        node.input_constants = dict(node_data.get("input_constants", {}))

        # 恢复可选的源码行范围（若存在则用于UI错误定位）
        node.source_lineno = int(node_data.get("source_lineno", 0) or 0)
        node.source_end_lineno = int(node_data.get("source_end_lineno", node.source_lineno or 0) or 0)

        # 变参节点端口补全：若端口名中存在形如"0~99"的占位输入，但当前没有任何数字输入端口，
        # 则为模型补充一个默认数字端口"0"，以便UI显示"默认口+加号"体验。
        has_variadic_placeholder = any("~" in str(port.name) for port in (node.inputs or []))
        if has_variadic_placeholder and not any(
            str(port.name).isdigit() for port in (node.inputs or [])
        ):
            from engine.graph.models.graph_model import PortModel
            node.inputs.append(PortModel(name="0", is_input=True))
        
        # 加载虚拟引脚相关字段
        node.is_virtual_pin = node_data.get("is_virtual_pin", False)
        node.virtual_pin_index = node_data.get("virtual_pin_index", 0)
        node.virtual_pin_type = node_data.get("virtual_pin_type", "")
        node.is_virtual_pin_input = node_data.get("is_virtual_pin_input", True)

        # 数据节点副本元信息（跨块复制）
        node.is_data_node_copy = bool(node_data.get("is_data_node_copy", False))
        node.original_node_id = node_data.get("original_node_id", "")
        node.copy_block_id = node_data.get("copy_block_id", "")
        if not node.is_data_node_copy:
            inferred_flag, inferred_original, inferred_block = _infer_copy_metadata_from_id(node.id)
            if inferred_flag:
                node.is_data_node_copy = True
                if not node.original_node_id:
                    node.original_node_id = inferred_original
                if not node.copy_block_id:
                    node.copy_block_id = inferred_block
        
        # 双向无痛编辑：加载用户自定义信息
        node.custom_var_names = node_data.get("custom_var_names", {})
        node.custom_comment = node_data.get("custom_comment", "")
        node.inline_comment = node_data.get("inline_comment", "")
        
        # 初始化端口映射缓存
        node._rebuild_port_maps()
        
        graph.nodes[node.id] = node
    
    edges_data = data.get("edges", [])
    if not isinstance(edges_data, list):
        raise TypeError("节点图序列化格式错误：字段 'edges' 必须为 list[dict]")

    for edge_data in edges_data:
        if not isinstance(edge_data, dict):
            raise TypeError("节点图序列化格式错误：字段 'edges' 必须为 list[dict]")
        edge = EdgeModel(
            id=edge_data["id"],
            src_node=edge_data["src_node"],
            src_port=edge_data["src_port"],
            dst_node=edge_data["dst_node"],
            dst_port=edge_data["dst_port"],
        )
        graph.edges[edge.id] = edge
    
    # 加载节点图变量
    graph.graph_variables = data.get("graph_variables", [])

    # 可选：加载基本块（避免场景初始化时重复识别）
    basic_blocks_data = data.get("basic_blocks", [])
    if isinstance(basic_blocks_data, list) and basic_blocks_data:
        parsed_blocks: List[BasicBlock] = []
        for block_data in basic_blocks_data:
            nodes_list = list(block_data.get("nodes", [])) if isinstance(block_data.get("nodes", []), list) else []
            color_value = str(block_data.get("color", "#FF5E9C"))
            alpha_value = float(block_data.get("alpha", 0.2))
            parsed_blocks.append(BasicBlock(nodes=nodes_list, color=color_value, alpha=alpha_value))
        graph.basic_blocks = parsed_blocks
    
    # 🔧 修复：更新_next_id以避免ID冲突
    max_id = 0
    for node_id in graph.nodes.keys():
        if node_id.startswith("node_"):
            parts = node_id.split("_")
            if len(parts) > 1 and parts[1].isdigit():
                max_id = max(max_id, int(parts[1]))
    
    for edge_id in graph.edges.keys():
        if edge_id.startswith("edge_"):
            parts = edge_id.split("_")
            if len(parts) > 1 and parts[1].isdigit():
                max_id = max(max_id, int(parts[1]))
    
    graph._next_id = max_id + 1
    
    return graph


def _strip_copy_suffix(node_id: str) -> str:
    marker = "_copy_"
    result = node_id or ""
    while True:
        idx = result.rfind(marker)
        if idx == -1:
            break
        result = result[:idx]
    return result


def _infer_copy_metadata_from_id(node_id: str) -> Tuple[bool, str, str]:
    marker = "_copy_"
    if not node_id or marker not in node_id:
        return False, "", ""
    original_id = _strip_copy_suffix(node_id)
    if not original_id or original_id == node_id:
        return False, "", ""
    suffix = node_id.rsplit(marker, 1)[-1]
    copy_block_id = ""
    if "_" in suffix:
        candidate_block, _ = suffix.rsplit("_", 1)
        copy_block_id = candidate_block
    return True, original_id, copy_block_id

