from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .._common import IdRefPlaceholderUsage


def build_backfill_deps_rows(
    *,
    fmt: str,
    graphs_total: int,
    id_ref_usage: IdRefPlaceholderUsage,
    ui_keys: Iterable[str],
    selected_level_custom_variable_ids: Sequence[str],
    level_custom_variable_meta_by_id: Mapping[str, Mapping[str, object]] | None,
) -> list[dict[str, str]]:
    total = int(graphs_total)
    if total <= 0:
        return []

    usage = id_ref_usage
    entity_list = sorted([str(x) for x in usage.entity_names], key=lambda t: t.casefold())
    component_list = sorted([str(x) for x in usage.component_names], key=lambda t: t.casefold())
    ui_key_list = sorted([str(x) for x in set(ui_keys or [])], key=lambda t: t.casefold())

    rows: list[dict[str, str]] = []

    def _add_pending(*, category: str, key: str) -> None:
        rows.append({"category": str(category), "key": str(key), "value": "", "status": "待识别", "note": ""})

    for name in entity_list:
        _add_pending(category="实体ID(entity)", key=str(name))
    for name in component_list:
        _add_pending(category="元件ID(component)", key=str(name))
    for k in ui_key_list:
        _add_pending(category="UI控件ID(ui_key)", key=str(k))

    fmt2 = str(fmt or "").strip()
    if fmt2 == "gil":
        ids = [str(x) for x in list(selected_level_custom_variable_ids or []) if str(x).strip() != ""]
        if ids:
            meta_by_id = level_custom_variable_meta_by_id or {}
            for vid in ids:
                meta = meta_by_id.get(str(vid))
                vname = str(meta.get("variable_name") or "").strip() if isinstance(meta, Mapping) else ""
                display = f"{vname} ({vid})" if vname else f"{vid}"
                _add_pending(category="自定义变量(关卡实体)", key=str(display))

    return list(rows)


def compute_backfill_signature_gia(
    *,
    id_ref_usage: IdRefPlaceholderUsage,
    ui_keys: Iterable[str],
    target_gil_text: str,
    id_ref_gil_text: str,
    ui_export_record_id: str | None,
    graphs_total: int,
) -> tuple:
    ref = str(target_gil_text or "").strip()
    ref_resolved = str(Path(ref).resolve()) if ref else ""
    ref2 = str(id_ref_gil_text or "").strip()
    ref2_resolved = str(Path(ref2).resolve()) if ref2 else ""
    rid = str(ui_export_record_id or "").strip()
    return (
        tuple(sorted(id_ref_usage.entity_names)),
        tuple(sorted(id_ref_usage.component_names)),
        tuple(sorted({str(x) for x in set(ui_keys or []) if str(x).strip() != ""})),
        ref_resolved,
        ref2_resolved,
        rid,
        int(graphs_total),
    )


def compute_backfill_signature_gil(
    *,
    id_ref_usage: IdRefPlaceholderUsage,
    ui_keys: Iterable[str],
    target_gil_text: str,
    id_ref_gil_text: str,
    use_base_as_id_ref_fallback: bool,
    selected_level_custom_variable_ids: Sequence[str],
    write_ui_effective: bool,
    ui_auto_sync_enabled: bool,
    ui_export_record_id: str | None,
    graphs_total: int,
) -> tuple:
    target = str(target_gil_text or "").strip()
    target_resolved = str(Path(target).resolve()) if target else ""
    ref2 = str(id_ref_gil_text or "").strip()
    ref2_resolved = str(Path(ref2).resolve()) if ref2 else ""
    ids = tuple([str(x) for x in list(selected_level_custom_variable_ids or [])])
    rid = str(ui_export_record_id or "").strip()
    return (
        tuple(sorted(id_ref_usage.entity_names)),
        tuple(sorted(id_ref_usage.component_names)),
        tuple(sorted({str(x) for x in set(ui_keys or []) if str(x).strip() != ""})),
        target_resolved,
        ref2_resolved,
        bool(use_base_as_id_ref_fallback),
        tuple(ids),
        bool(write_ui_effective),
        bool(ui_auto_sync_enabled),
        rid,
        int(graphs_total),
    )


__all__ = [
    "compute_backfill_signature_gia",
    "compute_backfill_signature_gil",
    "build_backfill_deps_rows",
]

