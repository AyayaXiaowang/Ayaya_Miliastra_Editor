from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置自定义变量",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("变量名", "字符串"), ("变量值", "泛型"), ("是否触发事件", "布尔值")],
    outputs=[("流程出", "流程")],
    description="为目标实体上的指定自定义变量设置值",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置自定义变量(game, 目标实体, 变量名, 变量值, 是否触发事件):
    """为目标实体上的指定自定义变量设置值"""
    game.set_custom_variable(目标实体, 变量名, 变量值, 是否触发事件)
