from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="修改小地图标识生效状态",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("小地图标识序号列表", "整数列表"), ("是否生效", "布尔值")],
    outputs=[("流程出", "流程")],
    description="通过节点输入的小地图标识序号列表，批量修改目标实体的小地图标识生效状态",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 修改小地图标识生效状态(game, 目标实体, 小地图标识序号列表, 是否生效):
    """通过节点输入的小地图标识序号列表，批量修改目标实体的小地图标识生效状态"""
    log_info(f"[修改小地图标识生效状态] 执行")
