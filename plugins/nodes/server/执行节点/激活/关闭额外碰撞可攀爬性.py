from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="激活/关闭额外碰撞可攀爬性",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("额外碰撞序号", "整数"), ("是否激活", "布尔值")],
    outputs=[("流程出", "流程")],
    description="修改实体额外碰撞组件的碰撞的可攀爬性",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 激活关闭额外碰撞可攀爬性(game, 目标实体, 额外碰撞序号, 是否激活):
    """修改实体额外碰撞组件的碰撞的可攀爬性"""
    log_info(f"[激活关闭额外碰撞可攀爬性] 执行")
