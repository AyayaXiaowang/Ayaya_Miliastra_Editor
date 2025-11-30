from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="权重随机",
    category="查询节点",
    inputs=[("权重列表", "整数列表")],
    outputs=[("权重序号", "整数")],
    description="输入一组权重组成的权重列表，按照权重随机选择其中的一个序号 例如：权重列表为{10，20，66，4}，那么此节点分别由10%、20%、66%、4%的概率输出0、1、2、3",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 权重随机(权重列表):
    """输入一组权重组成的权重列表，按照权重随机选择其中的一个序号 例如：权重列表为{10，20，66，4}，那么此节点分别由10%、20%、66%、4%的概率输出0、1、2、3"""
    if not 权重列表 or len(权重列表) == 0:
        return -1
    
    total_weight = sum(权重列表)
    if total_weight == 0:
        return random.randint(0, len(权重列表) - 1)
    
    rand_val = random.uniform(0, total_weight)
    current_sum = 0
    for i, weight in enumerate(权重列表):
        current_sum += weight
        if rand_val <= current_sum:
            log_info(f"[权重随机] {权重列表} -> {i}")
            return i
    
    return len(权重列表) - 1
