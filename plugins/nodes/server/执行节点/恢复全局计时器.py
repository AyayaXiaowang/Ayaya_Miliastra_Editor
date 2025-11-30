from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="恢复全局计时器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("计时器名称", "字符串")],
    outputs=[("流程出", "流程")],
    description="使目标实体上一个处于暂停状态的计时器恢复运行",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 恢复全局计时器(game, 目标实体, 计时器名称):
    """使目标实体上一个处于暂停状态的计时器恢复运行"""
    log_info(f"[恢复全局计时器] 执行")
