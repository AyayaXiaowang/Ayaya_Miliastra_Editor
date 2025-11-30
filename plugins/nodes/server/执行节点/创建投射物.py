from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="创建投射物",
    category="执行节点",
    inputs=[("流程入", "流程"), ("元件ID", "元件ID"), ("位置", "三维向量"), ("旋转", "三维向量"), ("拥有者实体", "实体"), ("追踪目标", "实体"), ("是否覆写等级", "布尔值"), ("等级", "整数"), ("单位标签索引列表", "整数列表")],
    outputs=[("流程出", "流程"), ("创建出的实体", "实体")],
    description="根据元件ID创建一个投射物实体。与【创建元件】功能类似，但多一个【追踪目标】参数，可以为创建的投射物实体的投射运动器组件中追踪投射类型设置追踪目标",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 创建投射物(game, 元件ID, 位置, 旋转, 拥有者实体, 追踪目标, 是否覆写等级, 等级, 单位标签索引列表):
    """根据元件ID创建一个投射物实体。与【创建元件】功能类似，但多一个【追踪目标】参数，可以为创建的投射物实体的投射运动器组件中追踪投射类型设置追踪目标"""
    return None  # 创建出的实体
