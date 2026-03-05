from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.gil_dump_codec.protobuf_like import parse_binary_data_hex_text
from ugc_file_tools.ui.readable_dump import (
    RectTransformState,
    choose_best_rect_transform_state as _choose_best_rect_transform_state,
    choose_best_rect_transform_states as _choose_best_rect_transform_states,
    extract_primary_guid as _extract_primary_guid,
    extract_primary_name as _extract_primary_name,
    extract_ui_record_list as _extract_ui_record_list,
    find_rect_transform_state_lists as _find_rect_transform_state_lists,
)


@dataclass(frozen=True, slots=True)
class _SchemaExample:
    guid: int
    index_id: Optional[int]
    name: str
    rect_transform_source_path: Optional[str]
    source_gil: Optional[str]


def _now_iso() -> str:
    # 不要求带时区；仅作为本地沉淀库的“最后观测时间”
    return datetime.now().isoformat(timespec="seconds")


def _is_binary_data_text(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("<binary_data>")


def _is_numeric_key_dict(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if not value:
        return False
    for k in value.keys():
        if not isinstance(k, str):
            return False
        if not k.isdigit():
            return False
    return True


def _shape_signature(value: Any) -> Any:
    """
    生成“结构签名”（不包含具体值），用于把同类 record 归并到同一个 schema_id。

    设计目标：
    - 签名应稳定（跨运行、跨存档可比对）
    - 签名应忽略“可变值”（guid/name/坐标/颜色等），只保留字段结构
    - 对 `<binary_data>` 不在签名中记录长度，避免同类因 blob 长短变化而碎裂
    """
    if value is None:
        return {"t": "null"}
    if isinstance(value, bool):
        return {"t": "bool"}
    if isinstance(value, int):
        return {"t": "int"}
    if isinstance(value, float):
        return {"t": "float"}
    if isinstance(value, str):
        if _is_binary_data_text(value):
            return {"t": "binary_data"}
        # dump-json 中可能出现空字符串作为“空 bytes”的替代形态（例如 children list）
        if value == "":
            return {"t": "str_empty"}
        return {"t": "str"}
    if isinstance(value, list):
        # list 内部顺序在不同存档可能不同（尤其 meta 列表），这里按“元素形态集合”归并
        unique_shapes: Dict[str, Any] = {}
        for item in value:
            shape = _shape_signature(item)
            key = json.dumps(shape, ensure_ascii=False, sort_keys=True)
            unique_shapes[key] = shape
        shapes_sorted = [unique_shapes[k] for k in sorted(unique_shapes.keys())]
        return {"t": "list", "items": shapes_sorted}
    if isinstance(value, dict):
        # key 在 dump-json 中为数值字符串（field_number），稳定且有意义
        keys_sorted = sorted(value.keys(), key=lambda k: str(k))
        return {"t": "dict", "k": {str(k): _shape_signature(value.get(k)) for k in keys_sorted}}
    return {"t": type(value).__name__}


def _family_signature(value: Any) -> Any:
    """
    生成“族签名”（family signature）：比 shape_signature 更粗，用于把“同一控件概念的多种写法”聚类到同一 family_id。

    当前策略（保守 + 可解释）：
    - 将 protobuf-like message 的两种常见表示统一为同一类：
      - `<binary_data>...` blob -> 视为 {"t": "msg"}
      - key 全为数字字符串的 dict message -> 视为 {"t": "msg"}
    - 其余字段仍按结构递归记录（但不包含具体值）。

    注意：
    - family_id 仅用于观测/统计，不作为写回模板选择依据；避免过度归并导致写回风险。
    """
    if value is None:
        return {"t": "null"}
    if isinstance(value, bool):
        return {"t": "bool"}
    if isinstance(value, int):
        return {"t": "int"}
    if isinstance(value, float):
        return {"t": "float"}
    if isinstance(value, str):
        if _is_binary_data_text(value):
            return {"t": "msg"}
        if value == "":
            return {"t": "str_empty"}
        return {"t": "str"}
    if isinstance(value, list):
        unique_shapes: Dict[str, Any] = {}
        for item in value:
            shape = _family_signature(item)
            key = json.dumps(shape, ensure_ascii=False, sort_keys=True)
            unique_shapes[key] = shape
        shapes_sorted = [unique_shapes[k] for k in sorted(unique_shapes.keys())]
        return {"t": "list", "items": shapes_sorted}
    if isinstance(value, dict):
        if _is_numeric_key_dict(value):
            return {"t": "msg"}
        keys_sorted = sorted(value.keys(), key=lambda k: str(k))
        return {"t": "dict", "k": {str(k): _family_signature(value.get(k)) for k in keys_sorted}}
    return {"t": type(value).__name__}


def _hash_schema_signature(signature: Any) -> str:
    payload = json.dumps(signature, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


def _collect_binary_data_blobs(value: Any, path: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if _is_binary_data_text(value):
        data = parse_binary_data_hex_text(value)
        preview = data[:16]
        out.append(
            {
                "path": path,
                "length": len(data),
                "preview_hex": preview.hex().upper(),
            }
        )
        return out
    if isinstance(value, list):
        for idx, item in enumerate(value):
            out.extend(_collect_binary_data_blobs(item, f"{path}[{idx}]"))
        return out
    if isinstance(value, dict):
        for k, v in value.items():
            out.extend(_collect_binary_data_blobs(v, f"{path}/{k}"))
        return out
    return out


def _load_or_init_index(index_path: Path) -> Dict[str, Any]:
    if not index_path.exists():
        return {
            "format": "ugc_ui_schema_library_v1",
            "generated_at": _now_iso(),
            "schemas": [],
        }
    obj = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("ui_schema_library index.json 顶层不是 dict")
    fmt = obj.get("format")
    if fmt != "ugc_ui_schema_library_v1":
        raise ValueError(f"不支持的 ui_schema_library format: {fmt!r}")
    schemas = obj.get("schemas")
    if not isinstance(schemas, list):
        raise ValueError("ui_schema_library index.json.schemas 不是 list")
    return obj


def record_ui_schema_library_from_dll_dump(
    *,
    dll_dump_object: Dict[str, Any],
    source_gil_file_path: Optional[Path] = None,
    data_root: Optional[Path] = None,
    max_examples_per_schema: int = 3,
) -> Dict[str, Any]:
    """
    从 DLL dump-json 中提取 UI record list（4/9/502）并沉淀 schema library。

    写入：
    - <data_root>/index.json
    - <data_root>/records/<schema_id>.record.json
    """
    data_root_path = (Path(data_root).resolve() if data_root is not None else (Path(__file__).resolve().parent / "data"))
    records_dir = data_root_path / "records"
    records_dir.mkdir(parents=True, exist_ok=True)

    index_path = data_root_path / "index.json"
    index_obj = _load_or_init_index(index_path)

    existing_entries: Dict[str, Dict[str, Any]] = {}
    for entry in index_obj.get("schemas", []):
        if not isinstance(entry, dict):
            continue
        schema_id = entry.get("schema_id")
        if isinstance(schema_id, str) and schema_id.strip() != "":
            existing_entries[str(schema_id)] = entry

    ui_record_list = _extract_ui_record_list(dll_dump_object)
    if not isinstance(ui_record_list, list):
        raise ValueError("dll_dump_object 中的 UI record list 不是 list（期望 4/9/502）")

    source_gil_text = str(Path(source_gil_file_path).resolve()) if source_gil_file_path is not None else None

    added_schema_total = 0
    updated_schema_total = 0
    observed_record_total = 0
    family_stats: Dict[str, Dict[str, Any]] = {}

    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        guid_value = _extract_primary_guid(record)
        if guid_value is None:
            continue
        guid = int(guid_value)
        index_id_value = record.get("504") if isinstance(record.get("504"), int) else None
        name_text = str(_extract_primary_name(record) or "")

        rect_candidates = _find_rect_transform_state_lists(record)
        rect_path, rect_states = _choose_best_rect_transform_states(rect_candidates)
        rect_best = _choose_best_rect_transform_state(rect_states)
        rect_path_text = str(rect_path) if rect_path is not None else None

        signature = _shape_signature(record)
        schema_id = _hash_schema_signature(signature)
        family_signature = _family_signature(record)
        family_id = _hash_schema_signature(family_signature)

        schema_record_path = records_dir / f"{schema_id}.record.json"

        example = _SchemaExample(
            guid=guid,
            index_id=(int(index_id_value) if index_id_value is not None else None),
            name=name_text,
            rect_transform_source_path=rect_path_text,
            source_gil=source_gil_text,
        )

        entry = existing_entries.get(schema_id)
        if entry is None:
            entry = {
                "schema_id": schema_id,
                "shape_signature": signature,
                "count_total": 0,
                "first_seen_at": _now_iso(),
                "last_seen_at": _now_iso(),
                "record_template": str(schema_record_path.relative_to(data_root_path)).replace("\\", "/"),
                "examples": [],
                "label": "",
                "family_id": family_id,
                "family_signature": family_signature,
            }
            existing_entries[schema_id] = entry
            added_schema_total += 1
        else:
            entry["last_seen_at"] = _now_iso()
            updated_schema_total += 1
            if "family_id" not in entry:
                entry["family_id"] = family_id
            if "family_signature" not in entry:
                entry["family_signature"] = family_signature

        entry["count_total"] = int(entry.get("count_total") or 0) + 1

        examples = entry.get("examples")
        if not isinstance(examples, list):
            examples = []
            entry["examples"] = examples

        if len(examples) < int(max_examples_per_schema):
            examples.append(
                {
                    "guid": int(example.guid),
                    "index_id": int(example.index_id) if example.index_id is not None else None,
                    "name": str(example.name),
                    "rect_transform_source_path": example.rect_transform_source_path,
                    "source_gil": example.source_gil,
                }
            )

        if not schema_record_path.exists():
            record_bundle = {
                "schema_id": schema_id,
                "family_id": family_id,
                "source": {
                    "source_gil": source_gil_text,
                    "example_guid": guid,
                    "example_index_id": int(index_id_value) if index_id_value is not None else None,
                    "example_name": name_text,
                },
                "extracted": {
                    "rect_transform_source_path": rect_path_text,
                    "rect_transform_best": rect_best,
                    "binary_data_blobs": _collect_binary_data_blobs(record, path="record"),
                },
                "record": record,
            }
            schema_record_path.write_text(json.dumps(record_bundle, ensure_ascii=False, indent=2), encoding="utf-8")

        fam = family_stats.get(family_id)
        if fam is None:
            fam = {
                "family_id": str(family_id),
                "family_signature": family_signature,
                "count_total": 0,
                "schema_ids": set(),
            }
            family_stats[family_id] = fam
        fam["count_total"] = int(fam.get("count_total") or 0) + 1
        schema_ids = fam.get("schema_ids")
        if not isinstance(schema_ids, set):
            schema_ids = set()
            fam["schema_ids"] = schema_ids
        schema_ids.add(str(schema_id))

        observed_record_total += 1

    schemas_sorted = sorted(existing_entries.values(), key=lambda e: str(e.get("schema_id", "")))
    families_sorted = sorted(family_stats.values(), key=lambda e: str(e.get("family_id", "")))
    for fam in families_sorted:
        schema_ids = fam.get("schema_ids")
        if isinstance(schema_ids, set):
            fam["schema_ids"] = sorted(schema_ids)
    index_obj["generated_at"] = _now_iso()
    index_obj["schemas"] = schemas_sorted
    index_obj["families"] = families_sorted
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "data_root": str(data_root_path),
        "index": str(index_path),
        "records_dir": str(records_dir),
        "observed_record_total": int(observed_record_total),
        "added_schema_total": int(added_schema_total),
        "updated_schema_total": int(updated_schema_total),
        "source_gil": source_gil_text,
    }


def compute_ui_record_shape_signature(record: Dict[str, Any]) -> Any:
    """
    对单条 UI record 计算“结构签名”（不包含具体值），用于稳定归并为同一个 schema。

    注意：签名会忽略 guid/name/坐标等可变值；对 `<binary_data>` 仅记录为 binary_data，不记录长度。
    """
    if not isinstance(record, dict):
        raise TypeError("record 必须是 dict")
    return _shape_signature(record)


def compute_ui_record_schema_id(record: Dict[str, Any]) -> str:
    """
    对单条 UI record 计算 schema_id（sha1(shape_signature)）。
    """
    signature = compute_ui_record_shape_signature(record)
    return _hash_schema_signature(signature)


__all__ = [
    "record_ui_schema_library_from_dll_dump",
    "compute_ui_record_shape_signature",
    "compute_ui_record_schema_id",
]


