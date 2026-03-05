from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_执行节点_impl_helpers import *
from engine.utils.logging.logger import log_info


@node_spec(
    name="修改结构体",
    category="执行节点",
    semantic_id="struct.modify",
    # 静态输入包含流程与“结构体”（泛型结构体端口）；
    # 绑定具体结构体后，字段输入端口由图编辑器按字段列表动态补全。
    inputs=[("流程入", "流程"), ("结构体", "结构体")],
    outputs=[("流程出", "流程")],
    dynamic_port_type="泛型",
    input_port_aliases={"结构体": ["结构体实例"]},
    description="在选定结构体后，可以为结构体的各个字段生成对应类型的输入端口，用于修改字段值",
    doc_reference="服务器节点/执行节点/执行节点.md",
)
def 修改结构体(game, 结构体=None, **字段新值):
    """
    本地测试（MockRuntime）可执行语义：
    - 结构体在离线环境下以 `dict` 承载（来自【拼装结构体】或自定义变量中的快照）；
    - 本节点按字段名就地更新该 dict，并维护 `__field_order` 的稳定顺序；
    - `结构体名` 作为绑定/展示常量，不视作字段（会写入 `__struct_name` 元数据，便于调试）。
    """
    if not isinstance(结构体, dict):
        raise TypeError("修改结构体：结构体值必须为 dict（离线运行时以 dict 承载结构体）")

    struct_name = str(字段新值.pop("结构体名", "") or "").strip()

    reserved_meta_keys = {
        "__ayaya_struct__",
        "__struct_name",
        "__struct_id",
        "__field_order",
    }

    # 维护字段顺序：优先使用已有顺序，否则按当前 dict 的插入顺序初始化
    order = 结构体.get("__field_order", None)
    if not isinstance(order, list):
        order = [k for k in 结构体.keys() if not str(k).startswith("__")]

    changed_fields: list[str] = []
    for field_name, value in 字段新值.items():
        if field_name in reserved_meta_keys:
            continue
        结构体[field_name] = value
        changed_fields.append(field_name)
        if field_name not in order:
            order.append(field_name)

    结构体["__ayaya_struct__"] = True
    if struct_name:
        结构体["__struct_name"] = struct_name
    结构体["__field_order"] = list(order)

    log_info("[修改结构体] changed_fields={}, struct_name={}", len(changed_fields), struct_name or "<empty>")
    return
