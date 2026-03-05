from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ugc_file_tools.node_graph_semantics.graph_model import normalize_nodes_list as _normalize_nodes_list

from .composite_id_map import map_composite_id_to_composite_graph_id_int, map_composite_id_to_node_type_id_int
from .composite_writeback_apply import apply_composite_artifacts_to_payload_root_inplace
from .composite_writeback_types import CompositeWritebackArtifacts
from .composite_writeback_inner_graph import build_inner_graph_nodes_for_composite
from .composite_writeback_node_interface import (
    build_node_interface_message,
    build_record_id_map_from_node_interface,
    sorted_virtual_pins,
    virtual_pins_by_kind,
)
from .composite_writeback_port_mappings import build_port_mappings_for_composite
from .composite_writeback_proto import resource_locator


def _iter_graph_model_node_payloads(graph_model: Any) -> Iterable[Dict[str, Any]]:
    # 支持两种输入形态：
    # - dict GraphModel payload（工具链常见）
    # - engine.graph.models.graph_model.GraphModel（复合子图反序列化后常见）
    if hasattr(graph_model, "serialize") and callable(getattr(graph_model, "serialize")):
        payload = graph_model.serialize()
        if isinstance(payload, dict):
            graph_model = payload
    for n in list(_normalize_nodes_list(graph_model)):
        if isinstance(n, dict):
            yield n


def _apply_port_type_overrides_from_graph_metadata_inplace(*, graph_model_payload: Dict[str, Any]) -> None:
    """
    将 GraphModel.metadata.port_type_overrides 显式注入到 node payload 的 input/output_port_types。

    背景：
    - 复合节点子图（由引擎从 composite .py 生成）会在 metadata 中保存“端口类型覆盖”；
    - 若写回侧忽略该字段，子图内节点（如 获取列表长度、字典节点）的端口类型会退化到模板默认值，
      进而表现为“所有列表端口都显示为整数列表、字典端口显示为泛型”。
    """
    meta = graph_model_payload.get("metadata")
    if meta is None:
        return
    if not isinstance(meta, dict):
        raise TypeError("graph_model_payload.metadata must be dict when present")
    overrides = meta.get("port_type_overrides")
    if overrides is None:
        return
    if not isinstance(overrides, dict):
        raise TypeError("graph_model_payload.metadata.port_type_overrides must be dict when present")

    nodes = list(_normalize_nodes_list(graph_model_payload))
    node_by_id: Dict[str, Dict[str, Any]] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id") or "").strip()
        if nid:
            node_by_id[nid] = n

    for raw_node_id, raw_port_map in dict(overrides).items():
        node_id = str(raw_node_id or "").strip()
        if node_id == "":
            raise ValueError("metadata.port_type_overrides contains empty node id")
        node_payload = node_by_id.get(node_id)
        if node_payload is None:
            raise ValueError(f"metadata.port_type_overrides references missing node id: {node_id!r}")
        if not isinstance(raw_port_map, dict):
            raise TypeError(f"metadata.port_type_overrides[{node_id!r}] must be dict")

        inputs_value = node_payload.get("inputs")
        outputs_value = node_payload.get("outputs")
        if not isinstance(inputs_value, list) or not isinstance(outputs_value, list):
            raise TypeError(f"graph node inputs/outputs must be list: node_id={node_id!r}")
        inputs = [str(x) for x in inputs_value]
        outputs = [str(x) for x in outputs_value]

        for raw_port_name, raw_type_text in dict(raw_port_map).items():
            port_name = str(raw_port_name or "").strip()
            type_text = str(raw_type_text or "").strip()
            if port_name == "":
                raise ValueError(f"metadata.port_type_overrides has empty port name: node_id={node_id!r}")
            if type_text == "":
                raise ValueError(f"metadata.port_type_overrides has empty type text: node_id={node_id!r} port={port_name!r}")

            in_inputs = port_name in inputs
            in_outputs = port_name in outputs
            if in_inputs and in_outputs:
                raise ValueError(f"port name appears in both inputs and outputs: node_id={node_id!r} port={port_name!r}")
            if (not in_inputs) and (not in_outputs):
                raise ValueError(
                    "metadata.port_type_overrides references unknown port name: "
                    f"node_id={node_id!r} port={port_name!r}"
                )
            if in_inputs:
                node_payload.setdefault("input_port_types", {})[port_name] = type_text
            else:
                node_payload.setdefault("output_port_types", {})[port_name] = type_text


