from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info


@node_spec(
    name="拆分结构体",
    category="运算节点",
    # 静态输入仅声明“结构体实例”，具体字段输出端口由图编辑器在绑定结构体后按字段列表动态补全。
    inputs=[("结构体实例", "结构体")],
    outputs=[],
    dynamic_port_type="泛型",
    description="根据绑定的结构体定义，将结构体实例拆分为多个字段输出（每个字段一个输出端口）",
    doc_reference="服务器节点/运算节点/运算节点.md",
)
def 拆分结构体(game, 结构体实例=None, **字段值占位):
    """
    占位实现：真实拆分行为由图编辑器和运行时代码统一处理。

    - 图编辑器会根据信息为节点增加与结构体字段对应的数据输出端口；
    - 代码生成或运行时代码可以统一读取 GraphModel.metadata["struct_bindings"]
      中的绑定信息，按字段名从结构体实例中拆解并回填到各输出端口。
    """
    log_info("[拆分结构体] 占位实现（结构体字段拆分由上层统一处理）")
    # 为了保持兼容性，这里不对传入的结构体实例做任何假定处理，直接返回空元组。
    return ()

