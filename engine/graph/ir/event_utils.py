from __future__ import annotations

from typing import List
from engine.graph.models import NodeModel
from engine.graph.common import is_flow_port


def get_event_param_names_from_node(event_node: NodeModel) -> List[str]:
    """从事件节点输出端口推导事件处理方法的参数名（IR为权威来源）。
    
    规则：
    - 跳过流程端口
    - 端口名直接作为参数名（去除可选的分隔符冒号）
    """
    params: List[str] = []
    for p in event_node.outputs:
        if is_flow_port(event_node, p.name, True):
            continue
        name = p.name.replace(":", "").strip()
        params.append(name)
    return params




