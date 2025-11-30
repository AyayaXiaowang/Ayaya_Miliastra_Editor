from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="启动全局计时器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("计时器名称", "字符串")],
    outputs=[("流程出", "流程")],
    description="在目标实体上启动一个全局计时器 目标实体上的计时器，通过计时器名称进行唯一标识 计时器根据计时器管理中的配置，会对应创生倒计时、正计时的计时器",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 启动全局计时器(game, 目标实体, 计时器名称):
    """在目标实体上启动一个全局计时器 目标实体上的计时器，通过计时器名称进行唯一标识 计时器根据计时器管理中的配置，会对应创生倒计时、正计时的计时器"""
    log_info(f"[启动全局计时器] 执行")
