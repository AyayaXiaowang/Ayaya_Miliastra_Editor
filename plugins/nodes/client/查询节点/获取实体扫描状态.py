from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取实体扫描状态",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("扫描状态", "枚举")],
    description="获取实体扫描状态",
    doc_reference="客户端节点/查询节点/查询节点.md",
    output_enum_options={
        "扫描状态": [
            "目标不可用",
            "当前扫描目标",
            "候选目标",
            "不满足条件",
        ],
    },
)
def 获取实体扫描状态(game, 目标实体):
    """获取实体扫描状态"""
    return None  # 扫描状态
