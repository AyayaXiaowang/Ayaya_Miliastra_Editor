from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="激活基础运动器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("运动器名称", "字符串")],
    outputs=[("流程出", "流程")],
    description="激活一个配置在目标实体基础运动器组件上的运动器",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 激活基础运动器(game, 目标实体, 运动器名称):
    """激活一个配置在目标实体基础运动器组件上的运动器"""
    log_info(f"[激活基础运动器] 执行")
