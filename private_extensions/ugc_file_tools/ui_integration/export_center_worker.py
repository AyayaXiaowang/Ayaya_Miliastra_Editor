from __future__ import annotations

from pathlib import Path

from .export_center.plans import _ExportGiaPlan, _ExportGilPlan, _MergeSignalEntriesPlan, _RepairSignalsPlan


def make_export_center_worker_cls(*, QtCore: object):
    """
    延迟定义 QThread（避免模块顶层 import PyQt6）。
    """

    class _Worker(QtCore.QThread):  # type: ignore[misc]
        progress_changed = QtCore.pyqtSignal(int, int, str)  # current, total, label
        succeeded = QtCore.pyqtSignal(dict)  # report
        failed = QtCore.pyqtSignal(str)  # message

        def __init__(
            self,
            *,
            plan: object,
            workspace_root: Path,
            package_id: str,
            fmt: str,
            parent: object | None = None,
        ) -> None:
            super().__init__(parent)
            self._plan = plan
            self._workspace_root = Path(workspace_root).resolve()
            self._package_id = str(package_id)
            self._fmt = str(fmt)
            self.setObjectName(f"ExportCenterWorker:{self._package_id}:{self._fmt}")

        def run(self) -> None:
            import json
            from uuid import uuid4

            from ._cli_subprocess import build_run_ugc_file_tools_command, run_cli_with_progress

            out_dir = (Path(self._workspace_root).resolve() / "private_extensions" / "ugc_file_tools" / "out").resolve()
            tmp_dir = (out_dir / "_tmp_cli").resolve()
            tmp_dir.mkdir(parents=True, exist_ok=True)

            def _maybe_write_id_ref_overrides_json() -> Path | None:
                """
                将导出中心“手动覆盖的 entity_key/component_key 映射”落盘为临时 JSON，供子进程读取。

                返回：
                - overrides_json_path（若无覆盖则为 None）
                """
                comp_over = getattr(self._plan, "id_ref_override_component_name_to_id", None)
                ent_over = getattr(self._plan, "id_ref_override_entity_name_to_guid", None)

                comp_map: dict[str, int] = {}
                if isinstance(comp_over, dict):
                    for k, v in comp_over.items():
                        key = str(k or "").strip()
                        if key == "":
                            continue
                        if not isinstance(v, int) or int(v) <= 0:
                            continue
                        comp_map[key] = int(v)

                ent_map: dict[str, int] = {}
                if isinstance(ent_over, dict):
                    for k, v in ent_over.items():
                        key = str(k or "").strip()
                        if key == "":
                            continue
                        if not isinstance(v, int) or int(v) <= 0:
                            continue
                        ent_map[key] = int(v)

                if not comp_map and not ent_map:
                    return None

                overrides_file = (tmp_dir / f"id_ref_overrides_{uuid4().hex[:10]}.json").resolve()
                overrides_file.write_text(
                    json.dumps(
                        {
                            "version": 1,
                            "component_name_to_id": dict(comp_map),
                            "entity_name_to_guid": dict(ent_map),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                return Path(overrides_file)

            id_ref_overrides_json = _maybe_write_id_ref_overrides_json()

            if isinstance(self._plan, _RepairSignalsPlan):
                graphs_report_file = (tmp_dir / f"export_graphs_report_fixsig_{uuid4().hex[:10]}.json").resolve()
                out_dir_name = f"{self._plan.package_id}_fixsig_{uuid4().hex[:8]}"

                argv_graphs: list[str] = [
                    "tool",
                    "export_project_graphs_to_gia",
                    "--project-root",
                    str(Path(self._plan.project_root).resolve()),
                    "--scope",
                    "all",
                    "--node-pos-scale",
                    "2.0",
                    "--out-dir",
                    str(out_dir_name),
                    "--report",
                    str(graphs_report_file),
                    "--allow-unresolved-ui-keys",
                ]
                for p in list(self._plan.selected_graph_code_files):
                    argv_graphs.extend(["--graph-code", str(Path(p).resolve())])
                for r in list(self._plan.graph_source_roots):
                    argv_graphs.extend(["--graph-source-root", str(Path(r).resolve())])

                command = build_run_ugc_file_tools_command(workspace_root=Path(self._workspace_root), argv=argv_graphs)
                result = run_cli_with_progress(
                    command=command,
                    cwd=Path(self._workspace_root),
                    on_progress=lambda current, total, label: self.progress_changed.emit(
                        int(current), int(total), f"导出GIA（用于修复信号）：{label}"
                    ),
                    stderr_tail_max_lines=240,
                )
                if int(result.exit_code) != 0:
                    tail = [str(x) for x in list(result.stderr_tail)[-80:] if str(x).strip() != ""]
                    tail_text = "\n".join(tail) if tail else "(stderr 为空)"
                    self.failed.emit(f"修复信号失败（导出GIA阶段）：退出码={int(result.exit_code)}\n\n{tail_text}")
                    return
                if not graphs_report_file.is_file():
                    raise FileNotFoundError(str(graphs_report_file))
                graphs_report = json.loads(graphs_report_file.read_text(encoding="utf-8"))
                if not isinstance(graphs_report, dict):
                    raise TypeError("graphs export report must be dict")

                repair_report_file = (tmp_dir / f"repair_signals_report_{uuid4().hex[:10]}.json").resolve()
                self.progress_changed.emit(0, 1, "修复信号：执行…")

                argv_repair: list[str] = [
                    "tool",
                    "--dangerous",
                    "repair_gil_signals_from_export_report",
                    str(Path(self._plan.input_gil_path).resolve()),
                    str(Path(self._plan.output_gil_path).resolve()),
                    "--export-report",
                    str(graphs_report_file),
                    "--report",
                    str(repair_report_file),
                ]
                if not bool(self._plan.prune_placeholder_orphans):
                    argv_repair.append("--no-prune-placeholder-orphans")

                command2 = build_run_ugc_file_tools_command(workspace_root=Path(self._workspace_root), argv=argv_repair)
                result2 = run_cli_with_progress(
                    command=command2,
                    cwd=Path(self._workspace_root),
                    on_progress=None,
                    stderr_tail_max_lines=240,
                )
                if int(result2.exit_code) != 0:
                    tail = [str(x) for x in list(result2.stderr_tail)[-80:] if str(x).strip() != ""]
                    tail_text = "\n".join(tail) if tail else "(stderr 为空)"
                    self.failed.emit(f"修复信号失败：退出码={int(result2.exit_code)}\n\n{tail_text}")
                    return

                if not repair_report_file.is_file():
                    raise FileNotFoundError(str(repair_report_file))
                repair_report = json.loads(repair_report_file.read_text(encoding="utf-8"))
                if not isinstance(repair_report, dict):
                    raise TypeError("repair report must be dict")

                self.succeeded.emit(
                    {
                        "format": "repair_signals",
                        "plan": {
                            "package_id": self._plan.package_id,
                            "input_gil": str(self._plan.input_gil_path),
                            "output_gil": str(self._plan.output_gil_path),
                            "graphs_total": int(len(self._plan.selected_graph_code_files)),
                        },
                        "graphs_export": dict(graphs_report),
                        "report": dict(repair_report),
                    }
                )
                return

            if isinstance(self._plan, _MergeSignalEntriesPlan):
                from ._cli_subprocess import build_run_ugc_file_tools_command, run_cli_with_progress

                merge_report_file = (tmp_dir / f"merge_signal_entries_report_{uuid4().hex[:10]}.json").resolve()
                self.progress_changed.emit(0, 1, "合并信号条目：执行…")

                argv_merge: list[str] = [
                    "tool",
                    "--dangerous",
                    "merge_gil_signal_entries",
                    str(Path(self._plan.input_gil_path).resolve()),
                    str(Path(self._plan.output_gil_path).resolve()),
                    "--keep-signal-name",
                    str(self._plan.keep_signal_name),
                    "--remove-signal-name",
                    str(self._plan.remove_signal_name),
                    "--report",
                    str(merge_report_file),
                ]
                if str(self._plan.rename_keep_to or "").strip():
                    argv_merge.extend(["--rename-keep-to", str(self._plan.rename_keep_to)])
                if not bool(self._plan.patch_composite_pin_index):
                    argv_merge.append("--no-patch-composite-pin-index")

                command_merge = build_run_ugc_file_tools_command(workspace_root=Path(self._workspace_root), argv=argv_merge)
                result_merge = run_cli_with_progress(
                    command=command_merge,
                    cwd=Path(self._workspace_root),
                    on_progress=None,
                    stderr_tail_max_lines=240,
                )
                if int(result_merge.exit_code) != 0:
                    tail = [str(x) for x in list(result_merge.stderr_tail)[-80:] if str(x).strip() != ""]
                    tail_text = "\n".join(tail) if tail else "(stderr 为空)"
                    self.failed.emit(f"合并信号条目失败：退出码={int(result_merge.exit_code)}\n\n{tail_text}")
                    return

                if not merge_report_file.is_file():
                    raise FileNotFoundError(str(merge_report_file))
                merge_report = json.loads(merge_report_file.read_text(encoding="utf-8"))
                if not isinstance(merge_report, dict):
                    raise TypeError("merge report must be dict")

                self.succeeded.emit(
                    {
                        "format": "merge_signal_entries",
                        "plan": {
                            "package_id": self._plan.package_id,
                            "input_gil": str(self._plan.input_gil_path),
                            "output_gil": str(self._plan.output_gil_path),
                            "keep_signal_name": str(self._plan.keep_signal_name),
                            "remove_signal_name": str(self._plan.remove_signal_name),
                            "rename_keep_to": str(self._plan.rename_keep_to),
                            "patch_composite_pin_index": bool(self._plan.patch_composite_pin_index),
                        },
                        "report": dict(merge_report),
                    }
                )
                return

            if isinstance(self._plan, _ExportGilPlan):
                selection_file = (tmp_dir / f"writeback_selection_{uuid4().hex[:10]}.json").resolve()
                report_file = (tmp_dir / f"writeback_report_{uuid4().hex[:10]}.json").resolve()
                selection_manifest = {
                    "selected_struct_ids": [str(x) for x in list(self._plan.selected_struct_ids)],
                    "selected_ingame_struct_ids": [str(x) for x in list(self._plan.selected_ingame_struct_ids)],
                    "selected_signal_ids": [str(x) for x in list(self._plan.selected_signal_ids)],
                    "selected_custom_variable_refs": [dict(x) for x in list(self._plan.selected_custom_variable_refs)],
                    "selected_level_custom_variable_ids": [str(x) for x in list(self._plan.selected_level_custom_variable_ids)],
                    "selected_graph_code_files": [str(Path(p).resolve()) for p in list(self._plan.selected_graph_code_files)],
                    "selected_template_json_files": [str(Path(p).resolve()) for p in list(self._plan.selected_template_json_files)],
                    "selected_instance_json_files": [str(Path(p).resolve()) for p in list(self._plan.selected_instance_json_files)],
                    "graph_source_roots": [str(Path(p).resolve()) for p in list(self._plan.graph_source_roots)],
                    "write_ui": bool(self._plan.write_ui),
                    "ui_auto_sync_custom_variables": bool(self._plan.ui_auto_sync_custom_variables),
                    "ui_layout_conflict_resolutions": list(self._plan.ui_layout_conflict_resolutions),
                    "node_graph_conflict_resolutions": list(self._plan.node_graph_conflict_resolutions),
                    "template_conflict_resolutions": list(self._plan.template_conflict_resolutions),
                    "instance_conflict_resolutions": list(self._plan.instance_conflict_resolutions),
                    "prefer_signal_specific_type_id": bool(self._plan.prefer_signal_specific_type_id),
                }
                selected_ui_layout_names = [str(Path(p).stem).strip() for p in list(self._plan.selected_ui_html_files or [])]
                selected_ui_layout_names = [x for x in selected_ui_layout_names if x]
                if selected_ui_layout_names:
                    # 仅当用户明确勾选了 UI源码（HTML）页面时，才收窄 UI 写回范围；
                    # 否则 `write_ui=true` 将按项目存档内的全部 Workbench bundle 写回。
                    selection_manifest["selected_ui_layout_names"] = list(selected_ui_layout_names)
                selection_file.write_text(
                    json.dumps(selection_manifest, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                # --- 导出前：UI源码 HTML → Workbench bundle（写入 UI源码/__workbench_out__/） ---
                if self._plan.ui_workbench_bundle_update_html_files:
                    argv_update_ui: list[str] = [
                        "tool",
                        "export_ui_workbench_bundles_from_html",
                        "--project-root",
                        str(Path(self._plan.project_root).resolve()),
                        "--pc-canvas-size",
                        "1920x1080",
                    ]
                    for p in list(self._plan.ui_workbench_bundle_update_html_files):
                        argv_update_ui.extend(["--html", str(Path(p).resolve())])

                    command_ui = build_run_ugc_file_tools_command(
                        workspace_root=Path(self._workspace_root),
                        argv=argv_update_ui,
                    )
                    result_ui = run_cli_with_progress(
                        command=command_ui,
                        cwd=Path(self._workspace_root),
                        on_progress=lambda current, total, label: self.progress_changed.emit(
                            int(current),
                            int(total),
                            f"更新UI bundle：{label}",
                        ),
                        stderr_tail_max_lines=240,
                    )
                    if int(result_ui.exit_code) != 0:
                        tail = [str(x) for x in list(result_ui.stderr_tail)[-80:] if str(x).strip() != ""]
                        tail_text = "\n".join(tail) if tail else "(stderr 为空)"
                        self.failed.emit(f"导出失败（更新UI bundle）：子进程退出码={int(result_ui.exit_code)}\n\n{tail_text}")
                        return

                argv: list[str] = [
                    "project",
                    "import",
                    "--dangerous",
                    "--project-archive",
                    str(Path(self._plan.project_root).resolve()),
                    "--mode",
                    str(self._plan.struct_mode),
                    "--templates-mode",
                    str(self._plan.templates_mode),
                    "--instances-mode",
                    str(self._plan.instances_mode),
                    "--signals-param-build-mode",
                    str(self._plan.signals_param_build_mode),
                    "--ui-widget-templates-mode",
                    str(self._plan.ui_widget_templates_mode),
                    "--selection-json",
                    str(selection_file),
                    "--report",
                    str(report_file),
                    str(Path(self._plan.input_gil_path).resolve()),
                    str(self._plan.output_user_path),
                ]
                if self._plan.ui_export_record_id is not None:
                    argv.extend(["--ui-export-record", str(self._plan.ui_export_record_id)])
                if self._plan.id_ref_gil_file is not None:
                    argv.extend(["--id-ref-gil", str(Path(self._plan.id_ref_gil_file).resolve())])
                if id_ref_overrides_json is not None:
                    argv.extend(["--id-ref-overrides-json", str(Path(id_ref_overrides_json).resolve())])

                command = build_run_ugc_file_tools_command(workspace_root=Path(self._workspace_root), argv=argv)
                result = run_cli_with_progress(
                    command=command,
                    cwd=Path(self._workspace_root),
                    on_progress=lambda current, total, label: self.progress_changed.emit(int(current), int(total), str(label)),
                    stderr_tail_max_lines=240,
                )
                if int(result.exit_code) != 0:
                    tail = [str(x) for x in list(result.stderr_tail)[-80:] if str(x).strip() != ""]
                    tail_text = "\n".join(tail) if tail else "(stderr 为空)"
                    self.failed.emit(f"导出失败：子进程退出码={int(result.exit_code)}\n\n{tail_text}")
                    return

                if not report_file.is_file():
                    raise FileNotFoundError(str(report_file))
                report = json.loads(report_file.read_text(encoding="utf-8"))
                if not isinstance(report, dict):
                    raise TypeError("writeback report must be dict")
                self.succeeded.emit(
                    {
                        "format": "gil",
                        "plan": {
                            "package_id": self._plan.package_id,
                            "input_gil": str(self._plan.input_gil_path),
                            "output_user": str(self._plan.output_user_path),
                        },
                        "report": dict(report),
                    }
                )
                return

            if not isinstance(self._plan, _ExportGiaPlan):
                raise TypeError("unknown export plan type")

            combined: dict = {"format": "gia", "steps": []}

            # 1) graphs
            graph_sel2 = self._plan.graph_selection
            graph_files = list(getattr(graph_sel2, "graph_code_files", []) or [])
            graph_roots = list(getattr(graph_sel2, "graph_source_roots", []) or [])

            if graph_files:
                report_file = (tmp_dir / f"export_graphs_report_{uuid4().hex[:10]}.json").resolve()
                argv_graphs: list[str] = [
                    "tool",
                    "export_project_graphs_to_gia",
                    "--project-root",
                    str(Path(self._plan.project_root).resolve()),
                    "--scope",
                    "all",
                    "--node-pos-scale",
                    str(float(self._plan.node_pos_scale)),
                    "--out-dir",
                    str(self._plan.output_dir_name_in_out),
                    "--report",
                    str(report_file),
                ]
                for p in list(graph_files):
                    argv_graphs.extend(["--graph-code", str(Path(p).resolve())])
                for r in list(graph_roots):
                    argv_graphs.extend(["--graph-source-root", str(Path(r).resolve())])
                if self._plan.output_user_dir is not None:
                    argv_graphs.extend(["--copy-to", str(Path(self._plan.output_user_dir).resolve())])
                if bool(self._plan.allow_unresolved_ui_keys):
                    argv_graphs.append("--allow-unresolved-ui-keys")
                if self._plan.ui_export_record_id is not None:
                    argv_graphs.extend(["--ui-export-record", str(self._plan.ui_export_record_id)])
                if self._plan.id_ref_gil_file is not None:
                    argv_graphs.extend(["--id-ref-gil", str(Path(self._plan.id_ref_gil_file).resolve())])
                if id_ref_overrides_json is not None:
                    argv_graphs.extend(["--id-ref-overrides-json", str(Path(id_ref_overrides_json).resolve())])
                if bool(self._plan.bundle_enabled):
                    argv_graphs.append("--bundle")
                    if not bool(self._plan.bundle_include_signals):
                        argv_graphs.append("--no-bundle-include-signals")
                    if not bool(self._plan.bundle_include_ui_guid_registry):
                        argv_graphs.append("--no-bundle-include-ui-guid-registry")
                if bool(self._plan.pack_graphs_to_single_gia):
                    argv_graphs.append("--pack")
                    if str(self._plan.pack_output_gia_file_name or "").strip() != "":
                        argv_graphs.extend(["--pack-file-name", str(self._plan.pack_output_gia_file_name)])

                command = build_run_ugc_file_tools_command(workspace_root=Path(self._workspace_root), argv=argv_graphs)
                result = run_cli_with_progress(
                    command=command,
                    cwd=Path(self._workspace_root),
                    on_progress=lambda current, total, label: self.progress_changed.emit(int(current), int(total), f"节点图：{label}"),
                    stderr_tail_max_lines=240,
                )
                if int(result.exit_code) != 0:
                    tail = [str(x) for x in list(result.stderr_tail)[-80:] if str(x).strip() != ""]
                    tail_text = "\n".join(tail) if tail else "(stderr 为空)"
                    self.failed.emit(f"导出失败（节点图）：退出码={int(result.exit_code)}\n\n{tail_text}")
                    return
                if not report_file.is_file():
                    raise FileNotFoundError(str(report_file))
                graphs_report = json.loads(report_file.read_text(encoding="utf-8"))
                if not isinstance(graphs_report, dict):
                    raise TypeError("graphs export report must be dict")
                combined["graphs"] = dict(graphs_report)
                combined["steps"].append("graphs")

            # 2) templates
            if self._plan.template_json_files:
                # 分流：
                # - “模板导出”（语义生成 .gia）：不要求 source（适用于“空模型+自定义变量”等项目内模板）。
                # - “保真切片”（wire-level slice）：仅当模板携带 `metadata.ugc.source_*` 时才可用；
                #   主要用途是把“装饰物实例/实体摆放 instances”一并导出（这些信息不一定能从模板 JSON 可靠重建）。

                def _extract_decorations_count_from_template_obj(obj: object) -> int:
                    if not isinstance(obj, dict):
                        return 0
                    meta = obj.get("metadata")
                    if not isinstance(meta, dict):
                        return 0
                    common_inspector = meta.get("common_inspector") or meta.get("commonInspector")
                    if not isinstance(common_inspector, dict):
                        return 0
                    model = common_inspector.get("model")
                    if not isinstance(model, dict):
                        return 0
                    decorations = model.get("decorations")
                    if not isinstance(decorations, list) or not decorations:
                        return 0
                    return int(len(decorations))

                def _inspect_template_json(p: Path) -> tuple[bool, bool, str]:
                    obj = json.loads(Path(p).read_text(encoding="utf-8"))
                    has_decorations = _extract_decorations_count_from_template_obj(obj) > 0
                    if not isinstance(obj, dict):
                        return False, bool(has_decorations), "模板 JSON 根节点不是 dict"
                    meta = obj.get("metadata")
                    if not isinstance(meta, dict):
                        return False, bool(has_decorations), "模板缺少 metadata"
                    ugc = meta.get("ugc")
                    if not isinstance(ugc, dict):
                        return False, bool(has_decorations), "模板缺少 metadata.ugc"
                    source_gia_file = str(ugc.get("source_gia_file") or "").strip()
                    if source_gia_file == "":
                        return False, bool(has_decorations), "模板缺少 metadata.ugc.source_gia_file"
                    rid = ugc.get("source_template_root_id_int")
                    if not isinstance(rid, int):
                        return False, bool(has_decorations), "模板缺少 metadata.ugc.source_template_root_id_int(int)"
                    return True, bool(has_decorations), ""

                sliceable_files: list[Path] = []
                fallback_files: list[Path] = []
                fallback_reasons: list[dict[str, object]] = []
                for p in list(self._plan.template_json_files):
                    rp = Path(p).resolve()
                    ok, has_decorations, reason = _inspect_template_json(Path(rp))
                    if ok:
                        sliceable_files.append(Path(rp))
                    else:
                        fallback_files.append(Path(rp))
                        fallback_reasons.append(
                            {
                                "template_json": str(rp),
                                "reason": str(reason),
                                "has_decorations": bool(has_decorations),
                            }
                        )

                if fallback_reasons:
                    combined["templates_missing_source_info"] = list(fallback_reasons)

                # 2.1) sliceable → wire-level bundle slice
                if sliceable_files:
                    report_file = (tmp_dir / f"export_templates_instances_bundle_report_{uuid4().hex[:10]}.json").resolve()
                    selection_file = (tmp_dir / f"export_templates_instances_bundle_selection_{uuid4().hex[:10]}.json").resolve()
                    selection_file.write_text(
                        json.dumps([str(Path(p).resolve()) for p in list(sliceable_files)], ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    argv_tpl: list[str] = [
                        "tool",
                        "export_project_templates_instances_bundle_gia",
                        "--project-root",
                        str(Path(self._plan.project_root).resolve()),
                        "--out-dir",
                        str(self._plan.output_dir_name_in_out),
                        "--selection-json",
                        str(selection_file),
                        "--report",
                        str(report_file),
                    ]
                    if self._plan.output_user_dir is not None:
                        argv_tpl.extend(["--copy-to", str(Path(self._plan.output_user_dir).resolve())])
                    command = build_run_ugc_file_tools_command(workspace_root=Path(self._workspace_root), argv=argv_tpl)
                    result = run_cli_with_progress(
                        command=command,
                        cwd=Path(self._workspace_root),
                        on_progress=lambda current, total, label: self.progress_changed.emit(
                            int(current), int(total), f"元件（保真切片）：{label}"
                        ),
                        stderr_tail_max_lines=240,
                    )
                    if int(result.exit_code) != 0:
                        tail = [str(x) for x in list(result.stderr_tail)[-80:] if str(x).strip() != ""]
                        tail_text = "\n".join(tail) if tail else "(stderr 为空)"
                        self.failed.emit(f"导出失败（元件：保真切片）：退出码={int(result.exit_code)}\n\n{tail_text}")
                        return
                    if not report_file.is_file():
                        raise FileNotFoundError(str(report_file))
                    tpl_report = json.loads(report_file.read_text(encoding="utf-8"))
                    if not isinstance(tpl_report, dict):
                        raise TypeError("templates bundle export report must be dict")
                    combined["templates_instances_bundle"] = dict(tpl_report)
                    combined["steps"].append("templates_instances_bundle")

                # 2.2) fallback → export templates to .gia (empty-model)
                if fallback_files:
                    report_file2 = (tmp_dir / f"export_templates_report_{uuid4().hex[:10]}.json").resolve()
                    selection_file2 = (tmp_dir / f"export_templates_selection_{uuid4().hex[:10]}.json").resolve()
                    selection_file2.write_text(
                        json.dumps([str(Path(p).resolve()) for p in list(fallback_files)], ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    argv_tpl2: list[str] = [
                        "tool",
                        "export_project_templates_to_gia",
                        "--project-root",
                        str(Path(self._plan.project_root).resolve()),
                        "--out-dir",
                        str(self._plan.output_dir_name_in_out),
                        "--selection-json",
                        str(selection_file2),
                        "--decode-max-depth",
                        str(int(getattr(self._plan, "template_base_decode_max_depth", 24) or 24)),
                        "--report",
                        str(report_file2),
                    ]
                    base_gia = getattr(self._plan, "base_template_gia_file", None)
                    if base_gia is not None:
                        argv_tpl2.extend(["--base-gia", str(Path(base_gia).resolve())])
                    if self._plan.output_user_dir is not None:
                        argv_tpl2.extend(["--copy-to", str(Path(self._plan.output_user_dir).resolve())])

                    command2 = build_run_ugc_file_tools_command(workspace_root=Path(self._workspace_root), argv=argv_tpl2)
                    result2 = run_cli_with_progress(
                        command=command2,
                        cwd=Path(self._workspace_root),
                        on_progress=lambda current, total, label: self.progress_changed.emit(
                            int(current), int(total), f"元件（模板导出）：{label}"
                        ),
                        stderr_tail_max_lines=240,
                    )
                    if int(result2.exit_code) != 0:
                        tail = [str(x) for x in list(result2.stderr_tail)[-80:] if str(x).strip() != ""]
                        tail_text = "\n".join(tail) if tail else "(stderr 为空)"
                        self.failed.emit(f"导出失败（元件：空模型导出）：退出码={int(result2.exit_code)}\n\n{tail_text}")
                        return
                    if not report_file2.is_file():
                        raise FileNotFoundError(str(report_file2))
                    tpl_report2 = json.loads(report_file2.read_text(encoding="utf-8"))
                    if not isinstance(tpl_report2, dict):
                        raise TypeError("templates export report must be dict")
                    combined["templates"] = dict(tpl_report2)
                    combined["steps"].append("templates")

            # 2.5) player templates (combat presets)
            if getattr(self._plan, "player_template_json_files", None):
                player_template_files = list(getattr(self._plan, "player_template_json_files") or [])
                if player_template_files:
                    base_player_template_gia = getattr(self._plan, "base_player_template_gia_file", None)
                    if base_player_template_gia is None:
                        raise ValueError("base_player_template_gia_file 不能为空：导出玩家模板需要 base .gia")

                    report_file_pt = (tmp_dir / f"export_player_templates_report_{uuid4().hex[:10]}.json").resolve()
                    selection_file_pt = (tmp_dir / f"export_player_templates_selection_{uuid4().hex[:10]}.json").resolve()
                    selection_file_pt.write_text(
                        json.dumps([str(Path(p).resolve()) for p in list(player_template_files)], ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    argv_pt: list[str] = [
                        "tool",
                        "export_project_player_templates_to_gia",
                        "--project-root",
                        str(Path(self._plan.project_root).resolve()),
                        "--base-gia",
                        str(Path(base_player_template_gia).resolve()),
                        "--out-dir",
                        str(self._plan.output_dir_name_in_out),
                        "--selection-json",
                        str(selection_file_pt),
                        "--decode-max-depth",
                        str(int(getattr(self._plan, "player_template_base_decode_max_depth", 16) or 16)),
                        "--report",
                        str(report_file_pt),
                    ]
                    if self._plan.output_user_dir is not None:
                        argv_pt.extend(["--copy-to", str(Path(self._plan.output_user_dir).resolve())])

                    command_pt = build_run_ugc_file_tools_command(workspace_root=Path(self._workspace_root), argv=argv_pt)
                    result_pt = run_cli_with_progress(
                        command=command_pt,
                        cwd=Path(self._workspace_root),
                        on_progress=lambda current, total, label: self.progress_changed.emit(
                            int(current), int(total), f"玩家模板：{label}"
                        ),
                        stderr_tail_max_lines=240,
                    )
                    if int(result_pt.exit_code) != 0:
                        tail = [str(x) for x in list(result_pt.stderr_tail)[-80:] if str(x).strip() != ""]
                        tail_text = "\n".join(tail) if tail else "(stderr 为空)"
                        self.failed.emit(f"导出失败（玩家模板）：退出码={int(result_pt.exit_code)}\n\n{tail_text}")
                        return
                    if not report_file_pt.is_file():
                        raise FileNotFoundError(str(report_file_pt))
                    pt_report = json.loads(report_file_pt.read_text(encoding="utf-8"))
                    if not isinstance(pt_report, dict):
                        raise TypeError("player templates export report must be dict")
                    combined["player_templates"] = dict(pt_report)
                    combined["steps"].append("player_templates")

            # 3) basic structs
            if self._plan.selected_basic_struct_ids:
                out_file = f"{self._plan.output_dir_name_in_out}/structs/{self._plan.package_id}_结构体定义.gia"
                report_file = (tmp_dir / f"export_basic_structs_report_{uuid4().hex[:10]}.json").resolve()
                argv_structs: list[str] = [
                    "tool",
                    "export_basic_structs_to_gia",
                    "--project-archive",
                    str(Path(self._plan.project_root).resolve()),
                    "--output-gia",
                    str(out_file),
                    "--game-version",
                    "6.3.0",
                    "--report",
                    str(report_file),
                ]
                if self._plan.output_user_dir is not None:
                    argv_structs.extend(["--copy-to", str(Path(self._plan.output_user_dir).resolve())])
                for sid in list(self._plan.selected_basic_struct_ids):
                    argv_structs.extend(["--select-struct-id", str(sid)])

                self.progress_changed.emit(0, 1, "结构体：导出…")
                command = build_run_ugc_file_tools_command(workspace_root=Path(self._workspace_root), argv=argv_structs)
                result = run_cli_with_progress(
                    command=command,
                    cwd=Path(self._workspace_root),
                    on_progress=None,
                    stderr_tail_max_lines=240,
                )
                if int(result.exit_code) != 0:
                    tail = [str(x) for x in list(result.stderr_tail)[-80:] if str(x).strip() != ""]
                    tail_text = "\n".join(tail) if tail else "(stderr 为空)"
                    self.failed.emit(f"导出失败（基础结构体）：退出码={int(result.exit_code)}\n\n{tail_text}")
                    return
                if not report_file.is_file():
                    raise FileNotFoundError(str(report_file))
                structs_report = json.loads(report_file.read_text(encoding="utf-8"))
                if not isinstance(structs_report, dict):
                    raise TypeError("basic structs export report must be dict")
                combined["basic_structs"] = dict(structs_report)
                combined["steps"].append("basic_structs")

            # 4) signals
            if self._plan.selected_signal_ids:
                out_file = f"{self._plan.output_dir_name_in_out}/signals/{self._plan.package_id}_信号定义.gia"
                report_file = (tmp_dir / f"export_basic_signals_report_{uuid4().hex[:10]}.json").resolve()
                argv_signals: list[str] = [
                    "tool",
                    "export_basic_signals_to_gia",
                    "--project-archive",
                    str(Path(self._plan.project_root).resolve()),
                    "--output-gia",
                    str(out_file),
                    "--game-version",
                    "6.3.0",
                    "--report",
                    str(report_file),
                ]
                if self._plan.output_user_dir is not None:
                    argv_signals.extend(["--copy-to", str(Path(self._plan.output_user_dir).resolve())])
                for sid in list(self._plan.selected_signal_ids):
                    argv_signals.extend(["--select-signal-id", str(sid)])

                self.progress_changed.emit(0, 1, "信号：导出…")
                command = build_run_ugc_file_tools_command(workspace_root=Path(self._workspace_root), argv=argv_signals)
                result = run_cli_with_progress(
                    command=command,
                    cwd=Path(self._workspace_root),
                    on_progress=None,
                    stderr_tail_max_lines=240,
                )
                if int(result.exit_code) != 0:
                    tail = [str(x) for x in list(result.stderr_tail)[-80:] if str(x).strip() != ""]
                    tail_text = "\n".join(tail) if tail else "(stderr 为空)"
                    self.failed.emit(f"导出失败（基础信号）：退出码={int(result.exit_code)}\n\n{tail_text}")
                    return
                if not report_file.is_file():
                    raise FileNotFoundError(str(report_file))
                signals_report = json.loads(report_file.read_text(encoding="utf-8"))
                if not isinstance(signals_report, dict):
                    raise TypeError("basic signals export report must be dict")
                combined["signals"] = dict(signals_report)
                combined["steps"].append("signals")

            self.succeeded.emit(dict(combined))

    return _Worker

