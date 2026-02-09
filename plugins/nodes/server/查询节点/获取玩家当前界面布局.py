from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取玩家当前界面布局",
    category="查询节点",
    inputs=[("玩家实体", "实体")],
    outputs=[("布局索引", "整数")],
    description="获取指定玩家实体上当前生效的界面布局的索引",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取玩家当前界面布局(game, 玩家实体):
    """获取指定玩家实体上当前生效的界面布局的索引。

    说明：
    - 本地测试（MockRuntime）中，布局索引由 `切换当前界面布局` 写入到运行态的 `ui_current_layout_by_player`；
    - 若运行态未提供该字段，则回退为 0（默认布局）。
    """
    get_entity_id = getattr(game, "_get_entity_id", None)
    if callable(get_entity_id):
        player_id = str(get_entity_id(玩家实体))
    else:
        player_id = str(getattr(玩家实体, "entity_id", None) or 玩家实体)

    store = getattr(game, "ui_current_layout_by_player", None)
    if isinstance(store, dict):
        value = store.get(player_id, 0)
        idx = int(value or 0)
        log_info("[获取玩家当前界面布局] {} -> {}", player_id, idx)
        return idx

    return 0
