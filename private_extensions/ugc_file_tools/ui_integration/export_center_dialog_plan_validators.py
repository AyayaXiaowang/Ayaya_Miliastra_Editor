from __future__ import annotations

from pathlib import Path

from ._common import IdRefPlaceholderUsage, scan_id_ref_placeholders_in_graph_code_files
from .export_center.mgmt_cfg_ids import _collect_writeback_ids_from_mgmt_cfg_items
from .export_center.plans import _ExportGiaPlan, _ExportGilPlan, _MergeSignalEntriesPlan, _RepairSignalsPlan
from .export_center.write_ui_policy import compute_write_ui_effective_policy
from .export_center_dialog_types import ExportCenterGiaPage, ExportCenterGilPage, ExportCenterRepairPage


def _scan_id_ref_usage_for_graphs(*, graph_code_files: list[Path]) -> IdRefPlaceholderUsage:
    return scan_id_ref_placeholders_in_graph_code_files(graph_code_files=list(graph_code_files or []))


def validate_gia_plan(
    *,
    main_window: object,
    workspace_root: Path,
    package_id: str,
    project_root: Path,
    picker: object,
    gia: ExportCenterGiaPage,
) -> _ExportGiaPlan | None:
    from app.ui.foundation import dialog_utils

    from .graph_selection import build_graph_selection_from_resource_items

    selected_items = list(picker.get_selected_items())
    graph_sel = build_graph_selection_from_resource_items(
        selected_items=selected_items,
        workspace_root=Path(workspace_root),
        package_id=str(package_id),
    )
    template_json_files = [Path(it.absolute_path).resolve() for it in selected_items if it.category == "templates"]
    template_json_files.sort(key=lambda x: x.as_posix().casefold())
    player_template_json_files = [
        Path(it.absolute_path).resolve() for it in selected_items if it.category == "player_templates"
    ]
    player_template_json_files.sort(key=lambda x: x.as_posix().casefold())

    signal_ids, basic_struct_ids, ingame_struct_ids = _collect_writeback_ids_from_mgmt_cfg_items(selected_items)

    if not (
        graph_sel.graph_code_files
        or template_json_files
        or player_template_json_files
        or signal_ids
        or basic_struct_ids
    ):
        dialog_utils.show_warning_dialog(
            main_window,
            "提示",
            "请至少勾选 1 个可导出的资源（节点图/元件/玩家模板/信号/基础结构体）。",
        )
        return None

    out_dir_name = str(gia.out_dir_edit.text() or "").strip() or f"{package_id}_export"
    if any(part == ".." for part in Path(out_dir_name).parts):
        dialog_utils.show_warning_dialog(main_window, "提示", "out 子目录名不能包含 '..'。")
        return None

    output_user_dir_text = str(gia.copy_dir_edit.text() or "").strip()
    output_user_dir: Path | None = None
    if output_user_dir_text != "":
        output_user_dir = Path(output_user_dir_text).resolve()
        if not output_user_dir.is_absolute():
            dialog_utils.show_warning_dialog(main_window, "提示", "复制目录必须是绝对路径。")
            return None

    ui_export_record_id: str | None = None
    if not gia.ui_export_record_row.isHidden():
        rid = str(gia.ui_export_record_combo.currentData() or "").strip()
        if rid != "":
            ui_export_record_id = str(rid)

    id_ref_usage = _scan_id_ref_usage_for_graphs(graph_code_files=list(graph_sel.graph_code_files))
    base_text = str(gia.base_gil_edit.text() or "").strip()
    base_gil_file: Path | None = None
    if base_text != "":
        base_gil_file = Path(base_text).resolve()
        if not base_gil_file.is_file():
            dialog_utils.show_warning_dialog(main_window, "提示", f"基底 .gil 文件不存在：{str(base_gil_file)}")
            return None
        if base_gil_file.suffix.lower() != ".gil":
            dialog_utils.show_warning_dialog(main_window, "提示", "基底文件必须是 .gil。")
            return None

    id_ref_text = str(gia.gia_id_ref_edit.text() or "").strip()
    id_ref_gil_file: Path | None = None
    if id_ref_text != "":
        id_ref_gil_file = Path(id_ref_text).resolve()
        if not id_ref_gil_file.is_file():
            dialog_utils.show_warning_dialog(main_window, "提示", f"占位符参考文件不存在：{str(id_ref_gil_file)}")
            return None
        if id_ref_gil_file.suffix.lower() != ".gil":
            dialog_utils.show_warning_dialog(main_window, "提示", "占位符参考文件必须是 .gil。")
            return None

    effective_id_ref_gil_file = id_ref_gil_file if id_ref_gil_file is not None else base_gil_file

    pack_enabled = bool(gia.pack_graphs_cb.isChecked()) and int(len(graph_sel.graph_code_files)) >= 2
    pack_file_name = str(gia.pack_name_edit.text() or "").strip()
    if pack_enabled:
        # 允许留空：留空则走 CLI/pipeline 的默认命名（<package_id>_packed_graphs.gia）。
        if pack_file_name != "" and any(sep in pack_file_name for sep in ["/", "\\"]):
            dialog_utils.show_warning_dialog(
                main_window,
                "提示",
                "打包文件名不能包含路径分隔符（请只填文件名，例如 打包一起.gia）。",
            )
            return None
        if pack_file_name != "" and not pack_file_name.lower().endswith(".gia"):
            pack_file_name = pack_file_name + ".gia"
    else:
        pack_file_name = ""

    base_gia_text = str(gia.base_gia_edit.text() or "").strip()
    base_gia: Path | None = None
    if base_gia_text != "":
        base_gia = Path(base_gia_text).resolve()
        if (not base_gia.is_file()) or base_gia.suffix.lower() != ".gia":
            dialog_utils.show_warning_dialog(main_window, "提示", "base .gia 不存在或不是 .gia 文件。")
            return None

    base_player_template_gia_text = str(gia.player_template_base_gia_edit.text() or "").strip()
    base_player_template_gia: Path | None = None
    if player_template_json_files:
        if base_player_template_gia_text == "":
            dialog_utils.show_warning_dialog(
                main_window,
                "提示",
                "已勾选“玩家模板（战斗预设）”，请先选择『玩家模板 base .gia』（真源导出的默认玩家模板）。",
            )
            return None
        base_player_template_gia = Path(base_player_template_gia_text).resolve()
        if (not base_player_template_gia.is_file()) or base_player_template_gia.suffix.lower() != ".gia":
            dialog_utils.show_warning_dialog(main_window, "提示", "玩家模板 base .gia 不存在或不是 .gia 文件。")
            return None

    from engine.configs.settings import settings as engine_settings

    node_pos_scale = float(getattr(engine_settings, "UGC_GIA_NODE_POS_SCALE", 2.0) or 2.0)

    return _ExportGiaPlan(
        package_id=str(package_id),
        project_root=Path(project_root),
        graph_selection=graph_sel,
        template_json_files=list(template_json_files),
        player_template_json_files=list(player_template_json_files),
        selected_signal_ids=list(signal_ids),
        selected_basic_struct_ids=list(basic_struct_ids),
        selected_ingame_struct_ids=list(ingame_struct_ids),
        output_dir_name_in_out=str(out_dir_name),
        output_user_dir=output_user_dir,
        node_pos_scale=float(node_pos_scale),
        allow_unresolved_ui_keys=bool(gia.allow_unresolved_ui_keys_cb.isChecked()),
        ui_export_record_id=ui_export_record_id,
        id_ref_gil_file=effective_id_ref_gil_file,
        bundle_enabled=bool(gia.bundle_enabled_cb.isChecked()),
        bundle_include_signals=bool(gia.bundle_include_signals_cb.isChecked()),
        bundle_include_ui_guid_registry=bool(gia.bundle_include_ui_guid_cb.isChecked()),
        pack_graphs_to_single_gia=bool(pack_enabled),
        pack_output_gia_file_name=str(pack_file_name),
        base_template_gia_file=base_gia,
        base_player_template_gia_file=base_player_template_gia,
        template_base_decode_max_depth=int(gia.decode_depth_spin.value()),
        player_template_base_decode_max_depth=int(gia.decode_depth_spin.value()),
    )


