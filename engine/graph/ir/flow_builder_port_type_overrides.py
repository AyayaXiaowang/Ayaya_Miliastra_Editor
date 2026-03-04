from __future__ import annotations

import ast
from typing import Dict, Union

from engine.graph.models import GraphModel, NodeModel

from .var_env import VarEnv


def extract_annotation_type_text(annotation_expr: ast.expr) -> str:
    """从 AnnAssign 的注解表达式中提取类型名称文本。

    当前约定：
    - 仅当注解是字符串常量时才生效（例如: "字典" / "整数列表"）；
    - 其他形式的注解（如 Name/Attribute）暂不参与端口类型覆盖。
    """
    if isinstance(annotation_expr, ast.Constant) and isinstance(annotation_expr.value, str):
        annotation_text = annotation_expr.value.strip()
        if annotation_text != "":
            return annotation_text
    return ""


def register_port_type_override_from_annotation(
    *,
    graph_model: GraphModel,
    env: VarEnv,
    node: NodeModel,
    targets: Union[ast.Name, ast.Tuple],
    annotation_type: str,
) -> None:
    """基于带类型注解的赋值，为节点输出端口注册类型覆盖信息。

    规则简述：
    - 仅处理单变量目标（Name），忽略元组等复杂形式；
    - 通过 VarEnv 查找该变量当前映射到的 (node_id, port_name)，
      且要求 node_id 与当前节点一致，确保覆盖定位到正确的输出端口；
    - annotation_type 为非空字符串时，将其写入 GraphModel.metadata["port_type_overrides"]
      中，对应键为 {node_id: {port_name: annotation_type}}。
    """
    if not isinstance(targets, ast.Name):
        return
    variable_name = targets.id
    if not isinstance(variable_name, str) or variable_name == "":
        return
    if not isinstance(annotation_type, str) or annotation_type.strip() == "":
        return

    variable_source = env.get_variable(variable_name)
    if variable_source is None:
        return

    source_node_id, source_port_name = variable_source
    if source_node_id != node.id:
        return
    if not isinstance(source_port_name, str) or source_port_name == "":
        return

    overrides_raw = graph_model.metadata.get("port_type_overrides")
    if overrides_raw is None:
        overrides: Dict[str, Dict[str, str]] = {}
    else:
        overrides = dict(overrides_raw) if isinstance(overrides_raw, dict) else {}

    node_overrides = overrides.get(source_node_id)
    if node_overrides is None:
        node_overrides = {}
    else:
        node_overrides = dict(node_overrides)

    node_overrides[source_port_name] = annotation_type.strip()
    overrides[source_node_id] = node_overrides
    graph_model.metadata["port_type_overrides"] = overrides

