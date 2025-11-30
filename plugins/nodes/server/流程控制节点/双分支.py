from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_流程控制节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="双分支",
    category="流程控制节点",
    scopes=["server"],
    inputs=[("流程入", "流程"), ("条件", "布尔值")],
    outputs=[("是", "流程"), ("否", "流程")],
    description="根据布尔条件在【是】与【否】两个执行流之间分支。",
)
def 双分支(game, 条件, 是_callback=None, 否_callback=None):
    """根据输入条件的判断结果可以分出"是"与"否"两个不同的分支 当布尔值为"是"时，后续会执行【是】对应的执行流；布尔值为"否"时，会执行【否】对应的执行流"""
    log_info(f"[双分支] 条件 = {条件}")
    
    if 条件:
        log_info(f"  → 分支[是]")
        if 是_callback:
            是_callback()
    else:
        log_info(f"  → 分支[否]")
        if 否_callback:
            否_callback()
