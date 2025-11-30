from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="终止定时器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("定时器名称", "字符串")],
    outputs=[("流程出", "流程")],
    description="完全终止目标实体上的指定定时器，不可恢复",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 终止定时器(game, 目标实体, 定时器名称):
    """完全终止目标实体上的指定定时器，不可恢复"""
    game.stop_timer(目标实体, 定时器名称)
