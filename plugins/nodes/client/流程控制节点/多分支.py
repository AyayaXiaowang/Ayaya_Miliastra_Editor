from __future__ import annotations

from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_流程控制节点_impl_helpers import *  # noqa: F401,F403
from engine.utils.logging.logger import log_info


@node_spec(
    name="多分支",
    category="流程控制节点",
    inputs=[("流程入", "流程"), ("控制表达式", "泛型")],
    outputs=[("默认", "流程")],
    description="接受控制表达式，匹配分支回调，不匹配时走默认分支。",
    dynamic_port_type="流程",
    doc_reference="客户端节点/流程控制节点/流程控制节点.md",
    input_generic_constraints={
        "控制表达式": ["整数", "字符串"],
    },
)
def 多分支(game, 控制表达式, 分支_callbacks=None, 默认_callback=None):
    """根据控制表达式选择分支并触发对应回调。"""
    log_info(f"[多分支] 控制表达式 = {控制表达式}")
    if 分支_callbacks and isinstance(分支_callbacks, dict) and 控制表达式 in 分支_callbacks:
        callback = 分支_callbacks[控制表达式]
        log_info(f"  → 分支[{控制表达式}]")
        if callback:
            callback()
        return
    log_info("  → 默认分支")
    if 默认_callback:
        默认_callback()

