from __future__ import annotations

from typing import Dict, Any

from engine.graph.models import GraphModel, NodeModel
from engine.utils.graph.graph_utils import is_flow_port_name


def _find_node_def(node_obj: NodeModel, node_library: Dict[str, Any]):
    key1 = f"{node_obj.category}/{node_obj.title}"
    key2 = f"复合节点/{node_obj.title}"
    return node_library.get(key1) or node_library.get(key2)


def promote_flow_outputs_for_layout(model_copy: GraphModel, node_library: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """
    将模型中的“流程输出端口但名称不含‘流程’关键字”的端口临时改名为包含‘流程’的名字，
    以便布局/分块阶段使用基于端口名的规则正确识别流程边。

    仅修改 model_copy（克隆体），不影响原始模型与 UI 展示。
    """
    if not model_copy or not node_library:
        return {}

    edges_by_src: Dict[str, list] = {}
    for edge in model_copy.edges.values():
        edges_by_src.setdefault(edge.src_node, []).append(edge)

    rename_records: Dict[str, Dict[str, str]] = {}

    for node in list(model_copy.nodes.values()):
        node_def = _find_node_def(node, node_library)
        if not node_def:
            continue
        # 需要重命名的端口映射：旧名 -> 新名
        rename_map: Dict[str, str] = {}
        node_rename_record: Dict[str, str] = {}
        for port in node.outputs or []:
            port_name = port.name
            declared_type = getattr(node_def, "output_types", {}).get(port_name, "")
            if declared_type == "流程" and not is_flow_port_name(str(port_name)):
                new_name = f"流程:{port_name}"
                if new_name != port_name and not node.has_output_port(new_name):
                    rename_map[port_name] = new_name
                    node_rename_record[new_name] = port_name

        if not rename_map:
            continue

        # 应用端口重命名到节点输出列表
        for port in node.outputs:
            if port.name in rename_map:
                port.name = rename_map[port.name]
        node._rebuild_port_maps()

        # 同步修改所有引用该端口的边
        for edge in edges_by_src.get(node.id, ()):
            if edge.src_port in rename_map:
                edge.src_port = rename_map[edge.src_port]

        if node_rename_record:
            rename_records[node.id] = node_rename_record

    return rename_records


