from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from ..state import (
    _save_last_base_gil_path,
    _save_last_base_player_template_gia_path,
    _save_last_repair_input_gil_path,
    _save_last_use_builtin_empty_base_gil,
)

from ...export_center_dialog_plan_validators import (
    validate_gia_plan,
    validate_gil_plan,
    validate_merge_signal_entries_plan,
    validate_repair_signals_plan,
)


def ensure_no_running_export_task_or_warn(*, main_window: Any) -> bool:
    """检查是否存在运行中的导出任务并在需要时弹窗提示。"""

    from app.ui.foundation import dialog_utils

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
            return False
    return True


def call_save_now_or_raise(*, main_window: Any) -> None:
    """在导出前触发主程序保存并保证 package_controller 存在。"""

    package_controller = getattr(main_window, "package_controller", None)
    if package_controller is None:
        raise RuntimeError("主窗口缺少 package_controller，无法导出")
    save_now = getattr(package_controller, "save_now", None)
    if callable(save_now):
        save_now()


def validate_plan_by_format(
    *,
    fmt: str,
    main_window: Any,
    workspace_root: Path,
    package_id: str,
    project_root: Path,
    picker: Any,
    gia: Any,
    gil: Any,
    repair: Any,
) -> object | None:
    """按 fmt 校验并构造导出中心 plan。"""

    if str(fmt) == "gia":
        return validate_gia_plan(
            main_window=main_window,
            workspace_root=Path(workspace_root),
            package_id=str(package_id),
            project_root=Path(project_root),
            picker=picker,
            gia=gia,
        )
    if str(fmt) == "gil":
        return validate_gil_plan(
            main_window=main_window,
            workspace_root=Path(workspace_root),
            package_id=str(package_id),
            project_root=Path(project_root),
            picker=picker,
            gil=gil,
        )
    if str(fmt) == "merge_signal_entries":
        return validate_merge_signal_entries_plan(
            main_window=main_window,
            workspace_root=Path(workspace_root),
            package_id=str(package_id),
            project_root=Path(project_root),
            picker=picker,
            repair=repair,
        )
    return validate_repair_signals_plan(
        main_window=main_window,
        workspace_root=Path(workspace_root),
        package_id=str(package_id),
        project_root=Path(project_root),
        picker=picker,
        repair=repair,
    )


def persist_last_paths(*, workspace_root: Path, plan_obj: object, gia: Any) -> None:
    """将本次 plan 的关键路径写入导出中心状态缓存。"""

    from ..plans import _ExportGiaPlan, _ExportGilPlan, _MergeSignalEntriesPlan, _RepairSignalsPlan

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
        _save_last_repair_input_gil_path(workspace_root=Path(workspace_root), input_gil_path=Path(plan_obj.input_gil_path))


def inject_id_ref_overrides(*, plan_obj: object, rt: Any) -> object:
    """将识别表格双击选择产生的手动覆盖注入到 plan。"""

    from ..plans import _ExportGiaPlan, _ExportGilPlan

    if not isinstance(plan_obj, (_ExportGiaPlan, _ExportGilPlan)):
        return plan_obj
    comp_over = getattr(rt, "id_ref_override_component_name_to_id", None)
    ent_over = getattr(rt, "id_ref_override_entity_name_to_guid", None)
    return replace(
        plan_obj,
        id_ref_override_component_name_to_id=(dict(comp_over) if isinstance(comp_over, dict) else {}),
        id_ref_override_entity_name_to_guid=(dict(ent_over) if isinstance(ent_over, dict) else {}),
    )


__all__ = [
    "call_save_now_or_raise",
    "ensure_no_running_export_task_or_warn",
    "inject_id_ref_overrides",
    "persist_last_paths",
    "validate_plan_by_format",
]

