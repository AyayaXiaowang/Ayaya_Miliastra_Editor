from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *

@node_spec(
    name="设置节点图变量",
    category="执行节点",
    semantic_id="graph_var.set",
    inputs=[("流程入", "流程"), ("变量名", "字符串"), ("变量值", "泛型"), ("是否触发事件", "布尔值")],
    outputs=[("流程出", "流程")],
    description="为当前节点图内的指定节点图变量设置值",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置节点图变量(game, 变量名, 变量值, 是否触发事件):
    """为当前节点图内的指定节点图变量设置值"""
    name = str(变量名 or "").strip()
    if not name:
        raise ValueError("变量名不能为空")
    # 单一真源：委托 GameRuntime.set_graph_variable（同时支持 trace 与可选事件通知）
    game.set_graph_variable(name, 变量值, trigger_event=bool(是否触发事件))
