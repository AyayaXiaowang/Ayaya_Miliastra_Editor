from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from .base_gil_conflicts import (
    BaseGilConflictsScanCache,
    compute_base_gil_conflicts_scan_needs_from_plan,
    ensure_base_gil_conflicts_report,
)
from .conflict_utils import alloc_new_name_fallback, alloc_new_name_sequential, extract_int_map
from .precheck_utils import record_precheck_skip


def _clean_and_collect_template_infos(
    *, plan_obj: Any, precheck_skipped_inputs: list[dict[str, str]]
) -> tuple[Any, list[dict[str, object]]]:
    """预检过滤模板 JSON 并收集用于冲突检查的模板信息。"""

    import json

    selected_infos: list[dict[str, object]] = []
    cleaned_template_files: list[Path] = []
    for p in list(getattr(plan_obj, "selected_template_json_files", []) or []):
        path = Path(p).resolve()
        if not path.is_file():
            record_precheck_skip(precheck_skipped_inputs=precheck_skipped_inputs, category="templates", file_path=path, reason="文件不存在")
            continue
        obj = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            reason = "不是单模板 JSON（期望 dict；请不要选择 templates_index.json 这类索引文件）"
            if path.name == "templates_index.json":
                reason = "templates_index.json 是索引列表，不是单模板 JSON（每文件一个模板 dict）"
            record_precheck_skip(precheck_skipped_inputs=precheck_skipped_inputs, category="templates", file_path=path, reason=reason)
            continue
        template_id_text = str(obj.get("template_id") or "").strip()
        if template_id_text == "":
            record_precheck_skip(precheck_skipped_inputs=precheck_skipped_inputs, category="templates", file_path=path, reason="缺少 template_id")
            continue
        cleaned_template_files.append(path)

        template_name = str(obj.get("name") or "").strip() or template_id_text
        metadata = obj.get("metadata")
        ugc = metadata.get("ugc") if isinstance(metadata, dict) else None
        is_placeholder = bool(ugc.get("placeholder")) if isinstance(ugc, dict) else False
        if bool(is_placeholder):
            continue
        selected_infos.append({"template_json_file": path, "template_id_text": template_id_text, "template_name": template_name})

    if len(cleaned_template_files) != len(list(getattr(plan_obj, "selected_template_json_files", []) or [])):
        plan_obj = replace(plan_obj, selected_template_json_files=list(cleaned_template_files))
    return plan_obj, list(selected_infos)


def _build_conflict_templates(
    *, selected_infos: list[dict[str, object]], base_template_id_by_name: dict[str, int], scan_ok: bool
) -> list[dict[str, object]]:
    """构造模板同名冲突条目列表供 UI 弹窗展示。"""

    conflict_templates: list[dict[str, object]] = []
    if bool(scan_ok):
        for it in list(selected_infos):
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
        for it in list(selected_infos):
            conflict_templates.append(
                {
                    "template_json_file": str(it["template_json_file"]),
                    "template_name": str(it["template_name"]),
                    "existing_template_id_int": None,
                }
            )
    return list(conflict_templates)


def _prompt_template_conflicts_dialog(
    *, QtCore: Any, dialog: Any, conflict_templates: list[dict[str, object]]
) -> list[dict[str, object]] | None:
    """弹出模板冲突策略对话框并返回用户选择。"""

    from PyQt6 import QtWidgets
    from app.ui.foundation.theme_manager import Colors, Sizes
    from ...export_center_gil_conflicts_dialog import open_export_center_gil_template_conflicts_dialog

    return open_export_center_gil_template_conflicts_dialog(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        Sizes=Sizes,
        parent_dialog=dialog,
        conflict_templates=list(conflict_templates),
    )