def collect_composite_ids_from_graph_model(*, graph_model: Any) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for node_payload in _iter_graph_model_node_payloads(graph_model):
        composite_id = str(node_payload.get("composite_id") or "").strip()
        node_def_ref = node_payload.get("node_def_ref")
        kind = str(node_def_ref.get("kind") or "").strip().lower() if isinstance(node_def_ref, dict) else ""
        if composite_id == "" and isinstance(node_def_ref, dict) and kind == "composite":
            composite_id = str(node_def_ref.get("key") or "").strip()
        if composite_id == "":
            continue
        if composite_id in seen:
            continue
        seen.add(composite_id)
        out.append(composite_id)
    out.sort(key=lambda s: s.casefold())
    return out


def _patch_composite_instance_port_types_in_graph_model_inplace(
    *,
    graph_model: Any,
    composite_id: str,
    virtual_pins_sorted: Sequence[object],
) -> None:
    """
    将复合节点实例的 `input_port_types/output_port_types` 强制对齐到复合节点 virtual pins 的 `pin_type`。

    背景（用户问题复现）：
    - 当 GraphModel 中复合节点端口类型退化为“列表/字典/泛型”时，
      后续 `.gil` 写回会沿用模板默认值，表现为“所有列表端口都变成整数列表、字典端口变成泛型”。
    - 复合节点的真实端口类型应以复合节点接口（virtual pins）为准，不能依赖端口名或 UI 快照字段。
    """
    composite_id = str(composite_id or "").strip()
    if composite_id == "":
        return

    VIRTUAL_PIN_KIND_INFLOW = 1
    VIRTUAL_PIN_KIND_OUTFLOW = 2
    VIRTUAL_PIN_KIND_INPARAM = 3
    VIRTUAL_PIN_KIND_OUTPARAM = 4

    by_kind = _virtual_pins_by_kind(_sorted_virtual_pins(list(virtual_pins_sorted)))
    inflow = list(by_kind.get(VIRTUAL_PIN_KIND_INFLOW) or [])
    outflow = list(by_kind.get(VIRTUAL_PIN_KIND_OUTFLOW) or [])
    inparam = list(by_kind.get(VIRTUAL_PIN_KIND_INPARAM) or [])
    outparam = list(by_kind.get(VIRTUAL_PIN_KIND_OUTPARAM) or [])

    def _extract_pin_type_text(pin_obj: object) -> str:
        return str(getattr(pin_obj, "pin_type", "") or "").strip()

    def _extract_pin_name(pin_obj: object) -> str:
        return str(getattr(pin_obj, "pin_name", "") or getattr(pin_obj, "name", "") or "").strip()

    for node_payload in _iter_graph_model_node_payloads(graph_model):
        node_composite_id = str(node_payload.get("composite_id") or "").strip()
        node_def_ref = node_payload.get("node_def_ref")
        kind = str(node_def_ref.get("kind") or "").strip().lower() if isinstance(node_def_ref, dict) else ""
        if node_composite_id == "" and kind == "composite":
            node_composite_id = str(node_def_ref.get("key") or "").strip()
        if node_composite_id != composite_id:
            continue

        inputs = node_payload.get("inputs")
        outputs = node_payload.get("outputs")
        if not isinstance(inputs, list) or not isinstance(outputs, list):
            raise TypeError(f"composite node inputs/outputs must be list: composite_id={composite_id!r}")

        expected_inputs = len(inflow) + len(inparam)
        expected_outputs = len(outflow) + len(outparam)

        # 标准化/预处理阶段可能会把复合节点实例的 ports 列表清空（例如当 node_def 尚未携带接口端口时）。
        # 对齐写回口径：此处以 virtual pins 的顺序与名称作为真源，补齐缺失的 inputs/outputs 列表；
        # 若列表非空但长度不匹配，则 fail-fast 暴露数据不一致（避免静默错位）。
        if (expected_inputs > 0) and (len(inputs) == 0):
            filled = [_extract_pin_name(p) for p in list(inflow) + list(inparam)]
            if any(name == "" for name in filled):
                raise ValueError(f"composite virtual input pin name empty: composite_id={composite_id!r}")
            inputs[:] = list(filled)
        if (expected_outputs > 0) and (len(outputs) == 0):
            filled = [_extract_pin_name(p) for p in list(outflow) + list(outparam)]
            if any(name == "" for name in filled):
                raise ValueError(f"composite virtual output pin name empty: composite_id={composite_id!r}")
            outputs[:] = list(filled)

        if len(inputs) != expected_inputs:
            raise ValueError(
                "composite node inputs count mismatch: "
                f"composite_id={composite_id!r} expected={expected_inputs} got={len(inputs)} "
                f"(inflow={len(inflow)}, inparam={len(inparam)})"
            )
        if len(outputs) != expected_outputs:
            raise ValueError(
                "composite node outputs count mismatch: "
                f"composite_id={composite_id!r} expected={expected_outputs} got={len(outputs)} "
                f"(outflow={len(outflow)}, outparam={len(outparam)})"
            )

        for i, pin_obj in enumerate(inparam):
            port_name = str(inputs[len(inflow) + int(i)] or "").strip()
            pin_type_text = _extract_pin_type_text(pin_obj)
            if port_name == "":
                raise ValueError(f"composite node input port name empty: composite_id={composite_id!r} ordinal={int(i)}")
            if pin_type_text == "":
                raise ValueError(
                    f"composite virtual inparam pin_type missing: composite_id={composite_id!r} ordinal={int(i)}"
                )
            node_payload.setdefault("input_port_types", {})[port_name] = str(pin_type_text)

        for i, pin_obj in enumerate(outparam):
            port_name = str(outputs[len(outflow) + int(i)] or "").strip()
            pin_type_text = _extract_pin_type_text(pin_obj)
            if port_name == "":
                raise ValueError(
                    f"composite node output port name empty: composite_id={composite_id!r} ordinal={int(i)}"
                )
            if pin_type_text == "":
                raise ValueError(
                    f"composite virtual outparam pin_type missing: composite_id={composite_id!r} ordinal={int(i)}"
                )
            node_payload.setdefault("output_port_types", {})[port_name] = str(pin_type_text)


