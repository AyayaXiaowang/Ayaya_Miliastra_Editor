from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取扫描组件可扫描的所有合法对象",
    category="查询节点",
    outputs=[("对象列表", "实体列表")],
    description="获取扫描组件可扫描的所有合法对象，此处的合法对象指代所有携带扫描组件且过滤器返回为“是”的单位，与单位的可扫描状态无关",
    doc_reference="客户端节点/查询节点/查询节点.md"
)
def 获取扫描组件可扫描的所有合法对象():
    """获取扫描组件可扫描的所有合法对象，此处的合法对象指代所有携带扫描组件且过滤器返回为“是”的单位，与单位的可扫描状态无关"""
    return None  # 对象列表
