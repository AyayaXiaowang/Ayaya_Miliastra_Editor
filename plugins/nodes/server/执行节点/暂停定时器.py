from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="暂停定时器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("定时器名称", "字符串")],
    outputs=[("流程出", "流程")],
    description="暂停指定目标实体上的指定定时器。之后可以使用【恢复定时器】节点恢复该定时器的计时",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 暂停定时器(game, 目标实体, 定时器名称):
    """暂停指定目标实体上的指定定时器。之后可以使用【恢复定时器】节点恢复该定时器的计时"""
    log_info(f"[定时器] 暂停定时器'{定时器名称}'")
