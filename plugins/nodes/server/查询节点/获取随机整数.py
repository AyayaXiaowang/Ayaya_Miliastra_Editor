from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取随机整数",
    category="查询节点",
    inputs=[("下限", "整数"), ("上限", "整数")],
    outputs=[("结果", "整数")],
    description="获取一个大于等于下限，小于等于上限的随机整数。注意该节点生成的随机数包含上下限",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取随机整数(下限, 上限):
    """获取一个大于等于下限，小于等于上限的随机整数。注意该节点生成的随机数包含上下限"""
    result = random.randint(下限, 上限)
    log_info(f"[随机整数] {下限}-{上限} -> {result}")
    return result
