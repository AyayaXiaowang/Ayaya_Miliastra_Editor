from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="以整数设置玩家排行榜分数",
    category="执行节点",
    inputs=[("流程入", "流程"), ("玩家序号列表", "整数列表"), ("排行榜分数", "整数"), ("排行榜序号", "整数")],
    outputs=[("流程出", "流程")],
    description="以整数设置玩家排行榜分数",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 以整数设置玩家排行榜分数(game, 玩家序号列表, 排行榜分数, 排行榜序号):
    """以整数设置玩家排行榜分数"""
    if not isinstance(玩家序号列表, list):
        raise TypeError("以整数设置玩家排行榜分数：玩家序号列表 必须为 整数列表")

    lb_index = int(排行榜序号)
    score = int(排行榜分数)

    store = getattr(game, "leaderboards", None)
    if not isinstance(store, dict):
        store = {}
        setattr(game, "leaderboards", store)

    scores = store.get(lb_index, None)
    if not isinstance(scores, dict):
        scores = {}
        store[lb_index] = scores

    for player_idx in 玩家序号列表:
        scores[int(player_idx)] = int(score)

    log_info("[以整数设置玩家排行榜分数] lb_index={}, players={}, score={}", lb_index, len(玩家序号列表), score)
