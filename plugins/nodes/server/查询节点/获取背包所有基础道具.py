from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取背包所有基础道具",
    category="查询节点",
    inputs=[("背包持有者实体", "实体")],
    outputs=[("基础道具字典", "字典")],
    description="获取背包所有基础道具，包括道具类型和对应的数量",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取背包所有基础道具(game, 背包持有者实体):
    """获取背包所有基础道具，包括道具类型和对应的数量"""
    return {"药水": 10, "材料A": 50}
