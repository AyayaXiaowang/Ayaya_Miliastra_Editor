from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="激活/关闭碰撞触发源",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("是否激活", "布尔值")],
    outputs=[("流程出", "流程")],
    description="可以修改目标实体的碰撞触发源组件状态",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 激活关闭碰撞触发源(game, 目标实体, 是否激活):
    """可以修改目标实体的碰撞触发源组件状态"""
    log_info(f"[激活关闭碰撞触发源] 执行")
