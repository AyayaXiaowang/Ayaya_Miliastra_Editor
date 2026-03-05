from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    dump_gil_to_raw_json_object as _dump_gil_to_raw_json_object,
    write_back_modified_gil_by_reencoding_payload as _write_back_modified_gil_by_reencoding_payload,
)
from .web_ui_import_bundle import load_ui_control_group_template_json
from .web_ui_import_constants import (
    DEFAULT_SHARED_PROGRESSBAR_VARIABLE_NAMES,
    DEFAULT_VARIABLE_GROUP_NAME,
    DEFAULT_ITEM_DISPLAY_BUTTON_CONFIG_ID_VARIABLE_FULL_NAME,
    DEFAULT_ITEM_DISPLAY_BUTTON_COOLDOWN_SECONDS_VARIABLE_FULL_NAME,
    DEFAULT_ITEM_DISPLAY_BUTTON_QUANTITY_VARIABLE_FULL_NAME,
)
from ugc_file_tools.custom_variables.apply import (
    ensure_custom_variables_from_variable_defaults,
    ensure_text_placeholder_referenced_custom_variables,
)
from ugc_file_tools.custom_variables.defaults import normalize_variable_defaults_map
from ugc_file_tools.custom_variables.refs import extract_variable_refs_from_text_placeholders, parse_variable_ref_text
from ugc_file_tools.custom_variables.web_ui_apply import (
    ensure_item_display_referenced_custom_variables,
    ensure_progressbar_referenced_custom_variables,
    normalize_progressbar_binding_text,
)


