from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="添加朝向目标旋转型基础运动器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("运动器名称", "字符串"), ("运动器时长", "浮点数"), ("目标角度", "三维向量")],
    outputs=[("流程出", "流程")],
    description="在关卡运行时为目标实体动态添加一个朝向目标旋转型基础运动器",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 添加朝向目标旋转型基础运动器(game, 目标实体, 运动器名称, 运动器时长, 目标角度):
    """在关卡运行时为目标实体动态添加一个朝向目标旋转型基础运动器"""
    log_info(f"[添加朝向目标旋转型基础运动器] 执行")
