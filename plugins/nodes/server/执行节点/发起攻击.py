from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="发起攻击",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("伤害系数", "浮点数"), ("伤害增量", "浮点数"), ("位置偏移", "三维向量"), ("旋转偏移", "三维向量"), ("能力单元", "字符串"), ("是否覆写能力单元配置", "布尔值"), ("发起者实体", "实体")],
    outputs=[("流程出", "流程")],
    description="使指定实体发起攻击。使用该节点的实体上需要有对应的能力单元配置。 分为两种使用方式： 当能力单元为【攻击盒攻击】时，会以目标实体的位置为基准，打出一次攻击盒攻击 当能力单元为【直接攻击】时，会直接攻击目标实体",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 发起攻击(game, 目标实体, 伤害系数, 伤害增量, 位置偏移, 旋转偏移, 能力单元, 是否覆写能力单元配置, 发起者实体):
    """使指定实体发起攻击。使用该节点的实体上需要有对应的能力单元配置。 分为两种使用方式： 当能力单元为【攻击盒攻击】时，会以目标实体的位置为基准，打出一次攻击盒攻击 当能力单元为【直接攻击】时，会直接攻击目标实体"""
    log_info(f"[发起攻击] 执行")
