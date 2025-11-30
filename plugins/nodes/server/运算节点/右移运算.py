from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="右移运算",
    category="运算节点",
    inputs=[("值", "整数"), ("右移位数", "整数")],
    outputs=[("结果", "整数")],
    description="将输入值作为二进制数右移一定位数后输出 右移运算执行的是算术右移，会保留移位前的符号位",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 右移运算(game, 值, 右移位数):
    """将输入值作为二进制数右移一定位数后输出 右移运算执行的是算术右移，会保留移位前的符号位"""
    return 值 >> 右移位数
