from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="激活控件组库内界面控件组",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标玩家", "实体"), ("界面控件组索引", "整数")],
    outputs=[("流程出", "流程")],
    description="可以在目标玩家的界面布局上激活处于界面控件组库内的以自定义模板形式存在的界面控件组",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 激活控件组库内界面控件组(game, 目标玩家, 界面控件组索引):
    """可以在目标玩家的界面布局上激活处于界面控件组库内的以自定义模板形式存在的界面控件组"""
    log_info(f"[激活控件组库内界面控件组] 执行")
