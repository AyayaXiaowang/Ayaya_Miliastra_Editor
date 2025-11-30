from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置扫描标签的规则",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("规则类型", "枚举")],
    outputs=[("流程出", "流程")],
    description="设置扫描标签的规则，会以设置好的规则执行扫描标签的逻辑",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置扫描标签的规则(game, 目标实体, 规则类型):
    """设置扫描标签的规则，会以设置好的规则执行扫描标签的逻辑"""
    log_info(f"[设置扫描标签的规则] 执行")
