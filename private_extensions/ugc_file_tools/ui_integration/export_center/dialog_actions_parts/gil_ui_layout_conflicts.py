from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from dataclasses import replace

from .base_gil_conflicts import (
    BaseGilConflictsScanCache,
    compute_base_gil_conflicts_scan_needs_from_plan,
    ensure_base_gil_conflicts_report,
)
from .constants import (
    UI_BUNDLE_JSON_SUFFIX,
    UI_BUNDLE_MODE_KEY_BYTES,
    UI_BUNDLE_MODE_REQUIRED_BYTES,
    UI_BUNDLE_MODE_SCAN_WINDOW_BYTES,
    UI_HTML_FILE_SUFFIXES,
)


def _has_raw_template_writeback(*, project_root: Path) -> bool:
    """判断是否存在 raw_template 写回输入以跳过 Workbench bundle 冲突策略。"""

    ui_dir = Path(project_root) / "管理配置" / "UI控件模板" / "原始解析"
    return bool(ui_dir.is_dir() and any(ui_dir.glob("ugc_ui_widget_template_*.raw.json")))


def _collect_bundle_files(*, project_root: Path) -> tuple[Path, list[Path]]:
    """收集 UI Workbench bundle 文件列表。"""

    bundle_dir = (Path(project_root) / "管理配置" / "UI源码" / "__workbench_out__").resolve()
    bundle_files = [
        p.resolve() for p in sorted(bundle_dir.glob(f"*{UI_BUNDLE_JSON_SUFFIX}"), key=lambda x: x.as_posix()) if p.is_file()
    ]
    return bundle_dir, list(bundle_files)


def _infer_layout_name_from_bundle_file(*, bundle_path: Path) -> str:
    """从 `*.ui_bundle.json` 文件名推断 layout_name。"""

    name = str(Path(bundle_path).name)
    if name.endswith(UI_BUNDLE_JSON_SUFFIX):
        return name[: -len(UI_BUNDLE_JSON_SUFFIX)]
    return str(Path(bundle_path).stem)


def _build_html_files_to_check(*, selected_ui_html_files: list[Path], bundle_files: list[Path], ui_src_dir: Path) -> list[Path]:
    """构造需要检查“HTML vs bundle 过期/缺失”的 HTML 列表。"""

    if selected_ui_html_files:
        return [Path(p).resolve() for p in list(selected_ui_html_files)]

    html_files_to_check: list[Path] = []
    for p in list(bundle_files):
        stem = _infer_layout_name_from_bundle_file(bundle_path=Path(p))
        for ext in UI_HTML_FILE_SUFFIXES:
            candidate = (Path(ui_src_dir) / f"{stem}{ext}").resolve()
            if candidate.is_file():
                html_files_to_check.append(candidate)
                break
    return list(html_files_to_check)


