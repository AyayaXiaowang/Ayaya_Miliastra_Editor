from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="修改掉落物组件货币数量",
    category="执行节点",
    inputs=[("流程入", "流程"), ("掉落物实体", "实体"), ("货币配置ID", "配置ID"), ("货币数量", "整数")],
    outputs=[("流程出", "流程")],
    description="修改掉落物元件上掉落物组件内指定货币的数量",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 修改掉落物组件货币数量(game, 掉落物实体, 货币配置ID, 货币数量):
    """修改掉落物元件上掉落物组件内指定货币的数量"""
    log_info(f"[修改掉落物组件货币数量] 执行")
