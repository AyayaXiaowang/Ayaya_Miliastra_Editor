from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Dict, List


_HTML_VARIABLE_DEFAULTS_SINGLE_QUOTE_RE = re.compile(r"data-ui-variable-defaults\s*=\s*'([^']*)'", re.IGNORECASE)
_HTML_VARIABLE_DEFAULTS_DOUBLE_QUOTE_RE = re.compile(r'data-ui-variable-defaults\s*=\s*"([^"]*)"', re.IGNORECASE)


def _extract_variable_defaults_from_html_text(html_text: str) -> Dict[str, Any]:
    raw = str(html_text or "")
    if raw.strip() == "":
        return {}

    merged: Dict[str, Any] = {}
    matches: List[str] = []
    matches.extend([m.group(1) for m in _HTML_VARIABLE_DEFAULTS_SINGLE_QUOTE_RE.finditer(raw)])
    matches.extend([m.group(1) for m in _HTML_VARIABLE_DEFAULTS_DOUBLE_QUOTE_RE.finditer(raw)])
    if not matches:
        return {}

    # 按出现顺序合并：后者覆盖前者同名 key
    for text in matches:
        decoded = html.unescape(str(text or "").strip())
        if decoded == "":
            continue
        obj = json.loads(decoded)
        if not isinstance(obj, dict):
            raise ValueError("data-ui-variable-defaults 必须是 JSON object（dict）。")
        for k, v in obj.items():
            key = str(k or "").strip()
            if key == "":
                continue
            merged[key] = v
    return merged


def _try_infer_variable_defaults_from_sibling_html(template_json_path: Path) -> Dict[str, Any]:
    """
    兼容：当 Workbench 导出的 bundle JSON 未携带 variable_defaults 时，
    尝试从同目录上级的 HTML 源码中读取 `data-ui-variable-defaults`。
    约定路径：
      .../UI源码/__workbench_out__/<stem>.ui_bundle.json  ->  .../UI源码/<stem>.html
    """
    p = Path(template_json_path).resolve()
    if p.parent.name != "__workbench_out__":
        return {}
    stem = str(p.stem or "")
    if stem.endswith(".ui_bundle"):
        stem = stem[: -len(".ui_bundle")]
    html_path = (p.parent.parent / f"{stem}.html").resolve()
    if not html_path.is_file():
        return {}
    return _extract_variable_defaults_from_html_text(html_path.read_text(encoding="utf-8"))


def load_ui_control_group_template_json(path: Path) -> Dict[str, Any]:
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    # Workbench 推荐导出：UILayout bundle（layout + templates）
    if isinstance(obj, dict) and str(obj.get("bundle_type") or "") == "ui_workbench_ui_layout_bundle":
        template = flatten_ui_workbench_layout_bundle_to_template(obj)
        # 兜底：若 bundle 未包含 variable_defaults，则尝试从同级源码 HTML 推断
        if not isinstance(template.get("variable_defaults"), dict) or not template.get("variable_defaults"):
            inferred = _try_infer_variable_defaults_from_sibling_html(Path(path))
            if inferred:
                template["variable_defaults"] = inferred
        return template
    if isinstance(obj, dict) and isinstance(obj.get("template"), dict):
        template = obj["template"]
    else:
        template = obj
    if not isinstance(template, dict):
        raise TypeError("template json must be dict or {'template': dict}")
    if not isinstance(template.get("widgets"), list):
        raise ValueError("template json missing 'widgets' list")

    if not isinstance(template.get("variable_defaults"), dict) or not template.get("variable_defaults"):
        inferred = _try_infer_variable_defaults_from_sibling_html(Path(path))
        if inferred:
            template["variable_defaults"] = inferred
    return template


