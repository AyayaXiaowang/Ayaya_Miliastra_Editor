from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..export_center.mgmt_cfg_ids import _collect_writeback_ids_from_mgmt_cfg_items
from ..export_center.preview_models import (
    build_gia_preview_texts,
    build_gil_preview_texts,
    build_merge_signal_entries_preview_texts,
    build_repair_signals_preview_texts,
)
from ..export_center.write_ui_policy import compute_write_ui_effective_policy

from .env import ExportCenterDialogWiringEnv

_DEFER_SELECTION_UPDATE_DELAY_MS = 0
_LEVEL_VARS_PREVIEW_MAX_NAMES = 8


def _collect_selected_counts(selected_items: list[object]) -> dict[str, int]:
    """统计当前选择的资源数量并按类别返回计数。"""

    return {
        "graphs": sum(1 for it in selected_items if getattr(it, "category", None) == "graphs"),
        "templates": sum(1 for it in selected_items if getattr(it, "category", None) == "templates"),
        "instances": sum(1 for it in selected_items if getattr(it, "category", None) == "instances"),
        "player_templates": sum(1 for it in selected_items if getattr(it, "category", None) == "player_templates"),
        "mgmt_cfg": sum(1 for it in selected_items if getattr(it, "category", None) == "mgmt_cfg"),
        "ui_src": sum(1 for it in selected_items if getattr(it, "category", None) == "ui_src"),
        "custom_vars": sum(1 for it in selected_items if getattr(it, "category", None) == "custom_vars"),
    }


def _sync_ui_custom_vars_autoselect(env: ExportCenterDialogWiringEnv, selected_items: list[object]) -> bool:
    """根据勾选的 UI HTML 自动勾选对应 owner 的自定义变量条目并返回是否触发了异步勾选。"""

    selected_ui_html_files = [
        Path(getattr(it, "absolute_path")).resolve()
        for it in selected_items
        if str(getattr(it, "category", "") or "") == "ui_src"
        and str(getattr(it, "source_root", "") or "") == "project"
        and str(Path(getattr(it, "absolute_path")).suffix).lower() in {".html", ".htm"}
    ]
    selected_ui_html_files.sort(key=lambda x: x.as_posix().casefold())

    from ugc_file_tools.auto_custom_variable_registry_bridge import OWNER_LEVEL, OWNER_PLAYER
    from ugc_file_tools.auto_custom_variable_registry_bridge import (
        try_load_auto_custom_variable_registry_index_from_project_root,
    )
    from ugc_file_tools.node_graph_writeback.ui_custom_variable_sync import (
        scan_ui_html_files_for_placeholder_variable_refs_and_defaults,
    )
    from ugc_file_tools.ui_integration.resource_picker import build_custom_var_owner_select_all_item_key_for_project

    package_root = (Path(env.workspace_root).resolve() / "assets" / "资源库" / "项目存档" / str(env.package_id)).resolve()
    if not selected_ui_html_files:
        if getattr(env.rt, "ui_auto_selected_custom_var_keys", None):
            keys_to_remove = list(env.rt.ui_auto_selected_custom_var_keys)
            env.rt.ui_auto_selected_custom_var_keys = set()
            if keys_to_remove:
                env.QtCore.QTimer.singleShot(
                    _DEFER_SELECTION_UPDATE_DELAY_MS,
                    lambda keys=keys_to_remove: env.picker.remove_keys(list(keys)),
                )
                return True
        return False

    idx = try_load_auto_custom_variable_registry_index_from_project_root(project_root=package_root)
    if idx is None:
        return False

    scan = scan_ui_html_files_for_placeholder_variable_refs_and_defaults(selected_ui_html_files)
    required: set[tuple[str, str]] = set()
    for g, n, _path in set(scan.variable_refs or set()):
        gg = str(g or "").strip()
        nn = str(n or "").strip()
        if gg and nn:
            required.add((gg, nn))
    for full_name in dict(scan.normalized_variable_defaults or {}).keys():
        full = str(full_name or "").strip()
        if "." not in full:
            continue
        g, _, n = full.partition(".")
        if str(g).strip() and str(n).strip():
            required.add((str(g).strip(), str(n).strip()))

    group_to_owner = {"关卡": OWNER_LEVEL, "玩家自身": OWNER_PLAYER}
    auto_keys: set[str] = set()
    for group_name, _var_name in sorted(required, key=lambda t: (t[0].casefold(), t[1].casefold())):
        owner = group_to_owner.get(str(group_name))
        if owner is None:
            continue
        auto_keys.add(build_custom_var_owner_select_all_item_key_for_project(owner_ref=str(owner)))

    env.rt.ui_auto_selected_custom_var_keys = set(auto_keys)
    to_add = sorted(set(auto_keys) - set(env.picker.get_selected_keys()), key=lambda s: str(s).casefold())
    if to_add:
        env.QtCore.QTimer.singleShot(
            _DEFER_SELECTION_UPDATE_DELAY_MS,
            lambda keys=to_add: env.picker.add_keys(list(keys)),
        )
        return True
    return False


