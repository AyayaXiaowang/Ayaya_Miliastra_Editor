from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from ugc_file_tools.fs_naming import sanitize_file_stem
from ugc_file_tools.graph.node_graph.pos_scale import ensure_positive_finite_node_pos_scale
from ugc_file_tools.graph.port_type_gap_report import build_port_type_gap_report
from ugc_file_tools.graph.port_types import standardize_graph_model_payload_inplace
from ugc_file_tools.output_paths import resolve_output_dir_path_in_out_dir
from ugc_file_tools.ui.guid_registry import collect_ui_key_placeholders_from_graph_json_object

from .bundle_sidecars import _copy_dir_tree, _export_bundle_sidecars
from .graph_specs import _GraphExportSpec, _build_graph_specs_by_scanning_roots, _infer_resource_class_from_graph_code_file
from .id_ref_placeholders import resolve_id_ref_placeholders_for_graph
from .layout_index import LayoutIndexAutoFiller
from .pack import pack_gia_files_to_single
from .signal_bundle import build_per_graph_signal_bundle
from .signals_collect import _collect_used_signal_specs_from_graph_payload
from .types import ProgressCallback, ProjectExportGiaPlan, _emit_progress
from .ui_export_context import build_ui_export_context
from .ui_placeholders import resolve_ui_key_placeholders_for_graph


