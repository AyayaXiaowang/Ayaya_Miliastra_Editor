from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="激活/关闭碰撞触发器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("触发器序号", "整数"), ("是否激活", "布尔值")],
    outputs=[("流程出", "流程")],
    description="修改碰撞触发器组件的数据，使某一个序号的触发器激活/关闭",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 激活关闭碰撞触发器(game, 目标实体, 触发器序号, 是否激活):
    """修改碰撞触发器组件的数据，使某一个序号的触发器激活/关闭"""
    log_info(f"[激活关闭碰撞触发器] 执行")