def validate_gil_plan(
    *,
    main_window: object,
    workspace_root: Path,
    package_id: str,
    project_root: Path,
    picker: object,
    gil: ExportCenterGilPage,
) -> _ExportGilPlan | None:
    from app.ui.foundation import dialog_utils

    from .graph_selection import build_graph_selection_from_resource_items

    selected_items = list(picker.get_selected_items())
    graph_sel = build_graph_selection_from_resource_items(
        selected_items=selected_items,
        workspace_root=Path(workspace_root),
        package_id=str(package_id),
    )
    template_items = [it for it in selected_items if it.category == "templates"]
    shared_templates = [it for it in template_items if str(it.source_root) != "project"]
    if shared_templates:
        dialog_utils.show_warning_dialog(
            main_window,
            "提示",
            "GIL 写回的“元件”仅支持当前项目存档的 `元件库/`（不支持共享元件库）。\n"
            "请取消勾选共享元件后再导出。",
        )
        return None
    template_json_files = [Path(it.absolute_path).resolve() for it in template_items]
    template_json_files.sort(key=lambda x: x.as_posix().casefold())
    instance_items = [it for it in selected_items if it.category == "instances"]
    shared_instances = [it for it in instance_items if str(it.source_root) != "project"]
    if shared_instances:
        dialog_utils.show_warning_dialog(
            main_window,
            "提示",
            "GIL 写回的“实体摆放”仅支持当前项目存档的 `实体摆放/`（不支持共享实体摆放）。\n"
            "请取消勾选共享实体摆放后再导出。",
        )
        return None
    instance_json_files = [Path(it.absolute_path).resolve() for it in instance_items]
    instance_json_files.sort(key=lambda x: x.as_posix().casefold())
    signal_ids, basic_struct_ids, ingame_struct_ids = _collect_writeback_ids_from_mgmt_cfg_items(selected_items)
    # 仅 project scope 的 UI源码 选择才会触发 “UI 写回强制开启”。
    # shared scope 的 UI源码 不对应当前项目存档的 `管理配置/UI源码/__workbench_out__` bundle，不能用于写回 .gil。
    ui_src_selected = any(it.category == "ui_src" and str(getattr(it, "source_root", "")) == "project" for it in selected_items)
    # 自定义变量（注册表）：来自左侧资源树的 `custom_vars` 虚拟条目（按 owner_ref 分组/变量粒度可勾选）
    custom_var_items = [it for it in selected_items if str(getattr(it, "category", "")) == "custom_vars"]
    selected_custom_variable_refs: list[dict[str, str]] = []
    if custom_var_items:
        from engine.resources.auto_custom_variable_registry import load_auto_custom_variable_registry_from_code
        from engine.resources.auto_custom_variable_registry import normalize_owner_refs

        package_root = (Path(workspace_root).resolve() / "assets" / "资源库" / "项目存档" / str(package_id)).resolve()
        registry_path = (package_root / "管理配置" / "关卡变量" / "自定义变量注册表.py").resolve()
        if not registry_path.is_file():
            raise FileNotFoundError(str(registry_path))
        decls = load_auto_custom_variable_registry_from_code(registry_path)

        # owner_ref -> [variable_id...]
        all_ids_by_owner_cf: dict[str, list[str]] = {}
        for d in decls:
            vid = str(d.variable_id or "").strip()
            if not vid:
                continue
            for ref in normalize_owner_refs(d.owner):
                key = str(ref).strip().casefold()
                if not key:
                    continue
                all_ids_by_owner_cf.setdefault(key, []).append(vid)

        # expand selection (select_all / explicit)
        for it in custom_var_items:
            meta = getattr(it, "meta", None)
            m = meta if isinstance(meta, dict) else {}
            owner_ref = str(m.get("owner_ref") or "").strip()
            if owner_ref == "":
                continue
            owner_kind = str(m.get("owner_kind") or "").strip()
            owner_display = str(m.get("owner_display") or "").strip()
            if str(m.get("select_all") or "").strip() == "1":
                vids = all_ids_by_owner_cf.get(owner_ref.casefold(), [])
                for vid in vids:
                    selected_custom_variable_refs.append(
                        {
                            "owner_ref": str(owner_ref),
                            "owner_kind": str(owner_kind),
                            "owner_display": str(owner_display),
                            "variable_id": str(vid),
                        }
                    )
                continue
            vid = str(m.get("variable_id") or "").strip()
            if vid == "":
                continue
            selected_custom_variable_refs.append(
                {
                    "owner_ref": str(owner_ref),
                    "owner_kind": str(owner_kind),
                    "owner_display": str(owner_display),
                    "variable_id": str(vid),
                }
            )

        # dedupe (keep order)
        seen_pairs: set[tuple[str, str]] = set()
        deduped_refs: list[dict[str, str]] = []
        for r in selected_custom_variable_refs:
            o = str(r.get("owner_ref") or "").casefold()
            v = str(r.get("variable_id") or "").casefold()
            if not o or not v:
                continue
            k = (o, v)
            if k in seen_pairs:
                continue
            seen_pairs.add(k)
            deduped_refs.append(dict(r))
        selected_custom_variable_refs = list(deduped_refs)

    # 兼容：旧 UI 预览/识别面板仍以“关卡实体变量 id 列表”展示
    selected_level_custom_variable_ids = [
        str(r.get("variable_id") or "").strip()
        for r in selected_custom_variable_refs
        if str(r.get("owner_ref") or "").strip().lower() == "level"
    ]
    selected_ui_html_files = [
        Path(it.absolute_path).resolve()
        for it in selected_items
        if str(getattr(it, "category", "") or "") == "ui_src"
        and str(getattr(it, "source_root", "") or "") == "project"
        and str(Path(it.absolute_path).suffix).lower() in {".html", ".htm"}
    ]
    selected_ui_html_files.sort(key=lambda x: x.as_posix().casefold())
    write_ui = bool(
        compute_write_ui_effective_policy(
            fmt="gil",
            ui_src_selected=bool(ui_src_selected),
            user_choice=bool(gil.write_ui_cb.isChecked()),
        ).effective_write_ui
    )
    ui_auto_sync_custom_variables = bool(gil.ui_auto_sync_vars_cb.isChecked())
    ui_export_record_id: str | None = None
    if not gil.gil_ui_export_record_row.isHidden():
        rid = str(gil.gil_ui_export_record_combo.currentData() or "").strip()
        if rid != "":
            ui_export_record_id = str(rid)

    use_builtin_empty_base = bool(getattr(gil, "use_builtin_empty_base_cb").isChecked())
    if use_builtin_empty_base:
        from ugc_file_tools.gil.builtin_empty_base import get_builtin_empty_base_gil_path

        input_gil_path = get_builtin_empty_base_gil_path()
    else:
        input_text = str(gil.input_gil_edit.text() or "").strip()
        if input_text == "":
            dialog_utils.show_warning_dialog(main_window, "提示", "请先选择一个基础 .gil。")
            return None
        input_gil_path = Path(input_text).resolve()
        if not input_gil_path.is_file():
            dialog_utils.show_warning_dialog(main_window, "提示", f"基础 .gil 文件不存在：{str(input_gil_path)}")
            return None
        if input_gil_path.suffix.lower() != ".gil":
            dialog_utils.show_warning_dialog(main_window, "提示", "基础文件不是 .gil。")
            return None

    output_text = str(gil.output_gil_edit.text() or "").strip() or f"{package_id}.gil"
    output_user_path = Path(output_text)
    if output_user_path.suffix.lower() != ".gil":
        dialog_utils.show_warning_dialog(main_window, "提示", "输出路径必须以 .gil 结尾。")
        return None

    # 输出路径校验：
    # - 导出中心通过子进程运行 CLI（cwd=workspace_root），因此相对路径会按 workspace_root 解析。
    # - 必须禁止输出路径指向 input base（否则会覆盖 base 并导致后续解析/写回不稳定）。
    output_user_path_resolved = (
        output_user_path.resolve()
        if output_user_path.is_absolute()
        else (Path(workspace_root).resolve() / output_user_path).resolve()
    )
    if output_user_path_resolved == input_gil_path.resolve():
        dialog_utils.show_warning_dialog(main_window, "提示", "输出路径不能与输入基础 .gil 相同（会覆盖 base gil）。")
        return None

    if not (
        template_json_files
        or instance_json_files
        or graph_sel.graph_code_files
        or signal_ids
        or basic_struct_ids
        or ingame_struct_ids
        or write_ui
        or selected_custom_variable_refs
    ):
        dialog_utils.show_warning_dialog(
            main_window,
            "提示",
            "请至少勾选 1 类可写回内容（元件/实体摆放/节点图/信号/结构体/UI/自定义变量）。",
        )
        return None

    id_ref_text2 = str(gil.gil_id_ref_edit.text() or "").strip()
    id_ref_gil_file2: Path | None = None
    if id_ref_text2 != "":
        id_ref_gil_file2 = Path(id_ref_text2).resolve()
        if not id_ref_gil_file2.is_file():
            dialog_utils.show_warning_dialog(main_window, "提示", f"占位符参考文件不存在：{str(id_ref_gil_file2)}")
            return None
        if id_ref_gil_file2.suffix.lower() != ".gil":
            dialog_utils.show_warning_dialog(main_window, "提示", "占位符参考文件必须是 .gil。")
            return None

    return _ExportGilPlan(
        package_id=str(package_id),
        project_root=Path(project_root),
        input_gil_path=Path(input_gil_path),
        use_builtin_empty_base=bool(use_builtin_empty_base),
        output_user_path=Path(output_user_path),
        struct_mode=str(gil.struct_mode_combo.currentData() or "merge"),
        templates_mode=str(gil.templates_mode_combo.currentData() or "overwrite"),
        instances_mode=str(gil.instances_mode_combo.currentData() or "overwrite"),
        signals_param_build_mode=str(gil.signals_mode_combo.currentData() or "semantic"),
        prefer_signal_specific_type_id=bool(gil.prefer_signal_specific_type_id_cb.isChecked()),
        ui_widget_templates_mode=str(gil.ui_mode_combo.currentData() or "merge"),
        write_ui=bool(write_ui),
        ui_auto_sync_custom_variables=bool(ui_auto_sync_custom_variables),
        selected_ui_html_files=list(selected_ui_html_files),
        ui_workbench_bundle_update_html_files=[],
        ui_layout_conflict_resolutions=[],
        node_graph_conflict_resolutions=[],
        template_conflict_resolutions=[],
        instance_conflict_resolutions=[],
        selected_custom_variable_refs=list(selected_custom_variable_refs),
        selected_level_custom_variable_ids=list(selected_level_custom_variable_ids),
        selected_template_json_files=list(template_json_files),
        selected_instance_json_files=list(instance_json_files),
        selected_graph_code_files=list(graph_sel.graph_code_files),
        selected_struct_ids=list(basic_struct_ids),
        selected_ingame_struct_ids=list(ingame_struct_ids),
        selected_signal_ids=list(signal_ids),
        graph_source_roots=list(graph_sel.graph_source_roots),
        ui_export_record_id=ui_export_record_id,
        id_ref_gil_file=id_ref_gil_file2,
    )


