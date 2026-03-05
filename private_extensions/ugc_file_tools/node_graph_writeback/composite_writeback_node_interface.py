from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from ugc_file_tools.node_graph_semantics.var_base import map_server_port_type_to_var_type_id as _map_server_port_type_to_var_type_id
from ugc_file_tools.node_graph_semantics.dict_kv_types import try_resolve_dict_kv_var_types_from_type_text

from .composite_writeback_proto import pin_sig, resource_locator


_COMPOSITE_PIN_PERSISTENT_UID_BASE: int = 24


def sorted_virtual_pins(virtual_pins: Sequence[object]) -> List[object]:
    return sorted(
        list(virtual_pins),
        key=lambda p: (
            int(getattr(p, "pin_index", 0) or 0),
            str(getattr(p, "pin_name", "") or "").casefold(),
        ),
    )


def virtual_pins_by_kind(virtual_pins_sorted: Sequence[object]) -> Dict[int, List[object]]:
    out: Dict[int, List[object]] = {1: [], 2: [], 3: [], 4: []}
    for p in list(virtual_pins_sorted):
        is_flow = bool(getattr(p, "is_flow", False))
        is_input = bool(getattr(p, "is_input", False))
        kind = 1 if (is_flow and is_input) else 2 if (is_flow and (not is_input)) else 3 if ((not is_flow) and is_input) else 4
        out[int(kind)].append(p)
    return out


def _pin_type_to_var_type_int(pin_type_text: str) -> int:
    t = str(pin_type_text or "").strip()
    if t == "" or t == "流程" or ("泛型" in t):
        return 0
    if t.startswith("结构体列表"):
        return 26
    if t.startswith("结构体"):
        return 25
    return int(_map_server_port_type_to_var_type_id(t))


def _var_type_int_to_widget_type_int(var_type_int: int) -> int:
    """
    NodeEditorPack `TypedValue.WidgetType`（真源语义）：
    - 1: ID_INPUT（Entity/GUID 等）
    - 2: NUMBER_INPUT（Int）
    - 4: DECIMAL_INPUT（Float）
    - 5: TEXT_INPUT（String）
    - 6: ENUM_PICKER（Bool/Enum）
    - 7: VECTOR3_INPUT（三维向量）
    - 10001: STRUCT_BLOCK
    - 10002: LIST_GROUP
    - 10003: MAP_GROUP
    """
    vt = int(var_type_int)
    if vt in {1, 2, 16, 17, 20, 21}:
        return 1
    if vt == 3:
        return 2
    if vt == 5:
        return 4
    if vt == 6:
        return 5
    if vt in {4, 14, 18}:
        return 6
    if vt == 12:
        # 对齐真源：Vec3 的 type_info.field_1(widget_type) 为 7；缺失会导致编辑器/游戏侧不生成可编辑输入控件。
        return 7
    if vt in {25, 26}:
        return 10001
    if vt in {7, 8, 9, 10, 11, 13, 15}:
        return 10002
    if vt == 27:
        return 10003
    return 0


_LIST_ELEM_TYPE_BY_LIST_VT: Dict[int, int] = {
    7: 2,  # GUID列表 -> GUID
    8: 3,  # 整数列表 -> 整数
    9: 4,  # 布尔值列表 -> 布尔值
    10: 5,  # 浮点数列表 -> 浮点数
    11: 6,  # 字符串列表 -> 字符串
    13: 1,  # 实体列表 -> 实体
    15: 12,  # 三维向量列表 -> 三维向量
    22: 20,  # 配置ID列表 -> 配置ID
    23: 21,  # 元件ID列表 -> 元件ID
    24: 17,  # 阵营列表 -> 阵营
    26: 25,  # 结构体列表 -> 结构体
}


def _try_build_type_info_extra_fields(*, var_type_shell: int, pin_type_text: str) -> Dict[str, Any]:
    """
    对齐真源：TypedValue.type_info 的额外字段（除 widget_type/var_type_shell/var_type_kernel 外）。

    已观测到的关键字段：
    - 101: Bool/Enum picker 的附加信息（field_1=1/enum_id）
    - 102: List 的元素类型 type_info（field_1=<type_info>）
    - 105: Dict 的 key/value 类型（field_3=key_vt, field_4=value_vt, field_6=1, field_7=1）
    """
    vt = int(var_type_shell)

    # Bool：对齐样本（field_101.field_1=1）
    if vt == 4:
        return {"101": {"1": 1}}

    # Enum：对齐样本（shell=10000+enum_id, kernel=14, field_101.field_1=enum_id）
    if vt >= 10000:
        enum_id = int(vt - 10000)
        if enum_id > 0:
            return {"101": {"1": int(enum_id)}}
        return {}

    # List：写入元素类型 type_info
    elem_vt = _LIST_ELEM_TYPE_BY_LIST_VT.get(int(vt))
    if isinstance(elem_vt, int) and int(elem_vt) > 0:
        inner_widget = int(_var_type_int_to_widget_type_int(int(elem_vt)))
        inner: Dict[str, Any] = {"3": int(elem_vt), "4": int(elem_vt)}
        if int(inner_widget) != 0:
            inner["1"] = int(inner_widget)
        return {"102": {"1": inner}}

    # Dict：必须携带 K/V 类型（否则编辑器/游戏侧会把字典端口视为“未完整配置”）
    if vt == 27:
        kv = try_resolve_dict_kv_var_types_from_type_text(
            str(pin_type_text or ""),
            map_port_type_text_to_var_type_id=_map_server_port_type_to_var_type_id,
            reject_generic=True,
        )
        if kv is None:
            raise ValueError(f"字典虚拟引脚必须使用别名字典类型以提供 K/V：pin_type={pin_type_text!r}")
        key_vt, val_vt = kv
        return {"105": {"3": int(key_vt), "4": int(val_vt), "6": 1, "7": 1}}

    return {}


