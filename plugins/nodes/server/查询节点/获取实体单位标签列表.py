from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取实体单位标签列表",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("单位标签列表", "整数列表")],
    description="获取目标实体上携带的所有单位标签组成的列表",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取实体单位标签列表(game, 目标实体):
    """获取目标实体上携带的所有单位标签组成的列表"""
    return ["标签1", "标签2"]
