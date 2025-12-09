from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="对字典按键排序",
    category="执行节点",
    inputs=[("流程入", "流程"), ("字典", "泛型"), ("排序方式", "枚举")],
    outputs=[("流程出", "流程"), ("键列表", "泛型列表"), ("值列表", "泛型列表")],
    description="将指定字典按键进行顺序或逆序排序后输出",
    doc_reference="服务器节点/执行节点/执行节点.md",
    output_generic_constraints={
        "键列表": [
            "实体列表",
            "GUID列表",
            "整数列表",
            "字符串列表",
            "阵营列表",
            "配置ID列表",
            "元件ID列表",
        ],
        "值列表": [
            "实体列表",
            "GUID列表",
            "整数列表",
            "布尔值列表",
            "浮点数列表",
            "字符串列表",
            "三维向量列表",
            "元件ID列表",
            "配置ID列表",
            "阵营列表",
            "结构体列表",
        ],
    },
)
def 对字典按键排序(game, 字典, 排序方式):
    """将指定字典按键进行顺序或逆序排序后输出"""
    return None  # Mock返回
