from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取目标挂接点位置",
    category="查询节点",
    inputs=[("目标实体", "实体"), ("挂接点名称", "字符串")],
    outputs=[("挂接点位置", "三维向量")],
    description="获取指定目标实体上对应挂接点名称的挂接点位置",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 获取目标挂接点位置(game, 目标实体, 挂接点名称):
    """获取指定目标实体上对应挂接点名称的挂接点位置"""
    # Mock: 返回模拟挂接点位置
    return [0, 1, 0]  # 模拟在实体上方1米的位置