def _load_json_index_map(*, index_path: Path, id_key: str, package_root: Path) -> dict[str, tuple[str, str]]:
    """加载索引 JSON 并返回 abs_path_cf 到 (owner_ref, display_name) 的映射。"""

    import json  # local import: avoid adding weight to module import time

    if not index_path.is_file():
        return {}
    obj = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(obj, list):
        return {}
    out: dict[str, tuple[str, str]] = {}
    for item in obj:
        if not isinstance(item, dict):
            continue
        rid = str(item.get(id_key) or "").strip()
        nm = str(item.get("name") or "").strip()
        rel_out = str(item.get("output") or "").replace("\\", "/").strip()
        if not rid or not rel_out:
            continue
        abs_path = (package_root / rel_out).resolve()
        out[str(abs_path).casefold()] = (rid, nm)
    return out


def _sync_asset_custom_vars_autoselect(env: ExportCenterDialogWiringEnv, selected_items: list[object]) -> bool:
    """根据勾选的元件/实体自动勾选第三方 owner 的自定义变量条目并返回是否触发了异步勾选。"""

    from ugc_file_tools.ui_integration.resource_picker import build_custom_var_owner_select_all_item_key_for_project

    package_root = (Path(env.workspace_root).resolve() / "assets" / "资源库" / "项目存档" / str(env.package_id)).resolve()
    templates_map = _load_json_index_map(
        index_path=(package_root / "元件库" / "templates_index.json").resolve(),
        id_key="template_id",
        package_root=package_root,
    )
    instances_map = _load_json_index_map(
        index_path=(package_root / "实体摆放" / "instances_index.json").resolve(),
        id_key="instance_id",
        package_root=package_root,
    )

    desired_asset_keys: set[str] = set()
    for it in selected_items:
        cat = str(getattr(it, "category", "") or "")
        if cat not in {"templates", "instances"}:
            continue
        if str(getattr(it, "source_root", "") or "") != "project":
            continue
        abs_cf = str(Path(getattr(it, "absolute_path")).resolve()).casefold()
        if cat == "templates":
            ref = templates_map.get(abs_cf)
            if ref is None:
                continue
            owner_ref, display = ref
            desired_asset_keys.add(
                build_custom_var_owner_select_all_item_key_for_project(owner_ref=str(owner_ref), owner_display=str(display))
            )
        else:
            ref = instances_map.get(abs_cf)
            if ref is None:
                continue
            owner_ref, display = ref
            desired_asset_keys.add(
                build_custom_var_owner_select_all_item_key_for_project(owner_ref=str(owner_ref), owner_display=str(display))
            )

    current_asset_auto = set(getattr(env.rt, "asset_auto_selected_custom_var_keys", set()) or set())
    to_remove_asset = sorted(current_asset_auto - set(desired_asset_keys), key=lambda s: str(s).casefold())
    if to_remove_asset:
        env.rt.asset_auto_selected_custom_var_keys = set(desired_asset_keys)
        env.QtCore.QTimer.singleShot(
            _DEFER_SELECTION_UPDATE_DELAY_MS,
            lambda keys=to_remove_asset: env.picker.remove_keys(list(keys)),
        )
        return True

    env.rt.asset_auto_selected_custom_var_keys = set(desired_asset_keys)
    to_add_asset = sorted(set(desired_asset_keys) - set(env.picker.get_selected_keys()), key=lambda s: str(s).casefold())
    if to_add_asset:
        env.QtCore.QTimer.singleShot(
            _DEFER_SELECTION_UPDATE_DELAY_MS,
            lambda keys=to_add_asset: env.picker.add_keys(list(keys)),
        )
        return True
    return False


