from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="清空指定目标的仇恨列表",
    category="执行节点",
    inputs=[("流程入", "流程"), ("仇恨拥有者", "实体")],
    outputs=[("流程出", "流程")],
    description="仅自定义仇恨模式可用 清空仇恨拥有者的仇恨列表。可能会导致其脱战",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 清空指定目标的仇恨列表(game, 仇恨拥有者):
    """仅自定义仇恨模式可用 清空仇恨拥有者的仇恨列表。可能会导致其脱战"""
    log_info(f"[清空指定目标的仇恨列表] 执行")
