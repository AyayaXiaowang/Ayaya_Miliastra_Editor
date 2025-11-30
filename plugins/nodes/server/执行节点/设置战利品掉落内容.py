from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置战利品掉落内容",
    category="执行节点",
    inputs=[("流程入", "流程"), ("掉落者实体", "实体"), ("战利品掉落字典", "字典")],
    outputs=[("流程出", "流程")],
    description="以字典形式设置掉落者实体上战利品组件中战利品的掉落内容",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置战利品掉落内容(game, 掉落者实体, 战利品掉落字典):
    """以字典形式设置掉落者实体上战利品组件中战利品的掉落内容"""
    log_info(f"[设置战利品掉落内容] 执行")