def _sync_level_custom_variables_preview(env: ExportCenterDialogWiringEnv, selected_items: list[object]) -> int:
    """同步关卡实体自定义变量选择的预览文案并返回当前变量数量。"""

    fmt = str(env.format_combo.currentData() or "gia")
    if fmt != "gil":
        env.gil.selected_level_custom_variable_ids[:] = []
        env.gil.level_custom_variable_meta_by_id.clear()
        env.gil.level_vars_preview.setText("")
        return 0

    level_ids: list[str] = []
    level_meta: dict[str, dict[str, str]] = {}
    for it in selected_items:
        if str(getattr(it, "category", "")) != "custom_vars":
            continue
        meta = getattr(it, "meta", None)
        m = meta if isinstance(meta, dict) else {}
        owner_ref = str(m.get("owner_ref") or "").strip().lower()
        if owner_ref != "level":
            continue
        if str(m.get("select_all") or "").strip() == "1":
            from ugc_file_tools.auto_custom_variable_registry_bridge import (
                try_load_auto_custom_variable_registry_index_from_project_root,
            )

            package_root = (Path(env.workspace_root).resolve() / "assets" / "资源库" / "项目存档" / str(env.package_id)).resolve()
            idx2 = try_load_auto_custom_variable_registry_index_from_project_root(project_root=package_root)
            if idx2 is not None:
                for payload in idx2.payloads_by_owner_and_name.get("level", {}).values():
                    vid = str(payload.get("variable_id") or "").strip()
                    vname = str(payload.get("variable_name") or "").strip()
                    vtype = str(payload.get("variable_type") or "").strip()
                    if vid:
                        level_ids.append(vid)
                        level_meta[vid] = {
                            "variable_id": vid,
                            "variable_name": vname,
                            "variable_type": vtype,
                            "source": str(idx2.registry_path),
                        }
            continue

        vid = str(m.get("variable_id") or "").strip()
        if vid:
            level_ids.append(vid)
            level_meta[vid] = {
                "variable_id": vid,
                "variable_name": str(m.get("variable_name") or ""),
                "variable_type": str(m.get("variable_type") or ""),
                "source": str(getattr(it, "absolute_path", "")),
            }

    seen: set[str] = set()
    level_ids_dedup: list[str] = []
    for vid in level_ids:
        k = str(vid).casefold()
        if k in seen:
            continue
        seen.add(k)
        level_ids_dedup.append(str(vid))

    env.gil.selected_level_custom_variable_ids[:] = list(level_ids_dedup)
    env.gil.level_custom_variable_meta_by_id.clear()
    env.gil.level_custom_variable_meta_by_id.update(dict(level_meta))

    level_vars_count = len(list(env.gil.selected_level_custom_variable_ids or []))
    if int(level_vars_count) <= 0:
        env.gil.level_vars_preview.setText("未选择任何关卡实体自定义变量。导出时不会修改关卡实体 override_variables。")
        return 0

    names: list[str] = []
    for vid in list(env.gil.selected_level_custom_variable_ids or []):
        meta = env.gil.level_custom_variable_meta_by_id.get(str(vid))
        n = str(meta.get("variable_name") or "").strip() if isinstance(meta, dict) else ""
        names.append(n if n != "" else str(vid))
    shown = ", ".join(names[:_LEVEL_VARS_PREVIEW_MAX_NAMES])
    suffix = "" if len(names) <= _LEVEL_VARS_PREVIEW_MAX_NAMES else f" …（共 {len(names)} 个）"
    env.gil.level_vars_preview.setText(f"已选择：{len(names)} 个（{shown}{suffix}）")
    return int(level_vars_count)


