from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取局部变量",
    category="查询节点",
    inputs=[("初始值", "泛型")],
    outputs=[("局部变量", "局部变量"), ("值", "泛型")],
    description="可以获取局部变量，也可以设置该局部变量的【初始值】 设置【初始值】以后，出参的【值】输出即为输入的【初始值】 当出参【局部变量】与执行节点【设置局部变量】的入参【局部变量】连接后，执行节点【设置局部变量】的入参【值】会覆写该查询节点的出参【值】，再次使用【获取局部变量】节点时，出参【值】为覆写后的值",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取局部变量(game, 初始值):
    """可以获取局部变量，也可以设置该局部变量的【初始值】 设置【初始值】以后，出参的【值】输出即为输入的【初始值】 当出参【局部变量】与执行节点【设置局部变量】的入参【局部变量】连接后，执行节点【设置局部变量】的入参【值】会覆写该查询节点的出参【值】，再次使用【获取局部变量】节点时，出参【值】为覆写后的值"""
    # 注意：局部变量在生成阶段会被处理为Python变量
    # 这里返回初始值
    return None, 初始值  # 局部变量引用, 值
