from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="开启定点运动器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("运动器名称", "字符串"), ("移动方式", "枚举"), ("移动速度", "浮点数"), ("目标位置", "三维向量"), ("目标旋转", "三维向量"), ("是否锁定旋转", "布尔值"), ("参数类型", "枚举"), ("移动时间", "浮点数")],
    outputs=[("流程出", "流程")],
    description="在关卡运行时为目标实体动态添加一个定点运动型基础运动器",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 开启定点运动器(game, 目标实体, 运动器名称, 移动方式, 移动速度, 目标位置, 目标旋转, 是否锁定旋转, 参数类型, 移动时间):
    """在关卡运行时为目标实体动态添加一个定点运动型基础运动器"""
    log_info(f"[开启定点运动器] 执行")
