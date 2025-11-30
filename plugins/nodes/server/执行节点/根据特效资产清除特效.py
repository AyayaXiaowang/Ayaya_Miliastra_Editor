from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="根据特效资产清除特效",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("特效资产", "配置ID")],
    outputs=[("流程出", "流程")],
    description="清除指定目标实体上所有使用该特效资产的特效。仅限循环特效",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 根据特效资产清除特效(game, 目标实体, 特效资产):
    """清除指定目标实体上所有使用该特效资产的特效。仅限循环特效"""
    log_info(f"[根据特效资产清除特效] 执行")
