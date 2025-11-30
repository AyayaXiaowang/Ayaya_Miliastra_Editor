from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="修改小地图标识的玩家标记",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("小地图标识序号", "整数"), ("对应玩家实体", "实体")],
    outputs=[("流程出", "流程")],
    description="若小地图标识选择了玩家标记，在节点图输入对应玩家实体后，目标实体在小地图上的显示会变成输入玩家实体的头像",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 修改小地图标识的玩家标记(game, 目标实体, 小地图标识序号, 对应玩家实体):
    """若小地图标识选择了玩家标记，在节点图输入对应玩家实体后，目标实体在小地图上的显示会变成输入玩家实体的头像"""
    log_info(f"[修改小地图标识的玩家标记] 执行")
