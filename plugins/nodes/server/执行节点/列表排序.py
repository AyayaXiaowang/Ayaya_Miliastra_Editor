from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="列表排序",
    category="执行节点",
    inputs=[("流程入", "流程"), ("列表", "泛型列表"), ("排序方式", "枚举")],
    outputs=[("流程出", "流程")],
    description="将指定列表按照排序方式进行排序",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 列表排序(game, 列表, 排序方式):
    """将指定列表按照排序方式进行排序"""
    if isinstance(列表, list):
        if 排序方式 == "升序":
            列表.sort()
        elif 排序方式 == "降序":
            列表.sort(reverse=True)
        log_info(f"[列表排序] {排序方式}: {列表}")
