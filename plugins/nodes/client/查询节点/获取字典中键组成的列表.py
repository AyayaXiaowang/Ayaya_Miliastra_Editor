from __future__ import annotations

from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *  # noqa: F401,F403


@node_spec(
    name="获取字典中键组成的列表",
    category="查询节点",
    inputs=[("字典", "泛型字典")],
    outputs=[("键列表", "泛型列表")],
    description="获取字典中所有键组成的列表。由于字典中键值对是无序排列的，所以取出的键列表也不一定按照其插入顺序排列",
    doc_reference="客户端节点/查询节点/查询节点.md",
    output_generic_constraints={
        "键列表": [
            "实体列表",
            "GUID列表",
            "整数列表",
            "字符串列表",
            "阵营列表",
            "配置ID列表",
            "元件ID列表",
        ],
    },
)
def 获取字典中键组成的列表(game, 字典):
    """获取字典中所有键组成的列表。"""
    return list(字典.keys())

