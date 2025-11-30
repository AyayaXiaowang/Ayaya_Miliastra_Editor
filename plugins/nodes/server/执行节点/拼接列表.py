from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="拼接列表",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标列表", "泛型列表"), ("接入的列表", "泛型列表")],
    outputs=[("流程出", "流程")],
    description="将接入列表拼接在目标列表后。例如：目标列表为[1,2,3]，接入的列表为[4,5]，在执行该节点后，目标列表会变为[1，2，3，4，5]",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 拼接列表(game, 目标列表, 接入的列表):
    """将接入列表拼接在目标列表后。例如：目标列表为[1,2,3]，接入的列表为[4,5]，在执行该节点后，目标列表会变为[1，2，3，4，5]"""
    if isinstance(目标列表, list) and isinstance(接入的列表, list):
        目标列表.extend(接入的列表)
        log_info(f"[拼接列表] 结果: {目标列表}")
