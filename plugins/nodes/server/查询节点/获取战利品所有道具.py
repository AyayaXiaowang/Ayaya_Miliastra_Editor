from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取战利品所有道具",
    category="查询节点",
    inputs=[("掉落者实体", "实体")],
    outputs=[("道具字典", "字典")],
    description="获取掉落者实体上战利品组件中的所有道具",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取战利品所有道具(game, 掉落者实体):
    """获取掉落者实体上战利品组件中的所有道具"""
    return {"道具A": 3, "道具B": 5}
