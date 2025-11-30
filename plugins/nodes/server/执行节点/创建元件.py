from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="创建元件",
    category="执行节点",
    inputs=[("流程入", "流程"), ("元件ID", "元件ID"), ("位置", "三维向量"), ("旋转", "三维向量"), ("拥有者实体", "实体"), ("是否覆写等级", "布尔值"), ("等级", "整数"), ("单位标签索引列表", "整数列表")],
    outputs=[("流程出", "流程"), ("创建后实体", "实体")],
    description="根据元件ID创建一个实体",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 创建元件(game, 元件ID, 位置, 旋转, 拥有者实体, 是否覆写等级, 等级, 单位标签索引列表):
    """根据元件ID创建一个实体"""
    新实体 = game.create_mock_entity(f"元件_{元件ID}")
    if isinstance(位置, (list, tuple)) and len(位置) == 3:
        新实体.position = list(位置)
    if isinstance(旋转, (list, tuple)) and len(旋转) == 3:
        新实体.rotation = list(旋转)
    return 新实体
