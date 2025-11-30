from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询自定义变量快照",
    category="查询节点",
    inputs=[("自定义变量组件快照", "自定义变量快照"), ("变量名", "字符串")],
    outputs=[("变量值", "泛型")],
    description="从自定义变量组件快照中，查询指定变量名的值 仅可用于【实体销毁时】事件",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询自定义变量快照(game, 自定义变量组件快照, 变量名):
    """从自定义变量组件快照中，查询指定变量名的值 仅可用于【实体销毁时】事件"""
    return None  # 变量值
