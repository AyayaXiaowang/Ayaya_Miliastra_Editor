from __future__ import annotations

from typing import List
from engine.graph.models import NodeModel
from engine.graph.common import is_flow_port
from engine.utils.name_utils import make_valid_identifier


def get_event_param_names_from_node(event_node: NodeModel) -> List[str]:
    """从事件节点输出端口推导事件处理方法的参数名（IR为权威来源）。
    
    规则：
    - 跳过流程端口
    - 参数名必须是合法 Python 标识符：使用 `make_valid_identifier` 从端口名派生
    - 若派生后冲突（同名），则追加递增后缀保证唯一
    """
    params: List[str] = []
    used: set[str] = set()
    data_index = 0
    for p in event_node.outputs:
        if is_flow_port(event_node, p.name, True):
            continue
        raw_name = str(getattr(p, "name", "") or "")
        candidate = make_valid_identifier(raw_name)
        if not candidate or candidate == "_":
            candidate = f"event_param_{data_index}"
        base = candidate
        suffix = 1
        while candidate in used:
            suffix += 1
            candidate = f"{base}_{suffix}"
        used.add(candidate)
        params.append(candidate)
        data_index += 1
    return params




