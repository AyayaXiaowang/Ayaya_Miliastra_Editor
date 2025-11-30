from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置实体生效铭牌",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("铭牌配置ID列表", "配置ID列表")],
    outputs=[("流程出", "流程")],
    description="直接设置指定目标的生效铭牌列表，在入参列表中的铭牌配置会生效，不在列表中的会失效",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置实体生效铭牌(game, 目标实体, 铭牌配置ID列表):
    """直接设置指定目标的生效铭牌列表，在入参列表中的铭牌配置会生效，不在列表中的会失效"""
    log_info(f"[设置实体生效铭牌] 执行")
