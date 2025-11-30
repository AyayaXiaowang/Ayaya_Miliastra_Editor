from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="自定义变量变化时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID"), ("变量名", "字符串"), ("变化前值", "泛型"), ("变化后值", "泛型")],
    description="当前节点图所关联实体的自定义变量发生变化时，触发该事件 注意变化前值和变化后值为泛型，需确定其泛型类型后，才能正确接收到对应类型自定义变量的事件 容器类型的自定义变量没有变化前值和变化后值出参",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 自定义变量变化时(game):
    """当前节点图所关联实体的自定义变量发生变化时，触发该事件 注意变化前值和变化后值为泛型，需确定其泛型类型后，才能正确接收到对应类型自定义变量的事件 容器类型的自定义变量没有变化前值和变化后值出参"""
    事件源 = game.get_entity("self")
    return 事件源, "self_guid", "自定义变量1", "旧值", "新值"
