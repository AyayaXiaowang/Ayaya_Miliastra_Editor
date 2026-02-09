from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="激活/关闭模型显示",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("是否激活", "布尔值")],
    outputs=[("流程出", "流程")],
    description="更改实体的模型可见性属性设置，从而使实体的模型可见/不可见",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 激活关闭模型显示(game, 目标实体, 是否激活):
    """更改实体的模型可见性属性设置，从而使实体的模型可见/不可见"""
    log_info(f"[激活关闭模型显示] 执行")