def flatten_ui_workbench_layout_bundle_to_template(bundle: Dict[str, Any]) -> Dict[str, Any]:
    layout = bundle.get("layout")
    if not isinstance(layout, dict):
        raise ValueError("ui_workbench bundle missing layout(dict)")

    # Web-first 写回的核心只需要 widgets 列表；“templates/custom_groups”仅用于导出侧组织与排序。
    #
    # 历史/默认形态：
    # - bundle.templates(list) + layout.custom_groups(list[template_id])：按顺序拼接各模板 widgets
    #
    # 兼容形态（inline widgets，不引用模板）：
    # - bundle.layout.widgets(list[widget])：直接使用该列表作为写回输入（顺序即导出顺序）
    direct_widgets = layout.get("widgets")
    if isinstance(direct_widgets, list) and direct_widgets:
        widgets: List[Any] = []
        for w in direct_widgets:
            if isinstance(w, dict):
                widgets.append(w)
        if not widgets:
            raise ValueError("ui_workbench bundle layout.widgets contains no widget dicts")
        layout_id = str(layout.get("layout_id") or "").strip()
        layout_name = str(layout.get("layout_name") or "").strip()
        out = {
            "template_id": layout_id if layout_id else str(bundle.get("bundle_type") or "ui_workbench_bundle"),
            "template_name": layout_name if layout_name else "ui_workbench_bundle",
            "widgets": widgets,
            "_bundle": {
                "bundle_type": str(bundle.get("bundle_type") or ""),
                "bundle_version": int(bundle.get("bundle_version") or 0),
                "inline_widgets": True,
                "canvas_size_key": str(bundle.get("canvas_size_key") or ""),
                "canvas_size_label": str(bundle.get("canvas_size_label") or ""),
            },
        }
        # 附加：变量默认值（由 Workbench 导出；写回端用于“自动创建的实体自定义变量”默认值）
        if isinstance(bundle.get("variable_defaults"), dict):
            out["variable_defaults"] = dict(bundle.get("variable_defaults") or {})
        return out

    templates = bundle.get("templates")
    if not isinstance(templates, list):
        raise ValueError("ui_workbench bundle missing templates(list) (or layout.widgets(list) for inline mode)")

    templates_by_id: Dict[str, Dict[str, Any]] = {}
    for template in templates:
        if not isinstance(template, dict):
            continue
        tid = template.get("template_id")
        if not isinstance(tid, str) or tid.strip() == "":
            continue
        templates_by_id[str(tid)] = template

    custom_groups = layout.get("custom_groups")
    ordered_template_ids: List[str] = []
    if isinstance(custom_groups, list):
        for item in custom_groups:
            tid = str(item or "").strip()
            if tid == "":
                continue
            if tid in templates_by_id and tid not in ordered_template_ids:
                ordered_template_ids.append(tid)
    for tid in sorted(templates_by_id.keys()):
        if tid not in ordered_template_ids:
            ordered_template_ids.append(tid)

    widgets = []
    for tid in ordered_template_ids:
        template = templates_by_id.get(tid)
        if not isinstance(template, dict):
            continue
        widget_list = template.get("widgets")
        if not isinstance(widget_list, list):
            continue
        for w in widget_list:
            if isinstance(w, dict):
                widgets.append(w)

    if not widgets:
        raise ValueError("ui_workbench bundle contains no widgets")

    layout_id = str(layout.get("layout_id") or "").strip()
    layout_name = str(layout.get("layout_name") or "").strip()
    out = {
        "template_id": layout_id if layout_id else str(bundle.get("bundle_type") or "ui_workbench_bundle"),
        "template_name": layout_name if layout_name else "ui_workbench_bundle",
        "widgets": widgets,
        "_bundle": {
            "bundle_type": str(bundle.get("bundle_type") or ""),
            "bundle_version": int(bundle.get("bundle_version") or 0),
            "template_total": int(len(templates_by_id)),
            "ordered_template_ids_total": int(len(ordered_template_ids)),
            "canvas_size_key": str(bundle.get("canvas_size_key") or ""),
            "canvas_size_label": str(bundle.get("canvas_size_label") or ""),
        },
    }
    if isinstance(bundle.get("variable_defaults"), dict):
        out["variable_defaults"] = dict(bundle.get("variable_defaults") or {})
    return out

