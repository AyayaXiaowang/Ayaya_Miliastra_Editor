from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.ui.readable_dump import extract_primary_guid as _extract_primary_guid
from ugc_file_tools.ui.readable_dump import extract_primary_name as _extract_primary_name

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    get_children_guids_from_parent_record as _get_children_guids_from_parent_record,
    write_back_modified_gil_by_reencoding_payload as _write_back_modified_gil_by_reencoding_payload,
)
from .web_ui_import_component_groups import build_component_group_containers
from .web_ui_import_component_groups_finalize import finalize_component_groups
from .web_ui_import_context import WebUiImportContext
from .web_ui_import_guid_registry import add_html_stem_ui_key_aliases, save_ui_guid_registry, write_ui_click_actions_mapping_file
from .web_ui_import_grouping import get_atomic_component_group_key
from .web_ui_import_key_normalization import collect_ui_action_meta_by_ui_key, ensure_unique_ui_keys_in_widgets
from .web_ui_import_layout import reorder_layout_children_by_layer_desc
from .web_ui_import_prepare import prepare_web_ui_import_context
from .web_ui_import_run_state import WebUiImportRunState
from .web_ui_import_templates import WebUiImportTemplates, prepare_template_records
from .web_ui_import_types import ImportedWebItemDisplay, ImportedWebProgressbar, ImportedWebTextbox
from ugc_file_tools.custom_variables.apply import (
    ensure_custom_variables_from_variable_defaults,
    ensure_text_placeholder_referenced_custom_variables,
)
from ugc_file_tools.custom_variables.defaults import normalize_variable_defaults_map
from ugc_file_tools.custom_variables.web_ui_apply import (
    ensure_item_display_referenced_custom_variables,
    ensure_progressbar_referenced_custom_variables,
)
from .web_ui_import_verify import verify_import_result_with_dll_dump
from .web_ui_import_widget_item_display import import_item_display_widget
from .web_ui_import_widget_progressbar import import_progressbar_widget
from .web_ui_import_widget_textbox import import_textbox_widget

from .web_ui_import_builtin_visibility import (
    apply_builtin_visibility_overrides_to_layout,
    load_builtin_visibility_overrides_from_sibling_html_or_raise,
)


