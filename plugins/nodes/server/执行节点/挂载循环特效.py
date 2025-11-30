from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="挂载循环特效",
    category="执行节点",
    inputs=[("流程入", "流程"), ("特效资产", "配置ID"), ("目标实体", "实体"), ("挂接点名称", "字符串"), ("是否跟随目标运动", "布尔值"), ("是否跟随目标旋转", "布尔值"), ("位置偏移", "三维向量"), ("旋转偏移", "三维向量"), ("缩放倍率", "浮点数"), ("是否播放自带的音效", "布尔值")],
    outputs=[("流程出", "流程"), ("特效实例ID", "整数")],
    description="以目标实体为基准，挂载一个循环特效。需要有合法的目标实体以及挂接点 该节点会返回一个特效实例ID，可以将其存下。后续使用【清除循环特效】节点时，用这个特效实例ID来清除指定的循环特效",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 挂载循环特效(game, 特效资产, 目标实体, 挂接点名称, 是否跟随目标运动, 是否跟随目标旋转, 位置偏移, 旋转偏移, 缩放倍率, 是否播放自带的音效):
    """以目标实体为基准，挂载一个循环特效。需要有合法的目标实体以及挂接点 该节点会返回一个特效实例ID，可以将其存下。后续使用【清除循环特效】节点时，用这个特效实例ID来清除指定的循环特效"""
    return None  # 特效实例ID
