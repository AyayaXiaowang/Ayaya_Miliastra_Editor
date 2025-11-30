from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="开关实体光源",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("光源序号", "整数"), ("打开或关闭", "布尔值")],
    outputs=[("流程出", "流程")],
    description="调整指定目标实体上的光源组件对应序号的光源状态",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 开关实体光源(game, 目标实体, 光源序号, 打开或关闭):
    """调整指定目标实体上的光源组件对应序号的光源状态"""
    log_info(f"[开关实体光源] 执行")