def validate_repair_signals_plan(
    *,
    main_window: object,
    workspace_root: Path,
    package_id: str,
    project_root: Path,
    picker: object,
    repair: ExportCenterRepairPage,
) -> _RepairSignalsPlan | None:
    from app.ui.foundation import dialog_utils

    from .graph_selection import build_graph_selection_from_resource_items

    selected_items = list(picker.get_selected_items())
    graph_sel = build_graph_selection_from_resource_items(
        selected_items=selected_items,
        workspace_root=Path(workspace_root),
        package_id=str(package_id),
    )
    if not graph_sel.graph_code_files:
        dialog_utils.show_warning_dialog(main_window, "提示", "请至少勾选 1 个节点图（用于提取信号名称并生成修复依据）。")
        return None

    input_text = str(repair.repair_input_gil_edit.text() or "").strip()
    if input_text == "":
        dialog_utils.show_warning_dialog(main_window, "提示", "请先选择需要修复的 .gil 文件。")
        return None
    input_gil_path = Path(input_text).resolve()
    if not input_gil_path.is_file():
        dialog_utils.show_warning_dialog(main_window, "提示", f"目标 .gil 文件不存在：{str(input_gil_path)}")
        return None
    if input_gil_path.suffix.lower() != ".gil":
        dialog_utils.show_warning_dialog(main_window, "提示", "目标文件不是 .gil。")
        return None

    output_text = str(repair.repair_output_gil_edit.text() or "").strip()
    if output_text == "":
        dialog_utils.show_warning_dialog(main_window, "提示", "请填写输出路径（建议直接使用默认的“同目录旁边”输出）。")
        return None
    output_gil_path = Path(output_text)
    if output_gil_path.suffix.lower() != ".gil":
        dialog_utils.show_warning_dialog(main_window, "提示", "输出路径必须以 .gil 结尾。")
        return None
    if not output_gil_path.is_absolute():
        dialog_utils.show_warning_dialog(main_window, "提示", "输出路径必须是绝对路径。")
        return None
    if output_gil_path.resolve() == input_gil_path.resolve():
        dialog_utils.show_warning_dialog(main_window, "提示", "输出路径不能与输入相同（避免覆盖原文件）。")
        return None

    return _RepairSignalsPlan(
        package_id=str(package_id),
        project_root=Path(project_root),
        input_gil_path=Path(input_gil_path),
        output_gil_path=Path(output_gil_path).resolve(),
        selected_graph_code_files=list(graph_sel.graph_code_files),
        graph_source_roots=list(graph_sel.graph_source_roots),
        prune_placeholder_orphans=bool(repair.repair_prune_orphans_cb.isChecked()),
    )


