from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="通知服务器节点图",
    category="执行节点",
    inputs=[("流程入", "流程"), ("字符串1", "字符串"), ("字符串2", "字符串"), ("字符串3", "字符串")],
    outputs=[("流程出", "流程")],
    description="通知服务器节点图，支持携带三个字符串参数 该节点运行时可以将逻辑传到服务器节点图上，在服务器节点图上会触发【技能节点调用时】事件",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 通知服务器节点图(game, 字符串1, 字符串2, 字符串3):
    """通知服务器节点图，支持携带三个字符串参数 该节点运行时可以将逻辑传到服务器节点图上，在服务器节点图上会触发【技能节点调用时】事件"""
    log_info(f"[通知服务器节点图] 执行")
