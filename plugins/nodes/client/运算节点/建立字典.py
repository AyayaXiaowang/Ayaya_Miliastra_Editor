from __future__ import annotations

from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_运算节点_impl_helpers import *  # noqa: F401,F403


@node_spec(
    name="建立字典",
    category="运算节点",
    inputs=[("键列表", "泛型"), ("值列表", "泛型")],
    outputs=[("字典", "泛型字典")],
    description="根据输入的键和值列表的顺序依次建立键值对",
    doc_reference="客户端节点/运算节点/运算节点.md",
    input_generic_constraints={
        "键列表": [
            "实体列表",
            "GUID列表",
            "整数列表",
            "字符串列表",
            "阵营列表",
            "配置ID列表",
            "元件ID列表",
        ],
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
        ],
    },
)
def 建立字典(game, 键列表, 值列表):
    """根据键和值列表建立字典。"""
    if len(键列表) != len(set(键列表)):
        return {}
    length = min(len(键列表), len(值列表))
    return {键列表[i]: 值列表[i] for i in range(length)}

