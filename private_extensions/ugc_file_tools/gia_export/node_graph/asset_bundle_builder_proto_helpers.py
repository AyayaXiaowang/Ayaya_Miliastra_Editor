from __future__ import annotations

from typing import Any, Dict, Mapping, Tuple


def _make_resource_locator(*, origin: int, category: int, kind: int, guid: int = 0, runtime_id: int = 0) -> Dict[str, Any]:
    # ResourceLocator:
    # 1 source_domain, 2 service_domain, 3 kind, 4 asset_guid, 5 runtime_id
    return {
        "1": int(origin),
        "2": int(category),
        "3": int(kind),
        "4": int(guid),
        "5": int(runtime_id),
    }


def _make_pin_sig(*, kind_int: int, index_int: int) -> Dict[str, Any]:
    # PinSignature:
    # 1 kind, 2 index
    msg: Dict[str, Any] = {"1": int(kind_int)}
    if int(index_int) != 0:
        msg["2"] = int(index_int)
    return msg


def _make_pin_sig_with_source_ref(*, kind_int: int, index_int: int, source_ref_id_int: int | None) -> Dict[str, Any]:
    """
    NodeEditorPack `PinSignature` 支持在 kind=5(META_RPC_OPCODE) 时携带 source_ref(100)：
      message SignalId { int64 id = 1; }
      optional SignalId source_ref = 100;

    说明：
    - 该字段用于“信号绑定”去歧义：仅写信号名字符串在部分环境会被忽略/被外部表覆盖，导致导入后串号。
    - 这里把真源 `.gil` 中的 send_node_def_id 作为 source_ref.id 写入，保证与当前存档的信号定义表对齐。
    """
    msg = _make_pin_sig(kind_int=int(kind_int), index_int=int(index_int))
    if isinstance(source_ref_id_int, int) and int(source_ref_id_int) > 0 and int(kind_int) == 5:
        msg["100"] = {"1": int(source_ref_id_int)}
    return msg


def _make_node_connection(
    *,
    target_node_index: int,
    target_kind_int: int,
    target_shell_index_int: int,
    target_kernel_index_int: int,
) -> Dict[str, Any]:
    # NodeConnection:
    # 1 target_node_index, 2 target_pin_shell, 3 target_pin_kernel
    return {
        "1": int(target_node_index),
        "2": _make_pin_sig(kind_int=int(target_kind_int), index_int=int(target_shell_index_int)),
        "3": _make_pin_sig(kind_int=int(target_kind_int), index_int=int(target_kernel_index_int)),
    }


def _pin_sig_kind_index(pin_msg: Mapping[str, Any]) -> Tuple[int, int]:
    """
    读取 pin_msg["1"] (PinSignature) 的 (kind, index)。
    index==0 时可能省略 field_2，因此这里要兜底为 0。
    """

    def _coerce_int(v: Any) -> int:
        if isinstance(v, bool):
            return int(v)
        if isinstance(v, int):
            return int(v)
        if isinstance(v, str):
            s = v.strip()
            if s == "":
                return 0
            if s.isdigit():
                return int(s)
            if s.startswith("-") and s[1:].isdigit():
                return int(s)
        return 0

    sig = pin_msg.get("1")
    if not isinstance(sig, Mapping):
        return 0, 0
    kind = _coerce_int(sig.get("1"))
    idx = _coerce_int(sig.get("2", 0))
    return int(kind), int(idx)


def _pin_sort_key(pin_msg: Mapping[str, Any]) -> Tuple[int, int]:
    # 对齐真源习惯：流程 pins 在前，其次 IN_PARAM，再 OUT_PARAM，META 最后。
    kind, idx = _pin_sig_kind_index(pin_msg)
    kind_order = {
        1: 0,  # IN_FLOW（一般不显式写，但保持排序稳定）
        2: 1,  # OUT_FLOW
        3: 2,  # IN_PARAM
        4: 3,  # OUT_PARAM
        5: 4,  # META
        6: 5,  # META_*（极少作为 field_1.kind；主要出现在 binding_meta）
    }.get(int(kind), 99)
    return int(kind_order), int(idx)

