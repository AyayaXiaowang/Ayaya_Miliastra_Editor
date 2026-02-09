from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取实体的类型",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("实体类型", "枚举")],
    description="获取指定实体的类型",
    doc_reference="客户端节点/查询节点/查询节点.md",
    output_enum_options={
        "实体类型": [
            "实体类型_关卡",
            "实体类型_物件",
            "实体类型_玩家",
            "实体类型_角色",
            "实体类型_造物",
        ],
    },
)
def 获取实体的类型(game, 目标实体):
    """获取指定实体的类型"""
    # Mock: 返回模拟实体类型
    return "实体类型_物件"
