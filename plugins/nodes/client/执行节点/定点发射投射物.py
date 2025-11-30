from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="定点发射投射物",
    category="执行节点",
    inputs=[("流程入", "流程"), ("投射物的元件ID", "元件ID"), ("创建位置", "三维向量"), ("创建旋转", "三维向量"), ("追踪目标", "实体"), ("投射物阵营", "阵营")],
    outputs=[("流程出", "流程")],
    description="在世界坐标系的指定位置发射本地投射物",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 定点发射投射物(game, 投射物的元件ID, 创建位置, 创建旋转, 追踪目标, 投射物阵营):
    """在世界坐标系的指定位置发射本地投射物"""
    log_info(f"[定点发射投射物] 执行")
