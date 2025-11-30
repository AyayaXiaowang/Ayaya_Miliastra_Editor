from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info


@node_spec(
    name="监听信号",
    category="事件节点",
    inputs=[
        ("信号名", "字符串"),
    ],
    outputs=[
        ("流程出", "流程"),
        ("事件源实体", "实体"),
        ("事件源GUID", "GUID"),
        ("信号来源实体", "实体"),
    ],
    dynamic_port_type="泛型",
    description="监听已在信号管理器中定义的信号触发事件，需先选择需要监听的信号名",
    doc_reference="服务器节点/事件节点/事件节点.md",
)
def 监听信号(game):
    """监听已在信号管理器中定义的信号触发事件 需先选择需要监听的信号名。

    当前实现用于占位与调试，可执行代码生成器会根据绑定的 SignalConfig 将信号参数作为事件参数传入。
    """
    事件源 = game.create_mock_entity("监听者")
    信号源 = game.create_mock_entity("信号发送者")
    log_info("[监听信号] 占位实现（可执行代码生成路径会使用统一的信号事件上下文）")
    return 事件源, "监听者_guid", 信号源
