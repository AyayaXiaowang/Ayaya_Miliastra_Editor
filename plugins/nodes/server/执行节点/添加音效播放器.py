from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="添加音效播放器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("音效资产索引", "整数"), ("音量", "整数"), ("播放速度", "浮点数"), ("是否循环播放", "布尔值"), ("循环间隔时间", "浮点数"), ("是否为3D音效", "布尔值"), ("范围半径", "浮点数"), ("衰减方式", "枚举"), ("挂接点名称", "字符串"), ("挂接点偏移", "三维向量")],
    outputs=[("流程出", "流程"), ("音效播放器序号", "整数")],
    description="动态添加一个音效播放器，需要单位持有音效播放器组件",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 添加音效播放器(game, 目标实体, 音效资产索引, 音量, 播放速度, 是否循环播放, 循环间隔时间, 是否为3D音效, 范围半径, 衰减方式, 挂接点名称, 挂接点偏移):
    """动态添加一个音效播放器，需要单位持有音效播放器组件"""
    return None  # 音效播放器序号
