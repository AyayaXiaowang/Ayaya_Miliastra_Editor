from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="设置成就进度计数",
    category="执行节点",
    inputs=[("流程入", "流程"), ("设置实体", "实体"), ("成就序号", "整数"), ("进度计数", "整数")],
    outputs=[("流程出", "流程")],
    description="设置指定实体上对应成就序号的成就进度计数",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 设置成就进度计数(game, 设置实体, 成就序号, 进度计数):
    """设置指定实体上对应成就序号的成就进度计数"""
    idx = int(成就序号)
    count = int(进度计数)
    var_name = f"成就进度计数_{idx}"
    game.set_custom_variable(设置实体, var_name, int(count), trigger_event=True)
    log_info("[设置成就进度计数] {} = {}", var_name, int(count))
