from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ugc_file_tools.ui.guid_resolution import UiRecordIndex, build_ui_record_index_from_record_list

_CACHE_SCHEMA_VERSION = 1
_ANALYSIS_VERSION = 2


@dataclass(frozen=True, slots=True)
class GilBackfillAnalysis:
    """
    `.gil` 的“回填识别可复用分析结果”（与用户勾选内容无关）。

    说明：
    - 该分析结果用于导出中心“回填识别”缓存：同一份 base/id_ref `.gil` 未变化时可直接复用，
      避免重复 decode `.gil`（更快，也降低在某些样本/环境下触发不稳定的概率）。
    - 缓存命中条件：gil_path 相同，且 (file_size, mtime_ns) 未变化。
    """

    component_name_to_id: dict[str, int]
    entity_name_to_guid: dict[str, int]
    ui_records_total: int
    ui_index: UiRecordIndex | None
    custom_vars_by_entity_name: dict[str, dict[str, int]]


def _export_center_backfill_cache_dir(*, workspace_root: Path) -> Path:
    """
    导出中心“回填识别”的运行期缓存目录（按工程约定落在 app/runtime/cache/）。

    注意：
    - 这里不走 settings.RUNTIME_CACHE_ROOT：导出中心现有 state 与其它缓存均采用固定相对路径；
      保持一致，避免缓存散落导致排查困难。
    """
    cache_dir = (
        Path(workspace_root).resolve()
        / "app"
        / "runtime"
        / "cache"
        / "ugc_file_tools"
        / "export_center"
        / "backfill_gil_analysis"
    ).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _cache_key_for_gil_path(gil_file_path: Path) -> str:
    p = Path(gil_file_path).resolve()
    key_text = str(p).casefold()
    return hashlib.md5(key_text.encode("utf-8")).hexdigest()


def _cache_file_path(*, workspace_root: Path, gil_file_path: Path) -> Path:
    cache_dir = _export_center_backfill_cache_dir(workspace_root=workspace_root)
    key = _cache_key_for_gil_path(Path(gil_file_path))
    return (cache_dir / f"gil_{key}.json").resolve()


def _serialize_ui_index(ui_index: UiRecordIndex) -> dict[str, object]:
    return {
        "guid_set": sorted([int(x) for x in set(ui_index.guid_set) if int(x) > 0]),
        "name_by_guid": {str(int(k)): str(v) for k, v in dict(ui_index.name_by_guid).items() if isinstance(v, str)},
        "parent_by_guid": {
            str(int(k)): (int(v) if isinstance(v, int) else None) for k, v in dict(ui_index.parent_by_guid).items()
        },
        "children_by_parent": {
            str(int(k)): [int(x) for x in list(v or []) if isinstance(x, int) and int(x) > 0]
            for k, v in dict(ui_index.children_by_parent).items()
        },
        "component_type_ids_by_guid": {
            str(int(k)): sorted([int(x) for x in set(v or set()) if isinstance(x, int) and int(x) > 0])
            for k, v in dict(ui_index.component_type_ids_by_guid).items()
        },
        "guids_by_name": {
            str(k): [int(x) for x in list(v or []) if isinstance(x, int) and int(x) > 0] for k, v in dict(ui_index.guids_by_name).items()
        },
    }


