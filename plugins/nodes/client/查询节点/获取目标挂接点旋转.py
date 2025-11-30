from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取目标挂接点旋转",
    category="查询节点",
    inputs=[("目标实体", "实体"), ("挂接点名称", "字符串")],
    outputs=[("挂接点旋转", "三维向量")],
    description="获取指定目标实体上对应挂接点名称的挂接点旋转",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 获取目标挂接点旋转(game, 目标实体, 挂接点名称):
    """获取指定目标实体上对应挂接点名称的挂接点旋转"""
    # Mock: 返回模拟挂接点旋转
    return [0, 0, 0]  # 模拟无旋转
