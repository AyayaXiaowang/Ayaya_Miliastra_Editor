from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="停止并删除基础运动器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("运动器名称", "字符串"), ("是否停止所有基础运动器", "布尔值")],
    outputs=[("流程出", "流程")],
    description="停止并删除一个运行中的运动器",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 停止并删除基础运动器(game, 目标实体, 运动器名称, 是否停止所有基础运动器):
    """停止并删除一个运行中的运动器"""
    log_info(f"[停止并删除基础运动器] 执行")
