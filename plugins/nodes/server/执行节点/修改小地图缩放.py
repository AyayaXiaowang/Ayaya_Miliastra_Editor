from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="修改小地图缩放",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标玩家", "实体"), ("缩放尺寸", "浮点数")],
    outputs=[("流程出", "流程")],
    description="修改目标玩家的小地图界面控件的地图比例",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 修改小地图缩放(game, 目标玩家, 缩放尺寸):
    """修改目标玩家的小地图界面控件的地图比例"""
    log_info(f"[修改小地图缩放] 执行")
