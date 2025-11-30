from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="修改角色扰动装置",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("装置序号", "整数")],
    outputs=[("流程出", "流程")],
    description="通过序号修改目标实体上生效的角色扰动装置，若序号不存在则此次修改不生效",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 修改角色扰动装置(game, 目标实体, 装置序号):
    """通过序号修改目标实体上生效的角色扰动装置，若序号不存在则此次修改不生效"""
    log_info(f"[修改角色扰动装置] 执行")
