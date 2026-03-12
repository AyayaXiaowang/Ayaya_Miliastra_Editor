from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from .constants import PRECHECK_PREVIEW_MAX_ITEMS
from .precheck_utils import record_precheck_skip


def precheck_clean_gia_templates_index(*, plan_obj: object, precheck_skipped_inputs: list[dict[str, str]]) -> object:
    """预检剔除 GIA 模式误选的 templates_index.json。"""

    from ..plans import _ExportGiaPlan

    if not isinstance(plan_obj, _ExportGiaPlan) or not bool(plan_obj.template_json_files):
        return plan_obj

    cleaned_template_files: list[Path] = []
    for p in list(plan_obj.template_json_files or []):
        rp = Path(p).resolve()
        if rp.name == "templates_index.json":
            record_precheck_skip(
                precheck_skipped_inputs=precheck_skipped_inputs,
                category="templates",
                file_path=rp,
                reason="templates_index.json 是索引列表，不是单模板 JSON（每文件一个模板 dict）",
            )
            continue
        cleaned_template_files.append(rp)

    if len(cleaned_template_files) != len(list(plan_obj.template_json_files or [])):
        return replace(plan_obj, template_json_files=list(cleaned_template_files))
    return plan_obj


def _format_precheck_skipped_inputs_preview_lines(*, precheck_skipped_inputs: list[dict[str, str]]) -> list[str]:
    """格式化预检跳过清单预览（用于“无事可做”提示）。"""

    if not precheck_skipped_inputs:
        return []
    lines: list[str] = []
    lines.append("")
    lines.append(f"预检已跳过 {len(precheck_skipped_inputs)} 个输入文件：")
    for item in precheck_skipped_inputs[: int(PRECHECK_PREVIEW_MAX_ITEMS)]:
        fp = str(item.get("file") or "").strip()
        reason = str(item.get("reason") or "").strip()
        name = Path(fp).name if fp else "(unknown)"
        lines.append(f"- {name}：{reason}" if reason else f"- {name}")
    if len(precheck_skipped_inputs) > int(PRECHECK_PREVIEW_MAX_ITEMS):
        lines.append(f"... 还有 {len(precheck_skipped_inputs) - int(PRECHECK_PREVIEW_MAX_ITEMS)} 个未展示")
    return list(lines)


def ensure_gia_plan_has_anything_or_warn(*, main_window: Any, plan_obj: object, precheck_skipped_inputs: list[dict[str, str]]) -> bool:
    """确保 GIA plan 预检后仍有可导出内容，否则提示并返回 False。"""

    from app.ui.foundation import dialog_utils
    from ..plans import _ExportGiaPlan

    if not isinstance(plan_obj, _ExportGiaPlan):
        return True

    graph_sel0 = plan_obj.graph_selection
    graph_files0 = list(getattr(graph_sel0, "graph_code_files", []) or [])
    has_any_gia = bool(graph_files0) or bool(plan_obj.template_json_files) or bool(plan_obj.selected_basic_struct_ids) or bool(
        plan_obj.selected_signal_ids
    ) or bool(plan_obj.selected_ingame_struct_ids)
    if bool(has_any_gia):
        return True

    lines: list[str] = ["没有可导出的内容（预检后为空）。"]
    lines.extend(_format_precheck_skipped_inputs_preview_lines(precheck_skipped_inputs=list(precheck_skipped_inputs)))
    dialog_utils.show_warning_dialog(main_window, "提示", "\n".join(lines))
    return False


def ensure_gil_plan_has_anything_or_warn(*, main_window: Any, plan_obj: object, precheck_skipped_inputs: list[dict[str, str]]) -> bool:
    """确保 GIL plan 预检后仍有可写回/可导出内容，否则提示并返回 False。"""

    from app.ui.foundation import dialog_utils
    from ..plans import _ExportGilPlan

    if not isinstance(plan_obj, _ExportGilPlan):
        return True

    has_any_gil = bool(plan_obj.write_ui) or bool(plan_obj.selected_graph_code_files) or bool(plan_obj.selected_template_json_files) or bool(
        plan_obj.selected_instance_json_files
    ) or bool(plan_obj.selected_struct_ids) or bool(plan_obj.selected_ingame_struct_ids) or bool(plan_obj.selected_signal_ids) or bool(
        plan_obj.selected_level_custom_variable_ids
    ) or bool(plan_obj.selected_custom_variable_refs)
    if bool(has_any_gil):
        return True

    lines2: list[str] = ["没有可写回/可导出的内容（预检后为空）。"]
    lines2.extend(_format_precheck_skipped_inputs_preview_lines(precheck_skipped_inputs=list(precheck_skipped_inputs)))
    dialog_utils.show_warning_dialog(main_window, "提示", "\n".join(lines2))
    return False


__all__ = [
    "ensure_gia_plan_has_anything_or_warn",
    "ensure_gil_plan_has_anything_or_warn",
    "precheck_clean_gia_templates_index",
]

