from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="播放限时特效",
    category="执行节点",
    inputs=[("流程入", "流程"), ("特效资产", "配置ID"), ("目标实体", "实体"), ("挂接点名称", "字符串"), ("是否跟随目标运动", "布尔值"), ("是否跟随目标旋转", "布尔值"), ("位置偏移", "三维向量"), ("旋转偏移", "三维向量"), ("缩放倍率", "浮点数"), ("是否播放自带的音效", "布尔值")],
    outputs=[("流程出", "流程")],
    description="以目标实体为基准，播放一个限时特效。需要有合法的目标实体以及挂接点",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 播放限时特效(game, 特效资产, 目标实体, 挂接点名称, 是否跟随目标运动, 是否跟随目标旋转, 位置偏移, 旋转偏移, 缩放倍率, 是否播放自带的音效):
    """以目标实体为基准，播放一个限时特效。需要有合法的目标实体以及挂接点"""
    game.play_effect(特效资产, 目标实体, 挂接点名称)
