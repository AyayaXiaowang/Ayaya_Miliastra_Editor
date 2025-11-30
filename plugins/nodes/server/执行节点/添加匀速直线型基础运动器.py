from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="添加匀速直线型基础运动器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("运动器名称", "字符串"), ("运动器时长", "浮点数"), ("速度向量", "三维向量")],
    outputs=[("流程出", "流程")],
    description="在运行时动态添加一个匀速直线型基础运动器",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 添加匀速直线型基础运动器(game, 目标实体, 运动器名称, 运动器时长, 速度向量):
    """在运行时动态添加一个匀速直线型基础运动器"""
    log_info(f"[添加匀速直线型基础运动器] 执行")
