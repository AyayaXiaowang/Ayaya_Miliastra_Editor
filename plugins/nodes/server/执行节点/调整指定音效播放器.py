from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="调整指定音效播放器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("音效播放器序号", "整数"), ("音量", "整数"), ("播放速度", "浮点数")],
    outputs=[("流程出", "流程")],
    description="可以调整指定目标实体上的音效播放器组件对应序号的音效播放器的音量和播放速度",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 调整指定音效播放器(game, 目标实体, 音效播放器序号, 音量, 播放速度):
    """可以调整指定目标实体上的音效播放器组件对应序号的音效播放器的音量和播放速度"""
    log_info(f"[调整指定音效播放器] 执行")
