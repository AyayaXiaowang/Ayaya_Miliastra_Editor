from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="以键查询字典值",
    category="查询节点",
    inputs=[("字典", "泛型字典"), ("键", "泛型")],
    outputs=[("值", "泛型")],
    description="根据键查询字典中对应的值，如果键不存在，则返回类型默认值",
    doc_reference="服务器节点/查询节点/查询节点.md",
    input_generic_constraints={
        "键": ["实体", "GUID", "整数", "字符串", "阵营", "配置ID", "元件ID"],
    },
    output_generic_constraints={
        "值": [
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
            "枚举",
            "结构体",
            "实体列表",
            "GUID列表",
            "整数列表",
            "布尔值列表",
            "浮点数列表",
            "字符串列表",
            "三维向量列表",
            "元件ID列表",
            "配置ID列表",
            "阵营列表",
            "结构体列表",
            "泛型列表",
        ],
    },
)
def 以键查询字典值(game, 字典, 键):
    """根据键查询字典中对应的值，如果键不存在，则返回类型默认值"""
    if isinstance(字典, dict):
        return 字典.get(键)
    return None
