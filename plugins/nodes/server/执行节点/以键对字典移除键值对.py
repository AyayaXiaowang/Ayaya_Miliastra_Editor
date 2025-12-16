from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="以键对字典移除键值对",
    category="执行节点",
    inputs=[("流程入", "流程"), ("字典", "泛型字典"), ("键", "泛型")],
    outputs=[("流程出", "流程")],
    description="以键移除指定字典中的键值对",
    doc_reference="服务器节点/执行节点/执行节点.md",
    input_generic_constraints={
        "键": ["实体", "GUID", "整数", "字符串", "阵营", "配置ID", "元件ID"],
    },
)
def 以键对字典移除键值对(game, 字典, 键):
    """以键移除指定字典中的键值对"""
    log_info(f"[以键对字典移除键值对] 执行")
