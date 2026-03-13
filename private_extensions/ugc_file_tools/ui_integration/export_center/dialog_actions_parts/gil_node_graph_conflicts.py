from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from .base_gil_conflicts import (
    BaseGilConflictsScanCache,
    compute_base_gil_conflicts_scan_needs_from_plan,
    ensure_base_gil_conflicts_report,
)
from .precheck_utils import record_precheck_skip


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


def _extract_base_node_graph_ids(*, base_report: dict[str, object]) -> dict[str, dict[str, int]]:
    """从 base report 中抽取 (scope, name)->graph_id 的映射。"""

    base_by_scope_and_name: dict[str, dict[str, int]] = {"server": {}, "client": {}}
    raw_scoped = base_report.get("node_graph_id_by_scope_and_name")
    if not isinstance(raw_scoped, dict):
        return dict(base_by_scope_and_name)
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
    return dict(base_by_scope_and_name)


def _clean_and_collect_graph_infos(
    *, plan_obj: Any, precheck_skipped_inputs: list[dict[str, str]]
) -> tuple[Any, list[dict[str, object]]]:
    """预检过滤节点图代码文件并收集用于冲突检查的图信息。"""

    from ugc_file_tools.project_archive_importer.node_graphs_importer_parts.constants import (
        GRAPH_NAME_LINE_RE,
        GRAPH_TYPE_LINE_RE,
        SCAN_HEAD_CHARS,
    )

    selected_infos: list[dict[str, object]] = []
    cleaned_graph_files: list[Path] = []
    for p in list(getattr(plan_obj, "selected_graph_code_files", []) or []):
        path = Path(p).resolve()
        if not path.is_file():
            record_precheck_skip(precheck_skipped_inputs=precheck_skipped_inputs, category="node_graphs", file_path=path, reason="文件不存在")
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
                record_precheck_skip(
                    precheck_skipped_inputs=precheck_skipped_inputs,
                    category="node_graphs",
                    file_path=path,
                    reason="无法推断节点图 scope（graph_type 缺失且路径不含 /server 或 /client）",
                )
                continue
        cleaned_graph_files.append(path)
        selected_infos.append({"graph_code_file": path, "scope": scope2, "graph_name": graph_name})

    if len(cleaned_graph_files) != len(list(getattr(plan_obj, "selected_graph_code_files", []) or [])):
        plan_obj = replace(plan_obj, selected_graph_code_files=list(cleaned_graph_files))
    return plan_obj, list(selected_infos)


def _build_conflict_graphs(
    *, selected_infos: list[dict[str, object]], base_by_scope_and_name: dict[str, dict[str, int]], scan_ok: bool
) -> list[dict[str, object]]:
    """构造节点图同名冲突条目列表供 UI 弹窗展示。"""

    conflict_graphs: list[dict[str, object]] = []
    if bool(scan_ok):
        for it in list(selected_infos):
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
        for it in list(selected_infos):
            conflict_graphs.append(
                {
                    "graph_code_file": str(it["graph_code_file"]),
                    "scope": str(it["scope"]),
                    "graph_name": str(it["graph_name"]),
                    "existing_graph_id_int": None,
                }
            )
    return list(conflict_graphs)


def _prompt_node_graph_conflicts_dialog(
    *, QtCore: Any, dialog: Any, conflict_graphs: list[dict[str, object]]
) -> list[dict[str, object]] | None:
    """弹出节点图冲突策略对话框并返回用户选择。"""

    from PyQt6 import QtWidgets
    from app.ui.foundation.theme_manager import Colors, Sizes
    from ...export_center_gil_conflicts_dialog import open_export_center_gil_node_graph_conflicts_dialog

    return open_export_center_gil_node_graph_conflicts_dialog(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        Sizes=Sizes,
        parent_dialog=dialog,
        conflict_graphs=list(conflict_graphs),
    )


