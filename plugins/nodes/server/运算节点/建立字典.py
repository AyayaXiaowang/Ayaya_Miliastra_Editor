from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="建立字典",
    category="运算节点",
    inputs=[("键列表", "泛型"), ("值列表", "泛型")],
    outputs=[("字典", "泛型")],
    description="根据输入的键和值列表的顺序依次建立键值对。 此节点会按照键和值列表中较短的一个进行字典创建，多余的部分会被截断 如果键列表中存在重复值，则会创建失败，返回空字典",
    doc_reference="服务器节点/运算节点/运算节点.md",
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
    """根据输入的键和值列表的顺序依次建立键值对。 此节点会按照键和值列表中较短的一个进行字典创建，多余的部分会被截断 如果键列表中存在重复值，则会创建失败，返回空字典"""
    # 检查键是否有重复
    if len(键列表) != len(set(键列表)):
        return {}
    
    # 取较短的长度
    length = min(len(键列表), len(值列表))
    
    # 创建字典
    return {键列表[i]: 值列表[i] for i in range(length)}
