from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="直接恢复生命",
    category="执行节点",
    inputs=[("流程入", "流程"), ("恢复发起实体", "实体"), ("恢复目标实体", "实体"), ("恢复量", "浮点数"), ("是否忽略恢复量调整", "布尔值"), ("产生仇恨的倍率", "浮点数"), ("产生仇恨的增量", "浮点数"), ("治疗标签列表", "字符串列表")],
    outputs=[("流程出", "流程")],
    description="直接恢复指定实体目标的生命。与【恢复生命】不同的是，此节点不需要使用能力单元",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 直接恢复生命(game, 恢复发起实体, 恢复目标实体, 恢复量, 是否忽略恢复量调整, 产生仇恨的倍率, 产生仇恨的增量, 治疗标签列表):
    """直接恢复指定实体目标的生命。与【恢复生命】不同的是，此节点不需要使用能力单元"""
    log_info(f"[直接恢复生命] 执行")
