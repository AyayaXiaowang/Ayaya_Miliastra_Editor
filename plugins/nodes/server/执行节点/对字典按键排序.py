from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="对字典按键排序",
    category="执行节点",
    inputs=[("流程入", "流程"), ("字典", "泛型字典"), ("排序方式", "枚举")],
    outputs=[("流程出", "流程"), ("键列表", "泛型列表"), ("值列表", "泛型列表")],
    description="将指定字典按键进行顺序或逆序排序后输出",
    doc_reference="服务器节点/执行节点/执行节点.md",
    input_generic_constraints={
        # 键排序仅支持“整数键字典”；值类型保持通用字典工具节点的允许集合（不允许字典值）。
        "字典": [
            "整数-实体字典",
            "整数-GUID字典",
            "整数-整数字典",
            "整数-布尔值字典",
            "整数-浮点数字典",
            "整数-字符串字典",
            "整数-三维向量字典",
            "整数-元件ID字典",
            "整数-配置ID字典",
            "整数-阵营字典",
            "整数-枚举字典",
            "整数-结构体字典",
            "整数-实体列表字典",
            "整数-GUID列表字典",
            "整数-整数列表字典",
            "整数-布尔值列表字典",
            "整数-浮点数列表字典",
            "整数-字符串列表字典",
            "整数-三维向量列表字典",
            "整数-元件ID列表字典",
            "整数-配置ID列表字典",
            "整数-阵营列表字典",
            "整数-结构体列表字典",
        ],
    },
    input_enum_options={
        "排序方式": [
            "排序规则_顺序",
            "排序规则_逆序",
        ],
    },
    output_generic_constraints={
        "键列表": [
            "整数列表",
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
            "泛型列表",
        ],
    },
)
def 对字典按键排序(game, 字典, 排序方式):
    """将指定字典按键进行顺序或逆序排序后输出"""
    if not isinstance(字典, dict):
        return [], []

    reverse = str(排序方式) == "排序规则_逆序"
    items = list(字典.items())
    items.sort(key=lambda item: item[0], reverse=reverse)
    keys = [k for k, _v in items]
    values = [v for _k, v in items]
    return keys, values
