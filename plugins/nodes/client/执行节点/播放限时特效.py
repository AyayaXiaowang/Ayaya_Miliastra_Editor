from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="播放限时特效",
    category="执行节点",
    inputs=[("流程入", "流程"), ("特效资产配置ID", "配置ID"), ("位置", "三维向量"), ("旋转", "三维向量"), ("缩放倍率", "浮点数"), ("是否播放默认音效", "布尔值")],
    outputs=[("流程出", "流程")],
    description="在指定的世界坐标位置播放限时特效",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 播放限时特效(game, 特效资产配置ID, 位置, 旋转, 缩放倍率, 是否播放默认音效):
    """在指定的世界坐标位置播放限时特效"""
    log_info(f"[播放限时特效] 执行")
