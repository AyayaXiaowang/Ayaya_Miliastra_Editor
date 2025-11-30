from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="复苏玩家所有角色",
    category="执行节点",
    inputs=[("流程入", "流程"), ("玩家实体", "实体"), ("是否扣除复苏次数", "布尔值")],
    outputs=[("流程出", "流程")],
    description="复苏指定玩家的所有角色实体。在超限模式中，由于每个玩家只有一个角色，与【复苏角色】的效果相同",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 复苏玩家所有角色(game, 玩家实体, 是否扣除复苏次数):
    """复苏指定玩家的所有角色实体。在超限模式中，由于每个玩家只有一个角色，与【复苏角色】的效果相同"""
    扣除提示 = "扣除复苏次数" if 是否扣除复苏次数 else "不扣除"
    log_info(f"[复苏角色] {玩家实体} 所有角色复苏 ({扣除提示})")
