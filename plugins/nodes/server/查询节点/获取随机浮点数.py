from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取随机浮点数",
    category="查询节点",
    inputs=[("下限", "浮点数"), ("上限", "浮点数")],
    outputs=[("结果", "浮点数")],
    description="获取一个大于等于下限，小于等于上限的随机浮点数。注意该节点生成的随机数包含上下限",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取随机浮点数(下限, 上限):
    """获取一个大于等于下限，小于等于上限的随机浮点数。注意该节点生成的随机数包含上下限"""
    result = random.uniform(下限, 上限)
    log_info(f"[随机浮点] {下限}-{上限} -> {result:.2f}")
    return result