def _deserialize_ui_index(obj: object) -> UiRecordIndex | None:
    if obj is None:
        return None
    if not isinstance(obj, dict):
        return None

    guid_set_raw = obj.get("guid_set")
    guid_set = set(int(x) for x in (guid_set_raw if isinstance(guid_set_raw, list) else []) if isinstance(x, int) and int(x) > 0)

    name_by_guid: dict[int, str] = {}
    raw_name_by_guid = obj.get("name_by_guid")
    if isinstance(raw_name_by_guid, dict):
        for k, v in raw_name_by_guid.items():
            if not isinstance(v, str):
                continue
            kk = str(k or "").strip()
            if not kk.isdigit():
                continue
            name_by_guid[int(kk)] = str(v)

    parent_by_guid: dict[int, int | None] = {}
    raw_parent = obj.get("parent_by_guid")
    if isinstance(raw_parent, dict):
        for k, v in raw_parent.items():
            kk = str(k or "").strip()
            if not kk.isdigit():
                continue
            if v is None:
                parent_by_guid[int(kk)] = None
                continue
            if isinstance(v, int):
                parent_by_guid[int(kk)] = int(v)

    children_by_parent: dict[int, list[int]] = {}
    raw_children = obj.get("children_by_parent")
    if isinstance(raw_children, dict):
        for k, v in raw_children.items():
            kk = str(k or "").strip()
            if not kk.isdigit():
                continue
            if not isinstance(v, list):
                continue
            children = [int(x) for x in v if isinstance(x, int) and int(x) > 0]
            children_by_parent[int(kk)] = list(children)

    component_type_ids_by_guid: dict[int, set[int]] = {}
    raw_types = obj.get("component_type_ids_by_guid")
    if isinstance(raw_types, dict):
        for k, v in raw_types.items():
            kk = str(k or "").strip()
            if not kk.isdigit():
                continue
            if not isinstance(v, list):
                continue
            component_type_ids_by_guid[int(kk)] = {int(x) for x in v if isinstance(x, int) and int(x) > 0}

    guids_by_name: dict[str, list[int]] = {}
    raw_guids_by_name = obj.get("guids_by_name")
    if isinstance(raw_guids_by_name, dict):
        for k, v in raw_guids_by_name.items():
            name = str(k or "").strip()
            if name == "":
                continue
            if not isinstance(v, list):
                continue
            guids_by_name[name] = [int(x) for x in v if isinstance(x, int) and int(x) > 0]

    if not guid_set:
        return None

    return UiRecordIndex(
        guid_set=set(guid_set),
        name_by_guid=dict(name_by_guid),
        parent_by_guid=dict(parent_by_guid),
        children_by_parent=dict(children_by_parent),
        component_type_ids_by_guid=dict(component_type_ids_by_guid),
        guids_by_name=dict(guids_by_name),
    )


def _as_list_allow_scalar(value: object) -> list[object]:
    if isinstance(value, list):
        return list(value)
    if value is None:
        return []
    return [value]


def extract_ui_record_list_from_payload_root(payload_root: Mapping[str, object]) -> list[object]:
    """
    从 dump-json payload_root 提取 UI record list（root4/9/502）。

    注意：
    - 回填识别不应因为 UI 段缺失而崩溃；缺失则返回空列表。
    """
    node9 = payload_root.get("9")
    if node9 is None:
        return []

    if isinstance(node9, str) and node9.startswith("<binary_data>"):
        from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import binary_data_text_to_numeric_message

        decoded = binary_data_text_to_numeric_message(node9)
        node9 = decoded

    if not isinstance(node9, dict):
        return []

    record_list = node9.get("502")
    if record_list is None:
        return []
    if isinstance(record_list, list):
        records = list(record_list)
    elif isinstance(record_list, dict):
        records = [record_list]
    else:
        return []

    # 兼容 dump-json 常见折叠形态：repeated message 在“只有 1 个元素”时可能被折叠为 dict 而非 list。
    # guid_resolution 的索引构建默认按 list 口径读取 component_list(505) 与 parent(504)。
    normalized: list[object] = []
    for r0 in records:
        if not isinstance(r0, dict):
            normalized.append(r0)
            continue

        rec = dict(r0)
        comp_list = rec.get("505")
        if isinstance(comp_list, dict):
            rec["505"] = [dict(comp_list)]
        parent_value = rec.get("504")
        if isinstance(parent_value, list) and parent_value and isinstance(parent_value[0], int):
            rec["504"] = int(parent_value[0])

        normalized.append(rec)

    return normalized


