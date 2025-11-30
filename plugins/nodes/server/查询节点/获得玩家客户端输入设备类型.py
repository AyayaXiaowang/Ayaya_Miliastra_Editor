from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获得玩家客户端输入设备类型",
    category="查询节点",
    inputs=[("玩家实体", "实体")],
    outputs=[("输入设备类型", "枚举")],
    description="获得玩家的客户端输入设备类型，根据用户界面的映射方式决定",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获得玩家客户端输入设备类型(game, 玩家实体):
    """获得玩家的客户端输入设备类型，根据用户界面的映射方式决定"""
    return "键盘鼠标"
