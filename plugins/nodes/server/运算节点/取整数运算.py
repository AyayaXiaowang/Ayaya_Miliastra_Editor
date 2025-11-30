from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="取整数运算",
    category="运算节点",
    inputs=[("输入", "浮点数"), ("取整方式", "枚举")],
    outputs=[("结果", "整数")],
    description="根据取整方式进行一次取整运算，返回取整后的正数",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 取整数运算(game, 输入, 取整方式):
    """根据取整方式进行一次取整运算，返回取整后的正数"""
    import math
    if 取整方式 == "向下取整":
        return math.floor(输入)
    elif 取整方式 == "向上取整":
        return math.ceil(输入)
    elif 取整方式 == "四舍五入":
        return round(输入)
    else:  # 默认截断
        return int(输入)
