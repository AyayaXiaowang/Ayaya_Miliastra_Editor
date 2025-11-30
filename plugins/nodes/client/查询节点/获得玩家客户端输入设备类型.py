from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获得玩家客户端输入设备类型",
    category="查询节点",
    outputs=[("输入设备类型", "枚举")],
    description="获得玩家的客户端输入设备类型，根据用户界面的映射方式决定",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 获得玩家客户端输入设备类型():
    """获得玩家的客户端输入设备类型，根据用户界面的映射方式决定"""
    return None  # 输入设备类型