def validate_merge_signal_entries_plan(
    *,
    main_window: object,
    workspace_root: Path,
    package_id: str,
    project_root: Path,
    picker: object,
    repair: ExportCenterRepairPage,
) -> _MergeSignalEntriesPlan | None:
    from app.ui.foundation import dialog_utils

    _ = workspace_root
    _ = picker

    input_text = str(repair.repair_input_gil_edit.text() or "").strip()
    if input_text == "":
        dialog_utils.show_warning_dialog(main_window, "提示", "请先选择需要修复的 .gil 文件。")
        return None
    input_gil_path = Path(input_text).resolve()
    if not input_gil_path.is_file():
        dialog_utils.show_warning_dialog(main_window, "提示", f"目标 .gil 文件不存在：{str(input_gil_path)}")
        return None
    if input_gil_path.suffix.lower() != ".gil":
        dialog_utils.show_warning_dialog(main_window, "提示", "目标文件不是 .gil。")
        return None

    output_text = str(repair.repair_output_gil_edit.text() or "").strip()
    if output_text == "":
        dialog_utils.show_warning_dialog(main_window, "提示", "请填写输出路径（建议直接使用默认的“同目录旁边”输出）。")
        return None
    output_gil_path = Path(output_text)
    if output_gil_path.suffix.lower() != ".gil":
        dialog_utils.show_warning_dialog(main_window, "提示", "输出路径必须以 .gil 结尾。")
        return None
    if not output_gil_path.is_absolute():
        dialog_utils.show_warning_dialog(main_window, "提示", "输出路径必须是绝对路径。")
        return None
    if output_gil_path.resolve() == input_gil_path.resolve():
        dialog_utils.show_warning_dialog(main_window, "提示", "输出路径不能与输入相同（避免覆盖原文件）。")
        return None

    keep_name = str(repair.merge_keep_signal_edit.text() or "").strip()
    remove_name = str(repair.merge_remove_signal_edit.text() or "").strip()
    rename_to = str(repair.merge_rename_keep_to_edit.text() or "").strip()
    if keep_name == "" or remove_name == "":
        dialog_utils.show_warning_dialog(main_window, "提示", "请填写 keep/remove 两个信号名。")
        return None
    if keep_name == remove_name:
        dialog_utils.show_warning_dialog(main_window, "提示", "keep/remove 不能相同。")
        return None

    return _MergeSignalEntriesPlan(
        package_id=str(package_id),
        project_root=Path(project_root),
        input_gil_path=Path(input_gil_path),
        output_gil_path=Path(output_gil_path).resolve(),
        keep_signal_name=str(keep_name),
        remove_signal_name=str(remove_name),
        rename_keep_to=str(rename_to),
        patch_composite_pin_index=bool(repair.merge_patch_cpi_cb.isChecked()),
    )