def run_project_export_to_gia(
    *,
    plan: ProjectExportGiaPlan,
    progress_cb: ProgressCallback | None = None,
) -> Dict[str, object]:
    project_root = Path(plan.project_archive_path).resolve()
    if not project_root.is_dir():
        raise FileNotFoundError(str(project_root))

    package_id = str(project_root.name).strip()
    if package_id == "":
        raise ValueError("package_id 不能为空（项目存档目录名为空）")

    # 复合节点/资源索引等依赖运行期 active_package_id（进程内全局作用域）。
    # 导出链路属于“按当前项目存档导出”，因此在进入扫描/解析前显式设置，避免串包或漏扫。
    from engine.utils.runtime_scope import set_active_package_id

    set_active_package_id(str(package_id))

    scope = str(plan.graphs_scope or "").strip().lower() or "all"
    if scope not in {"all", "server", "client"}:
        raise ValueError(f"unsupported graphs_scope: {scope!r}")

    include_server = scope in {"all", "server"}
    include_client = scope in {"all", "client"}

    # 节点坐标缩放：fail-fast 校验（避免生成 NaN/Inf 或 <=0 的坐标导致真源编辑器异常）
    node_pos_scale = ensure_positive_finite_node_pos_scale(
        value=plan.node_pos_scale,
        source="node_pos_scale",
    )

    id_ref_gil_file = Path(plan.id_ref_gil_file).resolve() if plan.id_ref_gil_file is not None else None
    if id_ref_gil_file is not None and not id_ref_gil_file.is_file():
        raise FileNotFoundError(str(id_ref_gil_file))

    id_ref_overrides_json_file = (
        Path(plan.id_ref_overrides_json_file).resolve() if plan.id_ref_overrides_json_file is not None else None
    )
    if id_ref_overrides_json_file is not None and not id_ref_overrides_json_file.is_file():
        raise FileNotFoundError(str(id_ref_overrides_json_file))

    from ugc_file_tools.id_ref_overrides import IdRefOverrides, load_id_ref_overrides_json_file

    id_ref_overrides: IdRefOverrides | None = None
    if id_ref_overrides_json_file is not None:
        id_ref_overrides = load_id_ref_overrides_json_file(Path(id_ref_overrides_json_file))

    from ugc_file_tools.writeback_defaults import default_node_graph_mapping_json_path

    mapping_path = Path(plan.node_type_semantic_map_json).resolve() if plan.node_type_semantic_map_json else default_node_graph_mapping_json_path()
    if not Path(mapping_path).is_file():
        raise FileNotFoundError(str(Path(mapping_path).resolve()))

    # 复用“节点图写回”侧的扫描与 GraphModel 导出能力（同一口径最稳）
    from ugc_file_tools.project_archive_importer.node_graphs_importer import (
        build_overview_object_by_scanning_node_graph_dir as _build_overview_object_by_scanning_node_graph_dir,
        export_graph_model_json_from_graph_code_with_context as _export_graph_model_json_from_graph_code_with_context,
        prepare_graph_generater_context as _prepare_graph_generater_context,
        resolve_graph_generater_root as _resolve_graph_generater_root,
    )

    gg_root = _resolve_graph_generater_root(project_root)

    # UI 导出记录/registry snapshot/output_gil UI records 索引
    ui_ctx = build_ui_export_context(plan=plan, gg_root=Path(gg_root).resolve(), package_id=str(package_id))
    record_id_text = str(ui_ctx.record_id_text)

    # === specs 构建 ===
    explicit_files = [Path(p).resolve() for p in list(plan.graph_code_files or []) if p is not None]
    explicit_files = [p for p in explicit_files if str(p)]

    if explicit_files:
        roots = [Path(project_root).resolve()]
        extra_roots = [Path(p).resolve() for p in list(plan.graph_source_roots or []) if p is not None]
        for r in extra_roots:
            if r not in roots:
                roots.append(r)

        all_specs = _build_graph_specs_by_scanning_roots(
            graph_source_roots=roots,
            include_server=bool(include_server),
            include_client=bool(include_client),
            strict_graph_code_files=False,
        )
        by_file = {Path(s.graph_code_file).resolve(): s for s in all_specs}
        missing = [str(p) for p in explicit_files if Path(p).resolve() not in by_file]
        if missing:
            raise ValueError(
                "显式导出的 graph_code_files 中包含无法识别为节点图的文件（缺少 graph_id metadata 或不在扫描根下）："
                f"{missing}"
            )
        specs = [by_file[Path(p).resolve()] for p in explicit_files]
    else:
        if bool(plan.graph_scan_all):
            overview_object = _build_overview_object_by_scanning_node_graph_dir(package_root=project_root)
        else:
            overview_json = (project_root / f"{package_id}总览.json").resolve()
            if not overview_json.is_file():
                raise FileNotFoundError(f"overview_json 不存在：{str(overview_json)}")
            overview_object = json.loads(overview_json.read_text(encoding="utf-8"))
            if not isinstance(overview_object, dict):
                raise TypeError("overview_json root must be dict")

        # 兼容旧行为：默认仅导出当前项目存档根下的节点图
        from ugc_file_tools.project_archive_importer.node_graphs_importer import build_graph_specs as _build_graph_specs

        raw_specs = _build_graph_specs(
            package_root=project_root,
            overview_object=overview_object,
            include_server=bool(include_server),
            include_client=bool(include_client),
            strict_graph_code_files=False,
        )
        # NOTE:
        # - node_graphs_importer.build_graph_specs 返回的是其内部 _GraphSpec（实现拆分区的 dataclass）；
        # - 本 pipeline 统一使用本域的 _GraphExportSpec，避免跨域类型对象被当作“非同一类型”触发 isinstance 失败。
        specs: list[_GraphExportSpec] = []
        for s in list(raw_specs or []):
            scope0 = getattr(s, "scope", None)
            graph_key0 = getattr(s, "graph_key", None)
            graph_name_hint0 = getattr(s, "graph_name_hint", None)
            graph_code_file0 = getattr(s, "graph_code_file", None)
            assigned_id0 = getattr(s, "assigned_graph_id_int", None)
            if not isinstance(scope0, str) or not isinstance(graph_key0, str) or not isinstance(graph_name_hint0, str) or not isinstance(graph_code_file0, Path):
                raise TypeError(f"invalid graph spec from node_graphs_importer: {type(s)!r} ({s!r})")
            if not isinstance(assigned_id0, int) or int(assigned_id0) <= 0:
                raise TypeError(f"invalid graph spec assigned_graph_id_int: {assigned_id0!r} ({s!r})")
            specs.append(
                _GraphExportSpec(
                    scope=str(scope0),
                    graph_key=str(graph_key0),
                    graph_name_hint=str(graph_name_hint0),
                    graph_code_file=Path(graph_code_file0),
                    assigned_graph_id_int=int(assigned_id0),
                )
            )

    selected_keys = [str(x or "").strip() for x in list(plan.graph_keys or [])]
    selected_keys = [x for x in selected_keys if x]
    if selected_keys:
        wanted = set(selected_keys)
        specs = [s for s in specs if str(s.graph_key) in wanted]
        found = {str(s.graph_key) for s in specs}
        missing = sorted(wanted - found, key=lambda text: text.casefold())
        if missing:
            raise ValueError(
                "未找到指定节点图（可能是共享节点图、或不在当前项目存档的 节点图 目录下）："
                f"{missing}"
            )

    default_out_name = f"{package_id}_gia_bundle" if bool(plan.bundle_enabled) else f"{package_id}_gia_export"
    output_dir_name = str(plan.output_dir_name_in_out or "").strip() or default_out_name
    output_dir = resolve_output_dir_path_in_out_dir(Path(output_dir_name))
    output_dir.mkdir(parents=True, exist_ok=True)

    # GraphModel(JSON) 是导出中间产物：不应落在 out（out 仅放“可直接给游戏使用的 .gia/.gil”）。
    # 这里将中间 JSON 缓存到“项目存档/管理配置”下，确保与当前项目（及其 HTML UI）紧密绑定。
    model_dir = (project_root / "管理配置" / "导出缓存" / "graph_models" / output_dir_name).resolve()
    model_dir.mkdir(parents=True, exist_ok=True)

    graphs_dir = output_dir / "graphs"
    graphs_dir.mkdir(parents=True, exist_ok=True)

    user_dir: Optional[Path] = None
    if plan.output_user_dir is not None:
        user_dir = Path(plan.output_user_dir).resolve()
        if not user_dir.is_absolute():
            raise ValueError("output_user_dir 必须是绝对路径（用于复制导出产物）")
        user_dir.mkdir(parents=True, exist_ok=True)

    inject_enabled = plan.inject_target_gil_file is not None
    pack_enabled = bool(plan.pack_graphs_to_single_gia) and int(len(specs)) >= 2
    parse_steps = int(len(specs))
    export_steps = int(len(specs))
    inject_steps = int(len(specs)) if bool(inject_enabled) else 0
    pack_steps = 1 if bool(pack_enabled) else 0
    total_steps = int(parse_steps + export_steps + inject_steps + pack_steps)
    _emit_progress(
        progress_cb,
        0,
        total_steps,
        "准备导出 .gia…"
        + ("（含注入）" if inject_enabled else "")
        + ("（含打包）" if pack_enabled else ""),
    )

    if not specs:
        return {
            "project_archive": str(project_root),
            "graphs_total": 0,
            "output_dir": str(output_dir),
            "graphs_dir": str(graphs_dir),
            "model_dir": str(model_dir),
            "exported_graphs": [],
            "copied_to_user_dir": str(user_dir) if user_dir is not None else "",
        }

    gg_ctx = _prepare_graph_generater_context(gg_root=Path(gg_root), package_id=str(package_id))

    from ugc_file_tools.gia_export.node_graph.asset_bundle_builder import (
        GiaAssetBundleGraphExportHints,
        create_gia_file_from_graph_model_json,
    )
    from ugc_file_tools.node_graph_semantics.type_id_map import build_node_def_key_to_type_id
    from ugc_file_tools.node_graph_semantics.var_base import (
        set_component_id_registry,
        set_entity_id_registry,
        set_ui_key_guid_registry,
    )
    from ugc_file_tools.component_id_registry import collect_component_key_placeholders_from_graph_json_object
    from ugc_file_tools.entity_id_registry import collect_entity_key_placeholders_from_graph_json_object

    exported: List[Dict[str, object]] = []
    port_type_gap_reports: List[Dict[str, object]] = []
    port_type_gap_summary = {"errors": 0, "warnings": 0, "total": 0}

    # === Signals (self-contained, recommended) ===
    # 导出 NodeGraph `.gia` 时把“信号 node_def GraphUnits”一并打包进 dependencies，
    # 从而导入到空存档也能自动展开信号端口/参数（不再依赖 base `.gil` / builtin 映射表）。
    from ugc_file_tools.signal_writeback.gia_export import collect_basic_signal_py_records, parse_signal_payload_to_params
    from ugc_file_tools.signal_writeback.signal_node_def_units_builder import build_signal_node_def_bundle_for_signals

    basic_signal_records = collect_basic_signal_py_records(project_archive_path=Path(project_root))
    signal_params_by_name: dict[str, list[dict[str, object]]] = {}
    for r in list(basic_signal_records):
        name, params = parse_signal_payload_to_params(r.payload)
        signal_params_by_name[str(name)] = [dict(p) for p in list(params)]

    # 复合节点子图内也可能包含信号节点：导出 `.gia` 的“自包含信号”需要递归收集。
    from engine.nodes.composite_node_manager import get_composite_node_manager

    composite_mgr = get_composite_node_manager(workspace_path=Path(gg_root).resolve(), verbose=False)
    composite_loaded: dict[str, object] = {}

    inject_target_gil_file = Path(plan.inject_target_gil_file).resolve() if plan.inject_target_gil_file is not None else None
    inject_backup_once = bool(plan.inject_create_backup)

    layout_filler = LayoutIndexAutoFiller(ui_ctx=ui_ctx)

    # ---------------------------------------------------------------------
    # Pass 1: 解析 GraphModel(JSON) + 收集全量用到的信号规格（跨图共享）
    # ---------------------------------------------------------------------
    graph_work_items: list[dict[str, object]] = []
    signal_specs_by_name: dict[str, dict[str, object]] = {}

    for i, spec in enumerate(specs, start=1):
        _emit_progress(
            progress_cb,
            int(i),
            total_steps,
            f"解析与自动布局节点图（{i}/{len(specs)}）…",
        )

        scope_text = str(spec.scope)
        node_type_id_by_node_def_key = build_node_def_key_to_type_id(
            mapping_path=Path(mapping_path),
            scope=scope_text,
            graph_generater_root=Path(gg_root),
        )
        graph_name = str(spec.graph_name_hint or spec.graph_key or spec.graph_code_file.stem)

        graph_model_json_path = model_dir / f"{scope_text}_{int(spec.assigned_graph_id_int)}_{spec.graph_code_file.stem}.graph_model.json"
        export_report = _export_graph_model_json_from_graph_code_with_context(
            ctx=gg_ctx,
            graph_code_file=spec.graph_code_file,
            output_json_file=graph_model_json_path,
            node_pos_scale=float(node_pos_scale),
        )

        graph_json_object = json.loads(Path(export_report["output_json"]).read_text(encoding="utf-8"))
        if not isinstance(graph_json_object, dict):
            raise TypeError("graph_model_json must be dict")

        graph_model_payload = graph_json_object.get("data")
        used_signal_specs = _collect_used_signal_specs_from_graph_payload(
            graph_payload=graph_model_payload,
            signal_params_by_name=signal_params_by_name,
            composite_mgr=composite_mgr,
            composite_loaded=composite_loaded,
        )
        used_signal_names = {str(x.get("signal_name") or "").strip() for x in used_signal_specs if isinstance(x, dict)} - {""}

        # merge specs by signal_name（同名参数不一致时 fail-fast，避免 silent 串号/断线）
        for ss in list(used_signal_specs):
            if not isinstance(ss, dict):
                continue
            n = str(ss.get("signal_name") or "").strip()
            if n == "":
                continue
            prev = signal_specs_by_name.get(n)
            if prev is None:
                signal_specs_by_name[n] = dict(ss)
                continue
            if prev.get("params") != ss.get("params"):
                raise ValueError(
                    "同名信号在不同节点图中解析出的参数列表不一致，无法构建稳定的自包含信号 bundle。\n"
                    f"- signal_name: {n!r}\n"
                    f"- prev_params: {prev.get('params')!r}\n"
                    f"- new_params: {ss.get('params')!r}\n"
                    f"- graph_code_file: {str(spec.graph_code_file)!r}"
                )

        graph_work_items.append(
            {
                "spec": spec,
                "scope_text": str(scope_text),
                "graph_name": str(graph_name),
                "node_type_id_by_node_def_key": dict(node_type_id_by_node_def_key),
                "export_report": dict(export_report),
                "graph_json_object": dict(graph_json_object),
                "used_signal_names": set(used_signal_names),
            }
        )

    shared_signal_bundle = build_signal_node_def_bundle_for_signals(signals=list(signal_specs_by_name.values())) if signal_specs_by_name else None

    # ---------------------------------------------------------------------
    # Pass 2: 导出 `.gia`（复用共享自包含信号 bundle，确保跨图一致）
    # ---------------------------------------------------------------------
    output_gia_files_for_pack: list[Path] = []

    for i, item in enumerate(graph_work_items, start=1):
        _emit_progress(
            progress_cb,
            int(parse_steps + i),
            total_steps,
            f"导出节点图 .gia（{i}/{len(graph_work_items)}）…",
        )

        spec = item.get("spec")
        if not isinstance(spec, _GraphExportSpec):
            raise TypeError("invalid graph_work_items: spec must be _GraphExportSpec")
        scope_text = str(item.get("scope_text") or spec.scope)
        graph_name = str(item.get("graph_name") or spec.graph_name_hint or spec.graph_key or spec.graph_code_file.stem)

        node_type_id_by_node_def_key = item.get("node_type_id_by_node_def_key")
        if not isinstance(node_type_id_by_node_def_key, dict):
            raise TypeError("invalid graph_work_items: node_type_id_by_node_def_key must be dict")

        export_report = item.get("export_report")
        if not isinstance(export_report, dict):
            raise TypeError("invalid graph_work_items: export_report must be dict")

        graph_json_object = item.get("graph_json_object")
        if not isinstance(graph_json_object, dict):
            raise TypeError("invalid graph_work_items: graph_json_object must be dict")

        used_signal_names = item.get("used_signal_names")
        if not isinstance(used_signal_names, set):
            raise TypeError("invalid graph_work_items: used_signal_names must be set[str]")

        per_graph_signal_ctx = build_per_graph_signal_bundle(
            shared_signal_bundle=shared_signal_bundle,
            used_signal_names=set(used_signal_names),
        )

        # === UIKey→GUID（用于节点图中 ui_key: 占位符的“编译期回填”） ===
        placeholders = collect_ui_key_placeholders_from_graph_json_object(graph_json_object=graph_json_object)
        resolved_ui = resolve_ui_key_placeholders_for_graph(
            placeholders=set(placeholders),
            graph_code_file=Path(spec.graph_code_file),
            ui_ctx=ui_ctx,
            allow_unresolved_ui_keys=bool(plan.allow_unresolved_ui_keys),
        )

        implicit_unresolved_ui_keys = list(resolved_ui.implicit_unresolved_ui_keys)
        allow_unresolved_effective = bool(resolved_ui.allow_unresolved_effective)
        effective_ui_key_to_guid = resolved_ui.effective_ui_key_to_guid

        if placeholders:
            set_ui_key_guid_registry(effective_ui_key_to_guid, allow_unresolved=bool(allow_unresolved_effective))
        else:
            set_ui_key_guid_registry(None, allow_unresolved=False)

        # === entity_key/component_key（用于节点图中对实体/元件 ID 的“编译期回填”）===
        required_component_names = collect_component_key_placeholders_from_graph_json_object(graph_json_object=graph_json_object)
        required_entity_names = collect_entity_key_placeholders_from_graph_json_object(graph_json_object=graph_json_object)

        resolved_id_ref = resolve_id_ref_placeholders_for_graph(
            required_component_names=set(required_component_names),
            required_entity_names=set(required_entity_names),
            id_ref_gil_file=Path(id_ref_gil_file).resolve() if id_ref_gil_file is not None else None,
            id_ref_overrides=id_ref_overrides,
        )

        set_component_id_registry(
            resolved_id_ref.component_name_to_id,
            allow_unresolved=bool(resolved_id_ref.allow_unresolved_id_ref_placeholders),
        )
        set_entity_id_registry(
            resolved_id_ref.entity_name_to_guid,
            allow_unresolved=bool(resolved_id_ref.allow_unresolved_id_ref_placeholders),
        )

        # === LayoutIndex 回填：布局索引类 GraphVariables（例如 “布局索引_选关页”） ===
        graph_variables_layout_index_auto_filled = layout_filler.autofill_graph_variables_layout_index(
            graph_json_object=graph_json_object,
        )

        # === GraphModel 标准化 + 端口类型缺口报告（导出入口落盘 report，显性化“不确定”）===
        graph_model_payload = graph_json_object.get("data")
        if not isinstance(graph_model_payload, dict):
            raise TypeError("graph_model payload must be dict (expected graph_json_object['data'])")

        outer_graph_variables = graph_json_object.get("graph_variables")
        graph_variables_for_inject = list(outer_graph_variables) if isinstance(outer_graph_variables, list) else None

        standardize_graph_model_payload_inplace(
            graph_model_payload=graph_model_payload,
            graph_variables=graph_variables_for_inject,
            workspace_root=Path(gg_root).resolve(),
            scope=str(scope_text),
            force_reenrich=True,
            fill_missing_edge_ids=True,
        )

        gap_report = build_port_type_gap_report(
            graph_model_payload=dict(graph_model_payload),
            graph_scope=str(scope_text),
            graph_name=str(graph_name),
            graph_id_int=int(spec.assigned_graph_id_int),
        )
        gap_report_file = ""
        if isinstance(gap_report, dict) and isinstance(gap_report.get("counts"), dict):
            counts = dict(gap_report.get("counts") or {})
            total = int(counts.get("total") or 0)
            err_count = int(counts.get("errors") or 0)
            warn_count = int(counts.get("warnings") or 0)

            if total > 0:
                report_dir = (Path(output_dir) / "reports" / "port_type_gaps").resolve()
                report_dir.mkdir(parents=True, exist_ok=True)
                safe_stem2 = sanitize_file_stem(str(graph_name))
                report_path = (report_dir / f"{str(scope_text)}__{int(spec.assigned_graph_id_int)}__{safe_stem2}.json").resolve()
                report_path.write_text(json.dumps(gap_report, ensure_ascii=False, indent=2), encoding="utf-8")
                gap_report_file = str(report_path)

                port_type_gap_reports.append(
                    {
                        "scope": str(scope_text),
                        "graph_id_int": int(spec.assigned_graph_id_int),
                        "graph_name": str(graph_name),
                        "report_file": str(report_path),
                        "counts": {"errors": int(err_count), "warnings": int(warn_count), "total": int(total)},
                    }
                )
                port_type_gap_summary["errors"] = int(port_type_gap_summary["errors"]) + int(err_count)
                port_type_gap_summary["warnings"] = int(port_type_gap_summary["warnings"]) + int(warn_count)
                port_type_gap_summary["total"] = int(port_type_gap_summary["total"]) + int(total)

                # fail-fast：存在任何缺口（非流程端口 effective 仍为泛型家族）直接抛错，禁止继续导出写坏存档。
                if total > 0:
                    first_items: list[str] = []
                    items = gap_report.get("items")
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
                        "端口类型缺口报告非空（导出禁止继续）："
                        f"graph={str(graph_name)!r} scope={str(scope_text)!r} total={int(total)} errors={int(err_count)} warnings={int(warn_count)} "
                        f"report_file={str(gap_report_file)!r} first={first_items!r}"
                    )

        resource_class = _infer_resource_class_from_graph_code_file(graph_code_file=Path(spec.graph_code_file), scope=scope_text)

        safe_stem = sanitize_file_stem(str(graph_name))
        output_gia_rel = Path(output_dir.name) / "graphs" / f"{safe_stem}.gia"
        write_result = create_gia_file_from_graph_model_json(
            graph_json_object=graph_json_object,
            hints=GiaAssetBundleGraphExportHints(
                graph_id_int=int(spec.assigned_graph_id_int),
                graph_name=str(graph_name),
                graph_scope=str(scope_text),
                resource_class=str(resource_class),
                graph_generater_root=Path(gg_root),
                node_type_id_by_node_def_key=dict(node_type_id_by_node_def_key),
                export_uid=0,
                game_version=str(graph_json_object.get("engine_version") or graph_json_object.get("game_version") or "6.3.0"),
                node_pos_scale=float(node_pos_scale),
                signal_send_node_def_id_by_signal_name=dict(per_graph_signal_ctx.get("signal_send_node_def_id_by_signal_name") or {})
                if per_graph_signal_ctx.get("signal_send_node_def_id_by_signal_name")
                else None,
                signal_send_signal_name_port_index_by_signal_name=dict(
                    per_graph_signal_ctx.get("signal_send_signal_name_port_index_by_signal_name") or {}
                )
                if per_graph_signal_ctx.get("signal_send_signal_name_port_index_by_signal_name")
                else None,
                signal_send_param_port_indices_by_signal_name=dict(per_graph_signal_ctx.get("signal_send_param_port_indices_by_signal_name") or {})
                if per_graph_signal_ctx.get("signal_send_param_port_indices_by_signal_name")
                else None,
                signal_send_param_var_type_ids_by_signal_name=dict(per_graph_signal_ctx.get("signal_send_param_var_type_ids_by_signal_name") or {})
                if per_graph_signal_ctx.get("signal_send_param_var_type_ids_by_signal_name")
                else None,
                listen_node_def_id_by_signal_name=dict(per_graph_signal_ctx.get("listen_node_def_id_by_signal_name") or {})
                if per_graph_signal_ctx.get("listen_node_def_id_by_signal_name")
                else None,
                listen_signal_name_port_index_by_signal_name=dict(per_graph_signal_ctx.get("listen_signal_name_port_index_by_signal_name") or {})
                if per_graph_signal_ctx.get("listen_signal_name_port_index_by_signal_name")
                else None,
                listen_param_port_indices_by_signal_name=dict(per_graph_signal_ctx.get("listen_param_port_indices_by_signal_name") or {})
                if per_graph_signal_ctx.get("listen_param_port_indices_by_signal_name")
                else None,
                extra_dependency_graph_units=list(per_graph_signal_ctx.get("extra_dependency_graph_units") or [])
                if per_graph_signal_ctx.get("extra_dependency_graph_units")
                else None,
                graph_related_ids=list(per_graph_signal_ctx.get("graph_related_ids") or []) if per_graph_signal_ctx.get("graph_related_ids") else None,
            ),
            output_gia_path=output_gia_rel,
        )
        set_ui_key_guid_registry(None, allow_unresolved=False)
        set_component_id_registry(None, allow_unresolved=False)
        set_entity_id_registry(None, allow_unresolved=False)
        output_gia_file = Path(write_result["output_gia_file"]).resolve()
        output_gia_files_for_pack.append(Path(output_gia_file))

        copied_path = ""
        if user_dir is not None and not bool(plan.bundle_enabled):
            target = (user_dir / output_gia_file.name).resolve()
            shutil.copy2(output_gia_file, target)
            copied_path = str(target)

        inject_report: dict[str, object] = {}
        if inject_enabled:
            from ugc_file_tools.save_patchers.gil_node_graph_injector import inject_gia_into_gil_node_graph

            _emit_progress(
                progress_cb,
                int(parse_steps + export_steps + i),
                total_steps,
                f"注入到 .gil（{i}/{len(graph_work_items)}）…",
            )

            gil_path = inject_target_gil_file
            from ugc_file_tools.beyond_local_maps import find_best_beyond_local_gil_for_node_graph_id, gil_contains_node_graph_id

            if gil_path is None or (gil_path.is_file() and not gil_contains_node_graph_id(gil_path, int(spec.assigned_graph_id_int))):
                best = find_best_beyond_local_gil_for_node_graph_id(int(spec.assigned_graph_id_int))
                if best is None:
                    raise ValueError(
                        "无法在 BeyondLocal 下自动定位包含目标 graph_id 的 .gil。\n"
                        f"- graph_id_int: {int(spec.assigned_graph_id_int)}\n"
                        "请手动选择目标地图 .gil（或先在编辑器内创建并保存对应 graph_id 的节点图）。"
                    )
                gil_path = best

            report_obj = inject_gia_into_gil_node_graph(
                source_gia_file=Path(output_gia_file),
                target_gil_file=Path(gil_path),
                output_gil_file=None,
                target_graph_id_int=int(spec.assigned_graph_id_int),
                check_gia_header=bool(plan.inject_check_gia_header),
                skip_non_empty_check=bool(plan.inject_skip_non_empty_check),
                create_backup=bool(inject_backup_once),
            )
            inject_backup_once = False
            inject_report = {
                "target_gil_file": str(report_obj.target_gil_file),
                "output_gil_file": str(report_obj.output_gil_file),
                "backup_file": str(report_obj.backup_file),
                "old_payload_size": int(report_obj.old_payload_size),
                "new_payload_size": int(report_obj.new_payload_size),
            }

        exported.append(
            {
                "scope": scope_text,
                "graph_id_int": int(spec.assigned_graph_id_int),
                "graph_name": str(graph_name),
                "resource_class": str(resource_class),
                "graph_code_file": str(spec.graph_code_file),
                "graph_model_json": str(export_report.get("output_json") or ""),
                "output_gia_file": str(output_gia_file),
                "copied_output_gia_file": str(copied_path),
                "port_type_gap_report_file": str(gap_report_file),
                "ui_export_record_id": (str(record_id_text) if ui_ctx.selected_ui_export_record is not None else ""),
                "ui_key_placeholders_total": int(len(placeholders)),
                "ui_key_placeholders_implicit_unresolved": list(implicit_unresolved_ui_keys),
                "ui_key_allow_unresolved_effective": bool(allow_unresolved_effective),
                "id_ref_gil_file": str(id_ref_gil_file) if id_ref_gil_file is not None else "",
                "id_ref_missing_entities": list(resolved_id_ref.missing_id_ref_entities),
                "id_ref_missing_components": list(resolved_id_ref.missing_id_ref_components),
                "id_ref_allow_unresolved_effective": bool(resolved_id_ref.allow_unresolved_id_ref_placeholders),
                "graph_variables_layout_index_auto_filled_total": int(len(graph_variables_layout_index_auto_filled)),
                "graph_variables_layout_index_auto_filled": list(graph_variables_layout_index_auto_filled),
                "injection": dict(inject_report),
            }
        )

    # pack：合并成单个 .gia（Root.field_1 为 GraphUnit 列表；field_2 为 dependencies）
    pack_output_gia_file: Path | None = None
    pack_copied_output_gia_file: Path | None = None
    if bool(pack_enabled):
        _emit_progress(
            progress_cb,
            int(parse_steps + export_steps + inject_steps + 1),
            total_steps,
            "打包为单个 .gia…",
        )

        pack_output_gia_file = pack_gia_files_to_single(
            output_gia_files_for_pack=list(output_gia_files_for_pack),
            graphs_dir=Path(graphs_dir).resolve(),
            package_id=str(package_id),
            pack_output_gia_file_name=str(plan.pack_output_gia_file_name or ""),
        )

        if user_dir is not None and not bool(plan.bundle_enabled):
            target = (user_dir / pack_output_gia_file.name).resolve()
            shutil.copy2(pack_output_gia_file, target)
            pack_copied_output_gia_file = Path(target)

    bundle_copied_items: dict[str, str] = {}
    copied_to_user_dir = str(user_dir) if user_dir is not None else ""

    if bool(plan.bundle_enabled):
        bundle_copied_items = _export_bundle_sidecars(
            project_root=project_root,
            output_dir=output_dir,
            include_signals=bool(plan.bundle_include_signals),
            include_ui_guid_registry=bool(plan.bundle_include_ui_guid_registry),
            workspace_root=Path(gg_root).resolve(),
            package_id=str(package_id),
            ui_key_to_guid_registry=(
                dict(ui_ctx.ui_key_to_guid_registry)
                if ui_ctx.selected_ui_export_record is not None and ui_ctx.ui_key_to_guid_registry
                else None
            ),
        )

        if user_dir is not None:
            # bundle 模式：复制整个输出目录到用户目录下同名子目录
            bundle_target = (user_dir / output_dir.name).resolve()
            _copy_dir_tree(src_dir=output_dir, dst_dir=bundle_target)
            copied_to_user_dir = str(bundle_target)

    return {
        "project_archive": str(project_root),
        "graphs_total": int(len(specs)),
        "output_dir": str(output_dir),
        "graphs_dir": str(graphs_dir),
        "model_dir": str(model_dir),
        "node_type_semantic_map_json": str(Path(mapping_path).resolve()),
        "port_type_gap_report_dir": str((Path(output_dir) / "reports" / "port_type_gaps").resolve()),
        "port_type_gap_summary": dict(port_type_gap_summary),
        "port_type_gap_reports": list(port_type_gap_reports),
        "ui_export_record_id": (str(record_id_text) if ui_ctx.selected_ui_export_record is not None else ""),
        "allow_unresolved_ui_keys": bool(plan.allow_unresolved_ui_keys),
        "bundle_enabled": bool(plan.bundle_enabled),
        "bundle_include_signals": bool(plan.bundle_include_signals),
        "bundle_include_ui_guid_registry": bool(plan.bundle_include_ui_guid_registry),
        "pack_enabled": bool(pack_enabled),
        "pack_output_gia_file": str(pack_output_gia_file) if pack_output_gia_file is not None else "",
        "pack_copied_output_gia_file": str(pack_copied_output_gia_file) if pack_copied_output_gia_file is not None else "",
        "inject_enabled": bool(inject_enabled),
        "inject_target_gil_file": str(inject_target_gil_file) if inject_target_gil_file is not None else "",
        "inject_check_gia_header": bool(plan.inject_check_gia_header),
        "inject_skip_non_empty_check": bool(plan.inject_skip_non_empty_check),
        "inject_create_backup": bool(plan.inject_create_backup),
        "bundle_copied_items": dict(bundle_copied_items),
        "exported_graphs": exported,
        "copied_to_user_dir": str(copied_to_user_dir),
    }

