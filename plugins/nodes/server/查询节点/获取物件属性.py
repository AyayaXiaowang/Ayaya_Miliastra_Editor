from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取物件属性",
    category="查询节点",
    inputs=[("物件实体", "实体")],
    outputs=[("等级", "整数"), ("当前生命值", "浮点数"), ("上限生命值", "浮点数"), ("当前攻击力", "浮点数"), ("基础攻击力", "浮点数"), ("当前防御力", "浮点数"), ("基础防御力", "浮点数")],
    description="获取物件的相关基础属性",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取物件属性(game, 物件实体):
    """获取物件的相关基础属性"""
    return None  # Mock返回
