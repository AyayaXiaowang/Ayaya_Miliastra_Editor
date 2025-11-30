from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="按比例转移指定实体的仇恨值",
    category="执行节点",
    inputs=[("流程入", "流程"), ("转移目标实体", "实体"), ("转移来源实体", "实体"), ("仇恨拥有者实体", "实体"), ("转移比例", "浮点数")],
    outputs=[("流程出", "流程")],
    description="仅自定义仇恨模式可用 将仇恨拥有者上对转移来源实体一定比例的仇恨转移到转移目标实体上",
    doc_reference="客户端节点/执行节点/执行节点.md"
)
def 按比例转移指定实体的仇恨值(game, 转移目标实体, 转移来源实体, 仇恨拥有者实体, 转移比例):
    """仅自定义仇恨模式可用 将仇恨拥有者上对转移来源实体一定比例的仇恨转移到转移目标实体上"""
    log_info(f"[按比例转移指定实体的仇恨值] 执行")
