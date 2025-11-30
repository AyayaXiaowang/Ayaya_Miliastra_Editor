"""
节点图核心配置。
从 `extended_configs.py` 聚合文件中拆分而来，现作为节点图相关的专门模块使用。
"""
from dataclasses import dataclass, field
from typing import List, Dict
from enum import Enum


# ============================================================================
# 节点图核心
# ============================================================================

class NodeGraphType(Enum):
    """节点图类型"""
    ENTITY_GRAPH = "实体节点图"
    UNIT_STATE_GRAPH = "单位状态节点图"
    PROFESSION_GRAPH = "职业节点图"
    SKILL_GRAPH = "技能节点图"
    LOCAL_FILTER_GRAPH = "本地过滤器节点图"


@dataclass
class NodeGraphConfig:
    """
    节点图配置
    参考：节点图.md
    
    节点图是自定义逻辑的载体
    """
    graph_name: str = ""
    graph_type: NodeGraphType = NodeGraphType.ENTITY_GRAPH
    execution_location: str = "服务端"  # 服务端、客户端
    
    # 节点图生命周期
    lifecycle_owner: str = ""  # 生命周期跟随的对象
    
    doc_reference: str = "节点图.md"
    
    notes: str = """
    节点图类型：
    1. 实体节点图 - 挂载于实体上，生命周期跟随实体
    2. 单位状态节点图 - 挂载于单位状态上，生命周期跟随单位状态
    3. 职业节点图 - 挂载于职业配置上，生命周期跟随职业
    4. 技能节点图 - 自定义技能使用的节点图
    5. 本地过滤器节点图 - 在组件中使用，描述自定义判定规则
    """


@dataclass
class UniversalNodeFunctionConfig:
    """
    节点图通用节点功能配置
    参考：节点图通用节点功能说明.md
    """
    # 双分支
    dual_branch_enabled: bool = True
    # 多分支
    multi_branch_enabled: bool = True
    # 循环
    loop_enabled: bool = True
    # 类型转换
    type_conversion_enabled: bool = True
    # 转发事件
    event_forward_enabled: bool = True
    # 打印字符串
    print_string_enabled: bool = True
    
    doc_reference: str = "节点图通用节点功能说明.md"


# ============================================================================
# 节点图调试与高级特性
# ============================================================================

@dataclass
class NodeGraphDebugConfig:
    """
    节点图日志调试配置
    参考：节点图日志.md, 复合节点图日志.md, 客户端节点图日志.md
    """
    # 节点图日志
    server_graph_log_enabled: bool = True
    server_graph_log_limit: int = 10  # 服务端节点图筛选上限
    
    # 客户端节点图日志
    client_graph_log_enabled: bool = True
    client_graph_log_limit: int = 99  # 客户端节点图筛选上限
    
    # 复合节点图日志
    compound_node_log_enabled: bool = True
    
    doc_reference: str = "节点图日志.md, 复合节点图日志.md, 客户端节点图日志.md"


# 结构体类型标识（用于区分不同用途的结构体定义）
STRUCT_TYPE_BASIC: str = "basic"
STRUCT_TYPE_INGAME_SAVE: str = "ingame_save"


# 结构体支持的数据类型（基础结构体）
BASIC_STRUCT_SUPPORTED_TYPES: List[str] = [
    "实体",
    "GUID",
    "整数",
    "布尔值",
    "浮点数",
    "字符串",
    "阵营",
    "三维向量",
    "元件ID",
    "配置ID",
    "结构体",
    "字典",
    "实体列表",
    "GUID列表",
    "整数列表",
    "布尔值列表",
    "浮点数列表",
    "字符串列表",
    "阵营列表",
    "三维向量列表",
    "元件ID列表",
    "配置ID列表",
    "结构体列表",
]

# 局内存档结构体支持的数据类型（不包含字典）
INGAME_SAVE_STRUCT_SUPPORTED_TYPES: List[str] = [
    type_name
    for type_name in BASIC_STRUCT_SUPPORTED_TYPES
    if type_name != "字典"
]


@dataclass
class StructDefinition:
    """
    基础结构体定义
    参考：结构体.md
    
    基础结构体是一种允许创作者将一组不同类型的数据整合在一起的高级数据结构，
    在节点图中作为通用数据容器使用。
    """
    struct_name: str = ""  # 结构体名称（唯一标识）
    members: Dict[str, str] = field(default_factory=dict)  # 成员：{字段名: 类型}
    
    # 支持的数据类型（允许包含字典类型）
    supported_types: List[str] = field(
        default_factory=lambda: list(BASIC_STRUCT_SUPPORTED_TYPES)
    )
    
    doc_reference: str = "结构体.md"
    
    notes: str = """
    基础结构体特点：
    1. 结构体的类型由其名字完全确定
    2. 结构体在节点图中以引用方式传递
    3. 支持结构体嵌套与字典类型字段
    """


@dataclass
class InGameSaveStructDefinition:
    """
    局内存档结构体定义
    参考：结构体.md、局内存档.md
    
    用于局内存档场景的结构体定义，在字段建模方式上与基础结构体保持一致，
    但为了简化局内存档数据的序列化与回放，不允许使用字典类型字段。
    """
    struct_name: str = ""  # 结构体名称（唯一标识）
    members: Dict[str, str] = field(default_factory=dict)  # 成员：{字段名: 类型}
    
    # 支持的数据类型（不包含字典类型）
    supported_types: List[str] = field(
        default_factory=lambda: list(INGAME_SAVE_STRUCT_SUPPORTED_TYPES)
    )
    
    doc_reference: str = "结构体.md"
    
    notes: str = """
    局内存档结构体特点：
    1. 仅用于描述局内存档相关的数据结构
    2. 字段类型集合与基础结构体一致，但显式排除字典类型字段
    3. 适合用于描述可序列化、可回放的局内状态快照
    """

