from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取射线检测结果",
    category="查询节点",
    inputs=[("检测发起者实体", "实体"), ("出射位置", "三维向量"), ("出射方向", "三维向量"), ("射线最大长度", "浮点数"), ("阵营筛选", "枚举"), ("实体类型筛选", "枚举"), ("命中层筛选", "枚举")],
    outputs=[("命中位置", "三维向量"), ("命中实体", "实体")],
    description="获取射线检测结果，会根据射线命中从近到远的顺序返回满足筛选条件的第一个目标或命中位置",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 获取射线检测结果(game, 检测发起者实体, 出射位置, 出射方向, 射线最大长度, 阵营筛选, 实体类型筛选, 命中层筛选):
    """获取射线检测结果，会根据射线命中从近到远的顺序返回满足筛选条件的第一个目标或命中位置"""
    return None  # Mock返回