def patch_web_ui_referenced_custom_variables_in_gil(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    template_json_file_path: Path,
    enable_progressbars: bool = True,
    enable_item_displays: bool = True,
) -> Dict[str, Any]:
    """
    仅补齐“实体自定义变量”（关卡/玩家自身）：
    - 从 Web Workbench 导出的 JSON（template/bundle/inline widgets bundle）中提取变量引用
    - 将这些变量写入 input `.gil` 的 root4/5/1 里对应实体条目的自定义变量列表
    - 输出新的 `.gil` 到 ugc_file_tools/out/

    注意：
    - 本函数**不会**写回 UI 控件/布局记录（不改 UI record list / children 树）。
    - 目标变量写入位置与 `web_ui_import_main.import_web_ui_control_group_template_to_gil_layout(...)`
      中的“变量自动创建”完全一致（复用同一套 ensure_* 实现）。
    """
    input_path = Path(input_gil_file_path).resolve()
    template_path = Path(template_json_file_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))
    if not template_path.is_file():
        raise FileNotFoundError(str(template_path))

    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))

    template_obj = load_ui_control_group_template_json(template_path)
    widgets = template_obj.get("widgets")
    if not isinstance(widgets, list):
        raise ValueError("template JSON 缺少 widgets(list)")

    # 变量默认值：由 Workbench bundle 导出（或由 load_ui_control_group_template_json 兜底从 sibling HTML 推断），
    # 用于在“自动创建的实体自定义变量”上写入默认值（不覆盖已存在同名变量）。
    variable_defaults_map = normalize_variable_defaults_map(template_obj.get("variable_defaults"))

    referenced_variable_full_names: Set[str] = set()
    progressbar_variable_roles: Dict[Tuple[str, str], Set[str]] = {}
    item_display_config_id_variable_refs: set[Tuple[str, str]] = set()
    item_display_int_variable_refs: set[Tuple[str, str]] = set()
    item_display_float_variable_refs: set[Tuple[str, str]] = set()
    text_placeholder_variable_refs: set[Tuple[str, str, Tuple[str, ...]]] = set()
    progressbar_binding_auto_filled_total = 0
    default_progressbar_variables_forced = False

    def _record_progressbar_var(role: str, var_name: Optional[str], full_name: Optional[str]) -> None:
        if not full_name or not var_name:
            return
        if "." not in str(full_name):
            return
        group_name = str(full_name).split(".", 1)[0]
        key = (group_name, str(var_name))
        progressbar_variable_roles.setdefault(key, set()).add(str(role))

    for widget in widgets:
        if not isinstance(widget, dict):
            continue
        widget_type = str(widget.get("widget_type") or "").strip()

        if widget_type == "进度条" and bool(enable_progressbars):
            settings = widget.get("settings")
            if not isinstance(settings, dict):
                settings = {}

            current_text = str(settings.get("current_var") or "")
            min_text = str(settings.get("min_var") or "")
            max_text = str(settings.get("max_var") or "")

            before_current = str(current_text)
            before_min = str(min_text)
            before_max = str(max_text)
            current_text = normalize_progressbar_binding_text(role="current", text=current_text)
            min_text = normalize_progressbar_binding_text(role="min", text=min_text)
            max_text = normalize_progressbar_binding_text(role="max", text=max_text)
            if (current_text != before_current) or (min_text != before_min) or (max_text != before_max):
                progressbar_binding_auto_filled_total += 1

            _gid, current_var_name, current_full = parse_variable_ref_text(current_text, allow_constant_number=False)
            _gid2, min_var_name, min_full = parse_variable_ref_text(min_text, allow_constant_number=True)
            _gid3, max_var_name, max_full = parse_variable_ref_text(max_text, allow_constant_number=True)

            if current_full:
                referenced_variable_full_names.add(str(current_full))
            if min_full:
                referenced_variable_full_names.add(str(min_full))
            if max_full:
                referenced_variable_full_names.add(str(max_full))

            _record_progressbar_var("current", current_var_name, current_full)
            _record_progressbar_var("min", min_var_name, min_full)
            _record_progressbar_var("max", max_var_name, max_full)
            continue

        if widget_type == "道具展示" and bool(enable_item_displays):
            settings = widget.get("settings")
            if not isinstance(settings, dict):
                settings = {}

            can_interact = bool(settings.get("can_interact")) if isinstance(settings, dict) else False
            if can_interact:
                display_type = str(settings.get("display_type") or "").strip() or "玩家当前装备"
                # 对齐写回端约定：可交互按钮锚点默认为“模板道具”，并绑定到关卡变量组的一套默认变量
                if str(display_type or "").strip() in ("", "玩家当前装备"):
                    display_type = "模板道具"
                    settings["display_type"] = "模板道具"

                config_var_raw = settings.get("config_id_variable")
                if not isinstance(config_var_raw, str) or str(config_var_raw).strip() in ("", "."):
                    settings["config_id_variable"] = str(DEFAULT_ITEM_DISPLAY_BUTTON_CONFIG_ID_VARIABLE_FULL_NAME)

                qty_var_raw = settings.get("quantity_variable")
                if not isinstance(qty_var_raw, str) or str(qty_var_raw).strip() in ("", "."):
                    settings["quantity_variable"] = str(DEFAULT_ITEM_DISPLAY_BUTTON_QUANTITY_VARIABLE_FULL_NAME)

                cooldown_var_raw = settings.get("cooldown_seconds_variable")
                if not isinstance(cooldown_var_raw, str) or str(cooldown_var_raw).strip() in ("", "."):
                    settings["cooldown_seconds_variable"] = str(DEFAULT_ITEM_DISPLAY_BUTTON_COOLDOWN_SECONDS_VARIABLE_FULL_NAME)

            for variable_key in (
                "config_id_variable",
                "cooldown_seconds_variable",
                "use_count_variable",
                "quantity_variable",
            ):
                value = settings.get(variable_key)
                if not isinstance(value, str):
                    continue
                _, _, full_name = parse_variable_ref_text(value, allow_constant_number=False)
                if not full_name:
                    continue
                referenced_variable_full_names.add(str(full_name))
                group_name, var_name = str(full_name).split(".", 1)
                if variable_key == "config_id_variable":
                    item_display_config_id_variable_refs.add((str(group_name), str(var_name)))
                elif variable_key == "cooldown_seconds_variable":
                    item_display_float_variable_refs.add((str(group_name), str(var_name)))
                elif variable_key in ("use_count_variable", "quantity_variable"):
                    item_display_int_variable_refs.add((str(group_name), str(var_name)))
            continue

        if widget_type == "文本框":
            settings = widget.get("settings")
            if not isinstance(settings, dict):
                settings = {}
            text_content = str(settings.get("text_content") or "")
            refs = extract_variable_refs_from_text_placeholders(text_content)
            for group_name, var_name, field_path in refs:
                g = str(group_name)
                n = str(var_name)
                fp = tuple(str(x) for x in (field_path or ()))
                text_placeholder_variable_refs.add((g, n, fp))
                referenced_variable_full_names.add(f"{g}.{n}")
            continue

    # 兜底（关键）：进度条导出端默认会绑定到一套“共享装饰进度条变量”（关卡.UI_装饰进度条_*）。
    # 在 vars-only/HTML 扫描模式下，如果用户没有显式提供 data-progress-*-var，
    # 我们也需要把这套默认变量补齐到关卡实体自定义变量里，避免用户看到“进度条变量没生成”。
    if bool(enable_progressbars) and not progressbar_variable_roles:
        default_progressbar_variables_forced = True
        for role, var_name in DEFAULT_SHARED_PROGRESSBAR_VARIABLE_NAMES.items():
            key = (str(DEFAULT_VARIABLE_GROUP_NAME), str(var_name))
            progressbar_variable_roles.setdefault(key, set()).add(str(role))
            referenced_variable_full_names.add(f"{DEFAULT_VARIABLE_GROUP_NAME}.{var_name}")

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)

    variable_defaults_created_custom_variables_report = ensure_custom_variables_from_variable_defaults(
        raw_dump_object,
        variable_defaults=variable_defaults_map,
    )
    progressbar_created_custom_variables_report = ensure_progressbar_referenced_custom_variables(
        raw_dump_object,
        progressbar_variable_roles=dict(progressbar_variable_roles),
        variable_defaults=variable_defaults_map,
    )
    item_display_created_custom_variables_report = ensure_item_display_referenced_custom_variables(
        raw_dump_object,
        config_id_variable_refs=set(item_display_config_id_variable_refs),
        int_variable_refs=set(item_display_int_variable_refs),
        float_variable_refs=set(item_display_float_variable_refs),
        variable_defaults=variable_defaults_map,
    )
    text_placeholder_created_custom_variables_report = ensure_text_placeholder_referenced_custom_variables(
        raw_dump_object,
        variable_refs=set(text_placeholder_variable_refs),
        variable_defaults=variable_defaults_map,
    )

    created_custom_variables_report = {
        "created_total": int(variable_defaults_created_custom_variables_report.get("created_total", 0))
        + int(progressbar_created_custom_variables_report.get("created_total", 0))
        + int(item_display_created_custom_variables_report.get("created_total", 0)),
        "existed_total": int(variable_defaults_created_custom_variables_report.get("existed_total", 0))
        + int(progressbar_created_custom_variables_report.get("existed_total", 0))
        + int(item_display_created_custom_variables_report.get("existed_total", 0)),
        "targets": {
            "variable_defaults": dict(variable_defaults_created_custom_variables_report.get("targets") or {}),
            "progressbars": dict(progressbar_created_custom_variables_report.get("targets") or {}),
            "item_displays": dict(item_display_created_custom_variables_report.get("targets") or {}),
            "text_placeholders": dict(text_placeholder_created_custom_variables_report.get("targets") or {}),
        },
        "variables": list(variable_defaults_created_custom_variables_report.get("variables") or [])
        + list(progressbar_created_custom_variables_report.get("variables") or [])
        + list(item_display_created_custom_variables_report.get("variables") or [])
        + list(text_placeholder_created_custom_variables_report.get("variables") or []),
    }

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_path,
        output_gil_path=output_path,
    )

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "template_json": str(template_path),
        "variable_defaults_total": int(len(variable_defaults_map)),
        "referenced_variables_total": int(len(referenced_variable_full_names)),
        "referenced_variables": sorted(referenced_variable_full_names),
        "progressbar_binding_auto_filled_total": int(progressbar_binding_auto_filled_total),
        "auto_created_custom_variables_for_progressbars": dict(progressbar_created_custom_variables_report),
        "auto_created_custom_variables_for_item_displays": dict(item_display_created_custom_variables_report),
        "auto_created_custom_variables_for_text_placeholders": dict(text_placeholder_created_custom_variables_report),
        "created_custom_variables_report": dict(created_custom_variables_report),
        "options": {
            "enable_progressbars": bool(enable_progressbars),
            "enable_item_displays": bool(enable_item_displays),
            "default_progressbar_variables_forced": bool(default_progressbar_variables_forced),
        },
    }
    return report

