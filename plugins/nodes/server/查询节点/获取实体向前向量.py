from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取实体向前向量",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("向前向量", "三维向量")],
    description="获取指定实体的向前向量（即该实体本地坐标系下的z轴正方向朝向）",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取实体向前向量(game, 目标实体):
    """获取指定实体的向前向量（即该实体本地坐标系下的z轴正方向朝向）"""
    return None  # 向前向量
