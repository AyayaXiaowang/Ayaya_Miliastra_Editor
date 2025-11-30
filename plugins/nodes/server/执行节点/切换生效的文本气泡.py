from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="切换生效的文本气泡",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("文本气泡配置ID", "配置ID")],
    outputs=[("流程出", "流程")],
    description="目标实体的文本气泡组件中，会以配置ID对应的文本气泡替换当前生效的文本气泡",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 切换生效的文本气泡(game, 目标实体, 文本气泡配置ID):
    """目标实体的文本气泡组件中，会以配置ID对应的文本气泡替换当前生效的文本气泡"""
    log_info(f"[切换生效的文本气泡] 执行")
