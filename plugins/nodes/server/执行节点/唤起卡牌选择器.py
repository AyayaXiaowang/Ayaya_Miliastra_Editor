from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="唤起卡牌选择器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标玩家", "实体"), ("卡牌选择器索引", "整数"), ("选择时长", "浮点数"), ("选择结果对应列表", "整数列表"), ("选择显示对应列表", "整数列表"), ("选择数量下限", "整数"), ("选择数量上限", "整数"), ("刷新方式", "枚举"), ("刷新数量下限", "整数"), ("刷新数量上限", "整数"), ("默认返回选择", "整数列表")],
    outputs=[("流程出", "流程")],
    description="对目标玩家打开提前制作好的卡牌选择器",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 唤起卡牌选择器(game, 目标玩家, 卡牌选择器索引, 选择时长, 选择结果对应列表, 选择显示对应列表, 选择数量下限, 选择数量上限, 刷新方式, 刷新数量下限, 刷新数量上限, 默认返回选择):
    """对目标玩家打开提前制作好的卡牌选择器"""
    log_info(f"[唤起卡牌选择器] 执行")
