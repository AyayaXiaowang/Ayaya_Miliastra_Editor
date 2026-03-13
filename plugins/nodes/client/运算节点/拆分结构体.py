from __future__ import annotations

from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.client_运算节点_impl_helpers import *  # noqa: F401,F403
from engine.utils.logging.logger import log_info


@node_spec(
    name="拆分结构体",
    category="运算节点",
    semantic_id="struct.split",
    inputs=[("结构体", "结构体")],
    outputs=[],
    dynamic_port_type="泛型",
    input_port_aliases={"结构体": ["结构体实例"]},
    description="根据绑定的结构体定义，将结构体实例拆分为多个字段输出（每个字段一个输出端口）",
    doc_reference="客户端节点/运算节点/运算节点.md",
)
def 拆分结构体(game, 结构体=None, **字段值占位):
    """将结构体字典拆分为 tuple 以便解包赋值。"""
    if not isinstance(结构体, dict):
        raise TypeError("拆分结构体：结构体值必须为 dict（离线运行时以 dict 承载结构体）")

    reserved_meta_keys = {
        "结构体名",
        "__ayaya_struct__",
        "__struct_name",
        "__struct_id",
        "__field_order",
    }

    explicit_fields = [k for k in 字段值占位.keys() if k not in reserved_meta_keys]
    if explicit_fields:
        values = tuple(结构体[k] for k in explicit_fields)
        log_info("[拆分结构体] explicit_fields={} -> {} values", len(explicit_fields), len(values))
        return values

    order = 结构体.get("__field_order", None)
    if isinstance(order, list) and order:
        values = tuple(结构体[k] for k in order if k in 结构体)
        log_info("[拆分结构体] __field_order={} -> {} values", len(order), len(values))
        return values

    struct_name = str(字段值占位.get("结构体名", "") or "").strip()
    if struct_name:
        from engine.struct import get_default_struct_repository

        repo = get_default_struct_repository()
        struct_id = repo.resolve_id_by_name(struct_name)
        if not struct_id:
            raise ValueError(f"拆分结构体：未知结构体名: {struct_name!r}")
        field_names = repo.get_field_names(struct_id)
        values = tuple(结构体.get(name) for name in field_names)
        log_info("[拆分结构体] struct_name={} fields={} -> {} values", struct_name, len(field_names), len(values))
        return values

    field_names = [k for k in 结构体.keys() if not str(k).startswith("__")]
    values = tuple(结构体.get(name) for name in field_names)
    log_info("[拆分结构体] fallback_fields={} -> {} values", len(field_names), len(values))
    return values

