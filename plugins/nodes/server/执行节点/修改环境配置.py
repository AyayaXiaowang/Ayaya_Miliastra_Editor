from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="修改环境配置",
    category="执行节点",
    inputs=[("流程入", "流程"), ("环境配置索引", "整数"), ("目标玩家列表", "实体列表"), ("是否启用天气配置", "布尔值"), ("天气配置序号", "整数")],
    outputs=[("流程出", "流程")],
    description="使指定玩家应用指定的环境配置，运行后会立即生效",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 修改环境配置(game, 环境配置索引, 目标玩家列表, 是否启用天气配置, 天气配置序号):
    """使指定玩家应用指定的环境配置，运行后会立即生效"""
    log_info(f"[修改环境配置] 执行")
