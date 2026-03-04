from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from ugc_file_tools.gil.graph_variable_scanner import scan_gil_file_graph_variables
from ugc_file_tools.graph.node_graph.pos_scale import ensure_positive_finite_node_pos_scale
from ugc_file_tools.node_graph_writeback.writer import write_graph_model_to_gil
from ugc_file_tools.output_paths import resolve_output_dir_path_in_out_dir, resolve_output_file_path_in_out_dir

from .export_graph_model import export_graph_model_json_from_graph_code_with_context
from .gg_context import _prepare_graph_generater_context, _resolve_graph_generater_root
from .constants import CLIENT_SCOPE_MASK, SCOPE_MASK, SERVER_SCOPE_MASK
from .specs import (
    _build_graph_specs,
    _build_graph_specs_by_scanning_roots,
    _build_overview_object_by_scanning_node_graph_dir,
    _extract_graph_id_int_from_graph_key,
    _pick_template_graph_id_int,
    _select_explicit_graph_specs,
)
from .types import NodeGraphsImportOptions
from .ui_scan import _collect_required_ui_keys_from_graph_code_files, _infer_required_ui_layout_names_from_graph_code_files


def import_node_graphs_from_project_archive_to_gil(
    *,
    project_archive_path: Path,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    server_template_gil_file_path: Path,
    server_template_library_dir: Path,
    client_template_gil_file_path: Path,
    client_template_library_dir: Path,
    mapping_json_path: Path,
    options: NodeGraphsImportOptions,
) -> Dict[str, Any]:
    from engine.graph.graph_code_parser import GraphParseError

    project_path = Path(project_archive_path).resolve()
    input_path = Path(input_gil_file_path).resolve()
    if not project_path.is_dir():
        raise FileNotFoundError(str(project_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    package_id = str(project_path.name).strip()
    if not package_id:
        raise ValueError("package_id 不能为空（项目存档目录名为空）")

    scope = str(options.scope or "").strip().lower() or "all"
    if scope not in {"all", "server", "client"}:
        raise ValueError(f"unsupported scope: {scope!r}")

    include_server = scope in {"all", "server"}
    include_client = scope in {"all", "client"}

    mapping_path = Path(mapping_json_path).resolve()
    if not mapping_path.is_file():
        raise FileNotFoundError(str(mapping_path))

    if include_server:
        server_template_gil = Path(server_template_gil_file_path).resolve()
        if not server_template_gil.is_file():
            raise FileNotFoundError(str(server_template_gil))
        server_template_dir = Path(server_template_library_dir).resolve()
        if not server_template_dir.is_dir():
            raise FileNotFoundError(str(server_template_dir))
    else:
        server_template_gil = Path("")
        server_template_dir = Path("")

    if include_client:
        client_template_gil = Path(client_template_gil_file_path).resolve()
        if not client_template_gil.is_file():
            raise FileNotFoundError(str(client_template_gil))
        client_template_dir = Path(client_template_library_dir).resolve()
        if not client_template_dir.is_dir():
            raise FileNotFoundError(str(client_template_dir))
    else:
        client_template_gil = Path("")
        client_template_dir = Path("")

    gg_root = _resolve_graph_generater_root(project_path)

    # ===== 同名节点图冲突策略（可选；导出中心透传）=====
    resolution_by_graph_code_file: Dict[str, Dict[str, str]] = {}
    skip_graph_code_files_casefold: set[str] = set()
    raw_conflicts = getattr(options, "node_graph_conflict_resolutions", None)
    if raw_conflicts is not None:
        if not isinstance(raw_conflicts, list):
            raise TypeError("node_graph_conflict_resolutions must be list[dict[str,str]] or None")
        for idx, item in enumerate(list(raw_conflicts)):
            if not isinstance(item, dict):
                raise TypeError(f"node_graph_conflict_resolutions[{idx}] must be dict")
            graph_code_file = str(item.get("graph_code_file") or "").strip()
            if graph_code_file == "":
                raise ValueError(f"node_graph_conflict_resolutions[{idx}].graph_code_file 不能为空")
            p = Path(graph_code_file)
            if not p.is_absolute():
                raise ValueError(
                    f"node_graph_conflict_resolutions[{idx}].graph_code_file must be absolute path: {graph_code_file!r}"
                )
            resolved = p.resolve()
            action = str(item.get("action") or "").strip().lower()
            if action not in {"overwrite", "add", "skip"}:
                raise ValueError(
                    f"node_graph_conflict_resolutions[{idx}].action 仅支持 overwrite/add/skip，实际为：{action!r}"
                )
            new_graph_name = str(item.get("new_graph_name") or "").strip()
            if action == "add" and new_graph_name == "":
                raise ValueError(f"node_graph_conflict_resolutions[{idx}] action=add 时 new_graph_name 不能为空")
            key = str(resolved).casefold()
            if key in resolution_by_graph_code_file:
                raise ValueError(
                    "node_graph_conflict_resolutions 中存在重复 graph_code_file（忽略大小写）："
                    f"{str(resolved)!r}"
                )
            res: Dict[str, str] = {"graph_code_file": str(resolved), "action": str(action)}
            if action == "add":
                res["new_graph_name"] = str(new_graph_name)
            resolution_by_graph_code_file[key] = res
            if action == "skip":
                skip_graph_code_files_casefold.add(key)

    selected_ui_export_record_id = str(getattr(options, "ui_export_record_id", "") or "").strip()
    selected_ui_guid_registry_snapshot_path: Path | None = None
    if selected_ui_export_record_id.lower() == "latest":
        from ugc_file_tools.ui.export_records import load_ui_export_records

        recs = load_ui_export_records(workspace_root=Path(gg_root).resolve(), package_id=str(package_id))
        if not recs:
            raise ValueError(
                "ui_export_record_id='latest' 但当前项目不存在任何 UI 导出记录。\n"
                f"- package_id: {str(package_id)!r}\n"
                "解决方案：先从网页导出一次 GIL（会自动生成记录），或留空使用当前 registry。"
            )
        required_layout_names: set[str] = set()
        required_ui_keys: set[str] = set()
        explicit_graph_code_files = [Path(p).resolve() for p in list(getattr(options, "graph_code_files", None) or []) if p is not None]
        if skip_graph_code_files_casefold:
            explicit_graph_code_files = [
                p for p in explicit_graph_code_files if str(p).casefold() not in skip_graph_code_files_casefold
            ]
        if explicit_graph_code_files:
            required_layout_names = _infer_required_ui_layout_names_from_graph_code_files(graph_code_files=explicit_graph_code_files)
            required_ui_keys = _collect_required_ui_keys_from_graph_code_files(graph_code_files=explicit_graph_code_files)

        # `latest` 的工程化含义（更贴近用户心智）：
        # - 优先选择“最新且 snapshot 内确实包含本次写回会用到的 ui_key”的导出记录；
        # - 若无法做到全覆盖，则退化为“覆盖率最高”的记录；
        # - 最后兜底才回退到 recs[0]（纯时间最新）。
        if required_ui_keys:
            from ugc_file_tools.ui.export_records import load_ui_guid_registry_snapshot

            want_keys = set(required_ui_keys)
            best_record_id: str | None = None
            best_covered: int = -1

            for r in recs:
                snap_path_text = str((r.payload.get("ui_guid_registry_snapshot_path") or "") if isinstance(r.payload, dict) else "").strip()
                if snap_path_text == "":
                    continue
                snap_path = Path(snap_path_text).resolve()
                if not snap_path.is_file():
                    continue
                mapping = load_ui_guid_registry_snapshot(Path(snap_path))
                covered = len(want_keys & set(mapping.keys()))
                if covered == len(want_keys):
                    best_record_id = str(r.record_id)
                    break
                if covered > best_covered:
                    best_covered = int(covered)
                    best_record_id = str(r.record_id)

            selected_ui_export_record_id = str(best_record_id or recs[0].record_id)
        elif required_layout_names:
            best_record_id: str | None = None
            best_score: int = -1
            want = set(required_layout_names)

            for r in recs:
                extra = r.payload.get("extra") if isinstance(r.payload, dict) else None
                layout_names_raw = extra.get("layout_names") if isinstance(extra, dict) else None
                layout_names = (
                    {str(x).strip() for x in list(layout_names_raw or []) if isinstance(x, str) and str(x).strip() != ""}
                    if isinstance(layout_names_raw, list)
                    else set()
                )
                score = len(want & layout_names) if layout_names else 0
                if score == len(want):
                    best_record_id = str(r.record_id)
                    break
                if score > best_score:
                    best_score = int(score)
                    best_record_id = str(r.record_id)
            selected_ui_export_record_id = str(best_record_id or recs[0].record_id)
        else:
            selected_ui_export_record_id = str(recs[0].record_id)
    if selected_ui_export_record_id != "":
        from ugc_file_tools.ui.export_records import try_get_ui_export_record_by_id

        rec = try_get_ui_export_record_by_id(
            workspace_root=Path(gg_root).resolve(),
            package_id=str(package_id),
            record_id=str(selected_ui_export_record_id),
        )
        if rec is None:
            raise ValueError(
                "未找到指定的 UI 导出记录（record_id 不存在或已被清理）。\n"
                f"- record_id: {selected_ui_export_record_id!r}\n"
                "解决方案：重新从网页导出一次 GIL 以生成记录，或改为留空使用当前 registry。"
            )
        snap_path_text = str(rec.payload.get("ui_guid_registry_snapshot_path") or "").strip()
        if snap_path_text == "":
            raise ValueError(f"UI 导出记录缺少 snapshot 路径：record_id={selected_ui_export_record_id!r}")
        snap_path = Path(snap_path_text).resolve()
        if not snap_path.is_file():
            raise FileNotFoundError(str(snap_path))
        selected_ui_guid_registry_snapshot_path = Path(snap_path).resolve()

    # 构造 overview：默认扫描全部节点图源码（更符合“项目导出全量”的预期）
    explicit_files = [Path(p).resolve() for p in list(getattr(options, "graph_code_files", None) or []) if p is not None]
    explicit_files = [p for p in explicit_files if str(p)]
    if explicit_files:
        roots = [Path(project_path).resolve()]
        extra_roots = [Path(p).resolve() for p in list(getattr(options, "graph_source_roots", None) or []) if p is not None]
        for r in extra_roots:
            if r not in roots:
                roots.append(r)

        all_specs = _build_graph_specs_by_scanning_roots(
            graph_source_roots=roots,
            include_server=bool(include_server),
            include_client=bool(include_client),
            strict_graph_code_files=bool(options.strict_graph_code_files),
        )
        specs = _select_explicit_graph_specs(all_specs=all_specs, explicit_files=explicit_files)
    else:
        if bool(options.scan_all):
            overview_object = _build_overview_object_by_scanning_node_graph_dir(package_root=project_path)
        else:
            overview_json = (project_path / f"{package_id}总览.json").resolve()
            if not overview_json.is_file():
                raise FileNotFoundError(f"overview_json 不存在：{str(overview_json)}")
            overview_object = json.loads(overview_json.read_text(encoding="utf-8"))
            if not isinstance(overview_object, dict):
                raise TypeError("overview_json root must be dict")

        specs = _build_graph_specs(
            package_root=project_path,
            overview_object=overview_object,
            include_server=bool(include_server),
            include_client=bool(include_client),
            strict_graph_code_files=bool(options.strict_graph_code_files),
        )
    if not specs:
        return {
            "project_archive": str(project_path),
            "input_gil": str(input_path),
            "output_gil": str(resolve_output_file_path_in_out_dir(Path(output_gil_file_path))),
            "graph_generater_root": str(gg_root),
            "ui_export_record_id": str(selected_ui_export_record_id or ""),
            "ui_guid_registry_snapshot_path": (
                str(selected_ui_guid_registry_snapshot_path)
                if selected_ui_guid_registry_snapshot_path is not None
                else ""
            ),
            "graphs_total": 0,
            "written_graphs": [],
            "skipped_graphs": [],
            "model_dir": "",
            "summary_json": "",
        }

    gg_ctx = _prepare_graph_generater_context(gg_root=gg_root, package_id=str(package_id))
    from engine.configs.settings import settings as engine_settings

    node_pos_scale = ensure_positive_finite_node_pos_scale(
        value=getattr(engine_settings, "UGC_GIA_NODE_POS_SCALE", 2.0),
        source="settings.UGC_GIA_NODE_POS_SCALE",
    )

    output_gil = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    # 保证输出文件存在：当全部节点图被 skip（冲突策略/strict parse 失败等）时，仍应产出一个可复制的 .gil。
    # - 多段写回时：前序步骤通常已写出 output_gil，此处不应覆盖。
    # - 仅节点图写回/首段写回时：output_gil 可能尚不存在；需要先复制一份 base。
    if not output_gil.is_file():
        output_gil.parent.mkdir(parents=True, exist_ok=True)
        if output_gil.resolve() != input_path.resolve():
            shutil.copy2(input_path, output_gil)
    output_model_dir_name = str(options.output_model_dir_name or "").strip() or f"{package_id}_graph_models"
    model_dir = resolve_output_dir_path_in_out_dir(Path(output_model_dir_name))
    model_dir.mkdir(parents=True, exist_ok=True)

    server_template_graph_id_int = (
        _pick_template_graph_id_int(template_gil=server_template_gil, expected_scope="server") if include_server else -1
    )
    client_template_graph_id_int = (
        _pick_template_graph_id_int(template_gil=client_template_gil, expected_scope="client") if include_client else -1
    )

    current_base = input_path
    existing_scan = scan_gil_file_graph_variables(current_base)
    existing_graph_id_ints: set[int] = {int(g.graph_id_int) for g in existing_scan.graphs}

    # 同名覆盖策略（重要）：以 (scope, graph_name) 为键复用 graph_id_int，避免 server/client 同名时互相覆盖。
    # - base `.gil` 可能同时包含 server/client 两张同名图；此时按 scope 精确匹配。
    # - 仅复用首个同名图的 graph_id_int（同一 scope 下若存在重复 name，则视为“已有歧义”，保持稳定选择）。
    existing_graph_id_int_by_scope_and_name: Dict[str, Dict[str, int]] = {"server": {}, "client": {}}
    for g in existing_scan.graphs:
        name_text = str(g.graph_name or "").strip()
        if name_text == "":
            continue

        graph_id_int = int(g.graph_id_int)
        scope_mask = int(graph_id_int) & int(SCOPE_MASK)
        scope_text = (
            "server"
            if int(scope_mask) == int(SERVER_SCOPE_MASK)
            else ("client" if int(scope_mask) == int(CLIENT_SCOPE_MASK) else "")
        )
        if scope_text == "":
            continue
        if name_text not in existing_graph_id_int_by_scope_and_name[scope_text]:
            existing_graph_id_int_by_scope_and_name[scope_text][name_text] = int(graph_id_int)
    reports: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    preloaded_ui_key_to_guid_for_writeback: dict[str, int] | None = None
    raw_preloaded = getattr(options, "ui_key_to_guid_for_writeback", None)
    if isinstance(raw_preloaded, dict) and raw_preloaded:
        cleaned: dict[str, int] = {}
        for k, v in raw_preloaded.items():
            key = str(k or "").strip()
            if key == "":
                continue
            if not isinstance(v, int) or int(v) <= 0:
                continue
            cleaned[key] = int(v)
        preloaded_ui_key_to_guid_for_writeback = cleaned if cleaned else None

    # `--ui-export-record` 支持：当不写回 UI 时，节点图写回阶段仍需要一份 ui_key→guid 映射来回填 `ui_key:` 占位符。
    # 由于 node_graph_writeback 阶段默认仅从 base `.gil` 的 UI records 反查（base 可能不包含完整 UI 记录），
    # 因此这里将 UI 导出记录绑定的 snapshot 映射合并进 preloaded 映射（不覆盖已有键）。
    ui_export_snapshot_mapping: dict[str, int] | None = None
    if selected_ui_guid_registry_snapshot_path is not None:
        from ugc_file_tools.ui.export_records import load_ui_guid_registry_snapshot

        ui_export_snapshot_mapping = load_ui_guid_registry_snapshot(Path(selected_ui_guid_registry_snapshot_path))

    effective_ui_key_to_guid_for_writeback: dict[str, int] | None = None
    merged_ui_key_map: dict[str, int] = dict(preloaded_ui_key_to_guid_for_writeback or {})
    if ui_export_snapshot_mapping:
        for k, v in ui_export_snapshot_mapping.items():
            key = str(k or "").strip()
            if key == "":
                continue
            if key in merged_ui_key_map:
                continue
            if not isinstance(v, int) or int(v) <= 0:
                continue
            merged_ui_key_map[key] = int(v)
    effective_ui_key_to_guid_for_writeback = merged_ui_key_map if merged_ui_key_map else None

    # ===== entity_key/component_key 占位符参考映射（从参考 `.gil` 抽取）=====
    id_ref_path = getattr(options, "id_ref_gil_file", None)
    effective_id_ref_gil: Path
    if id_ref_path is None:
        effective_id_ref_gil = Path(input_gil_file_path).resolve()
    else:
        effective_id_ref_gil = Path(id_ref_path).resolve()

    from ugc_file_tools.id_ref_from_gil import build_id_ref_mappings_from_gil_file

    extracted_component_name_to_id, extracted_entity_name_to_guid = build_id_ref_mappings_from_gil_file(
        gil_file_path=Path(effective_id_ref_gil),
    )
    preloaded_component_name_to_id: dict[str, int] | None = extracted_component_name_to_id or None
    preloaded_entity_name_to_guid: dict[str, int] | None = extracted_entity_name_to_guid or None

    # 可选：导出中心“手动覆盖”映射（占位符 name → ID）。
    id_ref_overrides_path = getattr(options, "id_ref_overrides_json_file", None)
    if id_ref_overrides_path is not None:
        from ugc_file_tools.id_ref_overrides import apply_id_ref_overrides, load_id_ref_overrides_json_file

        overrides = load_id_ref_overrides_json_file(Path(id_ref_overrides_path))
        preloaded_component_name_to_id, preloaded_entity_name_to_guid = apply_id_ref_overrides(
            component_name_to_id=preloaded_component_name_to_id,
            entity_name_to_guid=preloaded_entity_name_to_guid,
            overrides=overrides,
        )

    for spec in specs:
        scope_text = str(spec.scope)
        template_gil = server_template_gil if scope_text == "server" else client_template_gil
        template_library_dir = server_template_dir if scope_text == "server" else client_template_dir
        template_graph_id_int = server_template_graph_id_int if scope_text == "server" else client_template_graph_id_int

        graph_model_json_path = model_dir / f"{scope_text}_{int(spec.assigned_graph_id_int)}_{spec.graph_code_file.stem}.graph_model.json"
        # conflict resolution（按 graph_code_file 精确匹配；skip 可避免无谓导出 GraphModel）
        resolution = resolution_by_graph_code_file.get(str(Path(spec.graph_code_file).resolve()).casefold())
        action = (
            str(resolution.get("action") or "overwrite").strip().lower()
            if isinstance(resolution, dict)
            else "overwrite"
        )
        if action == "skip":
            skipped.append(
                {
                    "scope": scope_text,
                    "graph_key": str(spec.graph_key),
                    "graph_name": str(spec.graph_name_hint or ""),
                    "graph_code_file": str(spec.graph_code_file),
                    "requested_graph_id_int": int(spec.assigned_graph_id_int),
                    "reason": "skipped by node_graph_conflict_resolutions",
                }
            )
            continue

        try:
            export_report = export_graph_model_json_from_graph_code_with_context(
                ctx=gg_ctx,
                graph_code_file=spec.graph_code_file,
                output_json_file=graph_model_json_path,
                ui_export_record_id=(str(selected_ui_export_record_id) if selected_ui_export_record_id != "" else None),
                ui_guid_registry_snapshot_path=(
                    Path(selected_ui_guid_registry_snapshot_path)
                    if selected_ui_guid_registry_snapshot_path is not None
                    else None
                ),
                node_pos_scale=float(node_pos_scale),
            )
        except GraphParseError as e:
            # 导出中心：单图 strict 解析失败不应阻断整体写回；跳过并在 report.skipped_graphs 中体现。
            skipped.append(
                {
                    "scope": scope_text,
                    "graph_key": str(spec.graph_key),
                    "graph_name": str(spec.graph_name_hint or ""),
                    "graph_code_file": str(spec.graph_code_file),
                    "requested_graph_id_int": int(spec.assigned_graph_id_int),
                    "reason": "strict parse failed; skipped",
                    "error": str(e),
                }
            )
            continue
        graph_name_for_match = str(export_report.get("graph_name") or spec.graph_name_hint or "").strip()
        new_graph_name_for_write = str(export_report.get("graph_name") or spec.graph_name_hint or spec.graph_key)

        if action == "add":
            override_name = str(resolution.get("new_graph_name") or "").strip() if isinstance(resolution, dict) else ""
            if override_name == "":
                raise ValueError(
                    "node_graph_conflict_resolutions action=add 缺少 new_graph_name："
                    f"graph_code_file={str(spec.graph_code_file)!r}"
                )
            graph_name_for_match = str(override_name)
            new_graph_name_for_write = str(override_name)

        requested_graph_id_int = int(spec.assigned_graph_id_int)
        reserved_graph_id_int = _extract_graph_id_int_from_graph_key(str(spec.graph_key))
        if action == "add":
            # add 语义：写入为新图，允许分配新 graph_id_int；因此不再视为“保留 id”。
            reserved_graph_id_int = None
        existing_same_name_graph_id_int = None
        if graph_name_for_match != "":
            existing_same_name_graph_id_int = existing_graph_id_int_by_scope_and_name.get(scope_text, {}).get(
                graph_name_for_match
            )
        if action == "add" and isinstance(existing_same_name_graph_id_int, int):
            raise ValueError(
                "新增节点图名与目标 gil 已存在同名图冲突："
                f"scope={scope_text!r}, new_graph_name={graph_name_for_match!r}, existing_graph_id_int={int(existing_same_name_graph_id_int)}"
            )
        reuse_existing_graph_id_by_name = isinstance(existing_same_name_graph_id_int, int)

        # merge 语义：若 graph_key 显式携带 graph_id_int 且目标已存在，则视为“同一图已在存档中”，直接跳过（避免写出重复 id）。
        # 对“扫描生成但不携带 graph_id_int”的新图：若发生 id 冲突，则改为自动分配一个可用的新 graph_id_int。
        requested_graph_id_for_write: Optional[int]
        if isinstance(existing_same_name_graph_id_int, int):
            # 基底已有同名图：优先复用其 graph_id_int，并在写回层执行“同 id 替换”。
            requested_graph_id_for_write = int(existing_same_name_graph_id_int)
        else:
            requested_graph_id_for_write = int(requested_graph_id_int)
        conflict = int(requested_graph_id_for_write) in existing_graph_id_ints
        if conflict:
            if bool(reuse_existing_graph_id_by_name):
                # 同名复用：冲突即预期行为（将由写回层执行替换），不跳过。
                pass
            elif reserved_graph_id_int is not None:
                skipped.append(
                    {
                        "scope": scope_text,
                        "graph_key": str(spec.graph_key),
                        "graph_name": str(graph_name_for_match),
                        "graph_code_file": str(spec.graph_code_file),
                        "requested_graph_id_int": int(requested_graph_id_int),
                        "reason": "target already has same graph_id_int; skipped to avoid duplicate id",
                    }
                )
                continue
            else:
                requested_graph_id_for_write = None

        write_report = write_graph_model_to_gil(
            graph_model_json_path=Path(export_report["output_json"]),
            template_gil_path=template_gil,
            base_gil_path=current_base,
            template_library_dir=template_library_dir,
            output_gil_path=output_gil,
            template_graph_id_int=int(template_graph_id_int),
            new_graph_name=str(new_graph_name_for_write),
            new_graph_id_int=(int(requested_graph_id_for_write) if requested_graph_id_for_write is not None else None),
            mapping_path=mapping_path,
            graph_generater_root=gg_root,
            preloaded_ui_key_to_guid_for_writeback=effective_ui_key_to_guid_for_writeback,
            preloaded_component_name_to_id=preloaded_component_name_to_id,
            preloaded_entity_name_to_guid=preloaded_entity_name_to_guid,
            prefer_signal_specific_type_id=bool(getattr(options, "prefer_signal_specific_type_id", False)),
        )

        written_graph_id_int = int(write_report.get("new_graph_id_int"))
        existing_graph_id_ints.add(int(written_graph_id_int))
        if graph_name_for_match != "" and scope_text in existing_graph_id_int_by_scope_and_name:
            existing_graph_id_int_by_scope_and_name[scope_text][str(graph_name_for_match)] = int(written_graph_id_int)

        reports.append(
            {
                "scope": scope_text,
                "graph_key": str(spec.graph_key),
                "graph_name": str(graph_name_for_match),
                "graph_code_file": str(spec.graph_code_file),
                "graph_model_json": str(export_report.get("output_json") or ""),
                "requested_graph_id_int": int(requested_graph_id_int),
                "existing_same_name_graph_id_int": (
                    int(existing_same_name_graph_id_int) if isinstance(existing_same_name_graph_id_int, int) else None
                ),
                "reuse_existing_graph_id_by_name": bool(reuse_existing_graph_id_by_name),
                "requested_graph_id_for_write": (
                    int(requested_graph_id_for_write) if isinstance(requested_graph_id_for_write, int) else None
                ),
                "written_graph_id_int": int(written_graph_id_int),
                "write_report": dict(write_report),
            }
        )
        current_base = output_gil

    summary_path = resolve_output_file_path_in_out_dir(model_dir / "writeback_summary.json")
    summary_path.write_text(
        json.dumps(
            {
                "project_archive": str(project_path),
                "input_gil": str(input_path),
                "output_gil": str(output_gil),
                "graph_generater_root": str(gg_root),
                "mapping_json": str(mapping_path),
                "node_pos_scale": float(node_pos_scale),
                "ui_export_record_id": str(selected_ui_export_record_id or ""),
                "ui_guid_registry_snapshot_path": (
                    str(selected_ui_guid_registry_snapshot_path)
                    if selected_ui_guid_registry_snapshot_path is not None
                    else ""
                ),
                "server_template_gil": str(server_template_gil) if include_server else "",
                "client_template_gil": str(client_template_gil) if include_client else "",
                "server_template_graph_id_int": int(server_template_graph_id_int) if include_server else -1,
                "client_template_graph_id_int": int(client_template_graph_id_int) if include_client else -1,
                "graphs_total": int(len(specs)),
                "written_graphs": reports,
                "skipped_graphs": skipped,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "project_archive": str(project_path),
        "input_gil": str(input_path),
        "output_gil": str(output_gil),
        "graph_generater_root": str(gg_root),
        "mapping_json": str(mapping_path),
        "node_pos_scale": float(node_pos_scale),
        "ui_export_record_id": str(selected_ui_export_record_id or ""),
        "ui_guid_registry_snapshot_path": (
            str(selected_ui_guid_registry_snapshot_path)
            if selected_ui_guid_registry_snapshot_path is not None
            else ""
        ),
        "server_template_gil": str(server_template_gil) if include_server else "",
        "client_template_gil": str(client_template_gil) if include_client else "",
        "server_template_graph_id_int": int(server_template_graph_id_int) if include_server else -1,
        "client_template_graph_id_int": int(client_template_graph_id_int) if include_client else -1,
        "graphs_total": int(len(specs)),
        "written_graphs": reports,
        "skipped_graphs": skipped,
        "model_dir": str(model_dir),
        "summary_json": str(summary_path),
    }

