from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="关闭指定音效播放器",
    category="执行节点",
    inputs=[("流程入", "流程"), ("目标实体", "实体"), ("音效播放器序号", "整数")],
    outputs=[("流程出", "流程")],
    description="关闭指定目标实体上的音效播放器组件对应序号的音效播放器",
    doc_reference="服务器节点/执行节点/执行节点.md"
)
def 关闭指定音效播放器(game, 目标实体, 音效播放器序号):
    """关闭指定目标实体上的音效播放器组件对应序号的音效播放器"""
    log_info(f"[关闭指定音效播放器] 执行")
