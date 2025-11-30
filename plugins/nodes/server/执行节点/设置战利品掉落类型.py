from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置战利品掉落类型",
    category="执行节点",
    inputs=[("流程入", "流程"), ("掉落者实体", "实体"), ("掉落类型", "枚举")],
    outputs=[("流程出", "流程")],
    description="设置掉落者实体上战利品组件中战利品的掉落类型",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置战利品掉落类型(game, 掉落者实体, 掉落类型):
    """设置掉落者实体上战利品组件中战利品的掉落类型"""
    log_info(f"[设置战利品掉落类型] 执行")
