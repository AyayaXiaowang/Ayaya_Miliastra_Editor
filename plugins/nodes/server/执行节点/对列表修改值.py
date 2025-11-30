from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="对列表修改值",
    category="执行节点",
    inputs=[("流程入", "流程"), ("列表", "泛型列表"), ("序号", "整数"), ("值", "泛型")],
    outputs=[("流程出", "流程")],
    description="修改指定列表的指定序号位置的值",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 对列表修改值(game, 列表, 序号, 值):
    """修改指定列表的指定序号位置的值"""
    if isinstance(列表, list) and 0 <= 序号 < len(列表):
        列表[序号] = 值
        log_info(f"[列表修改] 序号{序号} = {值}")
