from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="清空指定实体的仇恨列表",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体")],
    outputs=[("流程出", "流程")],
    description="仅自定义仇恨模式可用 清空指定实体的仇恨列表，这通常会导致该目标脱战",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 清空指定实体的仇恨列表(game, 目标实体):
    """仅自定义仇恨模式可用 清空指定实体的仇恨列表，这通常会导致该目标脱战"""
    log_info(f"[清空指定实体的仇恨列表] 执行")
