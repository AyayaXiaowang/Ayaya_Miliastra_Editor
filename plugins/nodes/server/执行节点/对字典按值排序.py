from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="对字典按值排序",
    category="执行节点",
    inputs=[("流程入", "流程"), ("字典", "泛型字典"), ("排序方式", "枚举")],
    outputs=[("流程出", "流程"), ("键列表", "泛型列表"), ("值列表", "泛型列表")],
    description="将指定字典按值进行顺序或逆序排序后输出",
    doc_reference="服务器节点/执行节点/执行节点.md",
    input_generic_constraints={
        # 值排序仅支持数值字典（整数/浮点数），键类型沿用通用字典工具节点的允许集合。
        # 约束在此以“别名字典类型”枚举表达：键类型-值类型字典
        "字典": [
            "实体-整数字典",
            "实体-浮点数字典",
            "GUID-整数字典",
            "GUID-浮点数字典",
            "整数-整数字典",
            "整数-浮点数字典",
            "字符串-整数字典",
            "字符串-浮点数字典",
            "阵营-整数字典",
            "阵营-浮点数字典",
            "配置ID-整数字典",
            "配置ID-浮点数字典",
            "元件ID-整数字典",
            "元件ID-浮点数字典",
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
            "实体列表",
            "GUID列表",
            "整数列表",
            "字符串列表",
            "阵营列表",
            "配置ID列表",
            "元件ID列表",
        ],
        "值列表": [
            "整数列表",
            "浮点数列表",
        ],
    },
)
def 对字典按值排序(game, 字典, 排序方式):
    """将指定字典按值进行顺序或逆序排序后输出"""
    if not isinstance(字典, dict):
        return [], []

    reverse = str(排序方式) == "排序规则_逆序"
    items = list(字典.items())
    items.sort(key=lambda item: item[1], reverse=reverse)
    keys = [k for k, _v in items]
    values = [v for _k, v in items]
    return keys, values