def _build_left_summary_text(counts: dict[str, int]) -> str:
    """构建左侧“已选资源”摘要文本。"""

    summary_parts: list[str] = []
    if int(counts.get("graphs") or 0) > 0:
        summary_parts.append(f"节点图={int(counts['graphs'])}")
    if int(counts.get("templates") or 0) > 0:
        summary_parts.append(f"元件={int(counts['templates'])}")
    if int(counts.get("player_templates") or 0) > 0:
        summary_parts.append(f"玩家模板={int(counts['player_templates'])}")
    if int(counts.get("instances") or 0) > 0:
        summary_parts.append(f"实体摆放={int(counts['instances'])}")
    if int(counts.get("ui_src") or 0) > 0:
        summary_parts.append(f"UI源码={int(counts['ui_src'])}")
    if int(counts.get("mgmt_cfg") or 0) > 0:
        summary_parts.append(f"信号/结构体={int(counts['mgmt_cfg'])}")
    if int(counts.get("custom_vars") or 0) > 0:
        summary_parts.append(f"自定义变量={int(counts['custom_vars'])}")
    return ("已选：" + "  ".join(list(summary_parts))) if summary_parts else "未选择任何资源。"


def _set_execute_preview_for_gia(env: ExportCenterDialogWiringEnv, *, counts: dict[str, int], ids: tuple) -> str:
    """更新 GIA 模式下的执行计划预览并返回摘要 tooltip。"""

    signal_ids, basic_struct_ids, ingame_struct_ids = ids
    model = build_gia_preview_texts(
        package_id=str(env.package_id),
        graphs_count=int(counts["graphs"]),
        templates_count=int(counts["templates"]),
        mgmt_cfg_count=int(counts["mgmt_cfg"]),
        signal_ids_total=int(len(signal_ids)),
        basic_struct_ids_total=int(len(basic_struct_ids)),
        ingame_struct_ids_total=int(len(ingame_struct_ids)),
        out_dir_name=str(env.gia.out_dir_edit.text() or ""),
        copy_dir=str(env.gia.copy_dir_edit.text() or ""),
        base_gil_row_visible=bool(env.gia.base_gil_row.isVisible()),
        base_gil_text=str(env.gia.base_gil_edit.text() or ""),
        id_ref_row_visible=bool(env.gia.gia_id_ref_row.isVisible()),
        id_ref_text=str(env.gia.gia_id_ref_edit.text() or ""),
        id_ref_is_used=bool(env.rt.id_ref_usage_for_selected_graphs.is_used),
        player_templates_count=int(counts["player_templates"]),
        player_template_base_gia_row_visible=bool(env.gia.player_template_base_gia_row.isVisible()),
        player_template_base_gia_text=str(env.gia.player_template_base_gia_edit.text() or ""),
    )
    env.execute.plan_preview_text.setPlainText(str(model.preview_text))
    return str(model.summary_tooltip)


