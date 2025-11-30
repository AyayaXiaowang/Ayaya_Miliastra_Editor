from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info


@node_spec(
    name="修改结构体",
    category="执行节点",
    # 静态输入仅包含流程与“结构体实例”，具体要修改的字段输入端口由图编辑器在绑定结构体后动态补全。
    inputs=[("流程入", "流程"), ("结构体实例", "结构体")],
    outputs=[("流程出", "流程")],
    dynamic_port_type="泛型",
    description="在选定结构体后，可以为结构体的各个字段生成对应类型的输入端口，用于修改字段值",
    doc_reference="服务器节点/执行节点/执行节点.md",
)
def 修改结构体(game, 结构体实例=None, **字段新值):
    """
    占位实现：真实字段修改逻辑由运行时代码或代码生成统一处理。

    - 图编辑器会为绑定结构体的每个字段增加一个数据输入端口；
    - 代码生成或运行时代码可以统一读取 GraphModel.metadata["struct_bindings"]
      中该节点的绑定信息，按字段名将输入值写回结构体实例中。
    """
    log_info("[修改结构体] 占位实现（结构体字段修改由上层统一处理）")
    return
