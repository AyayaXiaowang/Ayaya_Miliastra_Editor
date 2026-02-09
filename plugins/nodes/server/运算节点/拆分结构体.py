from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_运算节点_impl_helpers import *
from engine.utils.logging.logger import log_info


@node_spec(
    name="拆分结构体",
    category="运算节点",
    semantic_id="struct.split",
    # 结构体端口为“泛型结构体”：最初仅有一个【结构体】端口；
    # 绑定具体结构体后，字段输出端口由图编辑器按字段列表动态补全。
    inputs=[("结构体", "结构体")],
    outputs=[],
    dynamic_port_type="泛型",
    input_port_aliases={"结构体": ["结构体实例"]},
    description="根据绑定的结构体定义，将结构体实例拆分为多个字段输出（每个字段一个输出端口）",
    doc_reference="服务器节点/运算节点/运算节点.md",
)
def 拆分结构体(game, 结构体=None, **字段值占位):
    """
    本地测试（MockRuntime）可执行语义：
    - `结构体` 以 `dict` 承载（来自【拼装结构体】或自定义变量中保存的结构体快照）；
    - 返回一个 tuple，用于在 Graph Code 中进行解包赋值；
    - 字段顺序优先级：
      1) 若调用方显式通过关键字参数传入“字段占位”（除 `结构体名` 外的 kwargs），则按关键字顺序输出这些字段；
         （用于兼容未来可能的“按需拆分”调用形态）
      2) 若结构体 dict 中包含 `__field_order`，则按该顺序输出；
      3) 若提供 `结构体名`，则按结构体定义仓库中的字段顺序输出；
      4) 否则按 dict 的插入顺序输出（跳过 `__*` 元数据键）。
    """
    if not isinstance(结构体, dict):
        raise TypeError("拆分结构体：结构体值必须为 dict（离线运行时以 dict 承载结构体）")

    reserved_meta_keys = {
        "结构体名",
        "__ayaya_struct__",
        "__struct_name",
        "__struct_id",
        "__field_order",
    }

    # 1) 显式占位字段（按 kwargs 顺序）
    explicit_fields = [k for k in 字段值占位.keys() if k not in reserved_meta_keys]
    if explicit_fields:
        values = tuple(结构体[k] for k in explicit_fields)
        log_info("[拆分结构体] explicit_fields={} -> {} values", len(explicit_fields), len(values))
        return values

    # 2) 结构体自身携带的字段顺序（来自【拼装结构体】）
    order = 结构体.get("__field_order", None)
    if isinstance(order, list) and order:
        values = tuple(结构体[k] for k in order if k in 结构体)
        log_info("[拆分结构体] __field_order={} -> {} values", len(order), len(values))
        return values

    # 3) 结构体名 → 结构体定义字段顺序
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

    # 4) dict 插入顺序（跳过 __* 元数据）
    field_names = [k for k in 结构体.keys() if not str(k).startswith("__")]
    values = tuple(结构体.get(name) for name in field_names)
    log_info("[拆分结构体] fallback_fields={} -> {} values", len(field_names), len(values))
    return values

