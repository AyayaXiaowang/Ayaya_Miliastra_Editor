from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from ugc_file_tools.node_graph_semantics.graph_generater import is_flow_port_by_node_def as _is_flow_port_by_node_def

from .composite_writeback_node_interface import virtual_pins_by_kind
from .composite_writeback_proto import pin_sig
from .node_editor_pack import resolve_node_editor_pack_pin_indices


_SIGNAL_NAME_PORT: str = "信号名"
_SIGNAL_NODE_TITLES: set[str] = {"发送信号", "监听信号", "向服务器节点图发送信号", "发送信号到服务端"}


def _drop_signal_name_meta_port_if_needed(*, node_title: str, data_ports: list[str]) -> list[str]:
    """
    对齐真源：信号节点的“信号名”是 META(kind=5) 端口，不应占用 data InParam(kind=3) 的 ordinal。

    若把 “信号名” 当作普通 data 输入端口，会导致 CompositeGraph.port_mappings 内部 pin_index 整体 +1，
    现象即用户描述的“第一个参数端口空、后续参数整体错位”。
    """
    if str(node_title) not in _SIGNAL_NODE_TITLES:
        return list(data_ports)
    return [p for p in list(data_ports) if str(p) != _SIGNAL_NAME_PORT]


def build_port_mappings_for_composite(
    *,
    composite_id: str,
    virtual_pins_sorted: Sequence[object],
    node_id_int_by_graph_node_id: Mapping[str, int],
    graph_node_by_graph_node_id: Mapping[str, Dict[str, Any]],
    node_title_by_graph_node_id: Mapping[str, str],
    node_type_id_by_graph_node_id: Mapping[str, int],
    node_defs_by_name: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    pins_by_kind = virtual_pins_by_kind(virtual_pins_sorted)
    ext_ordinal_by_pin_obj: Dict[int, int] = {}
    for kind_int, pins in pins_by_kind.items():
        for ordinal, p in enumerate(list(pins)):
            ext_ordinal_by_pin_obj[id(p)] = int(ordinal)

    mappings: List[Dict[str, Any]] = []
    for vp in list(virtual_pins_sorted):
        mapped_ports = list(getattr(vp, "mapped_ports", []) or [])
        if not mapped_ports:
            continue
        is_flow = bool(getattr(vp, "is_flow", False))
        is_input = bool(getattr(vp, "is_input", False))
        ext_kind_int = 1 if (is_flow and is_input) else 2 if (is_flow and (not is_input)) else 3 if ((not is_flow) and is_input) else 4
        ext_index = ext_ordinal_by_pin_obj.get(id(vp))
        if not isinstance(ext_index, int):
            continue
        external_sig = pin_sig(kind_int=int(ext_kind_int), index_int=int(ext_index))

        for mp in mapped_ports:
            internal_node_id = str(getattr(mp, "node_id", "") or "").strip()
            internal_port_name = str(getattr(mp, "port_name", "") or "").strip()
            internal_is_input = bool(getattr(mp, "is_input", False))
            internal_is_flow = bool(getattr(mp, "is_flow", False))
            if internal_node_id == "" or internal_port_name == "":
                continue
            internal_node_index = node_id_int_by_graph_node_id.get(str(internal_node_id))
            if not isinstance(internal_node_index, int) or int(internal_node_index) <= 0:
                raise ValueError(f"复合节点映射引用了未知内部节点：composite_id={composite_id!r} node_id={internal_node_id!r}")
            payload = graph_node_by_graph_node_id.get(str(internal_node_id))
            if not isinstance(payload, dict):
                raise ValueError(f"复合节点映射缺少内部节点 payload：node_id={internal_node_id!r}")
            title = str(node_title_by_graph_node_id.get(str(internal_node_id), "") or "").strip()
            if title == "":
                raise ValueError(f"复合节点映射缺少内部节点 title：node_id={internal_node_id!r}")
            node_def = node_defs_by_name.get(str(title))
            if node_def is None:
                raise ValueError(f"复合节点映射缺少内部 NodeDef：title={title!r} node_id={internal_node_id!r}")
            ports = payload.get("inputs" if bool(internal_is_input) else "outputs")
            if not isinstance(ports, list):
                raise ValueError(f"复合节点映射内部节点 ports 不是 list：title={title!r}")
            flow_ports = [
                str(p)
                for p in ports
                if _is_flow_port_by_node_def(node_def=node_def, port_name=str(p), is_input=bool(internal_is_input))
            ]
            data_ports = [
                str(p)
                for p in ports
                if not _is_flow_port_by_node_def(node_def=node_def, port_name=str(p), is_input=bool(internal_is_input))
            ]
            if (not bool(internal_is_flow)) and bool(internal_is_input):
                data_ports = _drop_signal_name_meta_port_if_needed(node_title=str(title), data_ports=list(data_ports))
            port_list = flow_ports if bool(internal_is_flow) else data_ports
            if str(internal_port_name) not in port_list:
                raise ValueError(
                    f"复合节点映射内部端口不存在：node={title!r} port={internal_port_name!r} ports={port_list!r}"
                )
            ordinal = int(port_list.index(str(internal_port_name)))
            internal_kind_int = (
                1
                if (internal_is_flow and internal_is_input)
                else 2
                if (internal_is_flow and (not internal_is_input))
                else 3
                if ((not internal_is_flow) and internal_is_input)
                else 4
            )

            internal_node_type_id_int = node_type_id_by_graph_node_id.get(str(internal_node_id))
            direction = "In" if bool(internal_is_input) else "Out"
            shell_index, kernel_index = resolve_node_editor_pack_pin_indices(
                node_type_id_int=int(internal_node_type_id_int) if isinstance(internal_node_type_id_int, int) else None,
                is_flow=bool(internal_is_flow),
                direction=str(direction),
                port_name=str(internal_port_name),
                ordinal=int(ordinal),
                fallback_index=int(ordinal),
            )

            # 真源语义：CompositeGraph.port_mappings 的 internal pin 同时写 shell_index(field_3) 与 kernel_index(field_4)，两者并不总相等。
            internal_shell_sig = pin_sig(kind_int=int(internal_kind_int), index_int=int(shell_index))
            internal_kernel_sig = pin_sig(kind_int=int(internal_kind_int), index_int=int(kernel_index))
            mappings.append(
                {
                    "1": dict(external_sig),
                    "2": int(internal_node_index),
                    "3": dict(internal_shell_sig),
                    "4": dict(internal_kernel_sig),
                }
            )
    return mappings


__all__ = ["build_port_mappings_for_composite"]

