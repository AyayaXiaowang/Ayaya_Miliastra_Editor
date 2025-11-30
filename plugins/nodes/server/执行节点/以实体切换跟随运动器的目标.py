from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="以实体切换跟随运动器的目标",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("跟随目标实体", "实体"), ("跟随目标挂接点名称", "字符串"), ("位置偏移", "三维向量"), ("旋转偏移", "三维向量"), ("跟随坐标系", "枚举"), ("跟随类型", "枚举")],
    outputs=[("流程出", "流程")],
    description="以实体切换跟随运动器的跟随目标",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 以实体切换跟随运动器的目标(game, 目标实体, 跟随目标实体, 跟随目标挂接点名称, 位置偏移, 旋转偏移, 跟随坐标系, 跟随类型):
    """以实体切换跟随运动器的跟随目标"""
    log_info(f"[以实体切换跟随运动器的目标] 执行")
