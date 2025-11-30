from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="根据时间戳计算星期几",
    category="运算节点",
    inputs=[("时间戳", "整数")],
    outputs=[("星期", "整数")],
    description="根据输入的时间戳将其转化为星期几",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 根据时间戳计算星期几(game, 时间戳):
    """根据输入的时间戳将其转化为星期几"""
    from datetime import datetime
    dt = datetime.fromtimestamp(时间戳)
    return dt.weekday() + 1  # Python weekday是0-6，游戏中可能是1-7