def _load_composite_node_manager(*, workspace_root: Path) -> Any:
    get_manager = getattr(import_module("engine.nodes.composite_node_manager"), "get_composite_node_manager")
    return get_manager(workspace_path=Path(workspace_root).resolve(), verbose=False)


def _load_composite_or_raise(*, manager: Any, composite_id: str) -> Any:
    if not manager.load_subgraph_if_needed(str(composite_id)):
        raise ValueError(f"复合节点子图加载失败：composite_id={composite_id!r}")
    composite = manager.get_composite_node(str(composite_id))
    if composite is None:
        raise ValueError(f"未找到复合节点定义：composite_id={composite_id!r}")
    return composite


def _sorted_virtual_pins(virtual_pins: Sequence[object]) -> List[object]:
    return sorted_virtual_pins(virtual_pins)


def _virtual_pins_by_kind(virtual_pins_sorted: Sequence[object]) -> Dict[int, List[object]]:
    return virtual_pins_by_kind(virtual_pins_sorted)


def _build_node_interface_message(
    *,
    composite_id: str,
    node_def_id_int: int,
    composite_graph_id_int: int,
    node_name: str,
    node_description: str,
    virtual_pins_sorted: Sequence[object],
) -> Dict[str, Any]:
    return build_node_interface_message(
        composite_id=str(composite_id),
        node_def_id_int=int(node_def_id_int),
        composite_graph_id_int=int(composite_graph_id_int),
        node_name=str(node_name),
        node_description=str(node_description),
        virtual_pins_sorted=list(virtual_pins_sorted),
    )


def _build_record_id_map_from_node_interface(
    *, node_def_id_int: int, node_interface: Mapping[str, Any]
) -> Dict[int, Dict[int, int]]:
    return build_record_id_map_from_node_interface(node_def_id_int=int(node_def_id_int), node_interface=node_interface)


