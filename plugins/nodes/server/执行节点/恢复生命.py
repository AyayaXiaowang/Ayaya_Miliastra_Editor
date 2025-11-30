from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="恢复生命",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("恢复量", "浮点数"), ("能力单元", "字符串"), ("是否覆写能力单元配置", "布尔值"), ("恢复发起者实体", "实体")],
    outputs=[("流程出", "流程")],
    description="通过能力单元为指定目标实体恢复生命",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 恢复生命(game, 目标实体, 恢复量, 能力单元, 是否覆写能力单元配置, 恢复发起者实体):
    """通过能力单元为指定目标实体恢复生命"""
    log_info(f"[恢复生命] 执行")
