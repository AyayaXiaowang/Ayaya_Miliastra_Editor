from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="两坐标点距离",
    category="运算节点",
    inputs=[("坐标点1", "三维向量"), ("坐标点2", "三维向量")],
    outputs=[("距离", "浮点数")],
    description="计算两个坐标点之间的欧式距离",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 两坐标点距离(game, 坐标点1, 坐标点2):
    """计算两个坐标点之间的欧式距离"""
    dx = 坐标点2[0] - 坐标点1[0]
    dy = 坐标点2[1] - 坐标点1[1]
    dz = 坐标点2[2] - 坐标点1[2]
    return math.sqrt(dx*dx + dy*dy + dz*dz)
