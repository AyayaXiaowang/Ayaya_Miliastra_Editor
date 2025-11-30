from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置扫描组件的生效扫描标签序号",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("扫描标签序号", "整数")],
    outputs=[("流程出", "流程")],
    description="将目标实体的扫描标签组件中对应序号的扫描标签设置为生效",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置扫描组件的生效扫描标签序号(game, 目标实体, 扫描标签序号):
    """将目标实体的扫描标签组件中对应序号的扫描标签设置为生效"""
    log_info(f"[设置扫描组件的生效扫描标签序号] 执行")
