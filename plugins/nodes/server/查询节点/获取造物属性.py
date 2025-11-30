from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取造物属性",
    category="查询节点",
    inputs=[("造物实体", "实体")],
    outputs=[("等级", "整数"), ("当前生命值", "浮点数"), ("上限生命值", "浮点数"), ("当前攻击力", "浮点数"), ("基础攻击力", "浮点数"), ("受打断值上限", "浮点数"), ("当前受打断值", "浮点数"), ("当前受打断状态", "枚举")],
    description="获取指定造物的属性",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取造物属性(game, 造物实体):
    """获取指定造物的属性"""
    return {"生命值": 1000, "攻击力": 100}
