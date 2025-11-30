from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="根据时间戳计算格式化时间",
    category="运算节点",
    inputs=[("时间戳", "整数")],
    outputs=[("年", "整数"), ("月", "整数"), ("日", "整数"), ("时", "整数"), ("分", "整数"), ("秒", "整数")],
    description="根据输入的时间戳将其转化为格式化时间",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 根据时间戳计算格式化时间(game, 时间戳):
    """根据输入的时间戳将其转化为格式化时间"""
    from datetime import datetime
    dt = datetime.fromtimestamp(时间戳)
    return dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second
