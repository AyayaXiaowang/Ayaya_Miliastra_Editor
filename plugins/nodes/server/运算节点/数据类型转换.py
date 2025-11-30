from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="数据类型转换",
    category="运算节点",
    inputs=[("输入", "泛型")],
    outputs=[("输出", "泛型")],
    description="将输入的参数类型转换为另一种类型输出。具体规则见基础概念-【基础数据类型之间的转换规则】",
    doc_reference="服务器节点/运算节点/运算节点.md",
    input_generic_constraints={
        "输入": ["整数", "实体", "GUID", "布尔值", "浮点数", "三维向量", "阵营"],
    },
    output_generic_constraints={
        "输出": ["布尔值", "浮点数", "字符串", "整数"],
    },
)
def 数据类型转换(game, 输入):
    """将输入的参数类型转换为另一种类型输出。具体规则见基础概念-【基础数据类型之间的转换规则】"""

    return 输入
