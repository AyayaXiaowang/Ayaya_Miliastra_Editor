from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="激活/关闭跟随运动器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("是否激活", "布尔值")],
    outputs=[("流程出", "流程")],
    description="使目标实体上的跟随运动器组件逻辑激活/关闭",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 激活关闭跟随运动器(game, 目标实体, 是否激活):
    """使目标实体上的跟随运动器组件逻辑激活/关闭"""
    log_info(f"[激活关闭跟随运动器] 执行")
