from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="销毁实体",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体")],
    outputs=[("流程出", "流程")],
    description="销毁指定实体，会有销毁表现，也可以触发一些销毁后才会触发的逻辑，比如本地投射物中的生命周期结束时行为 在关卡实体上可以监听到【实体销毁时】以及【实体移除/销毁时】事件",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 销毁实体(game, 目标实体):
    """销毁指定实体，会有销毁表现，也可以触发一些销毁后才会触发的逻辑，比如本地投射物中的生命周期结束时行为 在关卡实体上可以监听到【实体销毁时】以及【实体移除/销毁时】事件"""
    game.destroy_entity(目标实体)
    game.trigger_event("实体销毁时", 目标实体)
