from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="对字典设置或新增键值对",
    category="执行节点",
    inputs=[("流程入", "流程"), ("字典", "泛型"), ("键", "泛型"), ("值", "泛型")],
    outputs=[("流程出", "流程")],
    description="为指定字典新增一个键值对",
    doc_reference="服务器节点/执行节点/执行节点.md",
    input_generic_constraints={
        "键": ["实体", "GUID", "整数", "字符串", "阵营", "配置ID", "元件ID"],
        "值": [
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
            "结构体",
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
def 对字典设置或新增键值对(game, 字典, 键, 值):
    """为指定字典新增一个键值对"""
    log_info(f"[对字典设置或新增键值对] 执行")
