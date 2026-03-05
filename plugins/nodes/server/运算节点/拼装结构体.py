from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info


@node_spec(
    name="拼装结构体",
    category="运算节点",
    semantic_id="struct.build",
    # 结构体端口为“泛型结构体”：最初仅有一个【结构体】结构体输出端口；
    # 绑定具体结构体后，字段输入端口由图编辑器按字段列表动态补全。
    inputs=[],
    outputs=[("结构体", "结构体")],
    dynamic_port_type="泛型",
    output_port_aliases={"结构体": ["结果"]},
    description="根据绑定的结构体定义，将多个字段值拼合为一个结构体类型的值",
    doc_reference="服务器节点/运算节点/运算节点.md",
)
def 拼装结构体(game, **字段初始值):
    """
    本地测试（MockRuntime）可执行语义：
    - 结构体在离线环境下以 `dict` 承载，字段名 -> 字段值；
    - 额外注入少量保留元数据，便于后续【拆分结构体/修改结构体】在无需 struct_bindings 的情况下仍可工作：
      - `__ayaya_struct__`: 固定为 True，表示这是一个“结构体字典”
      - `__struct_name`: 结构体显示名（来自关键字参数 `结构体名`，可选）
      - `__field_order`: 字段顺序（按调用时关键字参数顺序记录，用于稳定拆分顺序）
    """
    # `结构体名` 不是字段，只是绑定/展示常量；在离线执行中作为元数据保留
    struct_name = str(字段初始值.pop("结构体名", "") or "").strip()

    reserved_meta_keys = {
        "__ayaya_struct__",
        "__struct_name",
        "__struct_id",
        "__field_order",
    }
    field_order = [k for k in 字段初始值.keys() if k not in reserved_meta_keys]

    # 结构体本体：字段名 -> 字段值（保持与旧占位实现兼容：字段仍在 dict 顶层）
    struct_value = {
        k: v for k, v in 字段初始值.items() if k not in reserved_meta_keys
    }

    struct_value["__ayaya_struct__"] = True
    if struct_name:
        struct_value["__struct_name"] = struct_name
    struct_value["__field_order"] = list(field_order)

    log_info("[拼装结构体] fields={}, struct_name={}", len(field_order), struct_name or "<empty>")
    return struct_value
