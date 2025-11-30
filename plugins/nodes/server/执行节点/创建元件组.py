from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="创建元件组",
    category="执行节点",
    inputs=[("流程入", "流程"), ("元件组索引", "整数"), ("位置", "三维向量"), ("旋转", "三维向量"), ("归属者实体", "实体"), ("等级", "整数"), ("单位标签索引列表", "整数列表"), ("是否覆写等级", "布尔值")],
    outputs=[("流程出", "流程"), ("创建后实体列表", "实体列表")],
    description="根据元件组索引创建该元件组内包含的实体",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 创建元件组(game, 元件组索引, 位置, 旋转, 归属者实体, 等级, 单位标签索引列表, 是否覆写等级):
    """根据元件组索引创建该元件组内包含的实体"""
    log_info(f"[创建元件组] 元件组{元件组索引} 在位置{位置}")
    # Mock: 创建3个模拟实体
    实体列表 = [
        game.create_mock_entity(f"元件组实体1"),
        game.create_mock_entity(f"元件组实体2"),
        game.create_mock_entity(f"元件组实体3")
    ]
    return 实体列表
