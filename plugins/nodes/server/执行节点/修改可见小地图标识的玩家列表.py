from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="修改可见小地图标识的玩家列表",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("小地图标识序号", "整数"), ("玩家列表", "实体列表")],
    outputs=[("流程出", "流程")],
    description="目标实体的小地图标识组件上对应序号的小地图标识对玩家列表中的玩家可见",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 修改可见小地图标识的玩家列表(game, 目标实体, 小地图标识序号, 玩家列表):
    """目标实体的小地图标识组件上对应序号的小地图标识对玩家列表中的玩家可见"""
    log_info(f"[修改可见小地图标识的玩家列表] 执行")
