from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="修改全局计时器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("计时器名称", "字符串"), ("变化值", "浮点数")],
    outputs=[("流程出", "流程")],
    description="通过节点图，可以将运行中的全局计时器时间进行调整 若计时器先暂停，后修改减少时间，则修改后时间最少为0s，若为倒计时，且修改时间为0，则会触发【全局计时器触发时】事件 若计时器先暂停，后修改时间到0s，再修改增加时间，则该计时器不会被触发 若有界面控件引用对应计时器，则界面控件的计时表现会同步修改",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 修改全局计时器(game, 目标实体, 计时器名称, 变化值):
    """通过节点图，可以将运行中的全局计时器时间进行调整 若计时器先暂停，后修改减少时间，则修改后时间最少为0s，若为倒计时，且修改时间为0，则会触发【全局计时器触发时】事件 若计时器先暂停，后修改时间到0s，再修改增加时间，则该计时器不会被触发 若有界面控件引用对应计时器，则界面控件的计时表现会同步修改"""
    log_info(f"[修改全局计时器] 执行")
