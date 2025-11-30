from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info


@node_spec(
    name="发送信号",
    category="执行节点",
    inputs=[
        ("流程入", "流程"),
        ("信号名", "字符串"),
    ],
    outputs=[("流程出", "流程")],
    dynamic_port_type="泛型",
    description="向关卡全局发送一个自定义信号，使用前需要先选择对应的信号名，然后才能正确的使用该信号的参数",
    doc_reference="服务器节点/执行节点/执行节点.md",
)
def 发送信号(game):
    """向关卡全局发送一个自定义信号，使用前需要先选择对应的信号名，然后才能正确的使用该信号的参数。

    当前实现仍然使用通用事件系统触发占位事件，真实的信号发送逻辑在可执行代码生成器中通过 game.emit_signal 完成。
    """
    log_info("[发送信号] 占位实现（可执行代码生成路径会使用统一的 emit_signal 调用）")
    game.trigger_event("自定义信号")
