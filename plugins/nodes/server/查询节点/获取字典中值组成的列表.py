from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取字典中值组成的列表",
    category="查询节点",
    inputs=[("字典", "泛型字典")],
    outputs=[("值列表", "泛型列表")],
    description="获取字典中所有值组成的列表。由于字典中键值对是无序排列的，所以取出的值列表也不一定按照其插入顺序排列",
    doc_reference="服务器节点/查询节点/查询节点.md",
    output_generic_constraints={
        "值列表": [
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
def 获取字典中值组成的列表(game, 字典):
    """获取字典中所有值组成的列表。由于字典中键值对是无序排列的，所以取出的值列表也不一定按照其插入顺序排列"""
    if isinstance(字典, dict):
        return list(字典.values())
    return []
