"""端口类型匹配系统

职责边界：
- 连线/连接判定侧请优先使用 `is_flow_port_with_context` 判断流程端口（名称规则 + 语义增强）。
- 节点定义 `NodeDef.get_port_type` 仅负责数据类型获取/推断，流程口类型的兜底只用于防错，不替代连线侧的上下文判断。
"""

from typing import Optional, Any, Dict
from engine.utils.graph.graph_utils import is_flow_port_name as is_flow_port_by_name

from engine.type_registry import (
    TYPE_CAMP,
    TYPE_CONFIG_ID,
    TYPE_COMPONENT_ID,
    TYPE_ENTITY,
    TYPE_FLOW,
    TYPE_GENERIC,
    TYPE_GENERIC_DICT,
    TYPE_GENERIC_LIST,
    TYPE_GUID,
    TYPE_INTEGER,
    TYPE_FLOAT,
    TYPE_BOOLEAN,
    TYPE_STRING,
    TYPE_STRUCT,
    TYPE_STRUCT_LIST,
    TYPE_VECTOR3,
    is_dict_type_name,
    is_list_type_name,
)


# 流程端口特殊类型
FLOW_PORT_TYPE = TYPE_FLOW

# 常见数据端口类型常量（统一集中定义）
ANY_PORT_TYPE = TYPE_GENERIC
GENERIC_PORT_TYPE = TYPE_GENERIC
# 兼容不同术语的布尔类型关键字集合（用于检索/统计等弱语义场景）
BOOLEAN_TYPE_KEYWORDS = ("布尔", "布尔值")


def _is_dict_type(port_type: str) -> bool:
    """判断是否为字典类型（包括别名字典：以“字典”结尾的类型名）。"""
    return is_dict_type_name(port_type)


def _is_list_type(port_type: str) -> bool:
    """判断是否为列表类型（任何以“列表”结尾的类型名）。"""
    return is_list_type_name(port_type)


def can_connect_ports(src_type: str, dst_type: str) -> bool:
    """判断两个端口是否可以连接
    
    规则：
    1. 只允许完全匹配的类型连接
    2. 泛型类型可以连接任何类型
    3. 流程端口只能连接流程端口
    4. 不允许任何隐式类型转换（必须通过转换节点显式转换）
    
    Args:
        src_type: 源端口类型
        dst_type: 目标端口类型
        
    Returns:
        是否可以连接
    """
    # 规范化为字符串并去除首尾空白，避免 None 或空字符串带来的干扰
    src = str(src_type or "").strip()
    dst = str(dst_type or "").strip()

    # 流程端口只能连接流程端口
    if src == FLOW_PORT_TYPE or dst == FLOW_PORT_TYPE:
        return src == dst

    # 泛型字典：只接受任意“字典类型”（包括别名字典）
    if src == TYPE_GENERIC_DICT or dst == TYPE_GENERIC_DICT:
        other = dst if src == TYPE_GENERIC_DICT else src
        return _is_dict_type(other)

    # 泛型列表：只接受任意“列表类型”
    if src == TYPE_GENERIC_LIST or dst == TYPE_GENERIC_LIST:
        other = dst if src == TYPE_GENERIC_LIST else src
        return _is_list_type(other)

    # 泛型/任意：可以接受任何类型
    # 注意：必须放在“结构体家族”规则之前，否则会把『泛型 ↔ 结构体』误判为不兼容。
    if src in (ANY_PORT_TYPE, GENERIC_PORT_TYPE) or dst in (ANY_PORT_TYPE, GENERIC_PORT_TYPE):
        return True

    # 结构体家族：
    # - "结构体" 代表“泛型结构体”占位；
    # - 具体结构体类型使用 "结构体<结构体名>" 表示（由 UI/类型代理生成）；
    # - 连线规则：仅允许 **同名互连**（避免未绑定结构体名时的“泛型结构体”误连到任意具体结构体）。
    struct_prefix = f"{TYPE_STRUCT}<"
    if src == TYPE_STRUCT or dst == TYPE_STRUCT or src.startswith(struct_prefix) or dst.startswith(struct_prefix):
        src_is_struct_family = src == TYPE_STRUCT or src.startswith(struct_prefix)
        dst_is_struct_family = dst == TYPE_STRUCT or dst.startswith(struct_prefix)
        if not (src_is_struct_family and dst_is_struct_family):
            return False
        return src == dst

    # 结构体列表家族：与结构体同口径（仅同名互连）
    struct_list_prefix = f"{TYPE_STRUCT_LIST}<"
    if (
        src == TYPE_STRUCT_LIST
        or dst == TYPE_STRUCT_LIST
        or src.startswith(struct_list_prefix)
        or dst.startswith(struct_list_prefix)
    ):
        src_is_struct_list_family = src == TYPE_STRUCT_LIST or src.startswith(struct_list_prefix)
        dst_is_struct_list_family = dst == TYPE_STRUCT_LIST or dst.startswith(struct_list_prefix)
        if not (src_is_struct_list_family and dst_is_struct_list_family):
            return False
        return src == dst

    # 完全匹配
    if src == dst:
        return True

    # ❌ 不允许任何隐式类型转换
    # 所有类型转换必须通过专门的转换节点显式实现
    # TYPE_CONVERSIONS 定义的转换规则仅用于转换节点，不用于直接连接
    
    return False


