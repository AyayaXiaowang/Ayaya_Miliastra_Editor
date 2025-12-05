from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info


@node_spec(
    name="拼装结构体",
    category="运算节点",
    # 静态输入包含“结构体名”，字段输入端口由图编辑器在绑定结构体后按字段列表动态补全。
    inputs=[("结构体名", "字符串")],
    outputs=[("结果", "结构体")],
    dynamic_port_type="泛型",
    description="根据绑定的结构体定义，将多个字段值拼合为一个结构体类型的值",
    doc_reference="服务器节点/运算节点/运算节点.md",
)
def 拼装结构体(game, 结构体名=None, **字段初始值):
    """
    占位实现：真实结构体构造逻辑由运行时代码或代码生成统一处理。

    - 图编辑器会为绑定结构体的每个字段增加一个数据输入端口；
    - 代码生成或运行时代码可以统一读取 GraphModel.metadata["struct_bindings"]
      中该节点的绑定信息，按字段名收集输入值并构造结构体实例。
    """
    log_info("[拼装结构体] 占位实现（结构体构造由上层统一处理）")
    # 这里返回传入字段字典，便于在测试或占位执行路径中观察到包含字段的字典结构。
    return 字段初始值