def _compute_stale_pairs_and_missing_bundles(*, html_files_to_check: list[Path], bundle_dir: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """计算哪些 HTML 对应的 bundle 缺失或过期（mtime 或导出模式）。"""

    stale_pairs: list[dict[str, object]] = []
    missing_bundles: list[dict[str, object]] = []
    for html_path in list(html_files_to_check):
        hp = Path(html_path).resolve()
        if not hp.is_file():
            continue
        expected_bundle = (Path(bundle_dir) / f"{hp.stem}{UI_BUNDLE_JSON_SUFFIX}").resolve()
        if not expected_bundle.is_file():
            missing_bundles.append({"html": str(hp), "expected_bundle": str(expected_bundle)})
            continue

        html_mtime_ns = int(hp.stat().st_mtime_ns)
        bundle_mtime_ns = int(expected_bundle.stat().st_mtime_ns)
        stale_by_mtime = html_mtime_ns > bundle_mtime_ns
        stale_by_mode = False
        if not bool(stale_by_mtime):
            raw = expected_bundle.read_bytes()
            idx = raw.find(UI_BUNDLE_MODE_KEY_BYTES)
            if idx < 0:
                stale_by_mode = True
            else:
                window = raw[idx : idx + int(UI_BUNDLE_MODE_SCAN_WINDOW_BYTES)]
                stale_by_mode = UI_BUNDLE_MODE_REQUIRED_BYTES not in window

        if bool(stale_by_mtime) or bool(stale_by_mode):
            stale_pairs.append(
                {
                    "html": str(hp),
                    "bundle": str(expected_bundle),
                    "html_mtime_ns": int(html_mtime_ns),
                    "bundle_mtime_ns": int(bundle_mtime_ns),
                    "stale_by_mtime": bool(stale_by_mtime),
                    "stale_by_mode": bool(stale_by_mode),
                }
            )

    return list(stale_pairs), list(missing_bundles)


def _dedupe_paths_casefold(*, paths: list[Path]) -> list[Path]:
    """对路径按 casefold 去重并保持顺序。"""

    seen_cf: set[str] = set()
    out: list[Path] = []
    for p in list(paths):
        rp = Path(p).resolve()
        k = str(rp).casefold()
        if k in seen_cf:
            continue
        seen_cf.add(k)
        out.append(rp)
    return list(out)


def _collect_bundle_update_htmls(*, stale_pairs: list[dict[str, object]], missing_bundles: list[dict[str, object]]) -> list[Path]:
    """从 stale/missing 结果中提取需要更新 bundle 的 HTML 列表。"""

    need_update_htmls: list[Path] = []
    for it in list(stale_pairs):
        p = Path(str(it.get("html") or "")).resolve()
        if p.is_file():
            need_update_htmls.append(p)
    for it2 in list(missing_bundles):
        p2 = Path(str(it2.get("html") or "")).resolve()
        if p2.is_file():
            need_update_htmls.append(p2)
    return _dedupe_paths_casefold(paths=list(need_update_htmls))


def _maybe_prepare_bundle_update_plan(*, dialog: Any, plan_obj: Any, need_update_htmls: list[Path], missing_bundles: list[dict[str, object]]) -> Any | None:
    """在 UI HTML 被选择且 bundle 过期/缺失时决定是否自动更新 bundle 并写入 plan。"""

    from app.ui.foundation import dialog_utils

    if not need_update_htmls:
        return plan_obj

    import importlib.util

    if importlib.util.find_spec("playwright") is None:
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
            return None

        proceed = dialog_utils.ask_yes_no_dialog(
            dialog,
            "缺少 Playwright，无法自动更新 UI bundle",
            "\n".join(base_lines + ["", "是否继续导出（将使用旧 bundle，可能导出旧页面）？"]).strip(),
            default_yes=False,
        )
        if not bool(proceed):
            return None
        return plan_obj

    return replace(plan_obj, ui_workbench_bundle_update_html_files=list(need_update_htmls))


def _extract_base_layout_guid_by_name(*, base_report: dict[str, object]) -> dict[str, int]:
    """从 base report 中抽取 layout_name -> guid 映射。"""

    base_layout_guid_by_name: dict[str, int] = {}
    raw_map = base_report.get("ui_layout_guid_by_name")
    if not isinstance(raw_map, dict):
        return {}
    for k, v in raw_map.items():
        name = str(k or "").strip()
        if name == "":
            continue
        if not isinstance(v, int) or int(v) <= 0:
            continue
        base_layout_guid_by_name.setdefault(name, int(v))
    return dict(base_layout_guid_by_name)


def _build_conflict_layouts(
    *, bundle_layout_names: list[str], base_layout_guid_by_name: dict[str, int], scan_ok: bool
) -> list[dict[str, object]]:
    """根据 base 扫描结果构造“布局同名冲突”清单。"""

    conflict_layouts: list[dict[str, object]] = []
    if bool(scan_ok):
        for layout_name in list(bundle_layout_names):
            if layout_name in base_layout_guid_by_name:
                conflict_layouts.append({"layout_name": str(layout_name), "existing_guid": int(base_layout_guid_by_name[layout_name])})
    else:
        for layout_name in list(bundle_layout_names):
            conflict_layouts.append({"layout_name": str(layout_name), "existing_guid": None})
    return list(conflict_layouts)


def _alloc_new_name_sequential(*, base_name: str, used_casefold: set[str]) -> str:
    """按 `__new_{i}` 递增分配不冲突的新名字。"""

    prefix = str(base_name)
    i = 1
    while True:
        candidate = f"{prefix}__new_{i}"
        if candidate.casefold() not in used_casefold:
            used_casefold.add(candidate.casefold())
            return candidate
        i += 1


def _alloc_new_name_fallback(*, base_name: str) -> str:
    """在无法获知 base 名单时用随机后缀分配新名字。"""

    from uuid import uuid4

    return f"{str(base_name)}__new_{uuid4().hex[:8]}"


def _build_ui_layout_resolutions(
    *,
    bundle_layout_names: list[str],
    base_layout_guid_by_name: dict[str, int],
    scan_ok: bool,
    user_choices: list[dict[str, object]],
    conflict_layouts: list[dict[str, object]],
) -> list[dict[str, str]]:
    """将用户选择转换为 `ui_layout_conflict_resolutions`。"""

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

    used_casefold: set[str] = {str(n).casefold() for n in base_layout_guid_by_name.keys()} if bool(scan_ok) else set()
    for name in list(bundle_layout_names):
        act0 = actions_by_layout_name.get(name, "overwrite") if name in actions_by_layout_name else "overwrite"
        if act0 in {"skip", "add"}:
            continue
        used_casefold.add(str(name).casefold())

    new_name_by_layout_name: dict[str, str] = {}
    for name in list(bundle_layout_names):
        if actions_by_layout_name.get(name) == "add":
            if bool(scan_ok):
                new_name_by_layout_name[name] = _alloc_new_name_sequential(base_name=str(name), used_casefold=used_casefold)
            else:
                new_name_by_layout_name[name] = _alloc_new_name_fallback(base_name=str(name))

    resolutions: list[dict[str, str]] = []
    for it in list(conflict_layouts):
        ln = str(it.get("layout_name") or "").strip()
        if ln == "":
            continue
        act = str(actions_by_layout_name.get(ln, "overwrite") or "overwrite").strip().lower()
        if act == "add":
            resolutions.append(
                {"layout_name": ln, "action": "add", "new_layout_name": str(new_name_by_layout_name.get(ln) or "").strip()}
            )
        elif act == "skip":
            resolutions.append({"layout_name": ln, "action": "skip"})
        else:
            resolutions.append({"layout_name": ln, "action": "overwrite"})
    return list(resolutions)


def _ensure_bundle_files_available_or_warn(*, main_window: Any, plan_obj: Any) -> tuple[Path, list[Path]] | None:
    """确保 bundle 文件可用或用户已显式选择 HTML，否则提示并终止。"""

    from app.ui.foundation import dialog_utils

    bundle_dir, bundle_files = _collect_bundle_files(project_root=Path(plan_obj.project_root))
    if not bundle_files and not bool(plan_obj.selected_ui_html_files):
        dialog_utils.show_warning_dialog(
            main_window,
            "提示",
            "当前启用了 UI 写回，但未找到 UI Workbench bundle：\n"
            f"- {str(bundle_dir)}/*{UI_BUNDLE_JSON_SUFFIX}\n\n"
            "请先在 UI Workbench 导出（生成 __workbench_out__ 产物），或改用 raw_template 写回后再导出。",
        )
        return None
    return Path(bundle_dir), list(bundle_files)


def _maybe_update_plan_for_stale_bundles(*, dialog: Any, plan_obj: Any, bundle_dir: Path, bundle_files: list[Path]) -> Any | None:
    """在用户选择 HTML 且 bundle 过期/缺失时尝试把“更新 bundle”注入 plan。"""

    ui_src_dir = (Path(plan_obj.project_root) / "管理配置" / "UI源码").resolve()
    selected_project_ui_htmls = [Path(p).resolve() for p in list(plan_obj.selected_ui_html_files)]
    html_files_to_check = _build_html_files_to_check(
        selected_ui_html_files=list(selected_project_ui_htmls),
        bundle_files=list(bundle_files),
        ui_src_dir=Path(ui_src_dir),
    )
    stale_pairs, missing_bundles = _compute_stale_pairs_and_missing_bundles(html_files_to_check=list(html_files_to_check), bundle_dir=Path(bundle_dir))

    if (stale_pairs or missing_bundles) and selected_project_ui_htmls:
        need_update_htmls = _collect_bundle_update_htmls(stale_pairs=list(stale_pairs), missing_bundles=list(missing_bundles))
        return _maybe_prepare_bundle_update_plan(
            dialog=dialog,
            plan_obj=plan_obj,
            need_update_htmls=list(need_update_htmls),
            missing_bundles=list(missing_bundles),
        )
    return plan_obj


def _prompt_and_apply_ui_layout_conflicts(
    *,
    QtCore: Any,
    dialog: Any,
    main_window: Any,
    workspace_root: Path,
    plan_obj: Any,
    bundle_files: list[Path],
    base_scan_cache: BaseGilConflictsScanCache,
    set_busy_for_preflight: Callable[[bool], None],
    on_progress_changed: Callable[[int, int, str], Any] | None,
    get_progress_widget: Callable[..., Any],
    precheck_warnings: list[dict[str, str]],
) -> Any | None:
    """弹出 UI 布局冲突策略对话框并将用户决策写回到 plan。"""

    from ..plans import _ExportGilPlan

    if not isinstance(plan_obj, _ExportGilPlan):
        return plan_obj

    bundle_layout_names = (
        [str(p.stem) for p in list(plan_obj.selected_ui_html_files)]
        if plan_obj.selected_ui_html_files
        else [_infer_layout_name_from_bundle_file(bundle_path=p) for p in list(bundle_files)]
    )
    bundle_layout_names = [str(x).strip() for x in list(bundle_layout_names) if str(x).strip() != ""]
    if not bundle_layout_names:
        return plan_obj

    need_ui_layouts, need_node_graphs, need_templates, need_instances = compute_base_gil_conflicts_scan_needs_from_plan(plan_obj)
    base_report, scan_ok = ensure_base_gil_conflicts_report(
        cache=base_scan_cache,
        QtCore=QtCore,
        main_window=main_window,
        workspace_root=Path(workspace_root),
        input_gil_path=Path(plan_obj.input_gil_path).resolve(),
        need_ui_layouts=bool(need_ui_layouts),
        need_node_graphs=bool(need_node_graphs),
        need_templates=bool(need_templates),
        need_instances=bool(need_instances),
        set_busy=set_busy_for_preflight,
        on_progress=on_progress_changed,
        get_progress_widget=get_progress_widget,
        precheck_warnings=precheck_warnings,
    )

    base_layout_guid_by_name = _extract_base_layout_guid_by_name(base_report=base_report)
    conflict_layouts = _build_conflict_layouts(
        bundle_layout_names=list(bundle_layout_names),
        base_layout_guid_by_name=dict(base_layout_guid_by_name),
        scan_ok=bool(scan_ok),
    )
    if not conflict_layouts:
        return plan_obj

    from PyQt6 import QtWidgets
    from app.ui.foundation.theme_manager import Colors, Sizes
    from ...export_center_gil_conflicts_dialog import open_export_center_gil_ui_layout_conflicts_dialog

    user_choices = open_export_center_gil_ui_layout_conflicts_dialog(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        Sizes=Sizes,
        parent_dialog=dialog,
        conflict_layouts=list(conflict_layouts),
    )
    if user_choices is None:
        return None

    resolutions = _build_ui_layout_resolutions(
        bundle_layout_names=list(bundle_layout_names),
        base_layout_guid_by_name=dict(base_layout_guid_by_name),
        scan_ok=bool(scan_ok),
        user_choices=list(user_choices or []),
        conflict_layouts=list(conflict_layouts),
    )
    return replace(plan_obj, ui_layout_conflict_resolutions=list(resolutions))


def resolve_gil_ui_layout_conflicts(
    *,
    QtCore: Any,
    dialog: Any,
    main_window: Any,
    workspace_root: Path,
    plan_obj: Any,
    base_scan_cache: BaseGilConflictsScanCache,
    set_busy_for_preflight: Callable[[bool], None],
    on_progress_changed: Callable[[int, int, str], Any] | None,
    get_progress_widget: Callable[..., Any],
    precheck_warnings: list[dict[str, str]],
) -> Any | None:
    """处理 UI Workbench bundle 的布局同名冲突策略并更新 plan。"""

    from ..plans import _ExportGilPlan

    if not isinstance(plan_obj, _ExportGilPlan) or not bool(plan_obj.write_ui):
        return plan_obj

    if bool(_has_raw_template_writeback(project_root=Path(plan_obj.project_root))):
        return plan_obj

    bundle_info = _ensure_bundle_files_available_or_warn(main_window=main_window, plan_obj=plan_obj)
    if bundle_info is None:
        return None
    bundle_dir, bundle_files = bundle_info

    plan2 = _maybe_update_plan_for_stale_bundles(dialog=dialog, plan_obj=plan_obj, bundle_dir=Path(bundle_dir), bundle_files=list(bundle_files))
    if plan2 is None:
        return None
    plan_obj = plan2

    return _prompt_and_apply_ui_layout_conflicts(
        QtCore=QtCore,
        dialog=dialog,
        main_window=main_window,
        workspace_root=Path(workspace_root),
        plan_obj=plan_obj,
        bundle_files=list(bundle_files),
        base_scan_cache=base_scan_cache,
        set_busy_for_preflight=set_busy_for_preflight,
        on_progress_changed=on_progress_changed,
        get_progress_widget=get_progress_widget,
        precheck_warnings=precheck_warnings,
    )


__all__ = [
    "resolve_gil_ui_layout_conflicts",
]

