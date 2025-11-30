from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="暂停基础运动器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("运动器名称", "字符串")],
    outputs=[("流程出", "流程")],
    description="暂停一个运行中的运动器，之后可使用恢复运动器节点使其恢复运动",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 暂停基础运动器(game, 目标实体, 运动器名称):
    """暂停一个运行中的运动器，之后可使用恢复运动器节点使其恢复运动"""
    log_info(f"[暂停基础运动器] 执行")
