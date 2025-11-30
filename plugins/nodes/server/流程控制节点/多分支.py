from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_流程控制节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="多分支",
    category="流程控制节点",
    scopes=["server"],
    inputs=[("流程入", "流程"), ("控制表达式", "泛型")],
    outputs=[("默认", "流程")],
    description="接受控制表达式，匹配分支回调，不匹配时走默认分支。",
    dynamic_port_type="流程",
    input_generic_constraints={
        "控制表达式": ["整数", "字符串"],
    },
)
def 多分支(game, 控制表达式, 分支_callbacks=None, 默认_callback=None):
    """接受一个输入参数作为控制表达式(支持整数或字符串)，根据控制表达式的值可以分出多个不同的分支 当出引脚上的值与控制表达式的值相等时，会沿该出引脚向后执行逻辑。如果没有找到匹配的引脚，则会走【默认】引脚"""
    log_info(f"[多分支] 控制表达式 = {控制表达式}")
    
    if 分支_callbacks and isinstance(分支_callbacks, dict):
        if 控制表达式 in 分支_callbacks:
            callback = 分支_callbacks[控制表达式]
            log_info(f"  → 分支[{控制表达式}]")
            if callback:
                callback()
            return
    
    log_info(f"  → 默认分支")
    if 默认_callback:
        默认_callback()
