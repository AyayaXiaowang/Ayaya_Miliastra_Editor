from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询对局游玩方式及人数",
    category="查询节点",
    outputs=[("游玩人数", "整数"), ("游玩方式", "枚举")],
    description="查询进入对局的理论人数，即参与匹配或开房间的人数和进入对局的方式",
    doc_reference="服务器节点/查询节点/查询节点.md",
    output_enum_options={
        "游玩方式": [
            "试玩",
            "房间游玩",
            "匹配游玩",
        ],
    },
)
def 查询对局游玩方式及人数(game=None):
    """查询进入对局的理论人数，即参与匹配或开房间的人数和进入对局的方式"""
    # 兼容：部分历史图可能会以“无 game 参数”形式调用该节点。
    if game is None:
        return 4, "匹配游玩"  # 游玩人数, 游玩方式

    player_count = int(getattr(game, "present_player_count", 0) or 0)
    if player_count <= 0:
        get_players = getattr(game, "get_present_player_entities", None)
        if callable(get_players):
            player_count = len(list(get_players()))
        else:
            player_count = 1

    mode = str(getattr(game, "play_mode", "") or "")
    if mode not in {"试玩", "房间游玩", "匹配游玩"}:
        mode = "匹配游玩"
    return int(player_count), mode
