from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="镜头朝向检测数据",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标类型", "枚举"), ("出射位置", "三维向量"), ("最近距离", "浮点数"), ("最远距离", "浮点数")],
    outputs=[("流程出", "流程"), ("目标旋转", "三维向量"), ("目标位置", "三维向量")],
    description="镜头朝向检测数据，从镜头向出射位置打射线，返回路线上合法目标的旋转与位置",
    doc_reference="客户端节点/执行节点/执行节点.md",
    input_enum_options={
        "目标类型": [
            "无",
            "友善阵营",
            "敌对阵营",
            "自己",
            "自身阵营",
            "全部",
            "剔除自身的全部",
            "友善阵营包括自身",
        ],
    },
)
def 镜头朝向检测数据(game, 目标类型, 出射位置, 最近距离, 最远距离):
    """镜头朝向检测数据，从镜头向出射位置打射线，返回路线上合法目标的旋转与位置"""
    return None  # Mock返回
