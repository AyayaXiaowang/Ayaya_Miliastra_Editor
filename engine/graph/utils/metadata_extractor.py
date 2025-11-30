"""元数据提取工具

从节点图代码的docstring中提取元数据信息。
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


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


def _parse_dict_type_tag(tag_content: str) -> tuple[Optional[str], Optional[str]]:
    """从方括号标签中解析“字典键/值类型”声明。

    支持格式示例（中英文分隔符均可）：
    - [键类型=整数, 值类型=字符串]
    - [键类型: GUID，值类型: 结构体]
    - [key_type=整数, value_type=字符串]

    返回 (key_type_name, value_type_name)，若未解析到则对应位置为 None。
    """
    key_type_name: Optional[str] = None
    value_type_name: Optional[str] = None

    text = tag_content.strip()
    if not text:
        return key_type_name, value_type_name

    normalized_text = text.replace("，", ",")
    segments = [segment.strip() for segment in normalized_text.split(",") if segment.strip()]

    for segment in segments:
        segment_normalized = segment.replace("：", ":")
        lower_segment = segment_normalized.lower()

        if "键类型" in segment_normalized or "键数据类型" in segment_normalized or "key_type" in lower_segment:
            if "=" in segment_normalized:
                _, rhs = segment_normalized.split("=", 1)
            elif ":" in segment_normalized:
                _, rhs = segment_normalized.split(":", 1)
            else:
                continue
            candidate = rhs.strip().strip('"').strip("'")
            if candidate:
                key_type_name = candidate
            continue

        if "值类型" in segment_normalized or "值数据类型" in segment_normalized or "value_type" in lower_segment:
            if "=" in segment_normalized:
                _, rhs = segment_normalized.split("=", 1)
            elif ":" in segment_normalized:
                _, rhs = segment_normalized.split(":", 1)
            else:
                continue
            candidate = rhs.strip().strip('"').strip("'")
            if candidate:
                value_type_name = candidate
            continue

    return key_type_name, value_type_name


def _strip_string_literal_quotes(raw_value: str) -> str:
    """去掉围绕在默认值外层的一对字符串引号。

    仅在同时满足以下条件时才会生效：
    - 文本长度至少为 2；
    - 首尾字符相同且为单引号或双引号。

    示例：
    - '"1077936132"' -> '1077936132'
    - "'文本'" -> '文本'
    - '未加引号' -> 原样返回
    """
    text = raw_value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


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
    
    节点图变量：
    - 初始位置: 三维向量 = (0, 0, 0)
    - 触发次数: 整数 = 0
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
    in_variables_section = False
    
    for line in lines:
        line = line.strip()
        
        # 检查是否进入节点图变量区域
        if line.startswith("节点图变量") or line.startswith("graph_variables"):
            in_variables_section = True
            continue
        
        # 解析节点图变量
        if in_variables_section and line.startswith('-'):
            # 格式：- 变量名: 类型 = 默认值 [对外暴露] [说明...]
            var_line = line[1:].strip()

            # 先处理尾部方括号标签，避免污染默认值
            is_exposed = False
            description_text = ""
            dict_key_type_name: Optional[str] = None
            dict_value_type_name: Optional[str] = None
            while var_line.endswith(']'):
                lb = var_line.rfind('[')
                if lb == -1:
                    break
                tag_content = var_line[lb + 1 : -1].strip()
                if not tag_content:
                    # 兼容空的 [] 写法，视为默认值一部分
                    break

                tag_handled = False

                if '对外暴露' in tag_content:
                    is_exposed = True
                    tag_handled = True

                key_type_candidate, value_type_candidate = _parse_dict_type_tag(tag_content)
                if key_type_candidate is not None:
                    dict_key_type_name = key_type_candidate
                    tag_handled = True
                if value_type_candidate is not None:
                    dict_value_type_name = value_type_candidate
                    tag_handled = True

                if not tag_handled:
                    description_text = (
                        f"{description_text}\n{tag_content}" if description_text else tag_content
                    )
                var_line = var_line[:lb].rstrip()
            
            if ':' in var_line:
                name_part, rest = var_line.split(':', 1)
                var_name = name_part.strip()
                
                # 解析类型和默认值
                if '=' in rest:
                    type_part, value_part = rest.split('=', 1)
                    var_type = type_part.strip()
                    default_text = value_part.strip()
                    if default_text:
                        default_value = _strip_string_literal_quotes(default_text)
                    else:
                        default_value = None
                else:
                    var_type = rest.strip()
                    default_value = None

                variable_entry: Dict[str, Any] = {
                    "name": var_name,
                    "variable_type": var_type,
                    "default_value": default_value,
                    "description": description_text,
                    "is_exposed": is_exposed,
                }

                normalized_var_type = var_type.strip()
                if normalized_var_type == "字典":
                    if dict_key_type_name is not None:
                        variable_entry["dict_key_type"] = dict_key_type_name
                    if dict_value_type_name is not None:
                        variable_entry["dict_value_type"] = dict_value_type_name

                metadata.graph_variables.append(variable_entry)
            continue
        
        # 解析元数据字段
        if ':' in line and not in_variables_section:
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


def _extract_constant_from_ast(value_node: ast.expr) -> Any:
    """从 AST 表达式节点中提取常量或简单容器值。

    支持的形式：
    - 常量：整数、浮点数、字符串、布尔值、None
    - 容器：
      - 列表/元组：元素本身也需要是可提取的常量
      - 字典：键和值均需要是可提取的常量

    无法静态提取时返回 None。
    """
    if isinstance(value_node, ast.Constant):
        return value_node.value

    if isinstance(value_node, ast.List):
        return [_extract_constant_from_ast(element) for element in value_node.elts]

    if isinstance(value_node, ast.Tuple):
        return tuple(_extract_constant_from_ast(element) for element in value_node.elts)

    if isinstance(value_node, ast.Dict):
        keys: List[Any] = []
        values: List[Any] = []
        for key_node, value_node_item in zip(value_node.keys, value_node.values):
            if key_node is None or value_node_item is None:
                return None
            key_value = _extract_constant_from_ast(key_node)
            value_value = _extract_constant_from_ast(value_node_item)
            keys.append(key_value)
            values.append(value_value)
        result_dict: Dict[Any, Any] = {}
        for key_item, value_item in zip(keys, values):
            result_dict[key_item] = value_item
        return result_dict

    return None


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
                default_value_value = _extract_constant_from_ast(value_node)
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
    """从代码字符串中提取元数据（支持 docstring 与 GRAPH_VARIABLES 双来源）。

    优先从 docstring 解析基础元数据；若代码中存在 GRAPH_VARIABLES 声明，
    则以代码级声明覆盖 docstring 中的节点图变量列表。
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


def load_graph_metadata_from_file(file_path: Path, *, encoding: str = "utf-8") -> GraphMetadata:
    """直接从节点图文件解析元数据。"""
    code = Path(file_path).read_text(encoding=encoding)
    return extract_metadata_from_code(code)