def get_port_type_color(port_type: str) -> str:
    """获取端口类型的颜色（用于UI显示）
    
    Args:
        port_type: 端口类型
        
    Returns:
        颜色代码（十六进制）
    """
    type_colors = {
        FLOW_PORT_TYPE: "#FFD700",  # 金黄色（流程）
        TYPE_CAMP: "#6BCB77",  # 草绿色（阵营）
        TYPE_ENTITY: "#FF6B6B",  # 红色
        TYPE_GUID: "#FFA500",  # 橙色
        TYPE_INTEGER: "#4ECDC4",  # 青色
        TYPE_FLOAT: "#45B7D1",  # 蓝色
        TYPE_BOOLEAN: "#A8E6CF",  # 绿色
        TYPE_STRING: "#FFD93D",  # 黄色
        TYPE_VECTOR3: "#C77DFF",  # 紫色
        TYPE_CONFIG_ID: "#F08A5D",  # 橘红
        TYPE_COMPONENT_ID: "#B8336A",  # 洋红
        TYPE_GENERIC: "#95A5A6",  # 灰色
    }
    
    # 列表类型使用基础类型的颜色但更浅
    if port_type.endswith("列表"):
        base_type = port_type[: -len("列表")]
        if base_type in type_colors:
            return type_colors[base_type]
    
    return type_colors.get(port_type, "#95A5A6")


def is_flow_port_with_context(node: Optional[Any], port_name: str, is_source: bool, node_library: Optional[Dict] = None) -> bool:
    """上下文感知的流程端口判断。

    判断优先级：
    1. 从节点定义（NodeDef）的端口类型字典中查找
    2. 基于端口名称判定（`is_flow_port_name`）
    3. 语义增强：多分支节点的所有输出端口视为流程端口

    Args:
        node: 节点对象（需具备 `title`/`outputs`/`category` 等属性；允许为 None）
        port_name: 端口名称
        is_source: True 表示作为源端口（输出端），False 表示目标端口（输入端）
        node_library: 节点库（可选），用于查找 NodeDef

    Returns:
        是否为流程端口
    """
    # 优先级1：从节点定义的端口类型字典中查找
    if node is not None and node_library is not None:
        # 尝试从节点库查找 NodeDef
        node_category = getattr(node, "category", "")
        node_title = getattr(node, "title", "")
        
        # 构建节点库键（格式：category/title）
        # 注意：复合节点在节点库中的键始终是"复合节点/xxx"
        node_keys_to_try = [
            f"{node_category}/{node_title}",  # 常规节点
            f"复合节点/{node_title}",  # 复合节点（无论category是什么，都尝试这个键）
        ]
        
        node_def = None
        for node_key in node_keys_to_try:
            node_def = node_library.get(node_key)
            if node_def is not None:
                break
        
        if node_def is not None:
            # 根据是否为源端口选择对应的类型字典
            type_dict = node_def.output_types if is_source else node_def.input_types
            if port_name in type_dict:
                port_type = type_dict[port_name]
                # 如果显式定义为"流程"类型，直接返回 True
                if port_type == FLOW_PORT_TYPE:
                    return True
    
    # 优先级2：基于名称的快速判定
    if is_flow_port_by_name(port_name):
        return True

    # 优先级3：语义增强：多分支节点的所有输出端口均为流程端口
    if node is not None and is_source:
        node_title = getattr(node, "title", "")
        if node_title == "多分支":
            output_ports = getattr(node, "outputs", [])
            output_names = [getattr(p, "name", "") for p in output_ports]
            return port_name in output_names if output_names else False

    return False
