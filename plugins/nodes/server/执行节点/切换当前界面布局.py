from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="切换当前界面布局",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标玩家", "实体"), ("布局索引", "整数")],
    outputs=[("流程出", "流程")],
    description="可以通过布局索引来切换目标玩家当前的界面布局",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 切换当前界面布局(game, 目标玩家, 布局索引):
    """可以通过布局索引来切换目标玩家当前的界面布局"""
    index = int(布局索引)
    log_info("[切换当前界面布局] layout_index={}", index)
    # 离线运行时：记录 UI patch（不代表真实游戏 UI）
    ui_switch = getattr(game, "ui_switch_layout", None)
    if callable(ui_switch):
        ui_switch(目标玩家, index)
