from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from ..writeback_feature_flags import is_writeback_feature_enabled


def _build_graph_variable_type_text_by_name(graph_variables: List[Dict[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for item in list(graph_variables):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        type_text = str(item.get("variable_type") or "").strip()
        if name == "" or type_text == "":
            continue
        if name not in out:
            out[name] = type_text
    return out


_LAYOUT_INDEX_HTML_STEM_IN_DESC_RE = re.compile(
    r"""[（(](?P<stem>[^（）()]+?)\.html[)）]""",
    flags=re.IGNORECASE,
)
_LAYOUT_INDEX_UI_KEY_HINT_IN_DESC_RE = re.compile(
    r"""LAYOUT_INDEX__HTML__(?P<stem>[^\s，。,。)）]+)""",
    flags=re.IGNORECASE,
)


def _infer_layout_index_html_stem_from_graph_variable_description(description: str) -> str | None:
    """
    节点图里“布局索引”类 GraphVariables 的描述通常包含：
    - `（<stem>.html）`
    - 或显式 hint：`LAYOUT_INDEX__HTML__<stem>`
    """
    desc = str(description or "").strip()
    if desc == "":
        return None
    m = _LAYOUT_INDEX_HTML_STEM_IN_DESC_RE.search(desc)
    if m is not None:
        stem = str(m.group("stem") or "").strip()
        return stem if stem != "" else None
    m = _LAYOUT_INDEX_UI_KEY_HINT_IN_DESC_RE.search(desc)
    if m is not None:
        stem = str(m.group("stem") or "").strip()
        return stem if stem != "" else None
    return None


def _extract_ui_record_list_from_base_raw_dump_object(base_raw_dump_object: Dict[str, Any]) -> List[object] | None:
    root_data = base_raw_dump_object.get("4")
    if not isinstance(root_data, dict):
        return None
    field9 = root_data.get("9")
    if not isinstance(field9, dict):
        return None
    record_list = field9.get("502")
    if not isinstance(record_list, list):
        return None
    return list(record_list)


def _maybe_backfill_layout_index_registry_from_base_ui_records(
    *,
    ui_key_to_guid_registry: Dict[str, int],
    graph_variables: List[Dict[str, Any]],
    base_raw_dump_object: Dict[str, Any] | None,
) -> Tuple[Dict[str, int], Dict[str, Any]]:
    """
    工程化兜底：当 UI guid registry 未提供/缺失 `LAYOUT_INDEX__HTML__*` 时，尝试从 base `.gil` 的 UI records 反查布局 root GUID，
    并将结果写入 registry，供后续 graph_variables(default_value) 自动回填使用。

    约束（保守）：
    - 只对“布局索引_”前缀且 default_value 仍为 0/空 的整数图变量尝试回填；
    - 仅在 UI records 能唯一定位到 root guid 时写入（否则不写，避免误回填）；
    - 仅接受看起来像 GUID 的值（>1_000_000_000）。
    """
    report: Dict[str, Any] = {
        "applied": False,
        "attempted_total": 0,
        "added_total": 0,
        "reason": "skipped",
    }
    if base_raw_dump_object is None:
        return dict(ui_key_to_guid_registry), {**report, "reason": "base_raw_dump_object_missing"}

    record_list = _extract_ui_record_list_from_base_raw_dump_object(dict(base_raw_dump_object))
    if not record_list:
        return dict(ui_key_to_guid_registry), {**report, "reason": "base_ui_records_missing"}

    from ugc_file_tools.ui.guid_resolution import build_ui_record_index_from_record_list

    ui_index = build_ui_record_index_from_record_list(list(record_list))
    if ui_index is None:
        return dict(ui_key_to_guid_registry), {**report, "reason": "base_ui_records_empty_or_invalid"}

    # 收集“需要回填的 layout stems”
    stems: List[str] = []
    for v in list(graph_variables):
        if not isinstance(v, dict):
            continue
        name = str(v.get("name") or "").strip()
        if not name.startswith("布局索引_"):
            continue
        variable_type = str(v.get("variable_type") or "").strip()
        if variable_type != "整数":
            continue
        default_value = v.get("default_value")
        is_unset_int = (default_value is None) or (isinstance(default_value, int) and int(default_value) == 0)
        if not is_unset_int:
            continue
        stem = _infer_layout_index_html_stem_from_graph_variable_description(str(v.get("description") or ""))
        if stem is None:
            continue
        stems.append(str(stem))

    stems_uniq = sorted({str(s).strip() for s in stems if str(s).strip() != ""}, key=lambda t: t.casefold())
    if not stems_uniq:
        return dict(ui_key_to_guid_registry), {**report, "reason": "no_layout_index_stems"}

    updated: Dict[str, int] = dict(ui_key_to_guid_registry or {})
    added_total = 0
    for stem in stems_uniq:
        # 兼容：部分链路约定使用 `<stem>_html` 作为 UI records 的 layout root name
        candidates = [str(stem), f"{stem}_html"]

        resolved: int | None = None
        for cand in candidates:
            guids = list(ui_index.guids_by_name.get(str(cand), []) or [])
            roots = [int(g) for g in guids if ui_index.parent_by_guid.get(int(g)) is None]
            uniq = sorted({int(x) for x in roots if int(x) > 1_000_000_000})
            if len(uniq) == 1:
                resolved = int(uniq[0])
                break

        if resolved is None:
            continue

        for kstem in {str(stem), f"{stem}_html"}:
            key = f"LAYOUT_INDEX__HTML__{kstem}"
            if key not in updated:
                updated[key] = int(resolved)
                added_total += 1

    return dict(updated), {
        **dict(report),
        "applied": bool(added_total > 0),
        "attempted_total": int(len(stems_uniq)),
        "added_total": int(added_total),
        "reason": ("ok" if added_total > 0 else "not_found_in_base_ui_records"),
    }


def _maybe_autofill_graph_variables_from_ui_registry(
    *,
    graph_variables: List[Dict[str, Any]],
    ui_key_to_guid_registry: Dict[str, int],
    enabled: bool,
    excluded_names: set[str] | None,
    base_raw_dump_object: Dict[str, Any] | None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    from ..graph_variables import apply_ui_registry_auto_fill_to_graph_variables

    graph_variables_ui_autofill_report: Dict[str, Any] = {
        "updated_total": 0,
        "updates": [],
        "skipped": True,
        "reason": "disabled_by_caller",
    }
    if not bool(enabled):
        return list(graph_variables), dict(graph_variables_ui_autofill_report)

    # 兜底：从 base UI records 回填 layout-index registry（不依赖外部 ui_guid_registry.json 文件）
    if is_writeback_feature_enabled("ui_registry_backfill_layout_index_from_base_ui_records"):
        effective_registry, layout_index_backfill_report = _maybe_backfill_layout_index_registry_from_base_ui_records(
            ui_key_to_guid_registry=dict(ui_key_to_guid_registry or {}),
            graph_variables=list(graph_variables),
            base_raw_dump_object=(dict(base_raw_dump_object) if isinstance(base_raw_dump_object, dict) else None),
        )
    else:
        effective_registry, layout_index_backfill_report = dict(ui_key_to_guid_registry or {}), {
            "applied": False,
            "attempted_total": 0,
            "added_total": 0,
            "reason": "disabled_by_flag",
        }

    excluded = {str(x).strip() for x in (excluded_names or set()) if str(x).strip() != ""}
    if excluded:
        fillables: List[Dict[str, Any]] = []
        for v in list(graph_variables):
            if not isinstance(v, dict):
                continue
            name = str(v.get("name") or "").strip()
            if name in excluded:
                continue
            fillables.append(v)

        filled, graph_variables_ui_autofill_report = apply_ui_registry_auto_fill_to_graph_variables(
            graph_variables=fillables,
            ui_key_to_guid_registry=effective_registry,
        )

        # 复原回原始顺序：排除项保留原样，其余替换为 filled 的对应项
        filled_iter = iter(list(filled))
        merged: List[Dict[str, Any]] = []
        for v in list(graph_variables):
            if not isinstance(v, dict):
                continue
            name = str(v.get("name") or "").strip()
            if name in excluded:
                merged.append(v)
            else:
                merged.append(next(filled_iter))

        graph_variables_ui_autofill_report = {
            **dict(graph_variables_ui_autofill_report),
            "layout_index_registry_backfill": dict(layout_index_backfill_report),
            "excluded_total": int(len(excluded)),
            "excluded_names": sorted(excluded, key=lambda t: t.casefold())[:200],
        }
        return merged, dict(graph_variables_ui_autofill_report)

    filled2, graph_variables_ui_autofill_report = apply_ui_registry_auto_fill_to_graph_variables(
        graph_variables=graph_variables,
        ui_key_to_guid_registry=effective_registry,
    )
    graph_variables_ui_autofill_report = {
        **dict(graph_variables_ui_autofill_report),
        "layout_index_registry_backfill": dict(layout_index_backfill_report),
    }
    return list(filled2), dict(graph_variables_ui_autofill_report)