def _set_execute_preview_for_gil(
    env: ExportCenterDialogWiringEnv,
    *,
    counts: dict[str, int],
    ids: tuple,
    selected_items: list[object],
    level_vars_count: int,
) -> str:
    """更新 GIL 模式下的执行计划预览并返回摘要 tooltip。"""

    from ..graph_selection import build_graph_selection_from_resource_items

    signal_ids, basic_struct_ids, ingame_struct_ids = ids
    use_builtin_empty_base = bool(getattr(env.gil, "use_builtin_empty_base_cb").isChecked())
    input_text = "（内置空存档）" if use_builtin_empty_base else str(env.gil.input_gil_edit.text() or "").strip()
    output_text = str(env.gil.output_gil_edit.text() or "").strip() or f"{env.package_id}.gil"
    ui_src_selected = int(counts["ui_src"]) > 0
    policy = compute_write_ui_effective_policy(
        fmt="gil",
        ui_src_selected=bool(ui_src_selected),
        user_choice=bool(env.rt.write_ui_user_choice),
    )
    forced_ui = bool(policy.forced)
    want_ui = bool(policy.effective_write_ui)
    graph_sel = build_graph_selection_from_resource_items(
        selected_items=selected_items,
        workspace_root=Path(env.workspace_root),
        package_id=str(env.package_id),
    )
    rid = str(env.gil.gil_ui_export_record_combo.currentData() or "").strip()
    model = build_gil_preview_texts(
        package_id=str(env.package_id),
        templates_count=int(counts["templates"]),
        instances_count=int(counts["instances"]),
        graphs_total=int(len(graph_sel.graph_code_files)),
        level_custom_variables_total=int(level_vars_count),
        signal_ids_total=int(len(signal_ids)),
        basic_struct_ids_total=int(len(basic_struct_ids)),
        ingame_struct_ids_total=int(len(ingame_struct_ids)),
        input_gil_text=str(input_text),
        output_gil_text=str(output_text),
        forced_ui=bool(forced_ui),
        write_ui_effective=bool(want_ui),
        ui_auto_sync_enabled=bool(env.gil.ui_auto_sync_vars_cb.isChecked()),
        prefer_signal_specific_type_id=bool(env.gil.prefer_signal_specific_type_id_cb.isChecked()),
        id_ref_row_visible=bool(env.gil.gil_id_ref_row.isVisible()),
        id_ref_text=str(env.gil.gil_id_ref_edit.text() or ""),
        ui_export_record_row_visible=bool(env.gil.gil_ui_export_record_row.isVisible()),
        ui_export_record_id=str(rid),
    )
    env.execute.plan_preview_text.setPlainText(str(model.preview_text))
    return str(model.summary_tooltip)


def _set_execute_preview_for_repair_modes(env: ExportCenterDialogWiringEnv, *, selected_items: list[object]) -> str:
    """更新修复/合并信号模式下的执行计划预览并返回摘要 tooltip。"""

    from ..graph_selection import build_graph_selection_from_resource_items

    fmt = str(env.format_combo.currentData() or "repair_signals")
    if fmt == "repair_signals":
        input_text = str(env.repair.repair_input_gil_edit.text() or "").strip()
        output_text = str(env.repair.repair_output_gil_edit.text() or "").strip()
        graph_sel = build_graph_selection_from_resource_items(
            selected_items=selected_items,
            workspace_root=Path(env.workspace_root),
            package_id=str(env.package_id),
        )
        model = build_repair_signals_preview_texts(
            package_id=str(env.package_id),
            graphs_total=int(len(graph_sel.graph_code_files)),
            input_gil_text=str(input_text),
            output_gil_text=str(output_text),
            prune_placeholder_orphans=bool(env.repair.repair_prune_orphans_cb.isChecked()),
        )
        env.execute.plan_preview_text.setPlainText(str(model.preview_text))
        return str(model.summary_tooltip)

    input_text = str(env.repair.repair_input_gil_edit.text() or "").strip()
    output_text = str(env.repair.repair_output_gil_edit.text() or "").strip()
    model = build_merge_signal_entries_preview_texts(
        package_id=str(env.package_id),
        input_gil_text=str(input_text),
        output_gil_text=str(output_text),
        keep_signal_name=str(env.repair.merge_keep_signal_edit.text() or ""),
        remove_signal_name=str(env.repair.merge_remove_signal_edit.text() or ""),
        rename_keep_to=str(env.repair.merge_rename_keep_to_edit.text() or ""),
        patch_composite_pin_index=bool(env.repair.merge_patch_cpi_cb.isChecked()),
    )
    env.execute.plan_preview_text.setPlainText(str(model.preview_text))
    return str(model.summary_tooltip)


