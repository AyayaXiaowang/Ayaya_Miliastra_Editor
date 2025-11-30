from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="修改背包道具数量",
    category="执行节点",
    inputs=[("流程入", "流程"), ("背包持有者实体", "实体"), ("道具配置ID", "配置ID"), ("变更值", "整数")],
    outputs=[("流程出", "流程")],
    description="修改背包内指定道具的数量",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 修改背包道具数量(game, 背包持有者实体, 道具配置ID, 变更值):
    """修改背包内指定道具的数量"""
    log_info(f"[修改背包道具数量] 执行")