def _apply_node_graph_conflict_choices(
    *,
    plan_obj: Any,
    selected_infos: list[dict[str, object]],
    conflict_graphs: list[dict[str, object]],
    base_by_scope_and_name: dict[str, dict[str, int]],
    scan_ok: bool,
    user_choices: list[dict[str, object]],
) -> Any:
    """将节点图冲突用户选择写回到 plan（含 new_graph_name 分配与 skip 过滤）。"""

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
        "server": {str(n).casefold() for n in base_by_scope_and_name.get("server", {}).keys()} if bool(scan_ok) else set(),
        "client": {str(n).casefold() for n in base_by_scope_and_name.get("client", {}).keys()} if bool(scan_ok) else set(),
    }
    for it in list(selected_infos):
        fp_cf = str(Path(it["graph_code_file"]).resolve()).casefold()
        act0 = actions_by_graph_file_cf.get(fp_cf, "overwrite")
        if act0 in {"skip", "add"}:
            continue
        scope4 = str(it["scope"])
        used_names_cf_by_scope.setdefault(scope4, set()).add(str(it["graph_name"]).casefold())

    new_name_by_graph_file_cf: dict[str, str] = {}
    for it in list(selected_infos):
        fp_cf = str(Path(it["graph_code_file"]).resolve()).casefold()
        if actions_by_graph_file_cf.get(fp_cf) == "add":
            if bool(scan_ok):
                used = used_names_cf_by_scope.setdefault(str(it["scope"]), set())
                new_name_by_graph_file_cf[fp_cf] = _alloc_new_name_sequential(base_name=str(it["graph_name"]), used_casefold=used)
            else:
                new_name_by_graph_file_cf[fp_cf] = _alloc_new_name_fallback(base_name=str(it["graph_name"]))

    resolutions: list[dict[str, str]] = []
    for it in list(conflict_graphs):
        fp2 = str(it.get("graph_code_file") or "").strip()
        if fp2 == "":
            continue
        fp2_resolved = str(Path(fp2).resolve())
        act2 = str(actions_by_graph_file_cf.get(fp2_resolved.casefold(), "overwrite") or "overwrite").strip().lower()
        if act2 == "add":
            new_name = str(new_name_by_graph_file_cf.get(fp2_resolved.casefold(), "") or "").strip()
            resolutions.append({"graph_code_file": fp2_resolved, "action": "add", "new_graph_name": new_name})
        elif act2 == "skip":
            resolutions.append({"graph_code_file": fp2_resolved, "action": "skip"})
        else:
            resolutions.append({"graph_code_file": fp2_resolved, "action": "overwrite"})

    selected_graph_files2: list[Path] = []
    for p in list(getattr(plan_obj, "selected_graph_code_files", []) or []):
        rp = str(Path(p).resolve())
        if actions_by_graph_file_cf.get(rp.casefold(), "overwrite") == "skip":
            continue
        selected_graph_files2.append(Path(p))

    return replace(
        plan_obj,
        selected_graph_code_files=list(selected_graph_files2),
        node_graph_conflict_resolutions=list(resolutions),
    )


def resolve_gil_node_graph_conflicts(
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
    """处理节点图同名冲突策略并更新 plan。"""

    from ..plans import _ExportGilPlan

    if not isinstance(plan_obj, _ExportGilPlan) or not bool(plan_obj.selected_graph_code_files):
        return plan_obj

    plan_obj, selected_infos = _clean_and_collect_graph_infos(plan_obj=plan_obj, precheck_skipped_inputs=precheck_skipped_inputs)
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

    base_by_scope_and_name = _extract_base_node_graph_ids(base_report=base_report)
    conflict_graphs = _build_conflict_graphs(selected_infos=list(selected_infos), base_by_scope_and_name=dict(base_by_scope_and_name), scan_ok=bool(scan_ok))
    if not conflict_graphs:
        return plan_obj

    user_choices = _prompt_node_graph_conflicts_dialog(QtCore=QtCore, dialog=dialog, conflict_graphs=list(conflict_graphs))
    if user_choices is None:
        return None

    return _apply_node_graph_conflict_choices(
        plan_obj=plan_obj,
        selected_infos=list(selected_infos),
        conflict_graphs=list(conflict_graphs),
        base_by_scope_and_name=dict(base_by_scope_and_name),
        scan_ok=bool(scan_ok),
        user_choices=list(user_choices or []),
    )


__all__ = [
    "resolve_gil_node_graph_conflicts",
]

