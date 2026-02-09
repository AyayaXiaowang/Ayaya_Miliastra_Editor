from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取预设状态",
    category="查询节点",
    inputs=[("目标实体", "实体"), ("预设状态索引", "整数")],
    outputs=[("预设状态值", "整数")],
    description="获取目标实体的指定预设状态的预设状态值。如果该实体没有指定的预设状态，则返回0",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 获取预设状态(game, 目标实体, 预设状态索引):
    """获取目标实体的指定预设状态的预设状态值。如果该实体没有指定的预设状态，则返回0"""
    # 本地测试（MockRuntime）最小语义：
    # - 允许通过自定义变量注入：key = f"预设状态_{index}"
    # - 未设置时回退为 0
    key = f"预设状态_{int(预设状态索引)}"
    get_custom = getattr(game, "get_custom_variable", None)
    if callable(get_custom):
        value = get_custom(目标实体, key, 0)
        return int(value or 0)
    return 0
