from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置节点图变量",
    category="执行节点",
    inputs=[("流程入", "流程"), ("变量名", "字符串"), ("变量值", "泛型"), ("是否触发事件", "布尔值")],
    outputs=[("流程出", "流程")],
    description="为当前节点图内的指定节点图变量设置值",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置节点图变量(game, 变量名, 变量值, 是否触发事件):
    """为当前节点图内的指定节点图变量设置值"""
    # 节点图变量存储在game的全局变量中
    if not hasattr(game, '节点图变量'):
        game.节点图变量 = {}
    game.节点图变量[变量名] = 变量值
    log_info(f"[节点图变量] {变量名} = {变量值}")
    if 是否触发事件:
        game.trigger_event(f"节点图变量变化_{变量名}", 变量名=变量名, 变量值=变量值)
