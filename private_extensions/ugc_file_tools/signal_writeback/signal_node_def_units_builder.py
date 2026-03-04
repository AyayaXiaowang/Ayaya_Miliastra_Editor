from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from ugc_file_tools.repo_paths import repo_root

from . import gia_export as _gia_export


@dataclass(frozen=True, slots=True)
class BuiltSignalNodeDefBundle:
    """
    自包含信号 node_def GraphUnits（用于打包进 NodeGraph 的 AssetBundle.dependencies）。
    """

    dependency_units: List[Dict[str, Any]]  # send/listen/server 三类 GraphUnit（每个信号 3 个）
    related_ids: List[Dict[str, Any]]  # GraphUnitId 列表（{"2":23,"4":id}），供 NodeGraph GraphUnit.relatedIds 使用

    send_node_def_id_by_signal_name: Dict[str, int]
    send_signal_name_port_index_by_signal_name: Dict[str, int]
    send_param_port_indices_by_signal_name: Dict[str, List[int]]
    send_param_var_type_ids_by_signal_name: Dict[str, List[int]]

    # listen: 用于在 NodeGraph 导出阶段对齐 runtime_id 与 compositePinIndex
    listen_node_def_id_by_signal_name: Dict[str, int]
    listen_signal_name_port_index_by_signal_name: Dict[str, int]
    listen_param_port_indices_by_signal_name: Dict[str, List[int]]


def _default_template_gia_path() -> Path:
    return (
        repo_root()
        / "private_extensions"
        / "ugc_file_tools"
        / "builtin_resources"
        / "gia_templates"
        / "signals"
        / "signal_node_defs_full.gia"
    ).resolve()


def _ensure_unique_node_def_id(base: int, *, used: set[int]) -> int:
    v = int(base)
    if v <= 0:
        v = 1
    # 分配 send/listen/server 3 连号，保证本次 bundle 内不冲突即可。
    # 注意：真源样本中的信号 node_def_id 是连续递增（例如 0x40000031/32/33），
    # 不做 “对 3 对齐” 的修正。
    while v in used or (v + 1) in used or (v + 2) in used:
        v += 1
    used.add(v)
    used.add(v + 1)
    used.add(v + 2)
    return int(v)


def _ensure_unique_port_block(start: int, *, width: int, used: set[int]) -> int:
    v = int(start)
    if v <= 0:
        v = 1
    while any((v + i) in used for i in range(int(width))):
        v += int(width)
    for i in range(int(width)):
        used.add(v + i)
    return int(v)


def _make_related_id(node_def_id_int: int) -> Dict[str, Any]:
    return {"2": 23, "4": int(node_def_id_int)}


