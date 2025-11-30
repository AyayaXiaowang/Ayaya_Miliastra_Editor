from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="添加单位状态",
    category="执行节点",
    inputs=[("流程入", "流程"), ("施加者实体", "实体"), ("施加目标实体", "实体"), ("单位状态配置ID", "配置ID"), ("施加层数", "整数"), ("单位状态参数字典", "字典")],
    outputs=[("流程出", "流程"), ("施加结果", "枚举"), ("槽位序号", "整数")],
    description="向指定目标实体添加一定层数的单位状态",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 添加单位状态(game, 施加者实体, 施加目标实体, 单位状态配置ID, 施加层数, 单位状态参数字典):
    """向指定目标实体添加一定层数的单位状态"""
    return None  # Mock返回
