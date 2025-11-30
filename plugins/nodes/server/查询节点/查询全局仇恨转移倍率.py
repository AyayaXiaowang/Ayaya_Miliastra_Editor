from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询全局仇恨转移倍率",
    category="查询节点",
    outputs=[("全局仇恨转移倍率", "浮点数")],
    description="查询全局仇恨转移倍率，在【关卡设置】中可以配置",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询全局仇恨转移倍率(game):
    """查询全局仇恨转移倍率，在【关卡设置】中可以配置"""
    return 1.0