def build_signal_node_def_bundle_for_signals(
    *,
    signals: Sequence[Mapping[str, Any]],
    template_gia: Path | None = None,
    # 端口索引：真源样本里信号端口通常位于 140 段（例如 信号名=142），
    # 且节点图里节点实例会直接引用这些 port_index（导入时按 port_index 匹配 pin）。
    # 因此自包含信号 node_def 的端口索引必须保持 140 段口径（按块分配）。
    port_index_start: int = 140,
    # node_def_id：按 3 连号分配（send/listen/server）。
    #
    # 注意：用户侧“节点图里用了信号 → 导入信号 .gia”的真源样本中，信号 node_def_id
    # 位于 0x4000xxxx（而复合节点 interface/node_def 常见于 0x6000xxxx），两者命名空间分离。
    # 默认从 0x40000031 起（真源样本常见的起点；且满足 send_id % 3 == 1）。
    node_def_id_start: int = 0x40000031,
    signal_index_start: int = 1,
) -> BuiltSignalNodeDefBundle:
    """
    给定信号规格（signal_name + params），构造自包含的 3 类信号 node_def GraphUnits（发送/监听/向服务器发送）。

    输入 `signals` 的每个元素 schema（最小）：
    {
      "signal_name": "...",
      "params": [{"param_name":"第X关","type_id":3}, ...]
    }
    """
    template_path = Path(template_gia).resolve() if template_gia is not None else _default_template_gia_path()
    if not template_path.is_file():
        raise FileNotFoundError(str(template_path))

    tpl_send_unit, tpl_listen_unit, tpl_server_unit = _gia_export._load_signal_node_def_templates_from_gia(template_path)

    used_node_def_ids: set[int] = set()
    used_ports: set[int] = set()

    dependency_units: List[Dict[str, Any]] = []
    related_ids: List[Dict[str, Any]] = []

    send_node_def_id_by_signal_name: Dict[str, int] = {}
    send_signal_name_port_index_by_signal_name: Dict[str, int] = {}
    send_param_port_indices_by_signal_name: Dict[str, List[int]] = {}
    send_param_var_type_ids_by_signal_name: Dict[str, List[int]] = {}

    listen_node_def_id_by_signal_name: Dict[str, int] = {}
    listen_signal_name_port_index_by_signal_name: Dict[str, int] = {}
    listen_param_port_indices_by_signal_name: Dict[str, List[int]] = {}

    # 对齐 `export_basic_signals_to_gia`：按 signal_name 稳定排序后再做连续编号，
    # 避免因输入顺序不同导致 node_def_id/port_index 抖动。
    items: list[Mapping[str, Any]] = []
    for it in list(signals):
        if not isinstance(it, Mapping):
            continue
        name = str(it.get("signal_name") or "").strip()
        if name == "":
            continue
        items.append(it)
    items.sort(key=lambda x: str(x.get("signal_name") or "").casefold())

    next_signal_index = int(signal_index_start)
    next_port_index = int(port_index_start)
    next_node_def_id = int(node_def_id_start)

    for item in items:
        signal_name = str(item.get("signal_name") or "").strip()

        raw_params = item.get("params") or []
        if not isinstance(raw_params, list):
            raise TypeError(f"signal.params must be list: signal={signal_name!r}")
        params: List[Dict[str, Any]] = []
        for p in raw_params:
            if not isinstance(p, Mapping):
                continue
            pn = str(p.get("param_name") or "").strip()
            pt = p.get("type_id")
            if pn == "" or not isinstance(pt, int):
                raise ValueError(f"signal param requires param_name/type_id: signal={signal_name!r}")
            params.append({"param_name": str(pn), "type_id": int(pt)})

        # 分配 node_def_id：按 3 连号（send/listen/server），对齐 `export_basic_signals_to_gia` 的口径。
        # 注意：此处只保证“本 bundle 内不冲突”；若要跨 bundle/跨复合节点避免冲突，需要上层做额外隔离策略。
        send_node_def_id = _ensure_unique_node_def_id(int(next_node_def_id), used=used_node_def_ids)
        listen_node_def_id = int(send_node_def_id + 1)
        server_node_def_id = int(send_node_def_id + 2)
        next_node_def_id = int(send_node_def_id + 3)

        signal_index_int = int(next_signal_index)
        next_signal_index += 1

        send_meta = _gia_export._build_node_def_meta_dict(node_def_id_int=send_node_def_id, scope_code_int=20000)
        listen_meta = _gia_export._build_node_def_meta_dict(node_def_id_int=listen_node_def_id, scope_code_int=20000)
        server_meta = _gia_export._build_node_def_meta_dict(node_def_id_int=server_node_def_id, scope_code_int=20002)

        # 分配端口索引块：一段连续的 port_index 供 send/listen/server + params 使用。
        # 这与真源样本一致（例如 信号名端口为 142，处于 140 段）。
        block_width = 16 + max(len(params), 0) * 3
        port_block = _ensure_unique_port_block(next_port_index, width=block_width, used=used_ports)
        next_port_index = int(port_block + block_width)

        send_flow_in = int(port_block)
        send_flow_out = int(port_block + 1)
        send_signal_name_port = int(port_block + 2)

        listen_flow = int(port_block + 3)
        listen_signal_name_port = int(port_block + 4)
        listen_event_source_entity = int(port_block + 5)
        listen_event_source_guid = int(port_block + 6)
        listen_signal_source_entity = int(port_block + 7)

        server_flow_in = int(port_block + 8)
        server_flow_out = int(port_block + 9)
        server_extra_port = int(port_block + 10)
        server_signal_name_port = int(port_block + 11)

        send_param_items: List[Dict[str, Any]] = []
        server_param_items: List[Dict[str, Any]] = []
        listen_param_ports: List[Dict[str, Any]] = []
        send_param_ports: List[int] = []
        send_param_vts: List[int] = []

        next_param_port = int(port_block + 12)
        for param_ordinal, p in enumerate(list(params)):
            param_name = str(p.get("param_name") or "").strip()
            type_id = p.get("type_id")
            if param_name == "" or not isinstance(type_id, int):
                raise ValueError("signal param requires param_name/type_id")

            send_port = int(next_param_port)
            listen_port = int(next_param_port + 1)
            server_port = int(next_param_port + 2)
            next_param_port += 3

            send_param_items.append(
                _gia_export._build_param_item_message_from_param_spec(
                    param_spec=p,
                    port_index_int=send_port,
                    param_ordinal_int=int(param_ordinal),
                    for_server_node=False,
                )
            )
            server_param_items.append(
                _gia_export._build_param_item_message_from_param_spec(
                    param_spec=p,
                    port_index_int=server_port,
                    param_ordinal_int=int(param_ordinal),
                    for_server_node=True,
                )
            )
            listen_param_ports.append(
                {
                    **dict(p),
                    "param_name": str(param_name),
                    "type_id": int(type_id),
                    "port_index": int(listen_port),
                }
            )
            send_param_ports.append(int(send_port))
            send_param_vts.append(int(type_id))

        # clone units
        send_unit = copy.deepcopy(dict(tpl_send_unit))
        listen_unit = copy.deepcopy(dict(tpl_listen_unit))
        server_unit = copy.deepcopy(dict(tpl_server_unit))

        # patch ids + related ids
        _gia_export._set_graph_unit_id_inplace(send_unit, node_def_id_int=send_node_def_id)
        _gia_export._set_graph_unit_id_inplace(listen_unit, node_def_id_int=listen_node_def_id)
        _gia_export._set_graph_unit_id_inplace(server_unit, node_def_id_int=server_node_def_id)

        _gia_export._set_graph_unit_related_ids_inplace(send_unit, related_node_def_ids=[listen_node_def_id, server_node_def_id])
        _gia_export._set_graph_unit_related_ids_inplace(listen_unit, related_node_def_ids=[send_node_def_id, server_node_def_id])
        _gia_export._set_graph_unit_related_ids_inplace(server_unit, related_node_def_ids=[send_node_def_id, listen_node_def_id])

        # patch node defs
        send_node_def = _gia_export._find_node_def_object_in_graph_unit(send_unit, expected_node_def_name="发送信号")
        listen_node_def = _gia_export._find_node_def_object_in_graph_unit(listen_unit, expected_node_def_name="监听信号")
        server_node_def = _gia_export._find_node_def_object_in_graph_unit(server_unit, expected_node_def_name="向服务器节点图发送信号")

        send_node_def = _gia_export._reset_send_node_def_for_new_signal(
            node_def=send_node_def,
            signal_index_int=signal_index_int,
            node_def_id_int=send_node_def_id,
            signal_name=signal_name,
            listen_meta_dict=listen_meta,
            server_meta_dict=server_meta,
            flow_in_port_index=send_flow_in,
            flow_out_port_index=send_flow_out,
            signal_name_port_index=send_signal_name_port,
            send_param_items=send_param_items,
        )
        listen_node_def = _gia_export._reset_listen_node_def_for_new_signal(
            node_def=listen_node_def,
            signal_index_int=signal_index_int,
            node_def_id_int=listen_node_def_id,
            signal_name=signal_name,
            send_meta_dict=send_meta,
            server_meta_dict=server_meta,
            flow_port_index=listen_flow,
            signal_name_port_index=listen_signal_name_port,
            fixed_output_port_indices=(listen_event_source_entity, listen_event_source_guid, listen_signal_source_entity),
            params=listen_param_ports,
        )
        server_node_def = _gia_export._reset_send_to_server_node_def_for_new_signal(
            node_def=server_node_def,
            signal_index_int=signal_index_int,
            node_def_id_int=server_node_def_id,
            signal_name=signal_name,
            listen_meta_dict=listen_meta,
            send_meta_dict=send_meta,
            flow_in_port_index=server_flow_in,
            flow_out_port_index=server_flow_out,
            extra_port_index=server_extra_port,
            signal_name_port_index=server_signal_name_port,
            server_param_items=server_param_items,
        )

        # write patched node_def back to units (reuse export_basic_signals_to_gia strategy)
        def _replace_node_def_inplace(unit: Dict[str, Any], *, expected: str, new_obj: Dict[str, Any]) -> None:
            expected_name = str(expected).strip()
            replaced = {"done": False}

            def walk(value: Any) -> Any:
                if isinstance(value, dict):
                    v200 = value.get("200")
                    if isinstance(v200, str) and v200.strip() == expected_name:
                        if isinstance(value.get("4"), dict) and isinstance(value.get("107"), dict):
                            replaced["done"] = True
                            return dict(new_obj)
                    for k, child in list(value.items()):
                        value[k] = walk(child)
                    return value
                if isinstance(value, list):
                    for i, child in enumerate(list(value)):
                        value[i] = walk(child)
                    return value
                return value

            walk(unit)
            if not replaced["done"]:
                raise ValueError(f"未能替换 node_def：{expected_name!r}")

        _replace_node_def_inplace(send_unit, expected="发送信号", new_obj=send_node_def)
        _replace_node_def_inplace(listen_unit, expected="监听信号", new_obj=listen_node_def)
        _replace_node_def_inplace(server_unit, expected="向服务器节点图发送信号", new_obj=server_node_def)

        # collect outputs
        dependency_units.extend([send_unit, listen_unit, server_unit])
        related_ids.extend([_make_related_id(send_node_def_id), _make_related_id(listen_node_def_id), _make_related_id(server_node_def_id)])

        send_node_def_id_by_signal_name[str(signal_name)] = int(send_node_def_id)
        send_signal_name_port_index_by_signal_name[str(signal_name)] = int(send_signal_name_port)
        send_param_port_indices_by_signal_name[str(signal_name)] = list(send_param_ports)
        send_param_var_type_ids_by_signal_name[str(signal_name)] = list(send_param_vts)

        listen_node_def_id_by_signal_name[str(signal_name)] = int(listen_node_def_id)
        listen_signal_name_port_index_by_signal_name[str(signal_name)] = int(listen_signal_name_port)
        listen_param_port_indices_by_signal_name[str(signal_name)] = [
            int(x.get("port_index"))
            for x in list(listen_param_ports)
            if isinstance(x, Mapping) and isinstance(x.get("port_index"), int)
        ]

    return BuiltSignalNodeDefBundle(
        dependency_units=list(dependency_units),
        related_ids=list(related_ids),
        send_node_def_id_by_signal_name=dict(send_node_def_id_by_signal_name),
        send_signal_name_port_index_by_signal_name=dict(send_signal_name_port_index_by_signal_name),
        send_param_port_indices_by_signal_name=dict(send_param_port_indices_by_signal_name),
        send_param_var_type_ids_by_signal_name=dict(send_param_var_type_ids_by_signal_name),
        listen_node_def_id_by_signal_name=dict(listen_node_def_id_by_signal_name),
        listen_signal_name_port_index_by_signal_name=dict(listen_signal_name_port_index_by_signal_name),
        listen_param_port_indices_by_signal_name=dict(listen_param_port_indices_by_signal_name),
    )

