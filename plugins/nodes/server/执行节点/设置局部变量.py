from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置局部变量",
    category="执行节点",
    inputs=[("流程入", "流程"), ("局部变量", "局部变量"), ("值", "泛型")],
    outputs=[("流程出", "流程")],
    description="与查询节点【获取局部变量】连接后可以覆写该局部变量的值",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置局部变量(game, 局部变量, 值):
    """与查询节点【获取局部变量】连接后可以覆写该局部变量的值"""
    # 注意：局部变量在生成阶段会被处理为Python变量赋值
    # 这个函数在生成的代码中实际上是 `变量名 = 值`
    # 这里提供一个占位实现
    log_info(f"[局部变量] 设置 = {值}")
