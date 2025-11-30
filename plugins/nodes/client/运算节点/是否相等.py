from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="是否相等",
    category="运算节点",
    inputs=[("枚举1", "泛型"), ("枚举2", "泛型")],
    outputs=[("结果", "布尔值")],
    description="判断两个输入是否相等 部分参数类型有较为特殊的判定规则： 浮点数：浮点数采用近似相等进行比较，当两个浮点数小于一个极小值时，这两个浮点数认为相等。例如：2.0000001与2.0认为相等 三维向量：三维向量的x、y、z分别采用浮点数近似相等比较",
    doc_reference="客户端节点/运算节点/运算节点.md",
    input_generic_constraints={
        "枚举1": [
            "实体",
            "GUID",
            "整数",
            "布尔值",
            "浮点数",
            "字符串",
            "阵营",
            "三维向量",
            "元件ID",
            "配置ID",
            "枚举",
        ],
        "枚举2": [
            "实体",
            "GUID",
            "整数",
            "布尔值",
            "浮点数",
            "字符串",
            "阵营",
            "三维向量",
            "元件ID",
            "配置ID",
            "枚举",
        ],
    },
)
def 是否相等(game, 枚举1, 枚举2):
    """判断两个输入是否相等 部分参数类型有较为特殊的判定规则： 浮点数：浮点数采用近似相等进行比较，当两个浮点数小于一个极小值时，这两个浮点数认为相等。例如：2.0000001与2.0认为相等 三维向量：三维向量的x、y、z分别采用浮点数近似相等比较"""
    # 浮点数近似相等判断
    if isinstance(枚举1, float) and isinstance(枚举2, float):
        return abs(枚举1 - 枚举2) < 1e-6
    # 三维向量近似相等
    if isinstance(枚举1, (list, tuple)) and isinstance(枚举2, (list, tuple)):
        if len(枚举1) == 3 and len(枚举2) == 3:
            return all(abs(枚举1[i] - 枚举2[i]) < 1e-6 for i in range(3))
    # 其他类型直接比较
    return 枚举1 == 枚举2