def collect_custom_variables_by_entity_name_from_payload_root(payload_root: dict[str, Any]) -> dict[str, dict[str, int]]:
    """
    读取 root4/5/1（实体条目）下的 override_variables(group1) 变量列表，返回：
      {entity_name: {var_name_norm_casefold: type_code_int}}
    """
    from ugc_file_tools.custom_variables.coerce import normalize_custom_variable_name_field2

    section5 = payload_root.get("5")
    if not isinstance(section5, dict):
        return {}

    def _extract_entity_name(entry: Mapping[str, Any]) -> str:
        # 兼容 dump-json 折叠：repeated 字段在只有 1 个元素时可能为 dict 而非 list
        meta_list = _as_list_allow_scalar(entry.get("5"))
        for item in meta_list:
            if not isinstance(item, dict):
                continue
            if item.get("1") != 1:
                continue
            name_container = item.get("11")
            name_value: object | None = None
            if isinstance(name_container, dict):
                name_value = name_container.get("1")
            elif isinstance(name_container, str):
                name_value = name_container
            if not isinstance(name_value, str):
                continue

            text = str(name_value)
            if text.startswith("<binary_data>"):
                from ugc_file_tools.gil_dump_codec.protobuf_like import parse_binary_data_hex_text

                raw_bytes = parse_binary_data_hex_text(text)
                decoded_text = raw_bytes.decode("utf-8", errors="replace")
                if "\x00" in decoded_text:
                    decoded_text = decoded_text.split("\x00", 1)[0]
                return str(decoded_text).strip()

            if "\x00" in text:
                text = text.split("\x00", 1)[0]
            return str(text).strip()
        return ""

    entry_list = section5.get("1")
    entries: list[object] = _as_list_allow_scalar(entry_list)

    out: dict[str, dict[str, int]] = {}
    for entry0 in entries:
        if not isinstance(entry0, dict):
            continue

        entity_name = _extract_entity_name(entry0)
        if str(entity_name).strip() == "":
            continue

        group_list = _as_list_allow_scalar(entry0.get("7"))
        group1_container: dict[str, object] | None = None
        for g0 in group_list:
            if not isinstance(g0, dict):
                continue
            if g0.get("1") != 1:
                continue
            if g0.get("2") != 1:
                continue
            container = g0.get("11")
            if isinstance(container, dict):
                group1_container = container
                break
        if group1_container is None:
            out[str(entity_name)] = {}
            continue

        variable_items_raw = group1_container.get("1")
        variable_items = _as_list_allow_scalar(variable_items_raw)
        by_name: dict[str, int] = {}
        for it0 in variable_items:
            if not isinstance(it0, dict):
                continue
            name_norm = normalize_custom_variable_name_field2(it0.get("2"))
            if name_norm == "":
                continue
            type_code = it0.get("3")
            type_int = int(type_code) if isinstance(type_code, int) else 0
            key = name_norm.casefold()
            if key not in by_name:
                by_name[key] = int(type_int)
        out[str(entity_name)] = dict(by_name)
    return dict(out)


def compute_gil_backfill_analysis(*, gil_file_path: Path) -> GilBackfillAnalysis:
    p = Path(gil_file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))

    from ugc_file_tools.id_ref_from_gil import build_id_ref_mappings_from_payload_root
    from ugc_file_tools.node_graph_writeback.gil_dump import dump_gil_to_raw_json_object, get_payload_root

    raw_dump_object = dump_gil_to_raw_json_object(p)
    payload_root = get_payload_root(raw_dump_object)

    component_name_to_id, entity_name_to_guid = build_id_ref_mappings_from_payload_root(payload_root=payload_root)

    ui_records = extract_ui_record_list_from_payload_root(payload_root)
    ui_index = build_ui_record_index_from_record_list(list(ui_records)) if ui_records else None

    custom_vars_by_entity_name = collect_custom_variables_by_entity_name_from_payload_root(payload_root)

    return GilBackfillAnalysis(
        component_name_to_id=dict(component_name_to_id),
        entity_name_to_guid=dict(entity_name_to_guid),
        ui_records_total=int(len(ui_records)),
        ui_index=ui_index,
        custom_vars_by_entity_name=dict(custom_vars_by_entity_name),
    )