def _build_typed_value_type_info_for_pin(*, kind_int: int, pin_type_text: str) -> Dict[str, Any]:
    """
    仅 data pin(kind 3/4) 写 type_info；flow pin 写空 message。
    """
    if int(kind_int) not in {3, 4}:
        return {}
    vt_shell = int(_pin_type_to_var_type_int(str(pin_type_text or "")))
    if int(vt_shell) == 0:
        return {}

    vt_kernel = int(vt_shell)
    # Enum：对齐样本，kernel 固定为 14（EnumBaseValue）
    if int(vt_shell) >= 10000:
        vt_kernel = 14

    widget = int(_var_type_int_to_widget_type_int(int(vt_shell)))
    type_info: Dict[str, Any] = {"3": int(vt_shell), "4": int(vt_kernel)}
    if int(widget) != 0:
        type_info["1"] = int(widget)
    type_info.update(_try_build_type_info_extra_fields(var_type_shell=int(vt_shell), pin_type_text=str(pin_type_text or "")))
    return type_info


def build_node_interface_message(
    *,
    composite_id: str,
    node_def_id_int: int,
    composite_graph_id_int: int,
    node_name: str,
    node_description: str,
    virtual_pins_sorted: Sequence[object],
) -> Dict[str, Any]:
    shell_ref = resource_locator(origin=10001, category=20000, kind=22001, runtime_id=int(node_def_id_int))
    kernel_ref = resource_locator(origin=10001, category=20000, kind=22001, runtime_id=int(node_def_id_int))
    graph_ref = resource_locator(origin=10000, category=20000, kind=21002, runtime_id=int(composite_graph_id_int))

    signature = {"1": shell_ref, "2": kernel_ref, "4": graph_ref}
    node_interface: Dict[str, Any] = {
        "4": signature,
        "107": {"1": 1000},  # Implementation.Category.COMPOSITE
        "200": str(node_name),
        "201": str(node_description or ""),
        "203": 6,  # TemplateRoot.USER_COMPOSITE
    }

    pins_by_kind = virtual_pins_by_kind(virtual_pins_sorted)
    # 真源/编辑器口径：NodeInterface pin 的 persistent_uid(field_8) 不是 “虚拟引脚定义的 pin_index(1..N)”，
    # 而是一个按 kind 顺序连续分配的稳定 UID（常见从 24 开始：InFlow=24, OutFlow=25, InParam=26...）。
    # 该 UID 会被节点图 pin record 的 compositePinIndex(field_7) 复用，用于稳定映射与端口对齐。
    uid_by_kind_and_ordinal: Dict[tuple[int, int], int] = {}
    next_uid = int(_COMPOSITE_PIN_PERSISTENT_UID_BASE)
    for kind_int in (1, 2, 3, 4):
        for ordinal, _pin_obj in enumerate(list(pins_by_kind.get(int(kind_int)) or [])):
            uid_by_kind_and_ordinal[(int(kind_int), int(ordinal))] = int(next_uid)
            next_uid += 1

    for kind_int, field_key in ((1, "100"), (2, "101"), (3, "102"), (4, "103")):
        pins = list(pins_by_kind[int(kind_int)])
        if not pins:
            continue
        items: List[Dict[str, Any]] = []
        for ordinal, p in enumerate(pins):
            pin_name = str(getattr(p, "pin_name", "") or "").strip()
            persistent_uid = uid_by_kind_and_ordinal.get((int(kind_int), int(ordinal)))
            if not isinstance(persistent_uid, int) or int(persistent_uid) <= 0:
                raise RuntimeError(
                    "internal error: persistent_uid allocation failed: "
                    f"composite_id={composite_id!r} kind={int(kind_int)} ordinal={int(ordinal)}"
                )
            type_info = _build_typed_value_type_info_for_pin(
                kind_int=int(kind_int),
                pin_type_text=str(getattr(p, "pin_type", "") or ""),
            )

            msg: Dict[str, Any] = {
                "2": 1,  # visibility_mask
                "3": pin_sig(kind_int=int(kind_int), index_int=int(ordinal)),
                "4": dict(type_info),  # type_info（flow pin 写空 message；data pin 写 widget/vartype）
                "8": int(persistent_uid),
            }
            if pin_name != "":
                msg["1"] = str(pin_name)
            items.append(msg)
        node_interface[str(field_key)] = items
    return node_interface


def build_record_id_map_from_node_interface(
    *, node_def_id_int: int, node_interface: Mapping[str, Any]
) -> Dict[int, Dict[int, int]]:
    inparams = node_interface.get("102")
    items = [x for x in list(inparams) if isinstance(x, dict)] if isinstance(inparams, list) else ([inparams] if isinstance(inparams, dict) else [])
    if not items:
        return {}
    by_index: Dict[int, int] = {}
    for item in items:
        sig = item.get("3")
        if not isinstance(sig, dict) or int(sig.get("1") or 0) != 3:
            continue
        ordinal = int(sig.get("2") or 0)
        uid = item.get("8")
        if isinstance(uid, int) and int(uid) > 0:
            by_index[int(ordinal)] = int(uid)
    return {int(node_def_id_int): by_index} if by_index else {}


__all__ = [
    "sorted_virtual_pins",
    "virtual_pins_by_kind",
    "build_node_interface_message",
    "build_record_id_map_from_node_interface",
]

