from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="按位写入",
    category="运算节点",
    inputs=[("被写入值", "整数"), ("写入值", "整数"), ("写入起始位", "整数"), ("写入结束位", "整数")],
    outputs=[("结果", "整数")],
    description="将写入值作为二进制数，写入被写入值（同样作为二进制数）的【起始位，结束位】。起始位从0开始算，写入的值长度包含起始位和结束位 如果写入值的二进制有效数字长度（从左起第一个1开始计算）超过写入的长度，则写入失败，返回被写入值 如果写入值是负数，也会因为写入值超出长度而写入失败（负数的二进制首位为符号位1）",
    doc_reference="服务器节点/运算节点/运算节点.md"
)
def 按位写入(game, 被写入值, 写入值, 写入起始位, 写入结束位):
    """将写入值作为二进制数，写入被写入值（同样作为二进制数）的【起始位，结束位】。起始位从0开始算，写入的值长度包含起始位和结束位 如果写入值的二进制有效数字长度（从左起第一个1开始计算）超过写入的长度，则写入失败，返回被写入值 如果写入值是负数，也会因为写入值超出长度而写入失败（负数的二进制首位为符号位1）"""
    # 检查写入值是否为负数
    if 写入值 < 0:
        return 被写入值
    
    # 计算写入长度
    写入长度 = 写入结束位 - 写入起始位 + 1
    
    # 检查写入值是否超出长度
    if 写入值 >= (1 << 写入长度):
        return 被写入值
    
    # 创建掩码
    mask = ((1 << 写入长度) - 1) << 写入起始位
    # 清除目标位
    result = 被写入值 & ~mask
    # 写入新值
    result |= (写入值 << 写入起始位)
    
    return result