def _build_inner_graph_nodes_for_composite(
    *,
    composite_graph_model: Any,
    graph_json_object: Dict[str, Any],
    graph_scope: str,
    graph_generater_root: Path,
    mapping_path: Path,
    node_defs_by_name: Dict[str, Any],
    signal_maps: Any,
    graph_variable_type_text_by_name: Dict[str, str],
    record_id_by_node_type_id_and_inparam_index: Dict[int, Dict[int, int]],
) -> Tuple[List[Dict[str, Any]], Dict[str, int], Dict[str, Dict[str, Any]], Dict[str, str], Dict[str, int]]:
    return build_inner_graph_nodes_for_composite(
        composite_graph_model=composite_graph_model,
        graph_json_object=dict(graph_json_object),
        graph_scope=str(graph_scope),
        graph_generater_root=Path(graph_generater_root),
        mapping_path=Path(mapping_path),
        node_defs_by_name=dict(node_defs_by_name),
        signal_maps=signal_maps,
        graph_variable_type_text_by_name=dict(graph_variable_type_text_by_name),
        record_id_by_node_type_id_and_inparam_index=dict(record_id_by_node_type_id_and_inparam_index),
    )


def _build_port_mappings_for_composite(
    *,
    composite_id: str,
    virtual_pins_sorted: Sequence[object],
    node_id_int_by_graph_node_id: Mapping[str, int],
    graph_node_by_graph_node_id: Mapping[str, Dict[str, Any]],
    node_title_by_graph_node_id: Mapping[str, str],
    node_type_id_by_graph_node_id: Mapping[str, int],
    node_defs_by_name: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    return build_port_mappings_for_composite(
        composite_id=str(composite_id),
        virtual_pins_sorted=list(virtual_pins_sorted),
        node_id_int_by_graph_node_id=node_id_int_by_graph_node_id,
        graph_node_by_graph_node_id=graph_node_by_graph_node_id,
        node_title_by_graph_node_id=node_title_by_graph_node_id,
        node_type_id_by_graph_node_id=node_type_id_by_graph_node_id,
        node_defs_by_name=node_defs_by_name,
    )


def build_composite_writeback_artifacts(
    *,
    graph_model: Any,
    graph_scope: str,
    workspace_root: Path,
    graph_generater_root: Path,
    mapping_path: Path,
    node_defs_by_name: Dict[str, Any],
    signal_maps: Any,
    graph_variable_type_text_by_name: Dict[str, str],
    active_package_id: str | None,
) -> CompositeWritebackArtifacts:
    set_active = getattr(import_module("engine.utils.runtime_scope"), "set_active_package_id")
    set_active(str(active_package_id).strip() if isinstance(active_package_id, str) and active_package_id.strip() else None)
    manager = _load_composite_node_manager(workspace_root=Path(workspace_root))
    queue = collect_composite_ids_from_graph_model(graph_model=graph_model)
    visited: set[str] = set()

    wrappers: List[Dict[str, Any]] = []
    graphs: List[Dict[str, Any]] = []
    record_id_map: Dict[int, Dict[int, int]] = {}

    get_graph_model_cls = getattr(import_module("engine.graph.models.graph_model"), "GraphModel")
    standardize_payload = getattr(
        import_module("ugc_file_tools.graph.port_types"),
        "standardize_graph_model_payload_inplace",
    )

    while queue:
        composite_id = str(queue.pop(0)).strip()
        if composite_id == "" or composite_id in visited:
            continue
        visited.add(composite_id)

        composite = _load_composite_or_raise(manager=manager, composite_id=composite_id)
        node_def_id_int = int(map_composite_id_to_node_type_id_int(composite_id))
        composite_graph_id_int = int(map_composite_id_to_composite_graph_id_int(composite_id))

        node_name = str(getattr(composite, "node_name", "") or "").strip() or str(composite_id)
        node_desc = str(getattr(composite, "node_description", "") or "")
        virtual_pins_sorted = _sorted_virtual_pins(list(getattr(composite, "virtual_pins", []) or []))

        node_interface = _build_node_interface_message(
            composite_id=str(composite_id),
            node_def_id_int=int(node_def_id_int),
            composite_graph_id_int=int(composite_graph_id_int),
            node_name=str(node_name),
            node_description=str(node_desc),
            virtual_pins_sorted=virtual_pins_sorted,
        )
        wrappers.append({"1": dict(node_interface)})
        for k, v in _build_record_id_map_from_node_interface(node_def_id_int=int(node_def_id_int), node_interface=node_interface).items():
            record_id_map.setdefault(int(k), {}).update(dict(v))

        # 关键：host graph 内的复合节点实例端口类型也必须对齐到复合节点接口 pin_type，
        # 否则写回阶段会因端口类型文本退化为“列表/字典/泛型”而沿用模板默认值（常见：整数列表/泛型字典）。
        _patch_composite_instance_port_types_in_graph_model_inplace(
            graph_model=graph_model,
            composite_id=str(composite_id),
            virtual_pins_sorted=list(virtual_pins_sorted),
        )

        sub_graph_dict = getattr(composite, "sub_graph", None)
        if not isinstance(sub_graph_dict, dict):
            raise TypeError(f"composite.sub_graph must be dict: composite_id={composite_id!r}")
        # 递归收集嵌套复合节点（按 sub_graph 的 GraphModel schema）
        try:
            sub_model = get_graph_model_cls.deserialize(dict(sub_graph_dict))
        except Exception as e:
            raise ValueError(f"复合节点子图 GraphModel 反序列化失败：composite_id={composite_id!r}") from e

        sub_model_payload = sub_model.serialize() if hasattr(sub_model, "serialize") else dict(sub_graph_dict)
        # 关键：先应用 sub_graph.metadata.port_type_overrides（真源：引擎生成子图时的端口类型覆盖表），
        # 否则子图内节点端口类型会退化到模板默认值（典型：列表全变整数列表、字典全变泛型），
        # 进而导致 CompositeGraph.inner_nodes 的 NodePin VarType 错误。
        if isinstance(sub_model_payload, dict):
            _apply_port_type_overrides_from_graph_metadata_inplace(graph_model_payload=sub_model_payload)
        # 关键：复合节点子图也必须补齐“有效端口类型快照”（input/output_port_types 与 declared types）。
        # 否则字典/动态端口等类型推断会在写回侧退化，导致内部节点 pins/records/Concrete 错漏百出。
        standardize_payload(
            graph_model_payload=sub_model_payload,
            graph_variables=(sub_model_payload.get("graph_variables") if isinstance(sub_model_payload, dict) else None),
            workspace_root=Path(workspace_root).resolve(),
            scope=str(graph_scope),
            force_reenrich=True,
            fill_missing_edge_ids=True,
            allow_title_fallback=False,
        )
        queue.extend(
            [cid for cid in collect_composite_ids_from_graph_model(graph_model=sub_model_payload) if cid not in visited]
        )

        sub_graph_payload = dict(sub_graph_dict)
        sub_graph_payload.setdefault("graph_id", str(composite_id))
        sub_graph_payload.setdefault("graph_name", str(node_name))
        sub_graph_payload.setdefault("description", str(node_desc))
        graph_json_object = {"data": sub_graph_payload, "engine_version": ""}

        inner_nodes, node_id_int_by_graph_node_id, graph_node_by_graph_node_id, node_title_by_graph_node_id, node_type_id_by_graph_node_id = (
            _build_inner_graph_nodes_for_composite(
                composite_graph_model=sub_model_payload,
                graph_json_object=graph_json_object,
                graph_scope=str(graph_scope),
                graph_generater_root=Path(graph_generater_root),
                mapping_path=Path(mapping_path),
                node_defs_by_name=dict(node_defs_by_name),
                signal_maps=signal_maps,
                graph_variable_type_text_by_name=dict(graph_variable_type_text_by_name),
                record_id_by_node_type_id_and_inparam_index=dict(record_id_map),
            )
        )

        port_mappings = _build_port_mappings_for_composite(
            composite_id=str(composite_id),
            virtual_pins_sorted=virtual_pins_sorted,
            node_id_int_by_graph_node_id=node_id_int_by_graph_node_id,
            graph_node_by_graph_node_id=graph_node_by_graph_node_id,
            node_title_by_graph_node_id=node_title_by_graph_node_id,
            node_type_id_by_graph_node_id=node_type_id_by_graph_node_id,
            node_defs_by_name=dict(node_defs_by_name),
        )
        graph_ref = resource_locator(origin=10000, category=20000, kind=21002, runtime_id=int(composite_graph_id_int))
        graph_obj: Dict[str, Any] = {"1": graph_ref, "3": list(inner_nodes)}
        if port_mappings:
            graph_obj["4"] = list(port_mappings)
        graphs.append(graph_obj)

    return CompositeWritebackArtifacts(
        node_def_wrappers=list(wrappers),
        composite_graph_objs=list(graphs),
        record_id_by_node_type_id_and_inparam_index=dict(record_id_map),
    )


__all__ = [
    "CompositeWritebackArtifacts",
    "build_composite_writeback_artifacts",
    "apply_composite_artifacts_to_payload_root_inplace",
    "collect_composite_ids_from_graph_model",
]

