from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="列表迭代循环",
    category="执行节点",
    inputs=[("流程入", "流程"), ("跳出循环", "流程"), ("列表", "泛型列表")],
    outputs=[("循环体", "流程"), ("循环完成", "流程"), ("迭代值", "泛型")],
    description="按照列表顺序遍历循环指定列表",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 列表迭代循环(game, 迭代列表):
    """按照列表顺序遍历循环指定列表"""
    # 注意：实际循环逻辑由代码生成器生成 for 循环代码
    log_info(f"[列表迭代] 遍历列表: {迭代列表}")
    if isinstance(迭代列表, list) and len(迭代列表) > 0:
        return 迭代列表[0]
    return None
