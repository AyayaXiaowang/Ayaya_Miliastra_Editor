from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="根据玩家GUID获取玩家序号",
    category="查询节点",
    inputs=[("玩家GUID", "GUID")],
    outputs=[("玩家序号", "整数")],
    description="根据玩家GUID获取玩家序号，玩家序号即该玩家为玩家几",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 根据玩家GUID获取玩家序号(game, 玩家GUID):
    """根据玩家GUID获取玩家序号，玩家序号即该玩家为玩家几"""
    # 本地测试/导出代码常见 GUID 形态：由【根据玩家序号获取玩家GUID】生成
    # - player_<n>_guid
    text = str(玩家GUID or "").strip()
    prefix = "player_"
    suffix = "_guid"
    if text.startswith(prefix) and text.endswith(suffix) and len(text) > len(prefix) + len(suffix):
        mid = text[len(prefix) : -len(suffix)]
        if mid.isdigit():
            idx = int(mid)
            return idx if idx > 0 else 1

    # 回退：无法解析时默认视为玩家1（保持与旧占位实现一致，避免离线运行期直接中断）
    return 1
