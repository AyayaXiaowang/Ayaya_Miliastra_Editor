from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="拼装列表",
    category="运算节点",
    inputs=[("0~99", "泛型")],
    outputs=[("列表", "泛型列表")],
    description="将多个类型相同的入参(至多100个)拼装为一个列表",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 拼装列表(game, 第一个值=0, *更多的值):
    """将多个类型相同的入参(至多100个)拼装为一个列表"""
    return [第一个值] + list(更多的值)
