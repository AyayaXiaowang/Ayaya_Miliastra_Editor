from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="对数运算",
    category="运算节点",
    inputs=[("真数", "浮点数"), ("底数", "浮点数")],
    outputs=[("结果", "浮点数")],
    description="计算以底数为底真数的对数 底数不应为负数或等于1、真数不应为负数，否则可能产生非法值",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 对数运算(game, 真数, 底数):
    """计算以底数为底真数的对数 底数不应为负数或等于1、真数不应为负数，否则可能产生非法值"""
    if 底数 <= 0 or 底数 == 1 or 真数 <= 0:
        return None  # 非法输入
    return math.log(真数, 底数)
