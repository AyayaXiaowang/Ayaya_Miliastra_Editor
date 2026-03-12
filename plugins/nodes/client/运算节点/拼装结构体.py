from __future__ import annotations

from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_运算节点_impl_helpers import *  # noqa: F401,F403
from engine.utils.logging.logger import log_info


@node_spec(
    name="拼装结构体",
    category="运算节点",
    semantic_id="struct.build",
    inputs=[],
    outputs=[("结构体", "结构体")],
    dynamic_port_type="泛型",
    output_port_aliases={"结构体": ["结果"]},
    description="根据绑定的结构体定义，将多个字段值拼合为一个结构体类型的值",
    doc_reference="客户端节点/运算节点/运算节点.md",
)
def 拼装结构体(game, **字段初始值):
    """将字段值拼合为结构体字典。"""
    struct_name = str(字段初始值.pop("结构体名", "") or "").strip()
    reserved_meta_keys = {
        "__ayaya_struct__",
        "__struct_name",
        "__struct_id",
        "__field_order",
    }
    field_order = [k for k in 字段初始值.keys() if k not in reserved_meta_keys]
    struct_value = {k: v for k, v in 字段初始值.items() if k not in reserved_meta_keys}
    struct_value["__ayaya_struct__"] = True
    if struct_name:
        struct_value["__struct_name"] = struct_name
    struct_value["__field_order"] = list(field_order)
    log_info("[拼装结构体] fields={}, struct_name={}", len(field_order), struct_name or "<empty>")
    return struct_value