def load_cached_gil_backfill_analysis(*, workspace_root: Path, gil_file_path: Path) -> GilBackfillAnalysis | None:
    ws = Path(workspace_root).resolve()
    if not ws.is_dir():
        raise FileNotFoundError(str(ws))
    p = Path(gil_file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))

    cache_path = _cache_file_path(workspace_root=ws, gil_file_path=p)
    if not cache_path.is_file():
        return None

    obj = json.loads(cache_path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        return None

    if int(obj.get("schema_version") or 0) != int(_CACHE_SCHEMA_VERSION):
        return None
    if int(obj.get("analysis_version") or 0) != int(_ANALYSIS_VERSION):
        return None

    st = p.stat()
    want_size = int(st.st_size)
    want_mtime_ns = int(st.st_mtime_ns)
    got_size = obj.get("file_size")
    got_mtime_ns = obj.get("mtime_ns")
    if not (isinstance(got_size, int) and isinstance(got_mtime_ns, int)):
        return None
    if int(got_size) != int(want_size) or int(got_mtime_ns) != int(want_mtime_ns):
        return None

    analysis = obj.get("analysis")
    if not isinstance(analysis, dict):
        return None

    comp_raw = analysis.get("component_name_to_id")
    ent_raw = analysis.get("entity_name_to_guid")
    if not isinstance(comp_raw, dict) or not isinstance(ent_raw, dict):
        return None

    component_name_to_id: dict[str, int] = {}
    for k, v in comp_raw.items():
        name = str(k or "").strip()
        if name == "":
            continue
        if isinstance(v, int) and int(v) > 0:
            component_name_to_id[name] = int(v)

    entity_name_to_guid: dict[str, int] = {}
    for k, v in ent_raw.items():
        name = str(k or "").strip()
        if name == "":
            continue
        if isinstance(v, int) and int(v) > 0:
            entity_name_to_guid[name] = int(v)

    ui_records_total_value = analysis.get("ui_records_total")
    ui_records_total = int(ui_records_total_value) if isinstance(ui_records_total_value, int) else 0

    ui_index = _deserialize_ui_index(analysis.get("ui_index"))

    custom_vars_raw = analysis.get("custom_vars_by_entity_name")
    custom_vars_by_entity_name: dict[str, dict[str, int]] = {}
    if isinstance(custom_vars_raw, dict):
        for ent_name, var_map in custom_vars_raw.items():
            ent = str(ent_name or "").strip()
            if ent == "":
                continue
            if not isinstance(var_map, dict):
                continue
            inner: dict[str, int] = {}
            for var_name, type_code in var_map.items():
                vn = str(var_name or "").strip()
                if vn == "":
                    continue
                if isinstance(type_code, int):
                    inner[vn] = int(type_code)
            custom_vars_by_entity_name[ent] = dict(inner)

    return GilBackfillAnalysis(
        component_name_to_id=dict(component_name_to_id),
        entity_name_to_guid=dict(entity_name_to_guid),
        ui_records_total=int(ui_records_total),
        ui_index=ui_index,
        custom_vars_by_entity_name=dict(custom_vars_by_entity_name),
    )


def save_cached_gil_backfill_analysis(*, workspace_root: Path, gil_file_path: Path, analysis: GilBackfillAnalysis) -> None:
    ws = Path(workspace_root).resolve()
    if not ws.is_dir():
        raise FileNotFoundError(str(ws))
    p = Path(gil_file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))

    cache_path = _cache_file_path(workspace_root=ws, gil_file_path=p)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    st = p.stat()
    payload: dict[str, object] = {
        "schema_version": int(_CACHE_SCHEMA_VERSION),
        "analysis_version": int(_ANALYSIS_VERSION),
        "gil_path": str(p),
        "file_size": int(st.st_size),
        "mtime_ns": int(st.st_mtime_ns),
        "analysis": {
            "component_name_to_id": dict(analysis.component_name_to_id),
            "entity_name_to_guid": dict(analysis.entity_name_to_guid),
            "ui_records_total": int(analysis.ui_records_total),
            "ui_index": (_serialize_ui_index(analysis.ui_index) if analysis.ui_index is not None else None),
            "custom_vars_by_entity_name": dict(analysis.custom_vars_by_entity_name),
        },
    }

    tmp_path = cache_path.with_name(f"{cache_path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(cache_path)


def load_or_compute_gil_backfill_analysis(
    *,
    workspace_root: Path | None,
    gil_file_path: Path,
) -> tuple[GilBackfillAnalysis, bool]:
    """
    返回：(analysis, cache_hit)。

    - workspace_root=None：禁用落盘缓存（直接计算，cache_hit=False）
    - workspace_root!=None：尝试命中缓存；未命中则计算并写入缓存
    """
    p = Path(gil_file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))

    if workspace_root is None:
        return compute_gil_backfill_analysis(gil_file_path=p), False

    ws = Path(workspace_root).resolve()
    if not ws.is_dir():
        raise FileNotFoundError(str(ws))

    cached = load_cached_gil_backfill_analysis(workspace_root=ws, gil_file_path=p)
    if cached is not None:
        return cached, True

    analysis = compute_gil_backfill_analysis(gil_file_path=p)
    save_cached_gil_backfill_analysis(workspace_root=ws, gil_file_path=p, analysis=analysis)
    return analysis, False


__all__ = [
    "GilBackfillAnalysis",
    "collect_custom_variables_by_entity_name_from_payload_root",
    "compute_gil_backfill_analysis",
    "extract_ui_record_list_from_payload_root",
    "load_cached_gil_backfill_analysis",
    "load_or_compute_gil_backfill_analysis",
    "save_cached_gil_backfill_analysis",
]

