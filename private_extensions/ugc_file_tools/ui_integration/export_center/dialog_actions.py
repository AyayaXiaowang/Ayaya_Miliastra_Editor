from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .state import (
    _save_last_base_gil_path,
    _save_last_base_player_template_gia_path,
    _save_last_export_format,
    _save_last_repair_input_gil_path,
    _save_last_use_builtin_empty_base_gil,
)
from ..export_center_dialog_plan_validators import (
    validate_gia_plan,
    validate_gil_plan,
    validate_merge_signal_entries_plan,
    validate_repair_signals_plan,
)
from .write_ui_policy import compute_write_ui_effective_policy
from ..export_center_gil_identify_worker import make_export_center_gil_identify_worker_cls
from ..export_center_worker import make_export_center_worker_cls
from ..graph_selection import build_graph_selection_from_resource_items


def start_export_center_action(
    *,
    QtCore: Any,
    main_window: Any,
    dialog: Any,
    workspace_root: Path,
    package_id: str,
    project_root: Path,
    picker: Any,
    gia: Any,
    gil: Any,
    repair: Any,
    format_combo: Any,
    rt: Any,
    stacked: Any,
    run_btn: Any,
    close_btn: Any,
    history_btn: Any,
    get_progress_widget: Callable[..., Any],
    append_task_history_entry: Callable[..., Any],
    now_ts: Callable[[], Any],
    on_progress_changed: Callable[[int, int, str], Any] | None = None,
    on_succeeded_report: Callable[[dict], Any] | None = None,
    on_failed_message: Callable[[str], Any] | None = None,
) -> None:
    """
    导出中心：点击“开始导出/开始修复”的动作入口（UI 层编排）。

    约束：
    - 不在此处调用 dialog.accept()/reject()，避免任务启动前对话框提前关闭；
    - 不在模块顶层导入 PyQt6；QtCore 由调用方注入；
    - 执行逻辑由 QThread worker 完成，UI 侧仅做 busy/progress/提示与历史记录。
    """
    from app.ui.foundation import dialog_utils

    fmt = str(format_combo.currentData() or "gia")

    for attr in [
        "_export_center_worker",
        "_export_gia_worker",
        "_export_gia_selected_worker",
        "_export_selected_graph_gia_worker",
        "_export_templates_gia_worker",
        "_export_basic_structs_gia_worker",
        "_export_gil_worker",
        "_export_gil_selected_worker",
    ]:
        existing_worker = getattr(main_window, attr, None)
        is_running = getattr(existing_worker, "isRunning", None)
        if callable(is_running) and bool(is_running()):
            dialog_utils.show_warning_dialog(
                main_window,
                "导出进行中",
                "已有一个导出任务正在运行，请等待完成后再开始新的导出。",
            )
            return

    package_controller = getattr(main_window, "package_controller", None)
    if package_controller is None:
        raise RuntimeError("主窗口缺少 package_controller，无法导出")
    save_now = getattr(package_controller, "save_now", None)
    if callable(save_now):
        save_now()

    plan_obj: object | None
    if fmt == "gia":
        plan_obj = validate_gia_plan(
            main_window=main_window,
            workspace_root=Path(workspace_root),
            package_id=str(package_id),
            project_root=Path(project_root),
            picker=picker,
            gia=gia,
        )
    elif fmt == "gil":
        plan_obj = validate_gil_plan(
            main_window=main_window,
            workspace_root=Path(workspace_root),
            package_id=str(package_id),
            project_root=Path(project_root),
            picker=picker,
            gil=gil,
        )
    elif fmt == "merge_signal_entries":
        plan_obj = validate_merge_signal_entries_plan(
            main_window=main_window,
            workspace_root=Path(workspace_root),
            package_id=str(package_id),
            project_root=Path(project_root),
            picker=picker,
            repair=repair,
        )
    else:
        plan_obj = validate_repair_signals_plan(
            main_window=main_window,
            workspace_root=Path(workspace_root),
            package_id=str(package_id),
            project_root=Path(project_root),
            picker=picker,
            repair=repair,
        )
    if plan_obj is None:
        return

    _save_last_export_format(workspace_root=Path(workspace_root), export_format=str(fmt))
    from .plans import _ExportGiaPlan, _ExportGilPlan, _MergeSignalEntriesPlan, _RepairSignalsPlan
    from dataclasses import replace

    selected_items = list(picker.get_selected_items())

    # 预检：记录“被自动跳过”的输入文件（避免单文件问题中断整个导出流程）
    precheck_skipped_inputs: list[dict[str, str]] = []

    def _record_precheck_skip(*, category: str, file_path: Path, reason: str) -> None:
        precheck_skipped_inputs.append(
            {
                "category": str(category),
                "file": str(Path(file_path).resolve()),
                "reason": str(reason),
            }
        )

    # 兼容：避免把元件库索引当作“模板文件”交给后续导出工具（会导致 fail-fast）
    if isinstance(plan_obj, _ExportGiaPlan) and bool(plan_obj.template_json_files):
        cleaned_template_files: list[Path] = []
        for p in list(plan_obj.template_json_files or []):
            rp = Path(p).resolve()
            if rp.name == "templates_index.json":
                _record_precheck_skip(
                    category="templates",
                    file_path=rp,
                    reason="templates_index.json 是索引列表，不是单模板 JSON（每文件一个模板 dict）",
                )
                continue
            cleaned_template_files.append(rp)
        if len(cleaned_template_files) != len(list(plan_obj.template_json_files or [])):
            plan_obj = replace(plan_obj, template_json_files=list(cleaned_template_files))

    if isinstance(plan_obj, _ExportGilPlan):
        _save_last_use_builtin_empty_base_gil(workspace_root=Path(workspace_root), enabled=bool(plan_obj.use_builtin_empty_base))
        if not bool(plan_obj.use_builtin_empty_base):
            _save_last_base_gil_path(workspace_root=Path(workspace_root), base_gil_path=Path(plan_obj.input_gil_path))
    if isinstance(plan_obj, _ExportGiaPlan):
        base_text = str(getattr(gia, "base_gil_edit").text() or "").strip()
        if base_text != "":
            p = Path(base_text).resolve()
            if p.is_file() and p.suffix.lower() == ".gil":
                _save_last_base_gil_path(workspace_root=Path(workspace_root), base_gil_path=Path(p))
        base_player_template_gia = getattr(plan_obj, "base_player_template_gia_file", None)
        if base_player_template_gia is not None:
            p2 = Path(base_player_template_gia).resolve()
            if p2.is_file() and p2.suffix.lower() == ".gia":
                _save_last_base_player_template_gia_path(workspace_root=Path(workspace_root), base_gia_path=Path(p2))
    if isinstance(plan_obj, (_RepairSignalsPlan, _MergeSignalEntriesPlan)):
        _save_last_repair_input_gil_path(
            workspace_root=Path(workspace_root),
            input_gil_path=Path(plan_obj.input_gil_path),
        )

    # --- GIL：base `.gil` 冲突扫描（子进程隔离，避免 UI 进程解码导致闪退） ---
    base_gil_conflicts_report: dict[str, object] | None = None
    base_gil_conflicts_scan_ok = True

    def _ensure_base_gil_conflicts_report() -> tuple[dict[str, object], bool, bool]:
        nonlocal base_gil_conflicts_report, base_gil_conflicts_scan_ok
        if base_gil_conflicts_report is not None:
            return dict(base_gil_conflicts_report), bool(base_gil_conflicts_scan_ok), False

        if not isinstance(plan_obj, _ExportGilPlan):
            base_gil_conflicts_report = {}
            base_gil_conflicts_scan_ok = True
            return {}, True, False

        need_ui_layouts = bool(plan_obj.write_ui)
        need_node_graphs = bool(plan_obj.selected_graph_code_files)
        need_templates = bool(plan_obj.selected_template_json_files)
        need_instances = bool(plan_obj.selected_instance_json_files)
        if not any([need_ui_layouts, need_node_graphs, need_templates, need_instances]):
            base_gil_conflicts_report = {}
            base_gil_conflicts_scan_ok = True
            return {}, True, False

        import json
        from uuid import uuid4

        from .._cli_subprocess import build_run_ugc_file_tools_command, run_cli_with_progress

        out_dir = (Path(workspace_root).resolve() / "private_extensions" / "ugc_file_tools" / "out").resolve()
        tmp_dir = (out_dir / "_tmp_cli").resolve()
        tmp_dir.mkdir(parents=True, exist_ok=True)
        report_file = (tmp_dir / f"export_center_base_gil_conflicts_{uuid4().hex[:10]}.json").resolve()

        argv_scan: list[str] = [
            "tool",
            "export_center_scan_base_gil_conflicts",
            str(Path(plan_obj.input_gil_path).resolve()),
            "--report",
            str(report_file),
            "--decode-max-depth",
            "16",
        ]
        if need_ui_layouts:
            argv_scan.append("--scan-ui-layouts")
        if need_node_graphs:
            argv_scan.append("--scan-node-graphs")
        if need_templates:
            argv_scan.append("--scan-templates")
        if need_instances:
            argv_scan.append("--scan-instances")

        command = build_run_ugc_file_tools_command(workspace_root=Path(workspace_root), argv=argv_scan)
        result = run_cli_with_progress(
            command=command,
            cwd=Path(workspace_root),
            on_progress=None,
            stderr_tail_max_lines=240,
        )
        if int(result.exit_code) != 0:
            tail = [str(x) for x in list(result.stderr_tail)[-120:] if str(x).strip() != ""]
            tail_text = "\n".join(tail) if tail else "(stderr 为空)"
            proceed = dialog_utils.ask_yes_no_dialog(
                dialog,
                "扫描基础 .gil 冲突信息失败",
                "\n".join(
                    [
                        f"子进程退出码={int(result.exit_code)}",
                        "",
                        "为避免 UI 进程解析 base .gil 导致闪退，本次冲突检查改为在子进程中扫描。",
                        "但该样本/环境下子进程扫描失败，因此无法自动判断“哪些资源同名已存在”。",
                        "",
                        "你仍可继续导出：导出中心将对“已勾选”的布局/节点图/模板/实体弹出 overwrite/add/skip 选择，",
                        "其中“基础GIL ID”列可能为空；建议优先选择 add/skip 以避免误覆盖。",
                        "",
                        "---- 子进程 stderr 末尾 ----",
                        tail_text,
                        "",
                        "是否继续？",
                    ]
                ).strip(),
                default_yes=False,
            )
            if not bool(proceed):
                base_gil_conflicts_report = {}
                base_gil_conflicts_scan_ok = False
                return {}, False, True
            base_gil_conflicts_report = {}
            base_gil_conflicts_scan_ok = False
            return {}, False, False

        if not report_file.is_file():
            raise FileNotFoundError(str(report_file))
        obj = json.loads(report_file.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            raise TypeError("base gil conflicts report must be dict")
        base_gil_conflicts_report = dict(obj)
        base_gil_conflicts_scan_ok = True
        return dict(base_gil_conflicts_report), True, False

    # --- GIL：导出前冲突检查（UI Workbench bundle：布局同名冲突） ---
    if isinstance(plan_obj, _ExportGilPlan) and bool(plan_obj.write_ui):
        # raw_template 写回不走 Workbench bundle 导入，布局名冲突策略当前仅针对 bundle 写回生效
        ui_dir = Path(plan_obj.project_root) / "管理配置" / "UI控件模板" / "原始解析"
        has_raw_template = bool(ui_dir.is_dir() and any(ui_dir.glob("ugc_ui_widget_template_*.raw.json")))
        if not bool(has_raw_template):
            bundle_dir = (Path(plan_obj.project_root) / "管理配置" / "UI源码" / "__workbench_out__").resolve()
            bundle_files = [p.resolve() for p in sorted(bundle_dir.glob("*.ui_bundle.json"), key=lambda x: x.as_posix()) if p.is_file()]
            if not bundle_files and not bool(plan_obj.selected_ui_html_files):
                dialog_utils.show_warning_dialog(
                    main_window,
                    "提示",
                    "当前启用了 UI 写回，但未找到 UI Workbench bundle：\n"
                    f"- {str(bundle_dir)}/*.ui_bundle.json\n\n"
                    "请先在 UI Workbench 导出（生成 __workbench_out__ 产物），或改用 raw_template 写回后再导出。",
                )
                return

            # 关键提示：导出中心写 UI 时只读取 `__workbench_out__/*.ui_bundle.json`，不会直接读取 `UI源码/*.html`。
            # 因此当用户修改了 HTML 但未重新导出 bundle 时，导出结果会“看起来还是旧页面”。
            ui_src_dir = (Path(plan_obj.project_root) / "管理配置" / "UI源码").resolve()
            selected_project_ui_htmls = list(plan_obj.selected_ui_html_files)

            html_files_to_check: list[Path] = []
            if selected_project_ui_htmls:
                html_files_to_check = list(selected_project_ui_htmls)
            else:
                # 没有显式选择 UI源码：仍尽量检查“bundle 对应的同名 HTML”（避免扫描无关 HTML 造成噪音）
                for p in bundle_files:
                    stem = str(Path(p).name)
                    suffix = ".ui_bundle.json"
                    if stem.endswith(suffix):
                        stem = stem[: -len(suffix)]
                    else:
                        stem = str(Path(p).stem)
                    for ext in [".html", ".htm"]:
                        candidate = (ui_src_dir / f"{stem}{ext}").resolve()
                        if candidate.is_file():
                            html_files_to_check.append(candidate)
                            break

            stale_pairs: list[dict[str, object]] = []
            missing_bundles: list[dict[str, object]] = []
            for html_path in html_files_to_check:
                if not html_path.is_file():
                    continue
                expected_bundle = (bundle_dir / f"{html_path.stem}.ui_bundle.json").resolve()
                if not expected_bundle.is_file():
                    missing_bundles.append({"html": str(html_path), "expected_bundle": str(expected_bundle)})
                    continue
                html_mtime_ns = int(html_path.stat().st_mtime_ns)
                bundle_mtime_ns = int(expected_bundle.stat().st_mtime_ns)
                stale_by_mtime = html_mtime_ns > bundle_mtime_ns
                stale_by_mode = False
                if not bool(stale_by_mtime):
                    # 关键口径：UI 多状态导出策略已固定为 “整态打组（full_state_groups）”。
                    # 若 bundle 仍为旧口径（minimal_redundancy 或缺少 mode 字段），也应视为需要更新。
                    raw = expected_bundle.read_bytes()
                    idx = raw.find(b'"_ui_state_consolidation_mode"')
                    if idx < 0:
                        stale_by_mode = True
                    else:
                        window = raw[idx : idx + 256]
                        stale_by_mode = b"full_state_groups" not in window

                if bool(stale_by_mtime) or bool(stale_by_mode):
                    stale_pairs.append(
                        {
                            "html": str(html_path),
                            "bundle": str(expected_bundle),
                            "html_mtime_ns": int(html_mtime_ns),
                            "bundle_mtime_ns": int(bundle_mtime_ns),
                            "stale_by_mtime": bool(stale_by_mtime),
                            "stale_by_mode": bool(stale_by_mode),
                        }
                    )

            if (stale_pairs or missing_bundles) and selected_project_ui_htmls:
                # 用户已选择 UI源码（HTML）：优先“自动更新一次 bundle”以保证导出产物为最新 UI。
                import importlib.util

                need_update_htmls: list[Path] = []
                for it in list(stale_pairs):
                    p = Path(str(it.get("html") or "")).resolve()
                    if p.is_file():
                        need_update_htmls.append(p)
                for it2 in list(missing_bundles):
                    p2 = Path(str(it2.get("html") or "")).resolve()
                    if p2.is_file():
                        need_update_htmls.append(p2)

                # 去重（保持顺序）
                seen_cf: set[str] = set()
                deduped: list[Path] = []
                for p in need_update_htmls:
                    k = str(p).casefold()
                    if k in seen_cf:
                        continue
                    seen_cf.add(k)
                    deduped.append(p)
                need_update_htmls = deduped

                if need_update_htmls:
                    if importlib.util.find_spec("playwright") is None:
                        # 无 Playwright：无法自动更新；缺失 bundle 的场景也无法继续导出（会漏页）。
                        base_lines: list[str] = []
                        base_lines.append("检测到 UI bundle 过期/缺失，但当前环境缺少 Playwright，无法在导出前自动更新。")
                        base_lines.append("导出中心写 UI 时只读取：管理配置/UI源码/__workbench_out__/*.ui_bundle.json")
                        base_lines.append("不会直接读取：管理配置/UI源码/*.html")
                        base_lines.append("")
                        base_lines.append("解决方式（任选其一）：")
                        base_lines.append("- 在 UI Workbench 手动导出/保存 bundle（更新 __workbench_out__）后再导出")
                        base_lines.append("- 或安装依赖：`pip install playwright` 并运行 `playwright install chromium`")

                        if missing_bundles:
                            dialog_utils.show_warning_dialog(dialog, "缺少 Playwright，无法自动更新 UI bundle", "\n".join(base_lines).strip())
                            return

                        proceed = dialog_utils.ask_yes_no_dialog(
                            dialog,
                            "缺少 Playwright，无法自动更新 UI bundle",
                            "\n".join(base_lines + ["", "是否继续导出（将使用旧 bundle，可能导出旧页面）？"]).strip(),
                            default_yes=False,
                        )
                        if not bool(proceed):
                            return

                    # Playwright 可用：把“需要更新的 HTML 列表”写入 plan，交由 worker 在后台子进程中更新 bundle。
                    plan_obj = replace(plan_obj, ui_workbench_bundle_update_html_files=list(need_update_htmls))

            def _infer_layout_name_from_bundle_file(bundle_path: Path) -> str:
                name = str(Path(bundle_path).name)
                suffix = ".ui_bundle.json"
                if name.endswith(suffix):
                    return name[: -len(suffix)]
                return str(Path(bundle_path).stem)

            bundle_layout_names = (
                [str(p.stem) for p in list(plan_obj.selected_ui_html_files)]
                if plan_obj.selected_ui_html_files
                else [_infer_layout_name_from_bundle_file(p) for p in bundle_files]
            )
            bundle_layout_names = [str(x).strip() for x in bundle_layout_names if str(x).strip() != ""]

            base_report, scan_ok, cancelled = _ensure_base_gil_conflicts_report()
            if bool(cancelled):
                return

            base_layout_guid_by_name: dict[str, int] = {}
            raw_map = base_report.get("ui_layout_guid_by_name")
            if isinstance(raw_map, dict):
                for k, v in raw_map.items():
                    name = str(k or "").strip()
                    if name == "":
                        continue
                    if not isinstance(v, int) or int(v) <= 0:
                        continue
                    base_layout_guid_by_name.setdefault(name, int(v))

            conflict_layouts: list[dict[str, object]] = []
            if bool(scan_ok):
                for layout_name in bundle_layout_names:
                    if layout_name in base_layout_guid_by_name:
                        conflict_layouts.append(
                            {
                                "layout_name": str(layout_name),
                                "existing_guid": int(base_layout_guid_by_name[layout_name]),
                            }
                        )
            else:
                # 扫描失败：无法判断“是否同名存在”，为安全起见对所有布局弹出策略选择。
                for layout_name in bundle_layout_names:
                    conflict_layouts.append({"layout_name": str(layout_name), "existing_guid": None})

            if conflict_layouts:
                from PyQt6 import QtWidgets
                from app.ui.foundation.theme_manager import Colors, Sizes
                from ..export_center_gil_conflicts_dialog import open_export_center_gil_ui_layout_conflicts_dialog

                user_choices = open_export_center_gil_ui_layout_conflicts_dialog(
                    QtCore=QtCore,
                    QtWidgets=QtWidgets,
                    Colors=Colors,
                    Sizes=Sizes,
                    parent_dialog=dialog,
                    conflict_layouts=conflict_layouts,
                )
                if user_choices is None:
                    return

                actions_by_layout_name: dict[str, str] = {}
                for item in list(user_choices or []):
                    if not isinstance(item, dict):
                        continue
                    ln = str(item.get("layout_name") or "").strip()
                    if ln == "":
                        continue
                    act = str(item.get("action") or "overwrite").strip().lower()
                    if act in {"overwrite", "add", "skip"}:
                        actions_by_layout_name[ln] = act

                # 分配“新增布局名”：
                # - scan_ok=True：避开 base + 本次将写入的其它布局名（忽略大小写）
                # - scan_ok=False：无法获知 base 名单，使用更强随机后缀降低撞名概率
                used_casefold: set[str] = (
                    {str(n).casefold() for n in base_layout_guid_by_name.keys()} if bool(scan_ok) else set()
                )
                for name in bundle_layout_names:
                    act = actions_by_layout_name.get(name, "overwrite") if name in actions_by_layout_name else "overwrite"
                    if act in {"skip", "add"}:
                        continue
                    used_casefold.add(str(name).casefold())

                def _alloc_new_layout_name(base_name: str) -> str:
                    prefix = str(base_name)
                    i = 1
                    while True:
                        candidate = f"{prefix}__new_{i}"
                        if candidate.casefold() not in used_casefold:
                            used_casefold.add(candidate.casefold())
                            return candidate
                        i += 1

                def _alloc_new_layout_name_fallback(base_name: str) -> str:
                    from uuid import uuid4

                    return f"{str(base_name)}__new_{uuid4().hex[:8]}"

                new_name_by_layout_name: dict[str, str] = {}
                for name in bundle_layout_names:
                    if actions_by_layout_name.get(name) == "add":
                        if bool(scan_ok):
                            new_name_by_layout_name[name] = _alloc_new_layout_name(str(name))
                        else:
                            new_name_by_layout_name[name] = _alloc_new_layout_name_fallback(str(name))

                resolutions: list[dict[str, str]] = []
                for it in conflict_layouts:
                    ln = str(it.get("layout_name") or "").strip()
                    if ln == "":
                        continue
                    act = str(actions_by_layout_name.get(ln, "overwrite") or "overwrite").strip().lower()
                    if act == "add":
                        resolutions.append(
                            {
                                "layout_name": ln,
                                "action": "add",
                                "new_layout_name": str(new_name_by_layout_name.get(ln) or "").strip(),
                            }
                        )
                    elif act == "skip":
                        resolutions.append({"layout_name": ln, "action": "skip"})
                    else:
                        resolutions.append({"layout_name": ln, "action": "overwrite"})

                plan_obj = replace(plan_obj, ui_layout_conflict_resolutions=list(resolutions))

    # --- GIL：导出前冲突检查（元件模板同名冲突：按 template_name） ---
    if isinstance(plan_obj, _ExportGilPlan) and bool(plan_obj.selected_template_json_files):
        import json

        selected_infos: list[dict[str, object]] = []
        cleaned_template_files: list[Path] = []
        for p in list(plan_obj.selected_template_json_files or []):
            path = Path(p).resolve()
            if not path.is_file():
                _record_precheck_skip(category="templates", file_path=path, reason="文件不存在")
                continue
            obj = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(obj, dict):
                reason = "不是单模板 JSON（期望 dict；请不要选择 templates_index.json 这类索引文件）"
                if path.name == "templates_index.json":
                    reason = "templates_index.json 是索引列表，不是单模板 JSON（每文件一个模板 dict）"
                _record_precheck_skip(category="templates", file_path=path, reason=reason)
                continue
            template_id_text = str(obj.get("template_id") or "").strip()
            if template_id_text == "":
                _record_precheck_skip(category="templates", file_path=path, reason="缺少 template_id")
                continue
            cleaned_template_files.append(path)

            template_name = str(obj.get("name") or "").strip() or template_id_text

            # 与写回端口径保持一致：占位模板默认不会写回，这里也不纳入冲突检查
            metadata = obj.get("metadata")
            ugc = metadata.get("ugc") if isinstance(metadata, dict) else None
            is_placeholder = bool(ugc.get("placeholder")) if isinstance(ugc, dict) else False
            if is_placeholder:
                continue

            selected_infos.append(
                {
                    "template_json_file": path,
                    "template_id_text": template_id_text,
                    "template_name": template_name,
                }
            )

        # 预检剔除：避免无效文件进入后续写回（子进程）导致 fail-fast
        if len(cleaned_template_files) != len(list(plan_obj.selected_template_json_files or [])):
            plan_obj = replace(plan_obj, selected_template_json_files=list(cleaned_template_files))

        # 都是占位模板/或已被过滤：无需冲突检查
        if not selected_infos:
            pass
        else:
            base_report, scan_ok, cancelled = _ensure_base_gil_conflicts_report()
            if bool(cancelled):
                return

            base_template_id_by_name: dict[str, int] = {}
            raw_map = base_report.get("template_id_by_name")
            if isinstance(raw_map, dict):
                for k, v in raw_map.items():
                    name = str(k or "").strip()
                    if name == "":
                        continue
                    if not isinstance(v, int) or int(v) <= 0:
                        continue
                    base_template_id_by_name.setdefault(name, int(v))

            conflict_templates: list[dict[str, object]] = []
            if bool(scan_ok):
                for it in selected_infos:
                    name0 = str(it["template_name"])
                    existing = base_template_id_by_name.get(name0)
                    if isinstance(existing, int):
                        conflict_templates.append(
                            {
                                "template_json_file": str(it["template_json_file"]),
                                "template_name": name0,
                                "existing_template_id_int": int(existing),
                            }
                        )
            else:
                # 扫描失败：无法判断“是否同名存在”，为安全起见对所有模板弹出策略选择。
                for it in selected_infos:
                    conflict_templates.append(
                        {
                            "template_json_file": str(it["template_json_file"]),
                            "template_name": str(it["template_name"]),
                            "existing_template_id_int": None,
                        }
                    )

            if conflict_templates:
                from PyQt6 import QtWidgets
                from app.ui.foundation.theme_manager import Colors, Sizes
                from ..export_center_gil_conflicts_dialog import open_export_center_gil_template_conflicts_dialog

                user_choices = open_export_center_gil_template_conflicts_dialog(
                    QtCore=QtCore,
                    QtWidgets=QtWidgets,
                    Colors=Colors,
                    Sizes=Sizes,
                    parent_dialog=dialog,
                    conflict_templates=conflict_templates,
                )
                if user_choices is None:
                    return

                actions_by_tpl_file_cf: dict[str, str] = {}
                for item in list(user_choices or []):
                    if not isinstance(item, dict):
                        continue
                    fp = str(item.get("template_json_file") or "").strip()
                    if fp == "":
                        continue
                    act = str(item.get("action") or "overwrite").strip().lower()
                    if act not in {"overwrite", "add", "skip"}:
                        continue
                    actions_by_tpl_file_cf[str(Path(fp).resolve()).casefold()] = act

                used_tpl_names_cf: set[str] = {str(n).casefold() for n in base_template_id_by_name.keys()} if bool(scan_ok) else set()
                for it in selected_infos:
                    fp_cf = str(Path(str(it["template_json_file"])).resolve()).casefold()
                    act0 = actions_by_tpl_file_cf.get(fp_cf, "overwrite")
                    if act0 in {"skip", "add"}:
                        continue
                    used_tpl_names_cf.add(str(it["template_name"]).casefold())

                def _alloc_new_template_name(base_name: str) -> str:
                    prefix = str(base_name)
                    i = 1
                    while True:
                        candidate = f"{prefix}__new_{i}"
                        if candidate.casefold() not in used_tpl_names_cf:
                            used_tpl_names_cf.add(candidate.casefold())
                            return candidate
                        i += 1

                def _alloc_new_template_name_fallback(base_name: str) -> str:
                    from uuid import uuid4

                    return f"{str(base_name)}__new_{uuid4().hex[:8]}"

                new_name_by_tpl_file_cf: dict[str, str] = {}
                by_file_cf: dict[str, dict[str, object]] = {
                    str(Path(str(it["template_json_file"])).resolve()).casefold(): dict(it) for it in selected_infos
                }
                for fp_cf, it in list(by_file_cf.items()):
                    if actions_by_tpl_file_cf.get(fp_cf) == "add":
                        if bool(scan_ok):
                            new_name_by_tpl_file_cf[fp_cf] = _alloc_new_template_name(base_name=str(it["template_name"]))
                        else:
                            new_name_by_tpl_file_cf[fp_cf] = _alloc_new_template_name_fallback(base_name=str(it["template_name"]))

                resolutions: list[dict[str, str]] = []
                for it in conflict_templates:
                    fp2 = str(it.get("template_json_file") or "").strip()
                    if fp2 == "":
                        continue
                    rp = str(Path(fp2).resolve())
                    act2 = str(actions_by_tpl_file_cf.get(rp.casefold(), "overwrite") or "overwrite").strip().lower()
                    if act2 == "add":
                        resolutions.append(
                            {
                                "template_json_file": rp,
                                "action": "add",
                                "new_template_name": str(new_name_by_tpl_file_cf.get(rp.casefold(), "") or "").strip(),
                            }
                        )
                    elif act2 == "skip":
                        resolutions.append({"template_json_file": rp, "action": "skip"})
                    else:
                        resolutions.append({"template_json_file": rp, "action": "overwrite"})

                selected_template_files2: list[Path] = []
                for p in list(plan_obj.selected_template_json_files or []):
                    rp2 = str(Path(p).resolve())
                    if actions_by_tpl_file_cf.get(rp2.casefold(), "overwrite") == "skip":
                        continue
                    selected_template_files2.append(Path(p))

                plan_obj = replace(
                    plan_obj,
                    selected_template_json_files=list(selected_template_files2),
                    template_conflict_resolutions=list(resolutions),
                )

    # --- GIL：导出前冲突检查（实体实例同名冲突：按 instance_name） ---
    if isinstance(plan_obj, _ExportGilPlan) and bool(plan_obj.selected_instance_json_files):
        import json

        selected_infos2: list[dict[str, object]] = []
        cleaned_instance_files: list[Path] = []
        for p in list(plan_obj.selected_instance_json_files or []):
            path = Path(p).resolve()
            if not path.is_file():
                _record_precheck_skip(category="instances", file_path=path, reason="文件不存在")
                continue
            if path.name == "instances_index.json":
                _record_precheck_skip(category="instances", file_path=path, reason="instances_index.json 是索引列表，不是单实例 JSON（每文件一个实例 dict）")
                continue
            obj = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(obj, dict):
                _record_precheck_skip(category="instances", file_path=path, reason="不是单实例 JSON（期望 dict）")
                continue
            instance_id_text = str(obj.get("instance_id") or "").strip()
            if instance_id_text == "":
                _record_precheck_skip(category="instances", file_path=path, reason="缺少 instance_id")
                continue
            cleaned_instance_files.append(path)
            instance_name = str(obj.get("name") or "").strip() or instance_id_text
            selected_infos2.append(
                {
                    "instance_json_file": path,
                    "instance_id_text": instance_id_text,
                    "instance_name": instance_name,
                }
            )

        # 预检剔除：避免无效文件进入后续写回（子进程）导致 fail-fast
        if len(cleaned_instance_files) != len(list(plan_obj.selected_instance_json_files or [])):
            plan_obj = replace(plan_obj, selected_instance_json_files=list(cleaned_instance_files))

        if not selected_infos2:
            pass
        else:
            base_report, scan_ok, cancelled = _ensure_base_gil_conflicts_report()
            if bool(cancelled):
                return

            base_instance_id_by_name: dict[str, int] = {}
            raw_map = base_report.get("instance_id_by_name")
            if isinstance(raw_map, dict):
                for k, v in raw_map.items():
                    name = str(k or "").strip()
                    if name == "":
                        continue
                    if not isinstance(v, int) or int(v) <= 0:
                        continue
                    base_instance_id_by_name.setdefault(name, int(v))

            conflict_instances: list[dict[str, object]] = []
            if bool(scan_ok):
                for it in selected_infos2:
                    name0 = str(it["instance_name"])
                    existing = base_instance_id_by_name.get(name0)
                    if isinstance(existing, int):
                        conflict_instances.append(
                            {
                                "instance_json_file": str(it["instance_json_file"]),
                                "instance_name": name0,
                                "existing_instance_id_int": int(existing),
                            }
                        )
            else:
                # 扫描失败：无法判断“是否同名存在”，为安全起见对所有实体弹出策略选择。
                for it in selected_infos2:
                    conflict_instances.append(
                        {
                            "instance_json_file": str(it["instance_json_file"]),
                            "instance_name": str(it["instance_name"]),
                            "existing_instance_id_int": None,
                        }
                    )

            if conflict_instances:
                from PyQt6 import QtWidgets
                from app.ui.foundation.theme_manager import Colors, Sizes
                from ..export_center_gil_conflicts_dialog import open_export_center_gil_instance_conflicts_dialog

                user_choices = open_export_center_gil_instance_conflicts_dialog(
                    QtCore=QtCore,
                    QtWidgets=QtWidgets,
                    Colors=Colors,
                    Sizes=Sizes,
                    parent_dialog=dialog,
                    conflict_instances=conflict_instances,
                )
                if user_choices is None:
                    return

                actions_by_inst_file_cf: dict[str, str] = {}
                for item in list(user_choices or []):
                    if not isinstance(item, dict):
                        continue
                    fp = str(item.get("instance_json_file") or "").strip()
                    if fp == "":
                        continue
                    act = str(item.get("action") or "overwrite").strip().lower()
                    if act not in {"overwrite", "add", "skip"}:
                        continue
                    actions_by_inst_file_cf[str(Path(fp).resolve()).casefold()] = act

                used_inst_names_cf: set[str] = {str(n).casefold() for n in base_instance_id_by_name.keys()} if bool(scan_ok) else set()
                for it in selected_infos2:
                    fp_cf = str(Path(str(it["instance_json_file"])).resolve()).casefold()
                    act0 = actions_by_inst_file_cf.get(fp_cf, "overwrite")
                    if act0 in {"skip", "add"}:
                        continue
                    used_inst_names_cf.add(str(it["instance_name"]).casefold())

                def _alloc_new_instance_name(base_name: str) -> str:
                    prefix = str(base_name)
                    i = 1
                    while True:
                        candidate = f"{prefix}__new_{i}"
                        if candidate.casefold() not in used_inst_names_cf:
                            used_inst_names_cf.add(candidate.casefold())
                            return candidate
                        i += 1

                def _alloc_new_instance_name_fallback(base_name: str) -> str:
                    from uuid import uuid4

                    return f"{str(base_name)}__new_{uuid4().hex[:8]}"

                new_name_by_inst_file_cf: dict[str, str] = {}
                by_file_cf2: dict[str, dict[str, object]] = {
                    str(Path(str(it["instance_json_file"])).resolve()).casefold(): dict(it) for it in selected_infos2
                }
                for fp_cf, it in list(by_file_cf2.items()):
                    if actions_by_inst_file_cf.get(fp_cf) == "add":
                        if bool(scan_ok):
                            new_name_by_inst_file_cf[fp_cf] = _alloc_new_instance_name(base_name=str(it["instance_name"]))
                        else:
                            new_name_by_inst_file_cf[fp_cf] = _alloc_new_instance_name_fallback(base_name=str(it["instance_name"]))

                resolutions2: list[dict[str, str]] = []
                for it in conflict_instances:
                    fp2 = str(it.get("instance_json_file") or "").strip()
                    if fp2 == "":
                        continue
                    rp = str(Path(fp2).resolve())
                    act2 = str(actions_by_inst_file_cf.get(rp.casefold(), "overwrite") or "overwrite").strip().lower()
                    if act2 == "add":
                        resolutions2.append(
                            {
                                "instance_json_file": rp,
                                "action": "add",
                                "new_instance_name": str(new_name_by_inst_file_cf.get(rp.casefold(), "") or "").strip(),
                            }
                        )
                    elif act2 == "skip":
                        resolutions2.append({"instance_json_file": rp, "action": "skip"})
                    else:
                        resolutions2.append({"instance_json_file": rp, "action": "overwrite"})

                selected_instance_files2: list[Path] = []
                for p in list(plan_obj.selected_instance_json_files or []):
                    rp2 = str(Path(p).resolve())
                    if actions_by_inst_file_cf.get(rp2.casefold(), "overwrite") == "skip":
                        continue
                    selected_instance_files2.append(Path(p))

                plan_obj = replace(
                    plan_obj,
                    selected_instance_json_files=list(selected_instance_files2),
                    instance_conflict_resolutions=list(resolutions2),
                )

    # --- GIL：导出前冲突检查（节点图同名冲突：按 (scope, graph_name)） ---
    if isinstance(plan_obj, _ExportGilPlan) and bool(plan_obj.selected_graph_code_files):
        from ugc_file_tools.project_archive_importer.node_graphs_importer_parts.constants import (
            GRAPH_NAME_LINE_RE,
            GRAPH_TYPE_LINE_RE,
            SCAN_HEAD_CHARS,
        )

        selected_infos: list[dict[str, object]] = []
        cleaned_graph_files: list[Path] = []
        for p in list(plan_obj.selected_graph_code_files or []):
            path = Path(p).resolve()
            if not path.is_file():
                _record_precheck_skip(category="node_graphs", file_path=path, reason="文件不存在")
                continue
            with path.open("r", encoding="utf-8-sig") as f:
                head = f.read(int(SCAN_HEAD_CHARS))
            m_name = GRAPH_NAME_LINE_RE.search(head)
            graph_name = str(m_name.group(1) if m_name else "").strip() or str(path.stem)
            m_type = GRAPH_TYPE_LINE_RE.search(head)
            graph_type_hint = str(m_type.group(1) if m_type else "").strip().lower()
            if graph_type_hint in {"server", "client"}:
                scope2 = graph_type_hint
            else:
                lowered = path.as_posix().lower()
                if "/client/" in lowered:
                    scope2 = "client"
                elif "/server/" in lowered:
                    scope2 = "server"
                else:
                    _record_precheck_skip(
                        category="node_graphs",
                        file_path=path,
                        reason="无法推断节点图 scope（graph_type 缺失且路径不含 /server 或 /client）",
                    )
                    continue
            cleaned_graph_files.append(path)
            selected_infos.append({"graph_code_file": path, "scope": scope2, "graph_name": graph_name})

        if len(cleaned_graph_files) != len(list(plan_obj.selected_graph_code_files or [])):
            plan_obj = replace(plan_obj, selected_graph_code_files=list(cleaned_graph_files))

        if not selected_infos:
            pass
        else:
            base_report, scan_ok, cancelled = _ensure_base_gil_conflicts_report()
            if bool(cancelled):
                return

            # base `.gil` 现有图：(scope, name) -> graph_id_int（first-wins）
            base_by_scope_and_name: dict[str, dict[str, int]] = {"server": {}, "client": {}}
            raw_scoped = base_report.get("node_graph_id_by_scope_and_name")
            if isinstance(raw_scoped, dict):
                for scope in ("server", "client"):
                    scoped = raw_scoped.get(scope)
                    if not isinstance(scoped, dict):
                        continue
                    for k, v in scoped.items():
                        name = str(k or "").strip()
                        if name == "":
                            continue
                        if not isinstance(v, int):
                            continue
                        base_by_scope_and_name.setdefault(scope, {})
                        if name not in base_by_scope_and_name[scope]:
                            base_by_scope_and_name[scope][name] = int(v)

            conflict_graphs: list[dict[str, object]] = []
            if bool(scan_ok):
                for it in selected_infos:
                    scope3 = str(it["scope"])
                    name3 = str(it["graph_name"])
                    existing = base_by_scope_and_name.get(scope3, {}).get(name3)
                    if isinstance(existing, int):
                        conflict_graphs.append(
                            {
                                "graph_code_file": str(it["graph_code_file"]),
                                "scope": scope3,
                                "graph_name": name3,
                                "existing_graph_id_int": int(existing),
                            }
                        )
            else:
                # 扫描失败：无法判断“是否同名存在”，为安全起见对所有节点图弹出策略选择。
                for it in selected_infos:
                    conflict_graphs.append(
                        {
                            "graph_code_file": str(it["graph_code_file"]),
                            "scope": str(it["scope"]),
                            "graph_name": str(it["graph_name"]),
                            "existing_graph_id_int": None,
                        }
                    )

            if conflict_graphs:
                from PyQt6 import QtWidgets
                from app.ui.foundation.theme_manager import Colors, Sizes
                from ..export_center_gil_conflicts_dialog import open_export_center_gil_node_graph_conflicts_dialog

                user_choices = open_export_center_gil_node_graph_conflicts_dialog(
                    QtCore=QtCore,
                    QtWidgets=QtWidgets,
                    Colors=Colors,
                    Sizes=Sizes,
                    parent_dialog=dialog,
                    conflict_graphs=conflict_graphs,
                )
                if user_choices is None:
                    return

                actions_by_graph_file_cf: dict[str, str] = {}
                for item in list(user_choices or []):
                    if not isinstance(item, dict):
                        continue
                    fp = str(item.get("graph_code_file") or "").strip()
                    if fp == "":
                        continue
                    act = str(item.get("action") or "overwrite").strip().lower()
                    if act not in {"overwrite", "add", "skip"}:
                        continue
                    resolved_fp = str(Path(fp).resolve())
                    actions_by_graph_file_cf[resolved_fp.casefold()] = act

                used_names_cf_by_scope: dict[str, set[str]] = {
                    "server": {str(n).casefold() for n in base_by_scope_and_name.get("server", {}).keys()}
                    if bool(scan_ok)
                    else set(),
                    "client": {str(n).casefold() for n in base_by_scope_and_name.get("client", {}).keys()}
                    if bool(scan_ok)
                    else set(),
                }
                for it in selected_infos:
                    fp_cf = str(Path(it["graph_code_file"]).resolve()).casefold()
                    act = actions_by_graph_file_cf.get(fp_cf, "overwrite")
                    if act in {"skip", "add"}:
                        continue
                    scope4 = str(it["scope"])
                    used_names_cf_by_scope.setdefault(scope4, set()).add(str(it["graph_name"]).casefold())

                def _alloc_new_graph_name(*, scope: str, base_name: str) -> str:
                    used = used_names_cf_by_scope.setdefault(str(scope), set())
                    prefix = str(base_name)
                    i = 1
                    while True:
                        candidate = f"{prefix}__new_{i}"
                        if candidate.casefold() not in used:
                            used.add(candidate.casefold())
                            return candidate
                        i += 1

                def _alloc_new_graph_name_fallback(base_name: str) -> str:
                    from uuid import uuid4

                    return f"{str(base_name)}__new_{uuid4().hex[:8]}"

                new_name_by_graph_file_cf: dict[str, str] = {}
                for it in selected_infos:
                    fp_cf = str(Path(it["graph_code_file"]).resolve()).casefold()
                    if actions_by_graph_file_cf.get(fp_cf) == "add":
                        if bool(scan_ok):
                            new_name_by_graph_file_cf[fp_cf] = _alloc_new_graph_name(
                                scope=str(it["scope"]),
                                base_name=str(it["graph_name"]),
                            )
                        else:
                            new_name_by_graph_file_cf[fp_cf] = _alloc_new_graph_name_fallback(str(it["graph_name"]))

                resolutions2: list[dict[str, str]] = []
                for it in conflict_graphs:
                    fp2 = str(it.get("graph_code_file") or "").strip()
                    if fp2 == "":
                        continue
                    fp2_resolved = str(Path(fp2).resolve())
                    act2 = str(actions_by_graph_file_cf.get(fp2_resolved.casefold(), "overwrite") or "overwrite").strip().lower()
                    if act2 == "add":
                        new_name = str(new_name_by_graph_file_cf.get(fp2_resolved.casefold(), "") or "").strip()
                        resolutions2.append({"graph_code_file": fp2_resolved, "action": "add", "new_graph_name": new_name})
                    elif act2 == "skip":
                        resolutions2.append({"graph_code_file": fp2_resolved, "action": "skip"})
                    else:
                        resolutions2.append({"graph_code_file": fp2_resolved, "action": "overwrite"})

                selected_graph_files2: list[Path] = []
                for p in list(plan_obj.selected_graph_code_files or []):
                    rp = str(Path(p).resolve())
                    if actions_by_graph_file_cf.get(rp.casefold(), "overwrite") == "skip":
                        continue
                    selected_graph_files2.append(Path(p))

                plan_obj = replace(
                    plan_obj,
                    selected_graph_code_files=list(selected_graph_files2),
                    node_graph_conflict_resolutions=list(resolutions2),
                )

    # 预检可能会把“误选文件”剔除到无事可做：此时不启动 worker，直接提示用户。
    if isinstance(plan_obj, _ExportGiaPlan):
        graph_sel0 = plan_obj.graph_selection
        graph_files0 = list(getattr(graph_sel0, "graph_code_files", []) or [])
        has_any_gia = bool(graph_files0) or bool(plan_obj.template_json_files) or bool(plan_obj.selected_basic_struct_ids) or bool(
            plan_obj.selected_signal_ids
        ) or bool(plan_obj.selected_ingame_struct_ids)
        if not bool(has_any_gia):
            lines: list[str] = ["没有可导出的内容（预检后为空）。"]
            if precheck_skipped_inputs:
                lines.append("")
                lines.append(f"预检已跳过 {len(precheck_skipped_inputs)} 个输入文件：")
                for item in precheck_skipped_inputs[:10]:
                    fp = str(item.get("file") or "").strip()
                    reason = str(item.get("reason") or "").strip()
                    name = Path(fp).name if fp else "(unknown)"
                    lines.append(f"- {name}：{reason}" if reason else f"- {name}")
                if len(precheck_skipped_inputs) > 10:
                    lines.append(f"... 还有 {len(precheck_skipped_inputs) - 10} 个未展示")
            dialog_utils.show_warning_dialog(main_window, "提示", "\n".join(lines))
            return

    if isinstance(plan_obj, _ExportGilPlan):
        has_any_gil = bool(plan_obj.write_ui) or bool(plan_obj.selected_graph_code_files) or bool(plan_obj.selected_template_json_files) or bool(
            plan_obj.selected_instance_json_files
        ) or bool(plan_obj.selected_struct_ids) or bool(plan_obj.selected_ingame_struct_ids) or bool(plan_obj.selected_signal_ids) or bool(
            plan_obj.selected_level_custom_variable_ids
        ) or bool(
            plan_obj.selected_custom_variable_refs
        )
        if not bool(has_any_gil):
            lines2: list[str] = ["没有可写回/可导出的内容（预检后为空）。"]
            if precheck_skipped_inputs:
                lines2.append("")
                lines2.append(f"预检已跳过 {len(precheck_skipped_inputs)} 个输入文件：")
                for item in precheck_skipped_inputs[:10]:
                    fp = str(item.get("file") or "").strip()
                    reason = str(item.get("reason") or "").strip()
                    name = Path(fp).name if fp else "(unknown)"
                    lines2.append(f"- {name}：{reason}" if reason else f"- {name}")
                if len(precheck_skipped_inputs) > 10:
                    lines2.append(f"... 还有 {len(precheck_skipped_inputs) - 10} 个未展示")
            dialog_utils.show_warning_dialog(main_window, "提示", "\n".join(lines2))
            return

    # 手动覆盖（来自“识别表格：缺失行双击选择”）：注入到 plan，供 worker/子进程透传。
    if isinstance(plan_obj, (_ExportGiaPlan, _ExportGilPlan)):
        comp_over = getattr(rt, "id_ref_override_component_name_to_id", None)
        ent_over = getattr(rt, "id_ref_override_entity_name_to_guid", None)
        plan_obj = replace(
            plan_obj,
            id_ref_override_component_name_to_id=(dict(comp_over) if isinstance(comp_over, dict) else {}),
            id_ref_override_entity_name_to_guid=(dict(ent_over) if isinstance(ent_over, dict) else {}),
        )

    selection_snapshot = [
        {
            "source_root": it.source_root,
            "category": it.category,
            "relative_path": it.relative_path,
            "absolute_path": str(it.absolute_path),
        }
        for it in list(selected_items)
    ]

    def _set_busy(busy: bool) -> None:
        run_btn.setEnabled(not bool(busy))
        close_btn.setEnabled(not bool(busy))
        history_btn.setEnabled(not bool(busy))
        format_combo.setEnabled(not bool(busy))
        picker.setEnabled(not bool(busy))
        stacked.setEnabled(not bool(busy))

    _set_busy(True)

    WorkerCls = make_export_center_worker_cls(QtCore=QtCore)
    worker = WorkerCls(
        plan=plan_obj,
        workspace_root=Path(workspace_root),
        package_id=str(package_id),
        fmt=str(fmt),
        parent=main_window,
    )
    setattr(main_window, "_export_center_worker", worker)

    state = {"succeeded": False, "failed": False}

    def _on_progress(current: int, total: int, label: str) -> None:
        get_progress_widget(visible=True).set_status(label=str(label), current=int(current), total=int(total))
        if on_progress_changed is not None:
            on_progress_changed(int(current), int(total), str(label))

    def _on_succeeded(report: dict) -> None:
        state["succeeded"] = True
        get_progress_widget(visible=False).set_status(label="完成", current=0, total=0)
        _set_busy(False)

        report2 = dict(report)
        if precheck_skipped_inputs:
            report2["precheck_skipped_inputs"] = list(precheck_skipped_inputs)

        fmt2 = str(report2.get("format") or "")

        append_task_history_entry(
            workspace_root=Path(workspace_root),
            entry={
                "ts": now_ts(),
                "kind": "export_center",
                "title": f"导出中心（{package_id}，{fmt2}）",
                "package_id": str(package_id),
                "format": str(fmt2),
                "selection": list(selection_snapshot),
                "report": dict(report2),
            },
        )

        if fmt2 == "gil":
            rep = report2.get("report") if isinstance(report2, dict) else None
            output_tool = str(rep.get("output_gil_resolved") or rep.get("output_gil") or "") if isinstance(rep, dict) else ""
            output_user = (
                str(rep.get("output_gil_user_resolved") or rep.get("output_gil_user") or "") if isinstance(rep, dict) else ""
            )
            from ugc_file_tools.recent_artifacts import append_recent_exported_gil

            append_recent_exported_gil(
                workspace_root=Path(workspace_root),
                gil_path=str(output_user or output_tool),
                source="export_center",
                title=f"export_center:{package_id}",
            )

        if fmt2 == "repair_signals":
            rep2 = report.get("report") if isinstance(report, dict) else None
            output_user2 = str(rep2.get("output_gil") or "") if isinstance(rep2, dict) else ""
            if output_user2:
                from ugc_file_tools.recent_artifacts import append_recent_exported_gil

                append_recent_exported_gil(
                    workspace_root=Path(workspace_root),
                    gil_path=str(output_user2),
                    source="export_center",
                    title=f"export_center:{package_id}:repair_signals",
                )

        if fmt2 == "merge_signal_entries":
            repm = report.get("report") if isinstance(report, dict) else None
            output_user_m = str(repm.get("output_gil") or "") if isinstance(repm, dict) else ""
            if output_user_m:
                from ugc_file_tools.recent_artifacts import append_recent_exported_gil

                append_recent_exported_gil(
                    workspace_root=Path(workspace_root),
                    gil_path=str(output_user_m),
                    source="export_center",
                    title=f"export_center:{package_id}:merge_signal_entries",
                )

        if fmt2 == "gil":
            rep = report.get("report") if isinstance(report, dict) else None
            output_tool = str(rep.get("output_gil_resolved") or rep.get("output_gil") or "") if isinstance(rep, dict) else ""
            output_user = str(rep.get("output_gil_user_resolved") or rep.get("output_gil_user") or "") if isinstance(rep, dict) else ""

            skipped_graphs: list[dict[str, object]] = []
            instances_missing: list[str] = []
            instances_filtered_by_selection = False
            if isinstance(rep, dict):
                steps = rep.get("steps")
                if isinstance(steps, list):
                    for step in steps:
                        if not isinstance(step, dict):
                            continue
                        if str(step.get("kind") or "") == "instances":
                            inst_rep = step.get("report")
                            if isinstance(inst_rep, dict):
                                instances_filtered_by_selection = bool(inst_rep.get("filtered_by_selection") or False)
                                raw_missing = inst_rep.get("instances_missing_in_target")
                                if isinstance(raw_missing, list) and raw_missing:
                                    instances_missing = [str(x).strip() for x in raw_missing if str(x).strip() != ""]
                            continue
                        if str(step.get("kind") or "") != "node_graphs":
                            continue
                        node_graphs_rep = step.get("report")
                        raw_skipped = node_graphs_rep.get("skipped_graphs") if isinstance(node_graphs_rep, dict) else None
                        if isinstance(raw_skipped, list) and raw_skipped:
                            skipped_graphs = [x for x in raw_skipped if isinstance(x, dict)]
                        continue

            gil_lines: list[str] = [
                "已生成 .gil：",
                f"- out 产物：{output_tool}",
                f"- 导出路径：{output_user}",
            ]
            if precheck_skipped_inputs:
                gil_lines.append("")
                gil_lines.append(f"注意：预检阶段自动跳过 {len(precheck_skipped_inputs)} 个输入文件：")
                for item in precheck_skipped_inputs[:10]:
                    fp0 = str(item.get("file") or "").strip()
                    reason0 = str(item.get("reason") or "").strip()
                    name0 = Path(fp0).name if fp0 else "(unknown)"
                    gil_lines.append(f"- {name0}：{reason0}" if reason0 else f"- {name0}")
                if len(precheck_skipped_inputs) > 10:
                    gil_lines.append(f"... 还有 {len(precheck_skipped_inputs) - 10} 个未展示")

            if skipped_graphs:
                gil_lines.append("")
                gil_lines.append(f"注意：节点图写回跳过 {len(skipped_graphs)} 个：")
                for item in skipped_graphs[:10]:
                    code_file = str(item.get("graph_code_file") or "").strip()
                    display_name = (
                        Path(code_file).name
                        if code_file
                        else (str(item.get("graph_name") or item.get("graph_key") or "").strip() or "(unknown)")
                    )
                    reason = str(item.get("reason") or "").strip()
                    err_text = str(item.get("error") or "").strip()
                    detail = reason
                    if err_text:
                        non_empty = [ln.strip() for ln in err_text.splitlines() if ln.strip() != ""]
                        bullet = next((ln for ln in non_empty if ln.startswith("- ")), (non_empty[0] if non_empty else ""))
                        if bullet:
                            detail = bullet
                    if detail:
                        gil_lines.append(f"- {display_name}：{detail}")
                    else:
                        gil_lines.append(f"- {display_name}")
                if len(skipped_graphs) > 10:
                    gil_lines.append(f"... 还有 {len(skipped_graphs) - 10} 个未展示")

            if instances_filtered_by_selection and instances_missing:
                gil_lines.append("")
                gil_lines.append(
                    f"提示：本次勾选的实体中，有 {len(instances_missing)} 个在 base 存档里不存在，"
                    "已按“新增实例”写入输出："
                )
                for iid in instances_missing[:10]:
                    gil_lines.append(f"- {iid}")
                if len(instances_missing) > 10:
                    gil_lines.append(f"... 还有 {len(instances_missing) - 10} 个未展示")

            dialog_utils.show_info_dialog(
                dialog,
                "导出完成",
                "\n".join(gil_lines),
            )
            if on_succeeded_report is not None:
                on_succeeded_report(dict(report2))
            return

        if fmt2 == "repair_signals":
            rep3 = report.get("report") if isinstance(report, dict) else None
            output_user3 = str(rep3.get("output_gil") or "") if isinstance(rep3, dict) else ""
            removed_entries = int(rep3.get("removed_signal_entries") or 0) if isinstance(rep3, dict) else 0
            id_remap_size = int(rep3.get("id_remap_size") or 0) if isinstance(rep3, dict) else 0
            node_changes = int(rep3.get("node_instance_id_changes") or 0) if isinstance(rep3, dict) else 0
            dialog_utils.show_info_dialog(
                dialog,
                "修复完成",
                "\n".join(
                    [
                        "已生成修复版 .gil：",
                        f"- 输出路径：{output_user3}",
                        f"- 合并/移除信号条目：{removed_entries}",
                        f"- 引用重绑映射条数：{id_remap_size}",
                        f"- 节点引用更新次数：{node_changes}",
                    ]
                ),
            )
            if on_succeeded_report is not None:
                on_succeeded_report(dict(report))
            return

        if fmt2 == "merge_signal_entries":
            repm2 = report.get("report") if isinstance(report, dict) else None
            output_user_m2 = str(repm2.get("output_gil") or "") if isinstance(repm2, dict) else ""
            removed_entries_m2 = int(repm2.get("removed_signal_entries") or 0) if isinstance(repm2, dict) else 0
            node_changes_m2 = int(repm2.get("node_instance_id_changes") or 0) if isinstance(repm2, dict) else 0
            pin_patches_m2 = int(repm2.get("node_pin_patches") or 0) if isinstance(repm2, dict) else 0
            dialog_utils.show_info_dialog(
                dialog,
                "修复完成",
                "\n".join(
                    [
                        "已生成修复版 .gil：",
                        f"- 输出路径：{output_user_m2}",
                        f"- 移除信号条目：{removed_entries_m2}",
                        f"- 节点引用更新次数：{node_changes_m2}",
                        f"- pin 端口索引修补次数：{pin_patches_m2}",
                    ]
                ),
            )
            if on_succeeded_report is not None:
                on_succeeded_report(dict(report))
            return

        graphs_rep = report.get("graphs") if isinstance(report, dict) else None
        tpl_rep = report.get("templates") if isinstance(report, dict) else None
        tpl_bundle_rep = report.get("templates_instances_bundle") if isinstance(report, dict) else None
        tpl_missing_source = report.get("templates_missing_source_info") if isinstance(report, dict) else None
        player_tpl_rep = report.get("player_templates") if isinstance(report, dict) else None
        structs_rep = report.get("basic_structs") if isinstance(report, dict) else None
        signals_rep = report.get("signals") if isinstance(report, dict) else None

        gia_lines: list[str] = ["已导出 .gia："]
        if precheck_skipped_inputs:
            gia_lines.append(f"注意：预检阶段自动跳过 {len(precheck_skipped_inputs)} 个输入文件（见导出中心历史/执行页结果）。")
        if isinstance(graphs_rep, dict):
            exported = graphs_rep.get("exported_graphs")
            gia_lines.append(f"- 节点图：{len(exported) if isinstance(exported, list) else 0} 个（out={graphs_rep.get('output_dir','')}）")

        # 元件导出：可能同时包含
        # - 保真切片：export_project_templates_instances_bundle_gia（report key: exported, templates_instances_dir）
        # - 空模型导出：export_project_templates_to_gia（report key: exported_templates, templates_dir）
        bundle_rep: dict | None = None
        if isinstance(tpl_bundle_rep, dict) and isinstance(tpl_bundle_rep.get("exported"), list):
            bundle_rep = dict(tpl_bundle_rep)
        elif isinstance(tpl_rep, dict) and isinstance(tpl_rep.get("exported"), list) and not isinstance(tpl_rep.get("exported_templates"), list):
            # 兼容旧 report：曾把 bundle.gia 切片报告写在 templates 下
            bundle_rep = dict(tpl_rep)

        bundle_count = 0
        bundle_out = ""
        if isinstance(bundle_rep, dict):
            exported = bundle_rep.get("exported")
            bundle_count = len(exported) if isinstance(exported, list) else 0
            bundle_out = str(bundle_rep.get("templates_instances_dir") or bundle_rep.get("output_dir") or "").strip()

        empty_count = 0
        empty_out = ""
        if isinstance(tpl_rep, dict) and isinstance(tpl_rep.get("exported_templates"), list):
            exported = tpl_rep.get("exported_templates")
            empty_count = len(exported) if isinstance(exported, list) else 0
            empty_out = str(tpl_rep.get("templates_dir") or tpl_rep.get("output_dir") or "").strip()

        if int(bundle_count) > 0 and int(empty_count) > 0:
            gia_lines.append(f"- 元件：{int(bundle_count)} 个（保真切片，out={bundle_out}） + {int(empty_count)} 个（模板导出，out={empty_out}）")
        elif int(bundle_count) > 0:
            gia_lines.append(f"- 元件：{int(bundle_count)} 个（保真切片，out={bundle_out}）")
        elif int(empty_count) > 0:
            gia_lines.append(f"- 元件：{int(empty_count)} 个（模板导出，out={empty_out}）")

        if isinstance(player_tpl_rep, dict):
            exported = player_tpl_rep.get("exported_player_templates")
            pt_count = len(exported) if isinstance(exported, list) else int(player_tpl_rep.get("player_templates_total") or 0)
            pt_out = str(player_tpl_rep.get("player_templates_dir") or player_tpl_rep.get("output_dir") or "").strip()
            gia_lines.append(f"- 玩家模板：{int(pt_count)} 个（out={pt_out}）")

        if isinstance(tpl_missing_source, list) and tpl_missing_source:
            missing_with_decorations = 0
            for item in list(tpl_missing_source):
                if not isinstance(item, dict):
                    continue
                if bool(item.get("has_decorations")):
                    missing_with_decorations += 1
            if int(missing_with_decorations) > 0:
                gia_lines.append(
                    f"注意：{int(missing_with_decorations)} 个元件模板包含装饰物，但本次仅导出模板（自定义变量），装饰物实例未随 .gia 导出。"
                )
        if isinstance(structs_rep, dict):
            gia_lines.append(f"- 基础结构体：{int(structs_rep.get('structs_total') or 0)} 个（out={structs_rep.get('output_gia_file','')}）")
        if isinstance(signals_rep, dict):
            gia_lines.append(f"- 信号：{int(signals_rep.get('signals_total') or 0)} 个（out={signals_rep.get('output_gia_file','')}）")
        dialog_utils.show_info_dialog(dialog, "导出完成", "\n".join(gia_lines))
        if on_succeeded_report is not None:
            on_succeeded_report(dict(report2))

    def _on_failed(message: str) -> None:
        state["failed"] = True
        get_progress_widget(visible=False).set_status(label="失败", current=0, total=0)
        _set_busy(False)
        if on_failed_message is not None:
            on_failed_message(str(message or "导出失败（子进程失败）。"))
        dialog_utils.show_warning_dialog(dialog, "导出失败", str(message or "导出失败（子进程失败）。"))

    def _on_worker_finished() -> None:
        setattr(main_window, "_export_center_worker", None)
        if state["succeeded"] or state["failed"]:
            return
        get_progress_widget(visible=False).set_status(label="失败", current=0, total=0)
        _set_busy(False)
        if on_failed_message is not None:
            on_failed_message("导出失败（请查看控制台错误）。")
        dialog_utils.show_warning_dialog(dialog, "导出失败", "导出失败（请查看控制台错误）。")

    worker.progress_changed.connect(_on_progress)
    worker.succeeded.connect(_on_succeeded)
    worker.failed.connect(_on_failed)
    worker.finished.connect(worker.deleteLater)
    worker.finished.connect(_on_worker_finished)
    get_progress_widget(visible=True).set_status(label="准备导出…", current=0, total=0)
    worker.start()


def start_export_center_backfill_identify_action(
    *,
    QtCore: Any,
    main_window: Any,
    dialog: Any,
    workspace_root: Path,
    package_id: str,
    project_root: Path,
    picker: Any,
    format_combo: Any,
    gia: Any,
    gil: Any,
    panel: Any,
    rt: Any,
    set_backfill_table_rows: Callable[..., Any],
    update_backfill_panels: Callable[..., Any],
) -> None:
    """
    导出中心：点击“识别”的动作入口（UI 层编排）。
    """
    from app.ui.foundation import dialog_utils

    fmt = str(format_combo.currentData() or "gia")
    selected_items = list(picker.get_selected_items())
    graph_sel0 = build_graph_selection_from_resource_items(
        selected_items=selected_items,
        workspace_root=Path(workspace_root),
        package_id=str(package_id),
    )
    if not graph_sel0.graph_code_files:
        dialog_utils.show_warning_dialog(dialog, "提示", "请先在左侧勾选至少 1 个节点图，再执行识别。")
        return

    if fmt not in {"gia", "gil"}:
        dialog_utils.show_warning_dialog(dialog, "提示", "当前模式不支持识别。")
        return

    base_gil_text = ""
    id_ref_gil_text = ""
    ui_export_record_id: str | None = None
    use_base_as_id_ref_fallback = bool(fmt in {"gia", "gil"})
    if fmt == "gia":
        base_gil_text = str(gia.base_gil_edit.text() or "").strip()
        id_ref_gil_text = str(gia.gia_id_ref_edit.text() or "").strip()
        if not gia.ui_export_record_row.isHidden():
            rid0 = str(gia.ui_export_record_combo.currentData() or "").strip()
            ui_export_record_id = str(rid0) if rid0 != "" else None

        # 回退：未选择基底 .gil 时，优先使用 UI 回填记录绑定的 output_gil_file（若存在）
        if base_gil_text == "" and ui_export_record_id is not None:
            from ugc_file_tools.ui.export_records import try_get_ui_export_record_by_id

            rec0 = try_get_ui_export_record_by_id(
                workspace_root=Path(workspace_root),
                package_id=str(package_id),
                record_id=str(ui_export_record_id),
            )
            if rec0 is not None:
                base2 = str(rec0.payload.get("output_gil_file") or "").strip()
                if base2 != "":
                    base_gil_text = str(base2)

        # 回退：仍未选择 base 时，使用占位符参考 .gil 作为 base（用于 UI records 反查）
        if base_gil_text == "" and id_ref_gil_text != "":
            base_gil_text = str(id_ref_gil_text)
    else:
        use_builtin_empty_base = bool(getattr(gil, "use_builtin_empty_base_cb").isChecked())
        if use_builtin_empty_base:
            from ugc_file_tools.gil.builtin_empty_base import get_builtin_empty_base_gil_path

            base_gil_text = str(get_builtin_empty_base_gil_path())
        else:
            base_gil_text = str(gil.input_gil_edit.text() or "").strip()
        id_ref_gil_text = str(gil.gil_id_ref_edit.text() or "").strip()
        if not gil.gil_ui_export_record_row.isHidden():
            rid1 = str(gil.gil_ui_export_record_combo.currentData() or "").strip()
            ui_export_record_id = str(rid1) if rid1 != "" else None

    if base_gil_text == "":
        dialog_utils.show_warning_dialog(dialog, "提示", "请先选择一个用于识别的基础 .gil（或选择 UI 回填记录）。")
        return

    # 识别报告属于“运行期缓存”：每次重新识别都应覆盖，避免双击缺失行时读到旧的 report。
    setattr(rt, "backfill_last_identify_report", None)

    base_gil_path = Path(base_gil_text).resolve()
    if (not base_gil_path.is_file()) or base_gil_path.suffix.lower() != ".gil":
        dialog_utils.show_warning_dialog(dialog, "提示", f"基础 .gil 文件不存在或格式不正确：{str(base_gil_path)}")
        return

    id_ref_gil_path: Path | None = None
    if id_ref_gil_text != "":
        p0 = Path(id_ref_gil_text).resolve()
        if (not p0.is_file()) or p0.suffix.lower() != ".gil":
            dialog_utils.show_warning_dialog(dialog, "提示", f"占位符参考 .gil 文件不存在或格式不正确：{str(p0)}")
            return
        id_ref_gil_path = Path(p0)

    existing_worker = getattr(main_window, "_export_center_gil_identify_worker", None)
    is_running2 = getattr(existing_worker, "isRunning", None)
    if callable(is_running2) and bool(is_running2()):
        dialog_utils.show_warning_dialog(dialog, "提示", "已有一个识别任务正在运行，请等待完成后再开始新的识别。")
        return

    required_level_custom_vars: list[dict[str, str]] = []
    scan_ui_placeholder_vars = False
    ui_source_dir: Path | None = None
    ui_selected_html_stems: list[str] = []
    if fmt == "gil":
        for vid in list(gil.selected_level_custom_variable_ids or []):
            meta = gil.level_custom_variable_meta_by_id.get(str(vid))
            if isinstance(meta, dict):
                required_level_custom_vars.append(
                    {
                        "variable_id": str(meta.get("variable_id") or vid),
                        "variable_name": str(meta.get("variable_name") or ""),
                        "variable_type": str(meta.get("variable_type") or ""),
                        "source": str(meta.get("source") or ""),
                    }
                )
            else:
                required_level_custom_vars.append({"variable_id": str(vid), "variable_name": "", "variable_type": "", "source": ""})

        ui_src_selected = any(it.category == "ui_src" for it in selected_items)
        policy = compute_write_ui_effective_policy(
            fmt="gil",
            ui_src_selected=bool(ui_src_selected),
            user_choice=bool(rt.write_ui_user_choice),
        )
        scan_ui_placeholder_vars = bool(bool(policy.effective_write_ui) and bool(gil.ui_auto_sync_vars_cb.isChecked()))
        ui_dir = (Path(project_root) / "管理配置" / "UI源码").resolve()
        ui_source_dir = ui_dir if (bool(policy.effective_write_ui) and ui_dir.is_dir()) else None

        # 用于 UIKey 识别：仅把“本次选择的 UI源码 页面”纳入 bundle 扫描范围（避免误判）
        for it in list(selected_items):
            if str(getattr(it, "category", "")) != "ui_src":
                continue
            p = Path(getattr(it, "absolute_path", "")).resolve()
            if p.is_file() and p.suffix.lower() in {".html", ".htm"}:
                ui_selected_html_stems.append(str(p.stem))

    WorkerCls = make_export_center_gil_identify_worker_cls(QtCore=QtCore)
    worker = WorkerCls(
        base_gil_file_path=Path(base_gil_path),
        id_ref_gil_file_path=(Path(id_ref_gil_path) if id_ref_gil_path is not None else None),
        use_base_as_id_ref_fallback=bool(use_base_as_id_ref_fallback),
        workspace_root=Path(workspace_root),
        package_id=str(package_id),
        ui_export_record_id=(str(ui_export_record_id) if ui_export_record_id is not None else None),
        required_entity_names=frozenset(rt.id_ref_usage_for_selected_graphs.entity_names),
        required_component_names=frozenset(rt.id_ref_usage_for_selected_graphs.component_names),
        required_ui_keys=frozenset(rt.ui_keys_for_selected_graphs),
        ui_key_layout_hints_by_key=dict(rt.ui_key_layout_hints_by_key),
        required_level_custom_variables=list(required_level_custom_vars),
        scan_ui_placeholder_variables=bool(scan_ui_placeholder_vars),
        ui_source_dir=ui_source_dir,
        ui_selected_html_stems=list(ui_selected_html_stems),
        parent=main_window,
    )
    setattr(main_window, "_export_center_gil_identify_worker", worker)

    state = {"succeeded": False, "failed": False}
    panel.identify_btn.setEnabled(False)
    panel.progress_label.setText("识别中…")
    panel.progress_row.setVisible(True)
    panel.progress_bar.setRange(0, 0)
    panel.progress_bar.setValue(0)

    progress_state = {"last_total": 0}

    def _on_progress(current: int, total: int, label: str) -> None:
        c = int(current)
        t = int(total)
        progress_state["last_total"] = int(t)
        if t <= 0:
            panel.progress_bar.setRange(0, 0)
        else:
            # UI 约束：不到最终成功，不显示 100%。
            # 因此将“完成(100%)”作为额外的最后一步：max=total+1，value<=total。
            panel.progress_bar.setRange(0, t + 1)
            panel.progress_bar.setValue(min(max(c, 0), t))

    def _on_identify_succeeded(report: dict) -> None:
        state["succeeded"] = True
        setattr(rt, "backfill_last_identify_report", dict(report))
        last_total = int(progress_state.get("last_total") or 0)
        if last_total > 0:
            panel.progress_bar.setRange(0, last_total + 1)
            panel.progress_bar.setValue(last_total + 1)
        else:
            panel.progress_bar.setRange(0, 1)
            panel.progress_bar.setValue(1)
        rows = report.get("rows")
        rows_list = list(rows) if isinstance(rows, list) else []
        pending_rows = getattr(rt, "backfill_pending_rows", None)
        pending_list = list(pending_rows) if isinstance(pending_rows, list) else []

        def _row_key(d: object) -> tuple[str, str]:
            if not isinstance(d, dict):
                return "", ""
            return str(d.get("category") or ""), str(d.get("key") or "")

        merged_by_key: dict[tuple[str, str], dict[str, object]] = {}
        ordered: list[tuple[str, str]] = []
        for r0 in pending_list:
            k0 = _row_key(r0)
            if k0 == ("", ""):
                continue
            merged_by_key[k0] = dict(r0)
            ordered.append(k0)
        for r1 in rows_list:
            k1 = _row_key(r1)
            if k1 == ("", ""):
                continue
            if k1 in merged_by_key:
                merged_by_key[k1].update(dict(r1))
            else:
                merged_by_key[k1] = dict(r1)
                ordered.append(k1)
        merged_rows = [merged_by_key[k] for k in ordered if k in merged_by_key]
        set_backfill_table_rows(panel, rows=merged_rows)
        update_backfill_panels()
        panel.progress_label.setText("")
        panel.progress_row.setVisible(False)

    def _on_identify_failed(message: str) -> None:
        state["failed"] = True
        panel.progress_bar.setRange(0, 1)
        panel.progress_bar.setValue(0)
        panel.progress_label.setText("")
        panel.progress_row.setVisible(False)
        dialog_utils.show_warning_dialog(dialog, "识别失败", str(message or "识别失败。"))
        update_backfill_panels()

    def _on_identify_finished() -> None:
        setattr(main_window, "_export_center_gil_identify_worker", None)
        if state["succeeded"] or state["failed"]:
            return
        panel.progress_bar.setRange(0, 1)
        panel.progress_bar.setValue(0)
        panel.progress_label.setText("")
        panel.progress_row.setVisible(False)
        update_backfill_panels()

    worker.progress_changed.connect(_on_progress)
    worker.succeeded.connect(_on_identify_succeeded)
    worker.failed.connect(_on_identify_failed)
    worker.finished.connect(worker.deleteLater)
    worker.finished.connect(_on_identify_finished)
    worker.start()


__all__ = [
    "start_export_center_action",
    "start_export_center_backfill_identify_action",
]

