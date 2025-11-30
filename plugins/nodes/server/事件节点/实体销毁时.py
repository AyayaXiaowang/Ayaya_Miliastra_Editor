from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_事件节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="实体销毁时",
    category="事件节点",
    outputs=[("流程出", "流程"), ("事件源实体", "实体"), ("事件源GUID", "GUID"), ("位置", "三维向量"), ("朝向", "三维向量"), ("实体类型", "枚举"), ("阵营", "阵营"), ("伤害来源", "实体"), ("归属者实体", "实体"), ("自定义变量组件快照", "自定义变量快照")],
    description="实体销毁事件。\n- 若节点图挂在关卡实体：可监听关卡内任意实体被销毁（全局广播）。\n- 若节点图挂在普通实体（含玩家/角色）：仅能收到该实体自身被销毁。\n仅包含因战斗（生命值变为0）或【销毁实体】节点而造成的销毁会触发该事件。",
    doc_reference="服务器节点/事件节点/事件节点.md"
)
def 实体销毁时(game):
    """实体销毁事件。
    
    作用域语义提示：
    - 挂在关卡实体：监听全局销毁（任意实体）。
    - 挂在普通实体：仅监听自身被销毁（无需再判断是否自身）。
    """
    事件源 = game.create_mock_entity("被销毁实体")
    return 事件源, "mock_guid_002", [0,0,0], [0,0,0], "物件", 1, None, None, {}