def _apply_template_conflict_choices(
    *,
    plan_obj: Any,
    selected_infos: list[dict[str, object]],
    conflict_templates: list[dict[str, object]],
    base_template_id_by_name: dict[str, int],
    scan_ok: bool,
    user_choices: list[dict[str, object]],
) -> Any:
    """将模板冲突用户选择写回到 plan（含 new_template_name 分配与 skip 过滤）。"""

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
    for it in list(selected_infos):
        fp_cf = str(Path(str(it["template_json_file"])).resolve()).casefold()
        act0 = actions_by_tpl_file_cf.get(fp_cf, "overwrite")
        if act0 in {"skip", "add"}:
            continue
        used_tpl_names_cf.add(str(it["template_name"]).casefold())

    by_file_cf: dict[str, dict[str, object]] = {str(Path(str(it["template_json_file"])).resolve()).casefold(): dict(it) for it in selected_infos}
    new_name_by_tpl_file_cf: dict[str, str] = {}
    for fp_cf, it in list(by_file_cf.items()):
        if actions_by_tpl_file_cf.get(fp_cf) == "add":
            if bool(scan_ok):
                new_name_by_tpl_file_cf[fp_cf] = alloc_new_name_sequential(base_name=str(it["template_name"]), used_casefold=used_tpl_names_cf)
            else:
                new_name_by_tpl_file_cf[fp_cf] = alloc_new_name_fallback(base_name=str(it["template_name"]))

    resolutions: list[dict[str, str]] = []
    for it in list(conflict_templates):
        fp2 = str(it.get("template_json_file") or "").strip()
        if fp2 == "":
            continue
        rp = str(Path(fp2).resolve())
        act2 = str(actions_by_tpl_file_cf.get(rp.casefold(), "overwrite") or "overwrite").strip().lower()
        if act2 == "add":
            resolutions.append(
                {"template_json_file": rp, "action": "add", "new_template_name": str(new_name_by_tpl_file_cf.get(rp.casefold(), "") or "").strip()}
            )
        elif act2 == "skip":
            resolutions.append({"template_json_file": rp, "action": "skip"})
        else:
            resolutions.append({"template_json_file": rp, "action": "overwrite"})

    selected_template_files2: list[Path] = []
    for p in list(getattr(plan_obj, "selected_template_json_files", []) or []):
        rp2 = str(Path(p).resolve())
        if actions_by_tpl_file_cf.get(rp2.casefold(), "overwrite") == "skip":
            continue
        selected_template_files2.append(Path(p))

    return replace(
        plan_obj,
        selected_template_json_files=list(selected_template_files2),
        template_conflict_resolutions=list(resolutions),
    )


def resolve_gil_template_conflicts(
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
    precheck_skipped_inputs: list[dict[str, str]],
    precheck_warnings: list[dict[str, str]],
) -> Any | None:
    """处理模板同名冲突策略并更新 plan。"""

    from ..plans import _ExportGilPlan

    if not isinstance(plan_obj, _ExportGilPlan) or not bool(plan_obj.selected_template_json_files):
        return plan_obj

    plan_obj, selected_infos = _clean_and_collect_template_infos(plan_obj=plan_obj, precheck_skipped_inputs=precheck_skipped_inputs)
    if not selected_infos:
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

    base_template_id_by_name = extract_int_map(base_report=base_report, key="template_id_by_name")
    conflict_templates = _build_conflict_templates(
        selected_infos=list(selected_infos),
        base_template_id_by_name=dict(base_template_id_by_name),
        scan_ok=bool(scan_ok),
    )
    if not conflict_templates:
        return plan_obj

    user_choices = _prompt_template_conflicts_dialog(QtCore=QtCore, dialog=dialog, conflict_templates=list(conflict_templates))
    if user_choices is None:
        return None

    return _apply_template_conflict_choices(
        plan_obj=plan_obj,
        selected_infos=list(selected_infos),
        conflict_templates=list(conflict_templates),
        base_template_id_by_name=dict(base_template_id_by_name),
        scan_ok=bool(scan_ok),
        user_choices=list(user_choices or []),
    )


__all__ = [
    "resolve_gil_template_conflicts",
]

