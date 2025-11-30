from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查找列表并返回值的序号",
    category="查询节点",
    inputs=[("目标列表", "泛型"), ("值", "泛型")],
    outputs=[("序号列表", "整数列表")],
    description="从列表中查找指定值，并返回列表中该值出现的序号列表 例如：目标列表为{1,2,3,2,1}，值为1，返回的序号列表为{0，4}，即1出现在目标列表的序号0和4",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查找列表并返回值的序号(目标列表, 值):
    """从列表中查找指定值，并返回列表中该值出现的序号列表 例如：目标列表为{1,2,3,2,1}，值为1，返回的序号列表为{0，4}，即1出现在目标列表的序号0和4"""
    if isinstance(目标列表, list):
        return [i for i, v in enumerate(目标列表) if v == 值]
    return []
