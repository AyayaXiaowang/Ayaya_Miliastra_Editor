from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="按位读出",
    category="运算节点",
    inputs=[("值", "整数"), ("读出起始位", "整数"), ("读出结束位", "整数")],
    outputs=[("结果", "整数")],
    description="从值（以二进制表示）的【起始位，结束位】读出值",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 按位读出(game, 值, 读出起始位, 读出结束位):
    """从值（以二进制表示）的【起始位，结束位】读出值"""
    # 计算读出长度
    读出长度 = 读出结束位 - 读出起始位 + 1
    # 创建掩码
    mask = (1 << 读出长度) - 1
    # 右移并应用掩码
    result = (值 >> 读出起始位) & mask
    return result
