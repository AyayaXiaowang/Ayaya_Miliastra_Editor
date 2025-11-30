from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询指定小地图标识信息",
    category="查询节点",
    inputs=[("目标实体", "实体"), ("小地图标识序号", "整数")],
    outputs=[("生效状态", "布尔值"), ("可见标识的玩家列表", "实体列表"), ("追踪标识的玩家列表", "实体列表")],
    description="查询目标实体上小地图标识组件中特定序号对应的小地图标识的信息",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询指定小地图标识信息(game, 目标实体, 小地图标识序号):
    """查询目标实体上小地图标识组件中特定序号对应的小地图标识的信息"""
    return {"图标": "icon_01", "显示": True}
