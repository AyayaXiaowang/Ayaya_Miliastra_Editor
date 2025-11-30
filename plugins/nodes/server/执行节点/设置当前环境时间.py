from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置当前环境时间",
    category="执行节点",
    inputs=[("流程入", "流程"), ("环境时间", "浮点数")],
    outputs=[("流程出", "流程")],
    description="立即切换环境时间到指定小时，参数需要是0~24之间的浮点数值 若目标小时数小于当前时间，视为天数+1",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置当前环境时间(game, 环境时间):
    """立即切换环境时间到指定小时，参数需要是0~24之间的浮点数值 若目标小时数小于当前时间，视为天数+1"""
    log_info(f"[设置环境时间] 当前时间={环境时间}小时")
