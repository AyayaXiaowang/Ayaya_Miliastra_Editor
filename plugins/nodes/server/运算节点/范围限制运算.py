from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="范围限制运算",
    category="运算节点",
    inputs=[("输入", "泛型"), ("下限", "泛型"), ("上限", "泛型")],
    outputs=[("结果", "泛型")],
    description="将输入值限制在[下限,上限]（上下限均包含）后输出。 - 如果输入值在下限到上限范围内，则返回原值 - 输入值如果小于下限，则返回下限值；如果输入值大于上限，则返回上限值 - 如果下限大于上限，认为是错误输入，返回非法值",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 范围限制运算(game, 输入, 下限, 上限):
    """将输入值限制在[下限,上限]（上下限均包含）后输出。 - 如果输入值在下限到上限范围内，则返回原值 - 输入值如果小于下限，则返回下限值；如果输入值大于上限，则返回上限值 - 如果下限大于上限，认为是错误输入，返回非法值"""
    if 下限 > 上限:
        return None  # 错误输入
    return max(下限, min(上限, 输入))
