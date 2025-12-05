from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Literal

from engine.utils.graph.graph_utils import is_flow_port_name
from engine.nodes.port_type_system import FLOW_PORT_TYPE
from .port_name_rules import get_dynamic_port_type
from .constants import NodeCategory, ALLOWED_SCOPES


@dataclass
class NodeDef:
    name: str
    category: NodeCategory
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    
    # 元数据
    description: str = ""
    scopes: List[str] = field(default_factory=list)  # ["server"] 或 ["client"] 或 ["server", "client"]
    mount_restrictions: List[str] = field(default_factory=list)
    doc_reference: str = ""
    
    # ⚠️ 核心：显式端口类型（从知识库提取）
    input_types: Dict[str, str] = field(default_factory=dict)   # {端口名: 数据类型}
    output_types: Dict[str, str] = field(default_factory=dict)  # {端口名: 数据类型}
    
    # 泛型约束：限定声明为泛型的端口实际允许的具体类型集合
    input_generic_constraints: Dict[str, List[str]] = field(default_factory=dict)
    output_generic_constraints: Dict[str, List[str]] = field(default_factory=dict)
    # 输入/输出端口的枚举候选项配置：{端口名: [选项1, 选项2, ...]}
    input_enum_options: Dict[str, List[str]] = field(default_factory=dict)
    output_enum_options: Dict[str, List[str]] = field(default_factory=dict)
    
    # 动态端口类型（用于支持运行时添加的端口）
    dynamic_port_type: str = ""  # 动态端口的默认类型，如"流程"、"泛型"等
    
    # 复合节点特殊标记
    is_composite: bool = False  # 是否是复合节点
    composite_id: str = ""  # 复合节点ID（仅当is_composite=True时有效）
    
    def is_available_in_scope(self, scope: str) -> bool:
        """检查节点是否在指定作用域可用。

        作用域判定优先级：
        1. 若 scopes 非空：仅当 scope 在 scopes 中时可用；
        2. 若 scopes 为空：
           - 若 doc_reference 中包含 \"服务器节点/\"，视为 server 节点；
           - 若 doc_reference 中包含 \"客户端节点/\"，视为 client 节点；
           - 若二者都不包含，则视为通用节点（在所有受支持作用域中均可用）。
        """
        if self.scopes:
            return scope in self.scopes
        
        doc_path = str(self.doc_reference or "")
        inferred_scopes: List[str] = []
        if "服务器节点/" in doc_path:
            inferred_scopes.append("server")
        if "客户端节点/" in doc_path:
            inferred_scopes.append("client")
        
        if inferred_scopes:
            return scope in inferred_scopes
        
        # 没有显式 scopes，且文档路径无法推断作用域时，默认视为通用节点
        return scope in ALLOWED_SCOPES
    
    def get_port_type(self, port_name: str, is_input: bool) -> str:
        """获取端口类型（必须有显式类型定义）"""
        type_dict = self.input_types if is_input else self.output_types
        if port_name in type_dict:
            return type_dict[port_name]

        inferred = get_dynamic_port_type(str(port_name), type_dict, self.dynamic_port_type)
        if inferred:
            return inferred

        # 流程端口统一视为“流程”类型（不强制要求显式声明）
        # 兼容错误方向查询（例如对目标节点右侧端口误用 is_input=True）
        if is_flow_port_name(str(port_name)):
            return FLOW_PORT_TYPE
        
        # 强约束：必须存在类型
        direction = "输入" if is_input else "输出"
        raise ValueError(f"节点 '{self.category}/{self.name}' 的{direction}端口 '{port_name}' 缺少类型定义")

    def get_generic_constraints(self, port_name: str, is_input: bool) -> List[str]:
        """
        获取指定端口的泛型约束（若存在）。
        返回复制后的列表，避免外部修改内部缓存。
        """
        source = self.input_generic_constraints if is_input else self.output_generic_constraints
        allowed = source.get(port_name, [])
        return list(allowed) if isinstance(allowed, list) else list(allowed or [])


def load_all_nodes(root: Path, include_composite: bool = True, verbose: bool = False) -> Dict[str, NodeDef]:
    """加载节点定义库。

    从实现库（plugins/nodes + @node_spec）构建权威节点定义；
    复合节点由复合节点管理器统一追加。
    """
    # 解析工作区路径：以传入的工作区根目录为准
    workspace_path = root

    # 1) 从实现库加载（唯一权威） - 走 V2 管线产物
    lib: Dict[str, NodeDef] = {}
    from .impl_definition_loader import load_all_nodes_from_impl
    impl_lib = load_all_nodes_from_impl(workspace_path, include_composite=False, verbose=verbose)
    lib.update(impl_lib)

    # 2) 追加复合节点（分阶段：先基础节点，再基于基础库解析复合节点，避免循环依赖）
    if include_composite:
        # 通过 composite 子管线追加复合节点定义（与主管线风格一致）
        from engine.nodes.pipeline.composite_runner import run_composite_pipeline
        composite_defs = run_composite_pipeline(workspace_path=workspace_path, base_node_library=lib, verbose=verbose)
        lib.update(composite_defs)
        if verbose:
            from engine.utils.logging.logger import log_info
            log_info(f"加载了 {len(composite_defs)} 个复合节点")

    return lib


def group_by_category(library: Dict[str, NodeDef]) -> Dict[str, List[NodeDef]]:
    result: Dict[str, List[NodeDef]] = {}
    for n in library.values():
        result.setdefault(n.category, []).append(n)
    for v in result.values():
        v.sort(key=lambda x: x.name)
    return result


def find_composite_node_def(library: Dict[str, NodeDef], 
                             composite_id: str = None, 
                             node_name: str = None) -> Optional[Tuple[str, NodeDef]]:
    """查找复合节点定义（优先使用composite_id精确匹配）
    
    此函数专门用于查找复合节点，支持两种查找方式：
    1. 通过 composite_id 精确查找（推荐，不受节点改名影响）
    2. 通过 node_name 模糊查找（兼容性，可能受改名影响）
    
    Args:
        library: 节点定义库
        composite_id: 复合节点的唯一ID（如 "composite_向量长度计算"）
        node_name: 复合节点的名称（如 "向量长度计算"）
        
    Returns:
        (node_def_key, node_def) 元组，如果找不到返回 None
        
    Example:
        >>> # 推荐方式：通过 composite_id 查找（精确、不受改名影响）
        >>> result = find_composite_node_def(library, composite_id="composite_向量长度计算")
        >>> if result:
        ...     key, node_def = result
        ...     print(f"找到复合节点：{node_def.name}")
        
        >>> # 兼容方式：通过名称查找（可能受改名影响）
        >>> result = find_composite_node_def(library, node_name="向量长度计算")
    """
    # 方式1：通过 composite_id 精确查找（推荐）
    if composite_id:
        for node_key, node_def in library.items():
            if (hasattr(node_def, 'is_composite') and node_def.is_composite and 
                hasattr(node_def, 'composite_id') and node_def.composite_id == composite_id):
                return (node_key, node_def)
    
    # 方式2：通过名称查找（兼容性回退）
    if node_name:
        node_key = f"复合节点/{node_name}"
        node_def = library.get(node_key)
        if node_def:
            return (node_key, node_def)
    
    # 未找到
    return None