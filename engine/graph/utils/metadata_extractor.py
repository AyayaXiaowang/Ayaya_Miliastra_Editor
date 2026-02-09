"""元数据提取工具

从节点图代码中提取元数据：基础信息依赖 docstring，图变量仅支持代码级 GRAPH_VARIABLES。
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.utils.graph_path_inference import infer_graph_type_and_folder_path
from engine.utils.source_text import read_text

from .ast_utils import NOT_EXTRACTABLE, extract_constant_value


@dataclass
class GraphMetadata:
    """节点图元数据结构"""

    graph_id: str = ""
    graph_name: str = ""
    graph_type: str = "server"
    folder_path: str = ""
    description: str = ""
    graph_variables: List[Dict[str, Any]] = field(default_factory=list)
    dynamic_ports: Dict[str, List[str]] = field(default_factory=dict)

    # 复合节点专用字段
    composite_id: str = ""
    node_name: str = ""
    node_description: str = ""
    scope: str = "server"


def apply_graph_path_inference(metadata: GraphMetadata, *, file_path: Path) -> None:
    """将节点图在资源库中的路径信息写回到 metadata（单一口径）。

    约定：
    - `graph_type/folder_path` 以文件路径为准：`.../节点图/<server|client>/<folder...>/<file>.py`；
    - docstring 中不再要求重复声明 folder_path，且当文件移动/改目录时避免 docstring 滞后。
    """

    graph_type, folder_path = infer_graph_type_and_folder_path(file_path)
    if not graph_type:
        return
    metadata.graph_type = graph_type
    metadata.scope = graph_type
    metadata.folder_path = folder_path


def parse_dynamic_ports(ports_str: str) -> Dict[str, List[str]]:
    """解析动态端口字符串
    
    格式：node_3=[分支1,分支2], node_5=[选项A]
    返回：{"node_3": ["分支1", "分支2"], "node_5": ["选项A"]}
    
    Args:
        ports_str: 动态端口字符串
        
    Returns:
        节点ID到端口名列表的映射
    """
    result = {}
    
    if not ports_str:
        return result
    
    # 匹配 node_id=[port1,port2,...] 格式
    pattern = r'(\w+)=\[(.*?)\]'
    matches = re.findall(pattern, ports_str)
    
    for node_id, ports in matches:
        port_list = [p.strip() for p in ports.split(',') if p.strip()]
        if port_list:
            result[node_id] = port_list
    
    return result


def extract_metadata_from_docstring(docstring: str) -> GraphMetadata:
    """从docstring提取元数据
    
    格式示例：
    ```
    graph_id: pressure_plate_001
    graph_name: 压力板逻辑
    graph_type: server
    description: 实现压力板的上下移动
    dynamic_ports: node_3=[分支1,分支2], node_5=[选项A]
    ```
    
    Args:
        docstring: 文档字符串
        
    Returns:
        GraphMetadata对象
    """
    metadata = GraphMetadata()
    
    if not docstring:
        return metadata
    
    lines = docstring.strip().split('\n')
    
    for line in lines:
        line = line.strip()

        if line.startswith("节点图变量") or line.startswith("graph_variables"):
            # 图变量不再从 docstring 解析，跳过此段落
            continue

        # 解析元数据字段
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip().lower()
            value = value.strip()
            
            # 普通节点图字段
            if key == "graph_id":
                metadata.graph_id = value
            elif key == "graph_name" or key == "name":
                metadata.graph_name = value
            elif key == "graph_type" or key == "type":
                metadata.graph_type = value
            elif key == "folder_path" or key == "folder":
                metadata.folder_path = value
            elif key == "description" or key == "desc":
                metadata.description = value
            elif key == "dynamic_ports":
                metadata.dynamic_ports = parse_dynamic_ports(value)
            
            # 复合节点字段
            elif key == "composite_id":
                metadata.composite_id = value
            elif key == "node_name":
                metadata.node_name = value
            elif key == "node_description":
                metadata.node_description = value
            elif key == "scope":
                metadata.scope = value
    
    return metadata


def _extract_graph_variables_from_list(list_node: ast.List) -> List[Dict[str, Any]]:
    """从 GRAPH_VARIABLES 的列表 AST 节点中提取变量配置字典列表。

    仅识别形如 GraphVariableConfig(...) 的调用。
    """
    result: List[Dict[str, Any]] = []

    for element in list_node.elts:
        if not isinstance(element, ast.Call):
            continue
        func_node = element.func
        if not isinstance(func_node, ast.Name):
            continue
        if func_node.id != "GraphVariableConfig":
            continue

        name_value: Optional[str] = None
        variable_type_value: Optional[str] = None
        default_value_value: Any = None
        description_value: str = ""
        is_exposed_value: bool = False
        struct_name_value: str = ""
        dict_key_type_value: str = ""
        dict_value_type_value: str = ""

        for keyword in element.keywords or []:
            key = keyword.arg
            value_node = keyword.value

            if key == "name" and isinstance(value_node, ast.Constant) and isinstance(
                value_node.value, str
            ):
                name_value = value_node.value.strip()
                continue

            if key == "variable_type" and isinstance(
                value_node, ast.Constant
            ) and isinstance(value_node.value, str):
                variable_type_value = value_node.value.strip()
                continue

            if key == "default_value":
                extracted = extract_constant_value(value_node)
                default_value_value = None if extracted is NOT_EXTRACTABLE else extracted
                continue

            if key == "description" and isinstance(
                value_node, ast.Constant
            ) and isinstance(value_node.value, str):
                description_value = value_node.value
                continue

            if key == "is_exposed" and isinstance(
                value_node, ast.Constant
            ) and isinstance(value_node.value, bool):
                is_exposed_value = value_node.value
                continue
            
            if key == "struct_name" and isinstance(
                value_node, ast.Constant
            ) and isinstance(value_node.value, str):
                struct_name_value = value_node.value.strip()
                continue

            if key == "dict_key_type" and isinstance(
                value_node, ast.Constant
            ) and isinstance(value_node.value, str):
                dict_key_type_value = value_node.value.strip()
                continue

            if key == "dict_value_type" and isinstance(
                value_node, ast.Constant
            ) and isinstance(value_node.value, str):
                dict_value_type_value = value_node.value.strip()
                continue

        if name_value is None or variable_type_value is None:
            continue

        entry: Dict[str, Any] = {
            "name": name_value,
            "variable_type": variable_type_value,
            "default_value": default_value_value,
            "description": description_value,
            "is_exposed": is_exposed_value,
        }

        normalized_type = variable_type_value.strip()
        if normalized_type in {"结构体", "结构体列表"}:
            if struct_name_value:
                entry["struct_name"] = struct_name_value
        if normalized_type == "字典":
            if dict_key_type_value:
                entry["dict_key_type"] = dict_key_type_value
            if dict_value_type_value:
                entry["dict_value_type"] = dict_value_type_value

        result.append(entry)

    return result


def extract_graph_variables_from_ast(tree: ast.Module) -> List[Dict[str, Any]]:
    """从 AST 模块中提取通过 GRAPH_VARIABLES 声明的图变量配置列表。

    约定：
    - 仅识别模块顶层的 GRAPH_VARIABLES 赋值；
    - 支持以下两种形式：
      - GRAPH_VARIABLES = [GraphVariableConfig(...), ...]
      - GRAPH_VARIABLES: list[GraphVariableConfig] = [GraphVariableConfig(...), ...]
    """
    variables: List[Dict[str, Any]] = []

    for node in tree.body:
        list_node: Optional[ast.List] = None

        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "GRAPH_VARIABLES":
                    if isinstance(node.value, ast.List):
                        list_node = node.value
                    break

        elif isinstance(node, ast.AnnAssign):
            target_node = node.target
            if isinstance(target_node, ast.Name) and target_node.id == "GRAPH_VARIABLES":
                value_node = node.value
                if isinstance(value_node, ast.List):
                    list_node = value_node

        if list_node is None:
            continue

        variables.extend(_extract_graph_variables_from_list(list_node))

    return variables


def extract_metadata_from_code(code: str) -> GraphMetadata:
    """从代码字符串中提取元数据：基础字段来自 docstring，图变量仅读取代码级 GRAPH_VARIABLES。

    优先从 docstring 解析 graph_id / graph_name 等基础信息；图变量清单始终依赖
    模块顶层的 GRAPH_VARIABLES 声明（若未声明则保持为空列表）。
    """
    tree = ast.parse(code)
    docstring = ast.get_docstring(tree)

    if docstring:
        metadata = extract_metadata_from_docstring(docstring)
    else:
        metadata = GraphMetadata()

    # 图变量声明仅支持代码级 GRAPH_VARIABLES，docstring 中的
    # 「节点图变量：」段落不再作为权威来源。
    metadata.graph_variables = []

    graph_variables_from_code = extract_graph_variables_from_ast(tree)
    if graph_variables_from_code:
        metadata.graph_variables = graph_variables_from_code

    return metadata


def load_graph_metadata_from_file(file_path: Path, *, encoding: str = "utf-8-sig") -> GraphMetadata:
    """直接从节点图文件解析元数据。

    说明：
    - 默认使用 `utf-8-sig` 以兼容带 BOM 的 UTF-8 源文件（Windows 常见）。
    - 该函数只做静态解析（ast.parse），不会执行任何代码。
    """
    code = read_text(Path(file_path), encoding=encoding)
    metadata = extract_metadata_from_code(code)
    apply_graph_path_inference(metadata, file_path=file_path)
    return metadata

