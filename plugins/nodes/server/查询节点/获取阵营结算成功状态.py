from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取阵营结算成功状态",
    category="查询节点",
    inputs=[("阵营", "阵营")],
    outputs=[("结算状态", "枚举")],
    description="获取阵营结算成功状态",
    doc_reference="服务器节点/查询节点/查询节点.md",
    output_enum_options={
        "结算状态": [
            "未定",
            "胜利",
            "失败",
        ],
    },
)
def 获取阵营结算成功状态(game, 阵营):
    """获取阵营结算成功状态"""
    return "未定"
