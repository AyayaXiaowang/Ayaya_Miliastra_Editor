from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from ugc_file_tools.node_graph_semantics.graph_generater import is_flow_port_by_node_def as _is_flow_port_by_node_def
from ugc_file_tools.node_graph_semantics.pin_rules import infer_index_of_concrete_for_generic_pin
from ugc_file_tools.node_graph_semantics.var_base import (
    map_server_port_type_to_var_type_id as _map_server_port_type_to_var_type_id,
    wrap_var_base_as_concrete_base as _wrap_var_base_as_concrete_base,
    build_var_base_message_server,
    build_var_base_message_server_empty,
)

from .asset_bundle_builder_id_map import (
    _map_composite_id_to_composite_graph_id_int,
    _map_composite_id_to_node_type_id_int,
)
from .asset_bundle_builder_graph_context import build_node_graph_build_context
from .asset_bundle_builder_node_editor_pack import _iter_nep_pins, _resolve_pin_indices
from .asset_bundle_builder_proto_helpers import _make_pin_sig, _make_resource_locator
from .asset_bundle_builder_types import GiaAssetBundleGraphExportHints


def _collect_composite_ids_from_graph_nodes(nodes: Sequence[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for n in list(nodes):
        if not isinstance(n, dict):
            continue
        composite_id = str(n.get("composite_id") or "").strip()
        if composite_id == "":
            continue
        if composite_id in seen:
            continue
        seen.add(composite_id)
        out.append(composite_id)
    out.sort(key=lambda s: s.casefold())
    return out


def _build_composite_node_interface_message(
    *,
    composite_id: str,
    node_def_id_int: int,
    composite_graph_id_int: int,
    node_name: str,
    node_description: str,
    virtual_pins: Sequence[object],
) -> Dict[str, Any]:
    """
    构造 NodeInterface（复合节点 node_def）。

    说明：
    - 复合节点虚拟引脚结构来自 `engine.nodes.advanced_node_features.VirtualPinConfig`；
      这里不强依赖其具体类型（只按属性名读取），以降低跨层耦合。
    """
    shell_ref = _make_resource_locator(origin=10001, category=20000, kind=22001, guid=0, runtime_id=int(node_def_id_int))
    kernel_ref = _make_resource_locator(origin=10001, category=20000, kind=22001, guid=0, runtime_id=int(node_def_id_int))
    graph_ref = _make_resource_locator(origin=10000, category=20000, kind=21002, guid=0, runtime_id=int(composite_graph_id_int))

    signature = {"1": shell_ref, "2": kernel_ref, "4": graph_ref}

    # === pin lists ===
    inflow_pins = [p for p in list(virtual_pins) if bool(getattr(p, "is_flow", False)) and bool(getattr(p, "is_input", False))]
    outflow_pins = [p for p in list(virtual_pins) if bool(getattr(p, "is_flow", False)) and (not bool(getattr(p, "is_input", False)))]
    inparam_pins = [p for p in list(virtual_pins) if (not bool(getattr(p, "is_flow", False))) and bool(getattr(p, "is_input", False))]
    outparam_pins = [p for p in list(virtual_pins) if (not bool(getattr(p, "is_flow", False))) and (not bool(getattr(p, "is_input", False)))]

    def _sort_pins(pins: List[object]) -> List[object]:
        return sorted(
            pins,
            key=lambda x: (
                int(getattr(x, "pin_index", 0) or 0),
                str(getattr(x, "pin_name", "") or "").casefold(),
            ),
        )

    inflow_pins = _sort_pins(inflow_pins)
    outflow_pins = _sort_pins(outflow_pins)
    inparam_pins = _sort_pins(inparam_pins)
    outparam_pins = _sort_pins(outparam_pins)

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
        NodeEditorPack `TypedValue.WidgetType`：
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

    def _make_pin_interface(p: object, *, kind_int: int, ordinal_index: int) -> Dict[str, Any]:
        pin_name = str(getattr(p, "pin_name", "") or "").strip()
        sig = _make_pin_sig(kind_int=int(kind_int), index_int=int(ordinal_index))

        type_info: Dict[str, Any] = {}
        if int(kind_int) in {3, 4}:
            vt = _pin_type_to_var_type_int(str(getattr(p, "pin_type", "") or ""))
            if int(vt) != 0:
                widget = int(_var_type_int_to_widget_type_int(int(vt)))
                if int(widget) != 0:
                    type_info["1"] = int(widget)  # widget_type（真源必有；缺失会导致编辑器不生成可编辑输入控件）
                type_info["3"] = int(vt)  # var_type_shell
                type_info["4"] = int(vt)  # var_type_kernel

        # 真源/引擎侧约定：复合节点虚拟引脚的 pin_index 作为稳定索引（从 1 开始）。
        persistent_uid = int(getattr(p, "pin_index", 0) or 0)

        msg: Dict[str, Any] = {
            "2": 1,  # visibility_mask（真源多为 1）
            "3": sig,
            "4": dict(type_info),  # flow pin 写空 message（对齐真源常见形态）
            "8": int(persistent_uid),
        }
        if pin_name != "":
            msg["1"] = str(pin_name)
        return msg

    node_interface: Dict[str, Any] = {
        "4": signature,
        "107": {"1": 1000},  # Implementation.Category.COMPOSITE
        "200": str(node_name),
        "201": str(node_description or ""),
        "203": 6,  # TemplateRoot.USER_COMPOSITE
    }

    if inflow_pins:
        node_interface["100"] = [_make_pin_interface(p, kind_int=1, ordinal_index=i) for i, p in enumerate(inflow_pins)]
    if outflow_pins:
        node_interface["101"] = [_make_pin_interface(p, kind_int=2, ordinal_index=i) for i, p in enumerate(outflow_pins)]
    if inparam_pins:
        node_interface["102"] = [_make_pin_interface(p, kind_int=3, ordinal_index=i) for i, p in enumerate(inparam_pins)]
    if outparam_pins:
        node_interface["103"] = [_make_pin_interface(p, kind_int=4, ordinal_index=i) for i, p in enumerate(outparam_pins)]

    return node_interface


def _build_composite_dependency_units_for_graph(
    *,
    graph_nodes: Sequence[Dict[str, Any]],
    hints: GiaAssetBundleGraphExportHints,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    给定“当前图”的 GraphModel.nodes，构造复合节点自包含依赖：
    - dependencies: [NodeInterface GraphUnit, CompositeGraph GraphUnit, ...]
    - related_ids: 仅包含 NodeInterface 的 relatedIds（GraphUnitId，class=23）
    """
    queue: List[str] = _collect_composite_ids_from_graph_nodes(graph_nodes)
    if not queue:
        return [], []

    from engine.nodes.composite_node_manager import get_composite_node_manager

    manager = get_composite_node_manager(workspace_path=Path(hints.graph_generater_root).resolve(), verbose=False)

    dependency_units: List[Dict[str, Any]] = []
    related_ids: List[Dict[str, Any]] = []
    visited: set[str] = set()

    while queue:
        composite_id = str(queue.pop(0)).strip()
        if composite_id == "" or composite_id in visited:
            continue
        visited.add(composite_id)

        if not manager.load_subgraph_if_needed(composite_id):
            raise ValueError(f"复合节点子图加载失败（请检查复合节点库/作用域）：composite_id={composite_id!r}")
        composite = manager.get_composite_node(composite_id)
        if composite is None:
            raise ValueError(f"未找到复合节点定义（请检查复合节点库/作用域）：composite_id={composite_id!r}")

        node_def_id_int = int(_map_composite_id_to_node_type_id_int(composite_id))
        composite_graph_id_int = int(_map_composite_id_to_composite_graph_id_int(composite_id))
        node_name = str(getattr(composite, "node_name", "") or "").strip() or str(composite_id)
        node_desc = str(getattr(composite, "node_description", "") or "")

        sub_graph = getattr(composite, "sub_graph", None)
        if not isinstance(sub_graph, dict):
            raise TypeError(f"composite.sub_graph must be dict: composite_id={composite_id!r}")

        # 递归：子图中若出现复合节点，继续打包
        sub_nodes = sub_graph.get("nodes")
        if isinstance(sub_nodes, list):
            queue.extend(_collect_composite_ids_from_graph_nodes(sub_nodes))

        # --- 构造 CompositeGraph 的 NodeGraphContainer（复用 GraphModel→NodeGraph 逻辑） ---
        graph_payload = dict(sub_graph)
        graph_payload.setdefault("graph_id", str(composite_id))
        graph_payload.setdefault("graph_name", str(node_name))
        graph_payload.setdefault("description", str(node_desc))
        sub_graph_json_object: Dict[str, Any] = {"data": graph_payload, "engine_version": str(hints.game_version or "6.3.0")}

        # === 交付边界（复合子图）端口类型缺口 fail-fast ===
        #
        # 说明：
        # - 外层 `.gia` 导出 pipeline 会对“顶层图”生成 gap_report 并 fail-fast；
        # - 但复合节点导出会在这里递归把子图打包进 bundle，若子图仍存在“泛型家族/容器占位(字典/列表)”端口，
        #   会在更深的 builder（pins/VarBase）阶段以 ValueError 形式爆栈，错误定位更差。
        # - 因此这里补齐：对子图同样做标准化 + gap_report，总缺口 counts.total>0 直接 fail-fast。
        from ugc_file_tools.graph.port_types import standardize_graph_model_payload_inplace
        from ugc_file_tools.graph.port_type_gap_report import build_port_type_gap_report
        from ugc_file_tools.output_paths import resolve_output_dir_path_in_out_dir
        import json

        inner_payload = sub_graph_json_object.get("data")
        if isinstance(inner_payload, dict):
            standardize_graph_model_payload_inplace(
                graph_model_payload=inner_payload,
                graph_variables=None,
                workspace_root=Path(hints.graph_generater_root).resolve(),
                scope="server",
                force_reenrich=True,
                fill_missing_edge_ids=True,
            )
            gap_report = build_port_type_gap_report(
                graph_model_payload=dict(inner_payload),
                graph_scope="server",
                graph_name=str(node_name),
                graph_id_int=int(composite_graph_id_int),
            )
            counts = dict(gap_report.get("counts") or {}) if isinstance(gap_report, dict) else {}
            total = int(counts.get("total") or 0)
            if total > 0:
                # 统一落盘到 out/reports，便于复现与对照（与顶层图保持同一证据链目录语义）
                report_dir = resolve_output_dir_path_in_out_dir(Path("reports") / "port_type_gaps")
                report_dir.mkdir(parents=True, exist_ok=True)
                report_path = (report_dir / f"server__composite__{str(composite_id)}.json").resolve()
                report_path.write_text(json.dumps(gap_report, ensure_ascii=False, indent=2), encoding="utf-8")

                first_items: list[str] = []
                items = gap_report.get("items") if isinstance(gap_report, dict) else None
                if isinstance(items, list):
                    for it in items:
                        if not isinstance(it, dict):
                            continue
                        first_items.append(
                            f"{str(it.get('severity') or '')}:{str(it.get('node_title') or '')}.{str(it.get('port_name') or '')} reason={str(it.get('reason') or '')}"
                        )
                        if len(first_items) >= 5:
                            break
                raise ValueError(
                    "复合节点子图存在未解决的端口类型缺口（导出禁止继续）："
                    f"composite_id={str(composite_id)!r} graph_name={str(node_name)!r} total_gaps={int(total)} "
                    f"report_file={str(report_path)!r} first={first_items!r}"
                )

        inner_ctx = build_node_graph_build_context(
            graph_json_object=sub_graph_json_object,
            hints=GiaAssetBundleGraphExportHints(
                graph_id_int=int(composite_graph_id_int),
                graph_name=str(node_name),
                graph_scope="server",
                resource_class="COMPOSITE_GRAPH",
                graph_generater_root=Path(hints.graph_generater_root),
                node_type_id_by_node_def_key=dict(hints.node_type_id_by_node_def_key),
                export_uid=0,
                game_version=str(hints.game_version or "6.3.0"),
                signal_send_node_def_id_by_signal_name=hints.signal_send_node_def_id_by_signal_name,
                signal_send_signal_name_port_index_by_signal_name=hints.signal_send_signal_name_port_index_by_signal_name,
                signal_send_param_port_indices_by_signal_name=hints.signal_send_param_port_indices_by_signal_name,
                signal_send_param_var_type_ids_by_signal_name=hints.signal_send_param_var_type_ids_by_signal_name,
                extra_dependency_graph_units=None,
                graph_related_ids=None,
                include_composite_nodes=False,
            ),
        )

        node_graph_container = inner_ctx.node_graph_container
        node_graph_msg = inner_ctx.node_graph_msg

        node_index_by_graph_node_id = inner_ctx.node_index_by_graph_node_id
        node_payload_by_graph_node_id = inner_ctx.node_payload_by_graph_node_id
        node_title_by_graph_node_id = inner_ctx.node_title_by_graph_node_id
        node_type_id_int_by_graph_node_id = inner_ctx.node_type_id_int_by_graph_node_id
        node_record_by_graph_node_id = inner_ctx.node_record_by_graph_node_id
        node_def_by_graph_node_id = inner_ctx.node_def_by_graph_node_id

        # ------------------------------------------------------------------
        # 真源对齐补丁：复合节点内部“拼装列表(169) -> 启动定时器(79).定时器序列”
        #
        # 现象（来自用户反馈）：
        # - 拼装列表 OUT_PARAM 被写成 Str（缺少“列表结构/ConcreteBase”），导致编辑器导入后断线；
        # - “是否循环”在编辑器侧以“是/否”下拉呈现，若落盘结构不完整也会表现为未设置。
        #
        # 根因：
        # - 复合节点的虚拟数据入（例如“延迟秒数: 浮点数”）通过 InterfaceMapping 绑定到
        #   拼装列表的泛型 InParam（R<T>）；但 GraphModel 对该泛型端口往往缺少明确类型，
        #   导致导出兜底成 Str，从而使 OUT_PARAM 也退化为 Str。
        #
        # 规则：
        # - 若复合节点存在一个“浮点数”虚拟输入映射到拼装列表的第一个元素（ShellIndex=1，label="0"），
        #   则：
        #   1) 强制拼装列表的元素输入端口按 Flt(5) 落盘（ConcreteBase），并将隐藏长度 Input0 设为 1；
        #   2) 强制拼装列表 OUT_PARAM 为 L<Flt>(10)（ConcreteBase）。
        # ------------------------------------------------------------------
        def _pin_kind_index(pin_sig: Any) -> Tuple[int, int]:
            if not isinstance(pin_sig, Mapping):
                return 0, 0
            k = int(pin_sig.get("1") or 0)
            i = int(pin_sig.get("2") or 0)
            return int(k), int(i)

        def _find_node_instance_by_index(node_index_int: int) -> Dict[str, Any] | None:
            # CompositeGraph 内部：node instances 在 field_3（field_4 另作 InterfaceMapping 使用）
            nodes_list = node_graph_msg.get("3")
            if not isinstance(nodes_list, list):
                return None
            for inst in nodes_list:
                if not isinstance(inst, dict):
                    continue
                if int(inst.get("1") or 0) == int(node_index_int):
                    return inst
            return None

        def _find_node_runtime_id(node_inst: Mapping[str, Any]) -> int:
            locator = node_inst.get("2")
            if not isinstance(locator, Mapping):
                return 0
            return int(locator.get("5") or 0)

        def _set_pin_var_type_and_base(
            *,
            node_title: str,
            node_type_id_int: int,
            pin_msg: Dict[str, Any],
            shell_index: int,
            is_input: bool,
            port_name_for_rules: str,
            var_type_int: int,
            wrap_as_generic: bool,
            const_value: Any | None,
        ) -> None:
            pin_msg["4"] = int(var_type_int)
            if const_value is not None:
                inner = build_var_base_message_server(var_type_int=int(var_type_int), value=const_value)
            else:
                inner = build_var_base_message_server_empty(var_type_int=int(var_type_int))
            if bool(wrap_as_generic):
                index_of_concrete = infer_index_of_concrete_for_generic_pin(
                    node_title=str(node_title),
                    port_name=str(port_name_for_rules),
                    is_input=bool(is_input),
                    var_type_int=int(var_type_int),
                    node_type_id_int=int(node_type_id_int),
                    pin_index=int(shell_index),
                )
                pin_msg["3"] = _wrap_var_base_as_concrete_base(inner=inner, index_of_concrete=index_of_concrete)
            else:
                pin_msg["3"] = dict(inner)

        # --- 注入 port_mappings（InterfaceMapping） ---
        # 复用 build_node_graph_build_context(...) 产出的稳定 node_index/title/payload 映射，
        # 确保 InterfaceMapping 使用的 node_index 与 node_instances 完全一致。

        virtual_pins = list(getattr(composite, "virtual_pins", []) or [])
        virtual_pins_sorted = sorted(
            virtual_pins,
            key=lambda p: (
                int(getattr(p, "pin_index", 0) or 0),
                str(getattr(p, "pin_name", "") or "").casefold(),
            ),
        )

        # === 复合内部泛型端口类型对齐（拼装列表 -> 启动定时器.定时器序列） ===
        # 不依赖 VirtualPin.mapped_ports 的细节；直接以“已存在的 data edge 结构”为真源：
        # 若检测到 Start_Timer(79) 的 定时器序列(IN_PARAM shell=3) 连接到 Assembly_List(169) 的 OUT_PARAM(0)，
        # 则强制 Assembly_List 的泛型端口收敛为 Flt/L<Flt>，并把隐藏长度设为 1。
        nodes_list = node_graph_msg.get("3")
        if isinstance(nodes_list, list):
            node_inst_by_index: Dict[int, Dict[str, Any]] = {}
            for inst in nodes_list:
                if not isinstance(inst, dict):
                    continue
                idx = int(inst.get("1") or 0)
                if idx > 0:
                    node_inst_by_index[int(idx)] = inst

            for inst in list(node_inst_by_index.values()):
                if int(_find_node_runtime_id(inst)) != 79:
                    continue
                pins = inst.get("4")
                if not isinstance(pins, list):
                    continue
                # Start_Timer: 定时器序列 = IN_PARAM(shell=3)
                seq_pin = None
                for pmsg in pins:
                    if not isinstance(pmsg, dict):
                        continue
                    kind, shell_idx = _pin_kind_index(pmsg.get("1"))
                    if int(kind) == 3 and int(shell_idx) == 3:
                        seq_pin = pmsg
                        break
                if not isinstance(seq_pin, dict):
                    continue
                conns = seq_pin.get("5")
                if not isinstance(conns, list):
                    continue
                for c in conns:
                    if not isinstance(c, dict):
                        continue
                    src_node_index = int(c.get("1") or 0)
                    src_pin_shell = c.get("2")
                    src_kind, src_idx = _pin_kind_index(src_pin_shell)
                    if int(src_kind) != 4 or int(src_idx) != 0:
                        continue
                    src_inst = node_inst_by_index.get(int(src_node_index))
                    if not isinstance(src_inst, dict):
                        continue
                    if int(_find_node_runtime_id(src_inst)) != 169:
                        continue

                    src_pins = src_inst.get("4")
                    if not isinstance(src_pins, list):
                        continue
                    for pmsg in src_pins:
                        if not isinstance(pmsg, dict):
                            continue
                        k2, s2 = _pin_kind_index(pmsg.get("1"))
                        if int(k2) == 3:
                            if int(s2) == 0:
                                _set_pin_var_type_and_base(
                                    node_title="拼装列表",
                                    node_type_id_int=169,
                                    pin_msg=pmsg,
                                    shell_index=int(s2),
                                    is_input=True,
                                    port_name_for_rules="列表长度",
                                    var_type_int=3,
                                    wrap_as_generic=False,
                                    const_value=1,
                                )
                            elif 1 <= int(s2) <= 100:
                                _set_pin_var_type_and_base(
                                    node_title="拼装列表",
                                    node_type_id_int=169,
                                    pin_msg=pmsg,
                                    shell_index=int(s2),
                                    is_input=True,
                                    port_name_for_rules=str(int(s2) - 1),
                                    var_type_int=5,
                                    wrap_as_generic=True,
                                    const_value=None,
                                )
                        elif int(k2) == 4 and int(s2) == 0:
                            _set_pin_var_type_and_base(
                                node_title="拼装列表",
                                node_type_id_int=169,
                                pin_msg=pmsg,
                                shell_index=int(s2),
                                is_input=False,
                                port_name_for_rules="列表",
                                var_type_int=10,
                                wrap_as_generic=True,
                                const_value=None,
                            )
                    break

        ext_index_by_kind_and_name: Dict[Tuple[int, str], int] = {}
        counters: Dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0}
        for vp in virtual_pins_sorted:
            pn = str(getattr(vp, "pin_name", "") or "").strip()
            if pn == "":
                continue
            is_flow = bool(getattr(vp, "is_flow", False))
            is_input = bool(getattr(vp, "is_input", False))
            kind_int = 1 if (is_flow and is_input) else 2 if (is_flow and (not is_input)) else 3 if ((not is_flow) and is_input) else 4
            i = int(counters[int(kind_int)])
            ext_index_by_kind_and_name[(int(kind_int), str(pn))] = int(i)
            counters[int(kind_int)] = int(i + 1)

        def _internal_pin_sig(
            *,
            internal_node_id: str,
            port_name: str,
            is_flow: bool,
            is_input: bool,
        ) -> Tuple[Dict[str, Any], Dict[str, Any], int]:
            payload = node_payload_by_graph_node_id.get(str(internal_node_id))
            if not isinstance(payload, dict):
                raise ValueError(f"interface mapping 引用了未知内部节点：{internal_node_id!r}")
            title = node_title_by_graph_node_id.get(str(internal_node_id), "")
            if title == "":
                raise ValueError(f"interface mapping 缺少内部节点 title：{internal_node_id!r}")
            node_def = node_def_by_graph_node_id.get(str(internal_node_id))
            if node_def is None:
                raise KeyError(f"复合节点子图引用了未知节点定义（NodeDef 不存在）：node_id={internal_node_id!r} title={title!r}")
            node_type_id_int = node_type_id_int_by_graph_node_id.get(str(internal_node_id))
            if not isinstance(node_type_id_int, int) or int(node_type_id_int) <= 0:
                raise KeyError(f"node_type_semantic_map 未覆盖该节点（无法构造复合节点映射）：node_id={internal_node_id!r} title={title!r}")
            node_record = node_record_by_graph_node_id.get(str(internal_node_id))

            inputs = payload.get("inputs")
            outputs = payload.get("outputs")
            inputs_list = [str(x) for x in inputs] if isinstance(inputs, list) else []
            outputs_list = [str(x) for x in outputs] if isinstance(outputs, list) else []

            if bool(is_flow):
                kind_int = 1 if bool(is_input) else 2
                direction = "In" if bool(is_input) else "Out"
                ports = inputs_list if bool(is_input) else outputs_list
                flow_ports = [
                    str(pn)
                    for pn in ports
                    if _is_flow_port_by_node_def(node_def=node_def, port_name=str(pn), is_input=bool(is_input))
                ]
                if str(port_name) not in flow_ports:
                    raise ValueError(f"internal flow port 不存在：node={title!r} port={port_name!r} ports={flow_ports!r}")
                # 复合节点类格式中，多分支（match-case）虚拟流程出口会锚定到子图里的【多分支】节点，
                # 其出口端口名通常是 case 值（例如 "0"/"1"/"foo"）或 "默认"。
                # 但 NodeEditorPack 的 FlowPins 采用 DefaultBranch/Case1.. 的结构化标识（CaseN 不含 zh 标签），
                # 直接用端口名匹配会退回到错误的默认出口（ShellIndex=0）。
                #
                # 这里基于该节点的“判断参数（cases list）”常量，做一次从 case 值 → CaseN 的稳定映射：
                # - Default ("默认") 仍走常规路径（ShellIndex=0）
                # - CaseN: ShellIndex = N（N 从 1 开始），对应 cases list 中的第 N 个元素
                if int(node_type_id_int) == 3 and (not bool(is_input)) and str(port_name) != "默认":
                    input_constants = payload.get("input_constants")
                    cases_list = None
                    if isinstance(input_constants, dict):
                        cases_list = input_constants.get("判断参数")
                        if cases_list is None:
                            cases_list = input_constants.get("cases")
                    if isinstance(cases_list, list) and isinstance(node_record, Mapping):
                        # 允许 int/str 混用：统一转成字符串比对
                        wanted = str(port_name)
                        case_pos_0 = None
                        for idx0, v in enumerate(cases_list):
                            if str(v) == wanted:
                                case_pos_0 = int(idx0)
                                break
                        if isinstance(case_pos_0, int) and int(case_pos_0) >= 0:
                            shell_target = int(case_pos_0 + 1)  # Case1 从 1 开始
                            nep_flow_pins = _iter_nep_pins(node_record, is_flow=True)
                            hit = next(
                                (p for p in nep_flow_pins if p.direction == "Out" and int(p.shell_index) == int(shell_target)),
                                None,
                            )
                            if hit is not None:
                                return (
                                    _make_pin_sig(kind_int=int(kind_int), index_int=int(hit.shell_index)),
                                    _make_pin_sig(kind_int=int(kind_int), index_int=int(hit.kernel_index)),
                                    int(kind_int),
                                )
                    # 若无法从 cases list 推断（例如动态 cases），回退到“按端口顺序”的兜底
                ordinal = int(flow_ports.index(str(port_name)))
            else:
                kind_int = 3 if bool(is_input) else 4
                direction = "In" if bool(is_input) else "Out"
                ports = inputs_list if bool(is_input) else outputs_list
                data_ports = [
                    str(pn)
                    for pn in ports
                    if not _is_flow_port_by_node_def(node_def=node_def, port_name=str(pn), is_input=bool(is_input))
                ]
                if str(port_name) not in data_ports:
                    raise ValueError(f"internal data port 不存在：node={title!r} port={port_name!r} ports={data_ports!r}")
                ordinal = int(data_ports.index(str(port_name)))

            shell_i, kernel_i = _resolve_pin_indices(
                node_record,
                is_flow=bool(is_flow),
                direction=str(direction),
                port_name=str(port_name),
                ordinal=int(ordinal),
                fallback_index=int(ordinal),
            )
            return _make_pin_sig(kind_int=int(kind_int), index_int=int(shell_i)), _make_pin_sig(kind_int=int(kind_int), index_int=int(kernel_i)), int(kind_int)

        port_mappings: List[Dict[str, Any]] = []
        for vp in virtual_pins_sorted:
            ext_pin_name = str(getattr(vp, "pin_name", "") or "").strip()
            if ext_pin_name == "":
                continue
            is_flow = bool(getattr(vp, "is_flow", False))
            is_input = bool(getattr(vp, "is_input", False))
            ext_kind_int = 1 if (is_flow and is_input) else 2 if (is_flow and (not is_input)) else 3 if ((not is_flow) and is_input) else 4
            ext_index = ext_index_by_kind_and_name.get((int(ext_kind_int), str(ext_pin_name)))
            if not isinstance(ext_index, int):
                continue
            external_sig = _make_pin_sig(kind_int=int(ext_kind_int), index_int=int(ext_index))

            mapped_ports = list(getattr(vp, "mapped_ports", []) or [])
            for mp in mapped_ports:
                internal_node_id = str(getattr(mp, "node_id", "") or "").strip()
                internal_port_name = str(getattr(mp, "port_name", "") or "").strip()
                internal_is_input = bool(getattr(mp, "is_input", False))
                internal_is_flow = bool(getattr(mp, "is_flow", False))
                if internal_node_id == "" or internal_port_name == "":
                    continue
                internal_node_index = node_index_by_graph_node_id.get(str(internal_node_id))
                if not isinstance(internal_node_index, int):
                    raise ValueError(
                        f"复合节点虚拟引脚映射引用了未知内部节点：composite_id={composite_id!r} node_id={internal_node_id!r}"
                    )
                internal_shell_sig, internal_kernel_sig, _ = _internal_pin_sig(
                    internal_node_id=str(internal_node_id),
                    port_name=str(internal_port_name),
                    is_flow=bool(internal_is_flow),
                    is_input=bool(internal_is_input),
                )
                port_mappings.append(
                    {
                        "1": dict(external_sig),
                        "2": int(internal_node_index),
                        "3": dict(internal_shell_sig),
                        "4": dict(internal_kernel_sig),
                    }
                )

        if port_mappings:
            # 稳定性：VirtualPin.mapped_ports 的构建顺序可能受解析/合并过程影响；
            # 但 CompositeGraph.port_mappings 在语义上是一个“映射集合”，不依赖顺序。
            # 这里按 (external_sig, internal_node_index, internal_shell_sig, internal_kernel_sig) 排序，
            # 避免同一输入在不同测试顺序/进程内缓存状态下产生快照抖动。
            def _port_mapping_sort_key(pm: Mapping[str, Any]) -> Tuple[int, int, int, int, int, int, int]:
                ext = pm.get("1")
                shell = pm.get("3")
                kernel = pm.get("4")
                ext_k = int(ext.get("1") or 0) if isinstance(ext, Mapping) else 0
                ext_i = int(ext.get("2") or 0) if isinstance(ext, Mapping) else 0
                node_i = int(pm.get("2") or 0)
                shell_k = int(shell.get("1") or 0) if isinstance(shell, Mapping) else 0
                shell_i = int(shell.get("2") or 0) if isinstance(shell, Mapping) else 0
                kernel_k = int(kernel.get("1") or 0) if isinstance(kernel, Mapping) else 0
                kernel_i = int(kernel.get("2") or 0) if isinstance(kernel, Mapping) else 0
                return (ext_k, ext_i, node_i, shell_k, shell_i, kernel_k, kernel_i)

            node_graph_msg["4"] = sorted(port_mappings, key=_port_mapping_sort_key)

        # === 真源对齐：多分支（Multiple_Branches, node_id=3）在复合子图内的“cases 列表” ===
        # 真源样本中，该节点的 InParam:
        # - index=0 为 Int（控制表达式）
        # - index=1 为 IntList（长度决定展开多少个 case 分支；len = outflow_count - 1）
        # 优先来源：复合节点虚拟引脚定义（单一真源）——即使宿主图不连接任何分支也必须保持稳定。
        # 说明：mapped_ports / InterfaceMapping 可能会因“宿主图未引用该出口”而不包含全部 outflow，
        # 因此不能依赖 port_mappings 推断 cases 数量。
        virtual_outflow_count = len(
            [
                p
                for p in list(virtual_pins_sorted)
                if bool(getattr(p, "is_flow", False)) and (not bool(getattr(p, "is_input", False)))
            ]
        )
        cases_count = max(0, int(virtual_outflow_count) - 1)

        nodes_list = node_graph_msg.get("3")
        if isinstance(nodes_list, list) and nodes_list and cases_count >= 0:
            for node_inst in nodes_list:
                if not isinstance(node_inst, dict):
                    continue
                locator = node_inst.get("2")
                if not isinstance(locator, dict):
                    continue
                # NodeProperty.kind=22000, runtime_id(node_id)=3
                if int(locator.get("3") or 0) != 22000:
                    continue
                if int(locator.get("5") or 0) != 3:
                    continue
                pins = node_inst.get("4")
                if not isinstance(pins, list):
                    continue

                by_kind_idx: Dict[Tuple[int, int], Dict[str, Any]] = {}
                for p in list(pins):
                    if not isinstance(p, dict):
                        continue
                    sig = p.get("1")
                    if not isinstance(sig, dict):
                        continue
                    k = int(sig.get("1") or 0)
                    idx = int(sig.get("2") or 0)
                    key = (k, idx)
                    # 去重策略：优先保留“非字符串/更具体类型”的 pin
                    prev = by_kind_idx.get(key)
                    if prev is None:
                        by_kind_idx[key] = p
                        continue
                    prev_t = int(prev.get("4") or 0) if isinstance(prev.get("4"), int) else 0
                    cur_t = int(p.get("4") or 0) if isinstance(p.get("4"), int) else 0
                    if prev_t == 6 and cur_t != 6:
                        by_kind_idx[key] = p

                # InParam 0: Int
                sig0 = _make_pin_sig(kind_int=3, index_int=0)
                pin0 = by_kind_idx.get((3, 0))
                if not isinstance(pin0, dict):
                    pin0 = {"1": dict(sig0), "2": dict(sig0)}
                    by_kind_idx[(3, 0)] = pin0
                # 真源对齐：控制表达式端口在 NodeEditorPack 中为 R<T>（反射端口）。
                # 即使具体类型是 Int，也需要 ConcreteBase(field_110) 才能让编辑器不显示“泛型”。
                inner_int = build_var_base_message_server_empty(var_type_int=3)
                pin0["3"] = _wrap_var_base_as_concrete_base(
                    inner=inner_int,
                    index_of_concrete=infer_index_of_concrete_for_generic_pin(
                        node_title="多分支",
                        port_name="控制表达式",
                        is_input=True,
                        var_type_int=3,
                        node_type_id_int=3,
                        pin_index=0,
                    ),
                )
                pin0["4"] = 3

                # InParam 1: IntList with length = cases_count (use zeros)
                sig1 = _make_pin_sig(kind_int=3, index_int=1)
                pin1 = by_kind_idx.get((3, 1))
                if not isinstance(pin1, dict):
                    pin1 = {"1": dict(sig1), "2": dict(sig1)}
                    by_kind_idx[(3, 1)] = pin1
                # 真源对齐：cases 列表的内容会直接决定编辑器显示的 Case 出口标签。
                # 例如若写成 [0, 0]，两个出口都会显示 0（用户反馈）。
                #
                # 这里按复合节点的虚拟流程出口推断 case 值：
                # - 默认分支不在 cases 列表中（通常为“默认/其他”或最后一个出口）；
                # - 对形如 “分支为0/分支为1” 的出口名，提取末尾数字作为 case 值；
                # - 推断失败时回退为 0..N-1，并保证去重。
                import re

                outflow_pins = [
                    p
                    for p in list(virtual_pins_sorted)
                    if bool(getattr(p, "is_flow", False)) and (not bool(getattr(p, "is_input", False)))
                ]
                outflow_names = [str(getattr(p, "pin_name", "") or "").strip() for p in outflow_pins]
                outflow_names = [n for n in outflow_names if n]

                def _is_default_name(name: str) -> bool:
                    t = str(name or "").strip()
                    return (t == "默认") or ("默认" in t) or (t == "分支为其他") or (t == "其他") or ("其他" in t)

                non_default_names = [n for n in outflow_names if not _is_default_name(n)]
                if len(non_default_names) < int(cases_count) and outflow_names:
                    # 若未能显式识别默认分支，回退：把最后一个出口当作默认
                    non_default_names = list(outflow_names[:-1])

                wanted_names = non_default_names[: int(cases_count)]
                inferred: list[int] = []
                for idx0, name in enumerate(wanted_names):
                    if str(name).isdigit():
                        inferred.append(int(name))
                        continue
                    m = re.search(r"(-?\d+)\s*$", str(name))
                    if m:
                        inferred.append(int(m.group(1)))
                        continue
                    inferred.append(int(idx0))

                # 保证长度与去重（避免出现 [0,0] 这种重复 label）
                while len(inferred) < int(cases_count):
                    inferred.append(int(len(inferred)))
                seen_vals: set[int] = set()
                for i, v in enumerate(list(inferred)):
                    if int(v) in seen_vals:
                        nxt = 0
                        while nxt in seen_vals:
                            nxt += 1
                        inferred[i] = int(nxt)
                    seen_vals.add(int(inferred[i]))

                inner_list = build_var_base_message_server(var_type_int=8, value=[int(x) for x in inferred[: int(cases_count)]])
                pin1["3"] = _wrap_var_base_as_concrete_base(inner=inner_list, index_of_concrete=None)
                pin1["4"] = 8

                # 写回 pins 列表（保持原有 flow pins、其余 pins）
                kept: List[Dict[str, Any]] = []
                seen_keys: set[Tuple[int, int]] = set()
                for p in list(pins):
                    if not isinstance(p, dict):
                        continue
                    sig = p.get("1")
                    if not isinstance(sig, dict):
                        continue
                    k = int(sig.get("1") or 0)
                    idx = int(sig.get("2") or 0)
                    key = (k, idx)
                    if key in {(3, 0), (3, 1)}:
                        continue
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    kept.append(p)
                kept.append(by_kind_idx[(3, 0)])
                kept.append(by_kind_idx[(3, 1)])
                node_inst["4"] = kept

        composite_graph_unit: Dict[str, Any] = {
            "1": {"2": 5, "4": int(composite_graph_id_int)},
            "5": 9,
            "13": dict(node_graph_container),
        }

        node_interface = _build_composite_node_interface_message(
            composite_id=str(composite_id),
            node_def_id_int=int(node_def_id_int),
            composite_graph_id_int=int(composite_graph_id_int),
            node_name=str(node_name),
            node_description=str(node_desc),
            virtual_pins=virtual_pins_sorted,
        )
        node_interface_unit: Dict[str, Any] = {
            "1": {"2": 23, "4": int(node_def_id_int)},
            "2": [{"2": 5, "4": int(composite_graph_id_int)}],
            "3": str(node_name),
            "5": 12,
            "14": {"1": {"1": dict(node_interface)}},
        }

        dependency_units.append(node_interface_unit)
        dependency_units.append(composite_graph_unit)
        related_ids.append({"2": 23, "4": int(node_def_id_int)})

    return list(dependency_units), list(related_ids)

