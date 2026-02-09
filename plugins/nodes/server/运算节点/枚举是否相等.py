from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="枚举是否相等",
    category="运算节点",
    semantic_id="enum.equals",
    inputs=[("枚举1", "枚举"), ("枚举2", "枚举")],
    outputs=[("结果", "布尔值")],
    description="比较两个枚举值是否相等（枚举候选集合由连线来源动态绑定）",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 枚举是否相等(game, 枚举1, 枚举2):
    """比较两个枚举值是否相等（枚举候选集合由连线来源动态绑定）"""
    return 枚举1 == 枚举2
