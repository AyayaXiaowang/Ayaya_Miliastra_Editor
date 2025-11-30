from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="根据格式化时间计算时间戳",
    category="运算节点",
    inputs=[("年", "整数"), ("月", "整数"), ("日", "整数"), ("时", "整数"), ("分", "整数"), ("秒", "整数")],
    outputs=[("时间戳", "整数")],
    description="根据输入的格式化时间将其转化为时间戳",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 根据格式化时间计算时间戳(game, 年, 月, 日, 时, 分, 秒):
    """根据输入的格式化时间将其转化为时间戳"""
    from datetime import datetime
    dt = datetime(int(年), int(月), int(日), int(时), int(分), int(秒))
    return int(dt.timestamp())
