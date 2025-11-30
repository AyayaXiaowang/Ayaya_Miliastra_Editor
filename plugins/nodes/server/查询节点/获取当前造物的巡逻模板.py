from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取当前造物的巡逻模板",
    category="查询节点",
    inputs=[("造物实体", "实体")],
    outputs=[("巡逻模板序号", "整数"), ("路径索引", "整数"), ("目标路点序号", "整数")],
    description="获取指定造物实体的巡逻模板信息",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取当前造物的巡逻模板(game, 造物实体):
    """获取指定造物实体的巡逻模板信息"""
    return {"模板ID": "patrol_01", "路径索引": 0}
