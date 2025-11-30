from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="清除循环特效",
    category="执行节点",
    inputs=[("流程入", "流程"), ("特效实例ID", "整数"), ("目标实体", "实体")],
    outputs=[("流程出", "流程")],
    description="根据特效实例ID清除目标实体上的指定循环特效。【挂载循环特效】节点在成功挂载后，会生成一个特效实例ID",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 清除循环特效(game, 特效实例ID, 目标实体, 循环体_callback, 循环完成_callback=None):
    """根据特效实例ID清除目标实体上的指定循环特效。【挂载循环特效】节点在成功挂载后，会生成一个特效实例ID"""
    log_info(f"[清除循环特效] 执行")