_HTML_VARIABLE_DEFAULTS_ATTR_RE = re.compile(
    r"""data-ui-variable-defaults\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    flags=re.IGNORECASE | re.DOTALL,
)


def _try_load_variable_defaults_from_sibling_html(template_json_path: Path) -> Optional[Dict[str, Any]]:
    """
    兼容兜底：当 bundle 未携带 variable_defaults 时，若 template_json 位于 UI源码/__workbench_out__/ 下，
    尝试从同级源码 HTML（../<stem>.html）读取 `data-ui-variable-defaults`。
    """
    p = Path(template_json_path).resolve()
    parts = [str(x) for x in p.parts]
    if "__workbench_out__" not in parts:
        return None
    if "UI源码" not in parts:
        return None
    if p.suffix.lower() != ".json":
        return None

    name = str(p.name)
    base = ""
    if name.endswith(".bundle.json"):
        base = name[: -len(".bundle.json")]
    else:
        base = str(p.stem)
    if base.strip() == "":
        return None

    html_path = (p.parent.parent / f"{base}.html").resolve()
    if not html_path.is_file():
        return None

    source_text = html_path.read_text(encoding="utf-8")
    m = _HTML_VARIABLE_DEFAULTS_ATTR_RE.search(source_text)
    if m is None:
        return None
    raw_value = str(m.group("value") or "").strip()
    if raw_value == "":
        return None

    # 允许用户写 HTML entity；并兼容常见写法：data-ui-variable-defaults='{\"a\":1}'
    value = html.unescape(raw_value).strip()
    if '\\"' in value:
        value = value.replace('\\"', '"')

    obj = json.loads(value)
    if not isinstance(obj, dict):
        raise TypeError(f"data-ui-variable-defaults 必须为 JSON object：{html_path}")
    return obj


def _index_ui_records_by_primary_guid_or_raise(ui_record_list: List[Any]) -> Dict[int, Dict[str, Any]]:
    """
    写回前不变量校验（fail-fast）：
    - UI record list(4/9/502) 中 GUID 必须唯一

    注意：用户明确不希望依赖“写回后去重/修剪”的后处理，因此这里不做修复，只做校验；
    一旦发现重复，直接抛错，便于定位“写入时为什么会重复追加”。
    """
    record_by_guid: Dict[int, Dict[str, Any]] = {}
    counts: Dict[int, int] = {}
    for rec in ui_record_list:
        if not isinstance(rec, dict):
            continue
        gid = _extract_primary_guid(rec)
        if not isinstance(gid, int) or int(gid) <= 0:
            continue
        g = int(gid)
        counts[g] = int(counts.get(g, 0)) + 1
        if g not in record_by_guid:
            record_by_guid[g] = rec

    dup_guids = [g for g, c in counts.items() if int(c) >= 2]
    if dup_guids:
        samples: List[Dict[str, Any]] = []
        for g in sorted(dup_guids)[:12]:
            rec0 = record_by_guid.get(int(g))
            samples.append(
                {
                    "guid": int(g),
                    "count": int(counts.get(int(g), 0)),
                    "name": (_extract_primary_name(rec0) if isinstance(rec0, dict) else None),
                    "parent": (rec0.get("504") if isinstance(rec0, dict) else None),
                }
            )
        raise RuntimeError(f"UI record list(4/9/502) 出现重复 GUID（将导致页面混乱/串页）：{samples!r}")

    return record_by_guid


def _assert_layout_children_parent_consistent(
    *,
    record_by_guid: Dict[int, Dict[str, Any]],
    layout_record: Dict[str, Any],
    layout_guid: int,
) -> None:
    """
    写回前不变量校验（fail-fast）：
    - layout.children 中的 child record 必须满足 child.parent(504)==layout_guid（若存在 504 字段）
    """
    children = _get_children_guids_from_parent_record(layout_record)
    if not children:
        return
    bad: List[Dict[str, Any]] = []
    for child_guid in children:
        gid = int(child_guid)
        rec = record_by_guid.get(int(gid))
        if not isinstance(rec, dict):
            continue
        parent_raw = rec.get("504")
        if isinstance(parent_raw, int) and int(parent_raw) != int(layout_guid):
            bad.append(
                {
                    "layout_guid": int(layout_guid),
                    "child_guid": int(gid),
                    "child_parent_field504": int(parent_raw),
                    "child_name": (_extract_primary_name(rec) or None),
                }
            )
    if bad:
        raise RuntimeError(f"layout.children 存在 parent(504) 不一致的 child（将导致串页/层级错乱）：{bad[:24]!r}")


def import_web_ui_control_group_template_to_gil_layout(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    template_json_file_path: Path,
    # 若 target_layout_guid=None，则会创建一个新布局并把控件放进去
    target_layout_guid: Optional[int] = None,
    new_layout_name: Optional[str] = None,
    base_layout_guid: Optional[int] = None,
    empty_layout: bool = False,
    clone_children: bool = True,
    # Web 坐标系：top-left 原点；GIL RectTransform：canvas 坐标系 bottom-left 原点
    pc_canvas_size: Tuple[float, float] = (1600.0, 900.0),
    mobile_canvas_size: Tuple[float, float] = (1280.0, 720.0),
    # 当前阶段：只落地进度条（色块/边框/阴影/按钮底色）
    enable_progressbars: bool = True,
    # ProgressBar 依赖“可克隆样本 record”；可通过 progressbar_template_gil_file_path 提供一份含 ProgressBar 的模板存档
    progressbar_template_gil_file_path: Optional[Path] = None,
    # TextBox 依赖“可克隆样本 record”；可通过 textbox_template_gil_file_path 提供一份含 TextBox 的模板存档
    enable_textboxes: bool = True,
    textbox_template_gil_file_path: Optional[Path] = None,
    # 道具展示（ItemDisplay）模板来源：若输入 .gil 内不存在道具展示样本，需额外提供
    item_display_template_gil_file_path: Optional[Path] = None,
    verify_with_dll_dump: bool = True,
    # 工程化：UIKey -> GUID 注册表（用于稳定复用 guid、让节点图只引用 ui_key）
    ui_guid_registry_file_path: Optional[Path] = None,
    # 是否自动同步写入“实体自定义变量”（关卡/玩家自身）：
    # - True：根据 UI 引用（进度条/道具展示/文本占位符）自动创建缺失变量
    # - False：仅写回 UI record/布局，不改 root4/5/1 的变量列表
    auto_sync_custom_variables: bool = True,
    # 固有控件（HUD）初始显隐覆盖：从 HTML `data-ui-builtin-visibility` 读取并写回到布局内固有控件 record。
    # 注意：导出中心“项目存档→写回 .gil”链路可能基于不含固有控件的 base `.gil`，因此允许上层显式关闭。
    enable_builtin_widgets_visibility_overrides: bool = True,
) -> Dict[str, Any]:
    ctx, raw_dump_object = prepare_web_ui_import_context(
        input_gil_file_path=input_gil_file_path,
        output_gil_file_path=output_gil_file_path,
        template_json_file_path=template_json_file_path,
        target_layout_guid=target_layout_guid,
        new_layout_name=new_layout_name,
        base_layout_guid=base_layout_guid,
        empty_layout=empty_layout,
        clone_children=clone_children,
        pc_canvas_size=pc_canvas_size,
        mobile_canvas_size=mobile_canvas_size,
        ui_guid_registry_file_path=ui_guid_registry_file_path,
    )

    widgets = ctx.template_obj.get("widgets")
    if not isinstance(widgets, list):
        raise ValueError("template JSON 缺少 widgets(list)")

    # 变量默认值：由 Workbench bundle 侧导出，写回端用于“自动创建的实体自定义变量”的默认值。
    variable_defaults_map = normalize_variable_defaults_map(ctx.template_obj.get("variable_defaults"))
    if not variable_defaults_map:
        fallback = _try_load_variable_defaults_from_sibling_html(Path(template_json_file_path))
        if fallback is not None:
            variable_defaults_map = normalize_variable_defaults_map(fallback)

    normalized_ui_key_collisions_fixed_total = ensure_unique_ui_keys_in_widgets(widgets)
    ui_action_meta_by_ui_key = collect_ui_action_meta_by_ui_key(widgets)

    templates: WebUiImportTemplates = prepare_template_records(
        ui_record_list=ctx.ui_record_list,
        widgets=widgets,
        enable_progressbars=bool(enable_progressbars),
        enable_textboxes=bool(enable_textboxes),
        progressbar_template_gil_file_path=Path(progressbar_template_gil_file_path).resolve()
        if progressbar_template_gil_file_path
        else None,
        textbox_template_gil_file_path=Path(textbox_template_gil_file_path).resolve() if textbox_template_gil_file_path else None,
        item_display_template_gil_file_path=Path(item_display_template_gil_file_path).resolve()
        if item_display_template_gil_file_path
        else None,
    )

    groups = build_component_group_containers(ctx, widgets=widgets)

    run = WebUiImportRunState(
        imported_progressbars=[],
        imported_textboxes=[],
        imported_item_displays=[],
        skipped_widgets=[],
        referenced_variable_full_names=set(),
        progressbar_variable_roles={},
        progressbar_binding_auto_filled_total=0,
        ui_click_actions=[],
        import_order_by_guid={},
        widget_sources_by_guid={},
        interactive_item_display_key_codes_used=set(),
        interactive_item_display_key_code_warnings=[],
        item_display_config_id_variable_refs=set(),
        item_display_int_variable_refs=set(),
        item_display_float_variable_refs=set(),
        text_placeholder_variable_refs=set(),
        visibility_changed_total=0,
    )

    # ------------------------------------------------------------------ 固有控件（HUD）初始显隐（HTML 真源）
    #
    # 约定：固有控件不在 HTML 中绘制，但“是否初始显示”必须由 HTML 页面显式声明：
    #   <html data-ui-builtin-visibility='{"小地图":false,"技能区":false,"队伍信息":false,"角色生命值条":false,"摇杆":false}'>
    #
    # 写回语义：对齐真源存档，写入到目标 record 的 visibility node14.502（缺失=可见，=1=隐藏）。
    builtin_visibility_report: Dict[str, Any]
    if bool(enable_builtin_widgets_visibility_overrides):
        builtin_overrides = load_builtin_visibility_overrides_from_sibling_html_or_raise(Path(template_json_file_path))
        builtin_visibility_report = apply_builtin_visibility_overrides_to_layout(
            ui_record_list=ctx.ui_record_list,
            layout_record=ctx.layout_record,
            overrides=builtin_overrides,
        )
        run.visibility_changed_total += int(builtin_visibility_report.get("visibility_changed_total") or 0)
    else:
        builtin_visibility_report = {
            "skipped": True,
            "reason": "enable_builtin_widgets_visibility_overrides=False",
            "visibility_changed_total": 0,
            "applied": {},
        }

    for widget_index, widget in enumerate(widgets):
        if not isinstance(widget, dict):
            continue
        widget_type = str(widget.get("widget_type") or "").strip()
        widget_id = str(widget.get("widget_id") or "")
        ui_key = str(widget.get("ui_key") or "").strip() or widget_id

        # 关键：写回的“组件打组”必须与 Workbench 侧看到的分组完全一致：
        # 后端写回以 `__html_component_key` 为权威来源（缺失时才从 ui_key 推导）。
        group_key = get_atomic_component_group_key(widget)
        group_record_for_widget = groups.group_records.get(group_key)
        target_parent_record: Dict[str, Any] = group_record_for_widget if group_record_for_widget is not None else ctx.layout_record
        target_parent_guid: int = int(groups.group_guids.get(group_key) or ctx.layout_guid) if group_record_for_widget is not None else int(ctx.layout_guid)

        if widget_type == "进度条":
            if not bool(enable_progressbars):
                run.skipped_widgets.append(
                    {"widget_id": widget_id, "widget_type": widget_type, "reason": "已禁用进度条导入（--skip-progressbars）"}
                )
                continue
            if templates.progressbar_record is None:
                raise RuntimeError("internal error: enable_progressbars=True but template_progressbar_record is None")
            import_progressbar_widget(
                ctx,
                run,
                widget_index=int(widget_index),
                widget=widget,
                target_parent_record=target_parent_record,
                target_parent_guid=int(target_parent_guid),
                layout_record=ctx.layout_record,
                group_key=str(group_key),
                group_child_entries=groups.group_child_entries,
                template_progressbar_record=templates.progressbar_record,
                pc_canvas_size=ctx.pc_canvas_size,
            )
            continue

        if widget_type == "文本框":
            if not bool(enable_textboxes):
                run.skipped_widgets.append(
                    {"widget_id": widget_id, "widget_type": widget_type, "reason": "未启用文本框导入（需要显式 --enable-textboxes）"}
                )
                continue
            if templates.textbox_record is None:
                raise RuntimeError("internal error: enable_textboxes=True but template_textbox_record is None")
            import_textbox_widget(
                ctx,
                run,
                widget_index=int(widget_index),
                widget=widget,
                target_parent_record=target_parent_record,
                target_parent_guid=int(target_parent_guid),
                layout_record=ctx.layout_record,
                group_key=str(group_key),
                group_child_entries=groups.group_child_entries,
                template_textbox_record=templates.textbox_record,
                pc_canvas_size=ctx.pc_canvas_size,
            )
            continue

        if widget_type == "道具展示":
            if templates.item_display_record is None:
                run.skipped_widgets.append(
                    {
                        "widget_id": widget_id,
                        "widget_type": widget_type,
                        "reason": "缺少 道具展示 模板 record；请提供 --item-display-template-gil 或使用包含道具展示样本的 base .gil。",
                    }
                )
                continue
            import_item_display_widget(
                ctx,
                run,
                widget_index=int(widget_index),
                widget=widget,
                target_parent_record=target_parent_record,
                target_parent_guid=int(target_parent_guid),
                layout_record=ctx.layout_record,
                group_key=str(group_key),
                group_child_entries=groups.group_child_entries,
                template_item_display_record=templates.item_display_record,
                pc_canvas_size=ctx.pc_canvas_size,
                ui_action_meta_by_ui_key=ui_action_meta_by_ui_key,
            )
            continue

        run.skipped_widgets.append(
            {
                "ui_key": ui_key,
                "widget_id": widget_id,
                "widget_type": widget_type,
                "reason": "当前未支持该控件类型（仅进度条/文本框/道具展示已覆盖）",
            }
        )

    grouped_components_total, grouped_component_children_total = finalize_component_groups(
        ctx,
        groups=groups,
        group_child_entries=groups.group_child_entries,
        import_order_by_guid=run.import_order_by_guid,
    )

    layout_children_order_report = reorder_layout_children_by_layer_desc(
        layout_record=ctx.layout_record,
        ui_record_list=ctx.ui_record_list,
    )

    if bool(auto_sync_custom_variables):
        variable_defaults_created_custom_variables_report = ensure_custom_variables_from_variable_defaults(
            raw_dump_object,
            variable_defaults=variable_defaults_map,
        )
        text_placeholder_created_custom_variables_report = ensure_text_placeholder_referenced_custom_variables(
            raw_dump_object,
            variable_refs=set(run.text_placeholder_variable_refs),
            variable_defaults=variable_defaults_map,
        )
        item_display_created_custom_variables_report = ensure_item_display_referenced_custom_variables(
            raw_dump_object,
            config_id_variable_refs=set(run.item_display_config_id_variable_refs),
            int_variable_refs=set(run.item_display_int_variable_refs),
            float_variable_refs=set(run.item_display_float_variable_refs),
            variable_defaults=variable_defaults_map,
        )
        # 注意：字典变量(type_code=27) 写回会清理 legacy 标量变量 "<dict>.<key>"。
        # 进度条 binding 只允许绑定到“标量变量名”（且变量名不含 '.'，推荐用 '__' 做镜像命名），
        # 因此不会与 legacy 清理冲突；仍保持“先写字典/结构，再写进度条标量”的顺序以便理解与排查。
        progressbar_created_custom_variables_report = ensure_progressbar_referenced_custom_variables(
            raw_dump_object,
            progressbar_variable_roles=run.progressbar_variable_roles,
            variable_defaults=variable_defaults_map,
        )
    else:
        variable_defaults_created_custom_variables_report = {
            "created_total": 0,
            "existed_total": 0,
            "targets": {},
            "variables": [],
            "skipped": True,
            "reason": "auto_sync_custom_variables=False",
        }
        progressbar_created_custom_variables_report = {
            "created_total": 0,
            "existed_total": 0,
            "targets": {},
            "variables": [],
            "skipped": True,
            "reason": "auto_sync_custom_variables=False",
        }
        item_display_created_custom_variables_report = {
            "created_total": 0,
            "existed_total": 0,
            "targets": {},
            "variables": [],
            "skipped": True,
            "reason": "auto_sync_custom_variables=False",
        }
        text_placeholder_created_custom_variables_report = {
            "created_total": 0,
            "existed_total": 0,
            "targets": {},
            "variables": [],
            "skipped": True,
            "reason": "auto_sync_custom_variables=False",
        }

    created_custom_variables_report = {
        "created_total": int(variable_defaults_created_custom_variables_report.get("created_total", 0))
        + int(progressbar_created_custom_variables_report.get("created_total", 0))
        + int(item_display_created_custom_variables_report.get("created_total", 0))
        + int(text_placeholder_created_custom_variables_report.get("created_total", 0)),
        "existed_total": int(variable_defaults_created_custom_variables_report.get("existed_total", 0))
        + int(progressbar_created_custom_variables_report.get("existed_total", 0))
        + int(item_display_created_custom_variables_report.get("existed_total", 0))
        + int(text_placeholder_created_custom_variables_report.get("existed_total", 0)),
        "targets": {
            "progressbars": dict(progressbar_created_custom_variables_report.get("targets") or {}),
            "item_displays": dict(item_display_created_custom_variables_report.get("targets") or {}),
            "text_placeholders": dict(text_placeholder_created_custom_variables_report.get("targets") or {}),
            "variable_defaults": dict(variable_defaults_created_custom_variables_report.get("targets") or {}),
        },
        "variables": list(variable_defaults_created_custom_variables_report.get("variables") or [])
        + list(progressbar_created_custom_variables_report.get("variables") or [])
        + list(item_display_created_custom_variables_report.get("variables") or [])
        + list(text_placeholder_created_custom_variables_report.get("variables") or []),
    }

    # 布局索引自动回填（重要）：节点 `切换当前界面布局` 的“布局索引”并不是 1..N 的序号，
    # 而是 **布局 root 的 GUID（107374xxxx）**（真源图验证）。
    #
    # 这里仍会从 layout registry(4/9/501[0]) 做一次反查校验：仅当该 layout_guid 已注册且不属于 template roots
    # 时，才写入 ui_guid_registry，供节点图侧引用。
    from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import try_infer_layout_index_from_layout_registry

    layout_index = try_infer_layout_index_from_layout_registry(raw_dump_object, layout_guid=int(ctx.layout_guid))
    template_id_text = str(ctx.template_obj.get("template_id") or "").strip()
    stem_text = str(ctx.template_path.stem).strip()
    layout_ui_key = f"LAYOUT__{template_id_text if template_id_text else stem_text}__{stem_text}"
    layout_index_ui_key = f"LAYOUT_INDEX__{template_id_text if template_id_text else stem_text}__{stem_text}"

    html_stem = ""
    name_lower = str(ctx.template_path.name).lower()
    if name_lower.endswith(".ui_bundle.json"):
        html_stem = str(ctx.template_path.name[: -len(".ui_bundle.json")]).strip()
    elif name_lower.endswith(".bundle.json"):
        html_stem = str(ctx.template_path.name[: -len(".bundle.json")]).strip()
    else:
        html_stem = str(stem_text).strip()
    layout_ui_key_html = f"LAYOUT__HTML__{html_stem}" if html_stem != "" else None
    layout_index_ui_key_html = f"LAYOUT_INDEX__HTML__{html_stem}" if html_stem != "" else None

    # 即便是首次生成 registry（registry_loaded=False），也应该写入布局索引映射，
    # 否则“UI 写回后立刻节点图写回”会缺少 LAYOUT_INDEX__... 导致解析/回填不稳定。
    if layout_index is not None:
        ctx.ui_key_to_guid[str(layout_index_ui_key)] = int(layout_index)
        if layout_index_ui_key_html is not None:
            ctx.ui_key_to_guid[str(layout_index_ui_key_html)] = int(layout_index)
        # 额外别名：用 layout root 的“显示名/页面名”（通常与 HTML stem 一致）作为 key，
        # 让节点图侧能用 `LAYOUT_INDEX__HTML__关卡大厅-选关界面` 这类更直观的引用方式。
        layout_name_alias = ""
        if isinstance(ctx.created_layout, dict):
            layout_name_alias = str(ctx.created_layout.get("name") or "").strip()
        if layout_name_alias == "":
            layout_name_alias = str(ctx.template_obj.get("template_name") or "").strip()
        if layout_name_alias != "":
            ctx.ui_key_to_guid[f"LAYOUT_INDEX__HTML__{layout_name_alias}"] = int(layout_index)

    # 关键：生成 `<html_stem>_html__...` 的稳定 alias key（并去掉 state/坐标后缀），
    # 让节点图侧可以稳定用 `ui_key:<页面名>_html__...` 引用，而不依赖 `HTML导入_界面布局__...` 这种导入中间前缀。
    ui_key_alias_report: Optional[Dict[str, Any]] = None
    if html_stem != "":
        ctx.ui_key_to_guid, ui_key_alias_report = add_html_stem_ui_key_aliases(ctx.ui_key_to_guid, html_stem=str(html_stem))

    if ctx.registry_path is not None:
        save_ui_guid_registry(ctx.registry_path, ctx.ui_key_to_guid)
        ctx.registry_saved = True

    # ------------------------------------------------------------------ 写回前不变量校验（fail-fast）
    # 用户诉求：不做“写回后处理/去重”，而是写入时确保不产生重复/串页。
    record_by_guid = _index_ui_records_by_primary_guid_or_raise(ctx.ui_record_list)
    _assert_layout_children_parent_consistent(
        record_by_guid=record_by_guid,
        layout_record=ctx.layout_record,
        layout_guid=int(ctx.layout_guid),
    )

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=ctx.input_path,
        output_gil_path=ctx.output_path,
    )

    # report: component groups detail
    component_group_details: List[Dict[str, Any]] = []
    for gk in groups.ordered_group_keys:
        if gk not in groups.group_records:
            continue
        group_guid = int(groups.group_guids.get(gk) or 0)
        entries = groups.group_child_entries.get(gk) or []
        component_group_details.append(
            {
                "group_key": str(gk),
                "group_ui_key": f"{gk}__group",
                "group_guid": int(group_guid),
                "children_total": int(len(entries)),
                "children": [{"guid": int(guid), "layer": int(layer), "widget_index": int(widget_index)} for (layer, widget_index, guid) in entries],
            }
        )

    report: Dict[str, Any] = {
        "input_gil": str(ctx.input_path),
        "output_gil": str(ctx.output_path),
        "template_json": str(ctx.template_path),
        "template_id": str(ctx.template_obj.get("template_id")),
        "template_name": str(ctx.template_obj.get("template_name")),
        "referenced_variables_total": int(len(run.referenced_variable_full_names)),
        "referenced_variables": sorted(run.referenced_variable_full_names),
        "progressbar_binding_auto_filled_total": int(run.progressbar_binding_auto_filled_total),
        "layout_children_order": dict(layout_children_order_report),
        "auto_created_custom_variables_for_progressbars": dict(progressbar_created_custom_variables_report),
        "auto_created_custom_variables_for_item_displays": dict(item_display_created_custom_variables_report),
        "auto_created_custom_variables_for_text_placeholders": dict(text_placeholder_created_custom_variables_report),
        "layout": {
            "target_layout_guid": int(ctx.layout_guid),
            "created_layout": ctx.created_layout,
            "layout_index": int(layout_index) if layout_index is not None else None,
        },
        "layout_ui_key": str(layout_ui_key),
        "layout_ui_key_html": (str(layout_ui_key_html) if layout_ui_key_html is not None else None),
        "layout_index_ui_key": str(layout_index_ui_key),
        "layout_index_ui_key_html": (str(layout_index_ui_key_html) if layout_index_ui_key_html is not None else None),
        "ui_guid_registry": {
            "path": (str(ctx.registry_path) if ctx.registry_path is not None else None),
            "loaded": bool(ctx.registry_loaded),
            "saved": bool(ctx.registry_saved),
            "entries_total": int(len(ctx.ui_key_to_guid)),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "dedup_by_guid": dict(ctx.registry_guid_dedup_report) if ctx.registry_guid_dedup_report is not None else None,
        },
        "ui_guid_registry_aliases": (dict(ui_key_alias_report) if ui_key_alias_report is not None else None),
        # 写回链路桥接：当不落盘 registry 时，将“本轮可用于节点图回填的 key 子集”放进 report，
        # 供上游 pipeline 在同次“UI+节点图写回”时直接使用（避免依赖外部 ui_guid_registry.json 文件）。
        "ui_key_to_guid_for_writeback": {
            k: int(v)
            for k, v in ctx.ui_key_to_guid.items()
            if isinstance(v, int)
            and int(v) > 0
            and (
                (html_stem != "" and str(k).startswith(f"{html_stem}_html__"))
                or str(k).startswith("UI_STATE_GROUP__")
                or str(k).startswith("LAYOUT_INDEX__HTML__")
            )
        },
        "guid_conflicts": {
            "avoided_total": int(len(ctx.guid_collision_avoided)),
            "avoided": ctx.guid_collision_avoided,
            "note": "当 registry 的 desired_guid 在基底存档里已存在但不属于目标布局 children（或结构不匹配）时，会自动改用新 GUID（max+1）以避免覆盖或报错。",
        },
        "component_groups": {
            "enabled": True,
            "grouped_components_total": int(grouped_components_total),
            "grouped_component_children_total": int(grouped_component_children_total),
            "groups": component_group_details,
            "group_guid_conflicts": {
                "avoided_total": int(len(groups.group_guid_collision_avoided)),
                "avoided": groups.group_guid_collision_avoided,
            },
        },
        "builtin_widgets_visibility_overrides": dict(builtin_visibility_report),
        "ui_key_normalization": {
            "dedup_collisions_fixed_total": int(normalized_ui_key_collisions_fixed_total),
            "note": "若输入 JSON 的 ui_key 在一次导入内不唯一，会被自动补齐稳定后缀（优先 rect 后缀），避免多个控件复用同一 GUID 导致“看起来丢控件”。",
        },
        "options": {
            "pc_canvas_size": {"x": float(ctx.pc_canvas_size[0]), "y": float(ctx.pc_canvas_size[1])},
            "reference_pc_canvas_size": {"x": float(ctx.reference_pc_canvas_size[0]), "y": float(ctx.reference_pc_canvas_size[1])},
            "mobile_canvas_size": {"x": float(ctx.mobile_canvas_size[0]), "y": float(ctx.mobile_canvas_size[1])},
            "console_canvas_size": (
                {"x": float(ctx.canvas_size_by_state_index[2][0]), "y": float(ctx.canvas_size_by_state_index[2][1])}
                if 2 in ctx.canvas_size_by_state_index
                else None
            ),
            "gamepad_canvas_size": (
                {"x": float(ctx.canvas_size_by_state_index[3][0]), "y": float(ctx.canvas_size_by_state_index[3][1])}
                if 3 in ctx.canvas_size_by_state_index
                else None
            ),
            "enable_progressbars": bool(enable_progressbars),
            "enable_textboxes": bool(enable_textboxes),
            "auto_sync_custom_variables": bool(auto_sync_custom_variables),
            "textbox_template_gil_file_path": str(Path(textbox_template_gil_file_path).resolve()) if textbox_template_gil_file_path else None,
            "item_display_template_gil_file_path": str(Path(item_display_template_gil_file_path).resolve())
            if item_display_template_gil_file_path
            else None,
            "ui_guid_registry_file_path": (str(ctx.registry_path) if ctx.registry_path is not None else None),
        },
        "result": {
            "imported_progressbars_total": int(len(run.imported_progressbars)),
            "imported_textboxes_total": int(len(run.imported_textboxes)),
            "imported_item_displays_total": int(len(run.imported_item_displays)),
            "initial_hidden_total": int(
                sum(1 for it in run.imported_progressbars if not bool(it.initial_visible))
                + sum(1 for it in run.imported_textboxes if not bool(it.initial_visible))
                + sum(1 for it in run.imported_item_displays if not bool(it.initial_visible))
            ),
            "visibility_changed_total": int(run.visibility_changed_total),
            "grouped_components_total": int(grouped_components_total),
            "grouped_component_children_total": int(grouped_component_children_total),
            "skipped_widgets_total": int(len(run.skipped_widgets)),
        },
        "ui_click_actions": list(run.ui_click_actions),
        "interactive_item_display_key_code_warnings": list(run.interactive_item_display_key_code_warnings),
        "imported_progressbars": [
            {
                "ui_key": item.ui_key,
                "widget_id": item.widget_id,
                "widget_name": item.widget_name,
                "guid": item.guid,
                "layer": item.layer,
                "initial_visible": bool(item.initial_visible),
                "source": dict(run.widget_sources_by_guid.get(int(item.guid)) or {}),
                "pc_canvas_position": {"x": item.pc_canvas_position[0], "y": item.pc_canvas_position[1]},
                "pc_size": {"x": item.pc_size[0], "y": item.pc_size[1]},
                "mobile_canvas_position": (
                    {"x": item.mobile_canvas_position[0], "y": item.mobile_canvas_position[1]}
                    if item.mobile_canvas_position is not None
                    else None
                ),
                "mobile_size": {"x": item.mobile_size[0], "y": item.mobile_size[1]} if item.mobile_size is not None else None,
                "console_canvas_position": (
                    {"x": item.console_canvas_position[0], "y": item.console_canvas_position[1]}
                    if item.console_canvas_position is not None
                    else None
                ),
                "console_size": {"x": item.console_size[0], "y": item.console_size[1]} if item.console_size is not None else None,
                "gamepad_canvas_position": (
                    {"x": item.gamepad_canvas_position[0], "y": item.gamepad_canvas_position[1]}
                    if item.gamepad_canvas_position is not None
                    else None
                ),
                "gamepad_size": {"x": item.gamepad_size[0], "y": item.gamepad_size[1]} if item.gamepad_size is not None else None,
                "raw_codes": dict(item.raw_codes),
            }
            for item in run.imported_progressbars
        ],
        "imported_textboxes": [
            {
                "ui_key": item.ui_key,
                "widget_id": item.widget_id,
                "widget_name": item.widget_name,
                "guid": item.guid,
                "layer": item.layer,
                "initial_visible": bool(item.initial_visible),
                "source": dict(run.widget_sources_by_guid.get(int(item.guid)) or {}),
                "pc_canvas_position": {"x": item.pc_canvas_position[0], "y": item.pc_canvas_position[1]},
                "pc_size": {"x": item.pc_size[0], "y": item.pc_size[1]},
                "mobile_canvas_position": (
                    {"x": item.mobile_canvas_position[0], "y": item.mobile_canvas_position[1]}
                    if item.mobile_canvas_position is not None
                    else None
                ),
                "mobile_size": {"x": item.mobile_size[0], "y": item.mobile_size[1]} if item.mobile_size is not None else None,
                "console_canvas_position": (
                    {"x": item.console_canvas_position[0], "y": item.console_canvas_position[1]}
                    if item.console_canvas_position is not None
                    else None
                ),
                "console_size": {"x": item.console_size[0], "y": item.console_size[1]} if item.console_size is not None else None,
                "gamepad_canvas_position": (
                    {"x": item.gamepad_canvas_position[0], "y": item.gamepad_canvas_position[1]}
                    if item.gamepad_canvas_position is not None
                    else None
                ),
                "gamepad_size": {"x": item.gamepad_size[0], "y": item.gamepad_size[1]} if item.gamepad_size is not None else None,
                "text_content": item.text_content,
                "font_size": int(item.font_size),
                "raw_codes": dict(item.raw_codes),
            }
            for item in run.imported_textboxes
        ],
        "imported_item_displays": [
            {
                "ui_key": item.ui_key,
                "widget_id": item.widget_id,
                "widget_name": item.widget_name,
                "guid": item.guid,
                "layer": item.layer,
                "initial_visible": bool(item.initial_visible),
                "source": dict(run.widget_sources_by_guid.get(int(item.guid)) or {}),
                "pc_canvas_position": {"x": item.pc_canvas_position[0], "y": item.pc_canvas_position[1]},
                "pc_size": {"x": item.pc_size[0], "y": item.pc_size[1]},
                "mobile_canvas_position": (
                    {"x": item.mobile_canvas_position[0], "y": item.mobile_canvas_position[1]}
                    if item.mobile_canvas_position is not None
                    else None
                ),
                "mobile_size": {"x": item.mobile_size[0], "y": item.mobile_size[1]} if item.mobile_size is not None else None,
                "console_canvas_position": (
                    {"x": item.console_canvas_position[0], "y": item.console_canvas_position[1]}
                    if item.console_canvas_position is not None
                    else None
                ),
                "console_size": {"x": item.console_size[0], "y": item.console_size[1]} if item.console_size is not None else None,
                "gamepad_canvas_position": (
                    {"x": item.gamepad_canvas_position[0], "y": item.gamepad_canvas_position[1]}
                    if item.gamepad_canvas_position is not None
                    else None
                ),
                "gamepad_size": {"x": item.gamepad_size[0], "y": item.gamepad_size[1]} if item.gamepad_size is not None else None,
                "display_type": item.display_type,
                "raw_codes": dict(item.raw_codes),
            }
            for item in run.imported_item_displays
        ],
        "skipped_widgets": run.skipped_widgets,
    }

    ui_actions_file_path = write_ui_click_actions_mapping_file(
        template_json_path=ctx.template_path,
        click_actions=list(run.ui_click_actions),
    )
    report["ui_click_actions_file"] = str(ui_actions_file_path) if ui_actions_file_path is not None else None

    if verify_with_dll_dump:
        report["verify"] = verify_import_result_with_dll_dump(
            output_gil_path=ctx.output_path,
            layout_guid=int(ctx.layout_guid),
            imported_progressbars=list(run.imported_progressbars),
            imported_textboxes=list(run.imported_textboxes),
            imported_item_displays=list(run.imported_item_displays),
            created_custom_variables_report=dict(created_custom_variables_report),
        )

    return report

