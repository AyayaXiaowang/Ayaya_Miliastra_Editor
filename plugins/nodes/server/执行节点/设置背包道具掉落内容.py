from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置背包道具掉落内容",
    category="执行节点",
    inputs=[("流程入", "流程"), ("背包持有者实体", "实体"), ("道具掉落字典", "字典"), ("掉落类型", "枚举")],
    outputs=[("流程出", "流程")],
    description="以字典形式设置背包道具掉落内容，并可以设置掉落类型",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置背包道具掉落内容(game, 背包持有者实体, 道具掉落字典, 掉落类型):
    """以字典形式设置背包道具掉落内容，并可以设置掉落类型"""
    log_info(f"[设置背包道具掉落内容] 执行")
