from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="修改玩家背景音乐",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("背景音乐索引", "整数"), ("开始时间", "浮点数"), ("结束时间", "浮点数"), ("音量", "整数"), ("是否循环播放", "布尔值"), ("循环播放间隔", "浮点数"), ("播放速度", "浮点数"), ("是否允许渐入渐出", "布尔值")],
    outputs=[("流程出", "流程")],
    description="修改玩家背景音乐相关参数",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 修改玩家背景音乐(game, 目标实体, 背景音乐索引, 开始时间, 结束时间, 音量, 是否循环播放, 循环播放间隔, 播放速度, 是否允许渐入渐出):
    """修改玩家背景音乐相关参数"""
    game.play_music(背景音乐索引, 音量)
