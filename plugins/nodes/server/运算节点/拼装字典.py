from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="拼装字典",
    category="运算节点",
    inputs=[("键0~49", "泛型"), ("值0~49", "泛型")],
    outputs=[("字典", "泛型字典")],
    dynamic_port_type="泛型",
    description="将至多50个键值对拼合为一个字典",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 拼装字典(game, 第一个键=0, 第一个值=0, *更多键值):
    """将至多50个键值对拼合为一个字典"""
    # 先放入默认第一对
    result = {第一个键: 第一个值}
    # 其余参数应按成对给出：键1, 值1, 键2, 值2, ...
    for i in range(0, len(更多键值), 2):
        if i + 1 < len(更多键值):
            key = 更多键值[i]
            value = 更多键值[i + 1]
            result[key] = value
    return result
