from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="对列表插入值",
    category="执行节点",
    inputs=[("流程入", "流程"), ("列表", "泛型列表"), ("插入序号", "整数"), ("插入值", "泛型")],
    outputs=[("流程出", "流程")],
    description="向指定列表的指定序号位置插入值。被插入的值在插入后会出现在列表的插入序号位置 例如：向列表[1，2，3，4]的序号2插入值5，插入后的列表为[1，2，5，3，4]（5出现在序号2的位置）",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 对列表插入值(game, 列表, 插入序号, 插入值):
    """向指定列表的指定序号位置插入值。被插入的值在插入后会出现在列表的插入序号位置 例如：向列表[1，2，3，4]的序号2插入值5，插入后的列表为[1，2，5，3，4]（5出现在序号2的位置）"""
    if isinstance(列表, list):
        列表.insert(插入序号, 插入值)
        log_info(f"[列表插入] 序号{插入序号} <- {插入值}, 结果: {列表}")