def _apply_empty_selection_override(
    env: ExportCenterDialogWiringEnv,
    *,
    fmt: str,
    selected_items: list[object],
    level_vars_count: int,
    counts: dict[str, int],
    summary_tooltip: str,
) -> tuple[str, str]:
    """在未勾选资源时应用摘要/预览文本的覆盖规则并返回更新后的 (summary_text, summary_tooltip)。"""

    if selected_items:
        return (_build_left_summary_text(counts), str(summary_tooltip))

    summary_text = "未选择任何资源。"
    tooltip = ""
    if fmt == "merge_signal_entries":
        summary_text = "合并信号条目模式：无需勾选资源。"
        return (summary_text, tooltip)
    if fmt != "gil":
        env.execute.plan_preview_text.setPlainText("未选择任何资源。")
        return (summary_text, tooltip)

    ui_src_selected2 = int(counts.get("ui_src") or 0) > 0
    policy2 = compute_write_ui_effective_policy(
        fmt="gil",
        ui_src_selected=bool(ui_src_selected2),
        user_choice=bool(env.rt.write_ui_user_choice),
    )
    if bool(level_vars_count) or bool(policy2.effective_write_ui):
        return (_build_left_summary_text(counts), str(summary_tooltip))

    env.execute.plan_preview_text.setPlainText("未选择任何资源。")
    return (summary_text, tooltip)


def update_preview(env: ExportCenterDialogWiringEnv, *, update_analysis_tab: Callable[[], None]) -> None:
    """刷新步骤3执行计划预览与左侧“已选资源”摘要并触发分析页联动更新。"""

    selected_items = list(env.picker.get_selected_items())
    counts = _collect_selected_counts(selected_items)

    ids = _collect_writeback_ids_from_mgmt_cfg_items(selected_items)
    fmt = str(env.format_combo.currentData() or "gia")
    env.gia.player_template_base_gia_row.setVisible(bool(fmt == "gia") and int(counts["player_templates"]) > 0)

    if fmt == "gil":
        if bool(_sync_ui_custom_vars_autoselect(env, selected_items)):
            return
        if bool(_sync_asset_custom_vars_autoselect(env, selected_items)):
            return

    level_vars_count = _sync_level_custom_variables_preview(env, selected_items)

    summary_text = _build_left_summary_text(counts)
    summary_tooltip = ""
    if fmt == "gia":
        summary_tooltip = _set_execute_preview_for_gia(env, counts=counts, ids=ids)
    elif fmt == "gil":
        summary_tooltip = _set_execute_preview_for_gil(
            env,
            counts=counts,
            ids=ids,
            selected_items=selected_items,
            level_vars_count=int(level_vars_count),
        )
    elif fmt in {"repair_signals", "merge_signal_entries"}:
        summary_tooltip = _set_execute_preview_for_repair_modes(env, selected_items=selected_items)
    else:
        env.execute.plan_preview_text.setPlainText("（未知模式）")
        summary_tooltip = ""

    prune_note = str(getattr(env.rt, "selection_pruned_note", "") or "").strip()
    if prune_note:
        summary_text = f"{summary_text}\n{prune_note}"
        env.rt.selection_pruned_note = ""

    summary_text, summary_tooltip = _apply_empty_selection_override(
        env,
        fmt=str(fmt),
        selected_items=selected_items,
        level_vars_count=int(level_vars_count),
        counts=counts,
        summary_tooltip=str(summary_tooltip),
    )
    env.left.selected_summary_label.setText(str(summary_text))
    env.left.selected_summary_label.setToolTip(str(summary_tooltip))

    update_analysis_tab()

