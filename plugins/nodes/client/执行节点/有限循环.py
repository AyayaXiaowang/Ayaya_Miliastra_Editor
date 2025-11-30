from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="有限循环",
    category="执行节点",
    inputs=[("流程入", "流程"), ("跳出循环", "流程"), ("循环起始值", "整数"), ("循环终止值", "整数")],
    outputs=[("循环体", "流程"), ("循环完成", "流程"), ("当前循环值", "整数")],
    description="从【循环起始值】开始到【循环终止值】结束，会遍历其中的循环值，每次整数加一。每次循环会执行一次【循环体】后连接的节点逻辑。完成一次完整遍历后，会执行【循环完成】后连接的节点逻辑。 可以使用【跳出循环】来提前结束该循环值遍历",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 有限循环(game, 循环起始值, 循环终止值):
    """从【循环起始值】开始到【循环终止值】结束，会遍历其中的循环值，每次整数加一。每次循环会执行一次【循环体】后连接的节点逻辑。完成一次完整遍历后，会执行【循环完成】后连接的节点逻辑。 可以使用【跳出循环】来提前结束该循环值遍历"""
    log_info(f"[有限循环] {循环起始值} -> {循环终止值}")
    protection = LoopProtection()
    for 当前循环值 in range(循环起始值, 循环终止值 + 1):
        protection.check()
        return 当前循环值
    return None
