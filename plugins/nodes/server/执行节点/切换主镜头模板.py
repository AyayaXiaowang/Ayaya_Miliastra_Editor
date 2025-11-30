from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="切换主镜头模板",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标玩家列表", "实体列表"), ("镜头模板名称", "字符串")],
    outputs=[("流程出", "流程")],
    description="使目标玩家列表的镜头模板切换至指定模板",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 切换主镜头模板(game, 目标玩家列表, 镜头模板名称):
    """使目标玩家列表的镜头模板切换至指定模板"""
    log_info(f"[切换主镜头模板] 执行")
