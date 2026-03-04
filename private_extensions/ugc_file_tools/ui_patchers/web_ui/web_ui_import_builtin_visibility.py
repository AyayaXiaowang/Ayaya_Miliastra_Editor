from __future__ import annotations

import html as _html
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from ugc_file_tools.ui.readable_dump import extract_primary_guid
from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import get_children_guids_from_parent_record

from .web_ui_import_rect import try_extract_widget_name
from .web_ui_import_visibility import apply_visibility_patch, parse_initial_visible


REQUIRED_UI_BUILTIN_WIDGET_NAMES: tuple[str, ...] = (
    "小地图",
    "技能区",
    "队伍信息",
    "角色生命值条",
    "摇杆",
)

_UI_BUILTIN_NAME_ALIASES: dict[str, str] = {
    # 兼容用户输入的繁体写法
    "揺杆": "摇杆",
}

_HTML_BUILTIN_VISIBILITY_ATTR_RE = re.compile(
    r"""data-ui-builtin-visibility\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    flags=re.IGNORECASE | re.DOTALL,
)


def load_builtin_visibility_overrides_from_sibling_html_or_raise(template_json_path: Path) -> Dict[str, bool]:
    """
    从 `UI源码/__workbench_out__/*.ui_bundle.json` 的同级 HTML（../<stem>.html）读取
    `data-ui-builtin-visibility`（JSON object），并返回：
      builtin_widget_name -> initial_visible(bool)

    约束（fail-fast）：
    - 必须显式提供且只能提供 REQUIRED_UI_BUILTIN_WIDGET_NAMES（允许“揺杆”别名）
    - 值必须可解析为 bool（支持 true/false/1/0/"true"/"false"）
    """
    p = Path(template_json_path).resolve()
    parts = [str(x) for x in p.parts]
    if "__workbench_out__" not in parts or "UI源码" not in parts:
        raise ValueError(f"仅支持从 UI源码/__workbench_out__/ 读取 sibling HTML：{p}")
    if p.suffix.lower() != ".json":
        raise ValueError(f"template_json_path 必须为 .json：{p}")

    name = str(p.name)
    if name.endswith(".ui_bundle.json"):
        stem = name[: -len(".ui_bundle.json")]
    elif name.endswith(".bundle.json"):
        stem = name[: -len(".bundle.json")]
    else:
        stem = str(p.stem)
    stem = str(stem).strip()
    if stem == "":
        raise ValueError(f"无法从文件名推断 HTML stem：{p}")

    html_path = (p.parent.parent / f"{stem}.html").resolve()
    if not html_path.is_file():
        raise FileNotFoundError(str(html_path))

    source_text = html_path.read_text(encoding="utf-8")
    m = _HTML_BUILTIN_VISIBILITY_ATTR_RE.search(source_text)
    if m is None:
        raise ValueError(f"HTML 缺少 data-ui-builtin-visibility（必须显式声明 5 个固有控件初始显隐）：{html_path}")
    raw_value = str(m.group("value") or "").strip()
    if raw_value == "":
        raise ValueError(f"data-ui-builtin-visibility 不能为空：{html_path}")

    value = _html.unescape(raw_value).strip()
    if '\\"' in value:
        value = value.replace('\\"', '"')

    obj = json.loads(value)
    if not isinstance(obj, dict):
        raise TypeError(f"data-ui-builtin-visibility 必须为 JSON object：{html_path}")

    overrides: Dict[str, bool] = {}
    unknown: list[str] = []
    for k, v in obj.items():
        key0 = str(k or "").strip()
        if key0 == "":
            continue
        key = _UI_BUILTIN_NAME_ALIASES.get(key0, key0)
        if key not in REQUIRED_UI_BUILTIN_WIDGET_NAMES:
            unknown.append(key0)
            continue
        overrides[key] = bool(parse_initial_visible(v, default_value=True))

    if unknown:
        raise ValueError(
            f"data-ui-builtin-visibility 包含不支持的固有控件名（仅允许 5 个）：{sorted(set(unknown))!r} ({html_path})"
        )

    missing = [n for n in REQUIRED_UI_BUILTIN_WIDGET_NAMES if n not in overrides]
    if missing:
        raise ValueError(
            f"data-ui-builtin-visibility 缺少必填项（必须显式声明 5 个固有控件）：{missing!r} ({html_path})"
        )

    return overrides


def apply_builtin_visibility_overrides_to_layout(
    *,
    ui_record_list: list[Any],
    layout_record: dict[str, Any],
    overrides: Dict[str, bool],
) -> Dict[str, Any]:
    record_by_guid: Dict[int, Dict[str, Any]] = {}
    for rec in ui_record_list:
        if not isinstance(rec, dict):
            continue
        gid = extract_primary_guid(rec)
        if isinstance(gid, int) and int(gid) > 0 and int(gid) not in record_by_guid:
            record_by_guid[int(gid)] = rec

    target_names = set(overrides.keys())
    matched_by_name: Dict[str, list[int]] = {n: [] for n in target_names}

    def _iter_layout_subtree_guids() -> Iterable[int]:
        stack = [int(x) for x in get_children_guids_from_parent_record(layout_record)]
        seen: set[int] = set()
        while stack:
            gid = int(stack.pop())
            if gid <= 0 or gid in seen:
                continue
            seen.add(gid)
            yield gid
            rec = record_by_guid.get(gid)
            if isinstance(rec, dict):
                stack.extend(int(x) for x in get_children_guids_from_parent_record(rec))

    for guid in _iter_layout_subtree_guids():
        rec = record_by_guid.get(int(guid))
        if not isinstance(rec, dict):
            continue
        name = try_extract_widget_name(rec)
        if isinstance(name, str) and name in target_names:
            matched_by_name[name].append(int(guid))

    duplicated = {n: guids for n, guids in matched_by_name.items() if len(guids) >= 2}
    if duplicated:
        raise RuntimeError(f"布局内存在重名固有控件，无法确定要改哪一个：{duplicated!r}")

    not_found = sorted([n for n, guids in matched_by_name.items() if not guids])
    if not_found:
        raise RuntimeError(f"布局内未找到这些固有控件（无法应用初始显隐覆盖）：{not_found!r}")

    changed_total = 0
    applied: Dict[str, Dict[str, Any]] = {}
    for name, visible in overrides.items():
        guid = int(matched_by_name[name][0])
        rec = record_by_guid.get(guid)
        if not isinstance(rec, dict):
            raise RuntimeError(f"internal error: matched guid missing record: {guid}")
        changed = int(apply_visibility_patch(rec, visible=bool(visible)))
        changed_total += changed
        applied[name] = {"guid": int(guid), "initial_visible": bool(visible), "changed": int(changed)}

    return {"visibility_changed_total": int(changed_total), "applied": applied}

