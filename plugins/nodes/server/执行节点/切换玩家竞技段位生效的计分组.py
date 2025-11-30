from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="切换玩家竞技段位生效的计分组",
    category="执行节点",
    inputs=[("流程入", "流程"), ("玩家实体", "实体"), ("计分组序号", "整数")],
    outputs=[("流程出", "流程")],
    description="以计分组的序号切换指定玩家竞技段位生效的计分组",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 切换玩家竞技段位生效的计分组(game, 玩家实体, 计分组序号):
    """以计分组的序号切换指定玩家竞技段位生效的计分组"""
    log_info(f"[切换玩家竞技段位生效的计分组] 执行")
