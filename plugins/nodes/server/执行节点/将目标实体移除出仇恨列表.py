from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="将目标实体移除出仇恨列表",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("仇恨拥有者实体", "实体")],
    outputs=[("流程出", "流程")],
    description="仅自定义仇恨模式可用 将目标实体从仇恨拥有者的仇恨列表中移除，可能会导致目标实体脱战",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 将目标实体移除出仇恨列表(game, 目标实体, 仇恨拥有者实体):
    """仅自定义仇恨模式可用 将目标实体从仇恨拥有者的仇恨列表中移除，可能会导致目标实体脱战"""
    log_info(f"[将目标实体移除出仇恨列表] 执行")
