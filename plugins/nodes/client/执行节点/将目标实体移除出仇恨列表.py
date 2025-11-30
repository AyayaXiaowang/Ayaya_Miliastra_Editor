from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="将目标实体移除出仇恨列表",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("仇恨拥有者实体", "实体")],
    outputs=[("流程出", "流程")],
    description="仅自定义仇恨模式可用 将目标实体移出仇恨拥有者实体的仇恨列表，这可能导致目标实体脱战",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 将目标实体移除出仇恨列表(game, 目标实体, 仇恨拥有者实体):
    """仅自定义仇恨模式可用 将目标实体移出仇恨拥有者实体的仇恨列表，这可能导致目标实体脱战"""
    log_info(f"[仇恨列表] 从{仇恨拥有者实体}的仇恨列表中移除{目标实体}")
