from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="切换造物巡逻模板",
    category="执行节点",
    inputs=[("流程入", "流程"), ("造物实体", "实体"), ("巡逻模板序号", "整数")],
    outputs=[("流程出", "流程")],
    description="造物切换的巡逻模板即刻切换，并按照新的巡逻模板进行移动",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 切换造物巡逻模板(game, 造物实体, 巡逻模板序号):
    """造物切换的巡逻模板即刻切换，并按照新的巡逻模板进行移动"""
    log_info(f"[切换造物巡逻模板] 执行")
