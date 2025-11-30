from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取实体的小地图标识状态",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("全量小地图标识序号列表", "整数列表"), ("生效的小地图标识序号列表", "整数列表"), ("未生效的小地图标识序号列表", "整数列表")],
    description="查询实体当前小地图标识的配置及生效情况",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取实体的小地图标识状态(game, 目标实体):
    """查询实体当前小地图标识的配置及生效情况"""
    return {"配置ID": "map_icon_1", "是否显示": True}
