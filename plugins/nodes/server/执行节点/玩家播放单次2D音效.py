from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="玩家播放单次2D音效",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("音效资产索引", "整数"), ("音量", "整数"), ("播放速度", "浮点数")],
    outputs=[("流程出", "流程")],
    description="玩家播放单次2D音效",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 玩家播放单次2D音效(game, 目标实体, 音效资产索引, 音量, 播放速度):
    """玩家播放单次2D音效"""
    game.play_sound(音效资产索引, 音量)
