from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ugc_file_tools.repo_paths import ugc_file_tools_root

UI_SCHEMA_LIBRARY_FORMAT = "ugc_ui_schema_library_v1"


def ui_schema_library_data_root() -> Path:
    return ugc_file_tools_root() / "ui_schema_library" / "data"


def _now_iso() -> str:
    # 不要求带时区；仅用于本地沉淀库的“最后更新时间”
    return datetime.now().isoformat(timespec="seconds")


def _sanitize_schema_id(schema_id: str) -> str:
    text = str(schema_id or "").strip().lower()
    if text == "":
        raise ValueError("schema_id 不能为空")
    if re.fullmatch(r"[0-9a-f]{40}", text) is None:
        raise ValueError("schema_id 必须是 40 位 hex（sha1）字符串")
    return text


def _normalize_label(label: str) -> str:
    text = str(label or "").strip()
    if text == "":
        raise ValueError("label 不能为空")
    # 统一为小写，便于跨平台/跨调用方式稳定匹配
    return text.lower()


def _resolve_data_root(data_root: Optional[Path]) -> Path:
    return (Path(data_root).resolve() if data_root is not None else ui_schema_library_data_root().resolve())


def load_schema_library_index(*, data_root: Optional[Path] = None) -> Dict[str, Any]:
    root = _resolve_data_root(data_root)
    index_path = root / "index.json"
    if not index_path.is_file():
        return {"format": UI_SCHEMA_LIBRARY_FORMAT, "generated_at": "", "schemas": []}

    obj = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("ui_schema_library index.json 顶层不是 dict")
    fmt = obj.get("format")
    if fmt != UI_SCHEMA_LIBRARY_FORMAT:
        raise ValueError(f"不支持的 ui_schema_library format: {fmt!r}")
    schemas = obj.get("schemas")
    if not isinstance(schemas, list):
        raise ValueError("ui_schema_library index.json.schemas 不是 list")
    return obj


def save_schema_library_index(index_obj: Dict[str, Any], *, data_root: Optional[Path] = None) -> Path:
    root = _resolve_data_root(data_root)
    index_path = root / "index.json"
    root.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return index_path


def find_schema_ids_by_label(label: str, *, data_root: Optional[Path] = None) -> List[str]:
    wanted = _normalize_label(label)
    index_obj = load_schema_library_index(data_root=data_root)
    out: List[str] = []
    for entry in index_obj.get("schemas", []):
        if not isinstance(entry, dict):
            continue
        sid = entry.get("schema_id")
        if not isinstance(sid, str):
            continue
        entry_label_text = str(entry.get("label") or "").strip()
        if entry_label_text == "":
            continue
        if entry_label_text.lower() == wanted:
            out.append(_sanitize_schema_id(sid))
    return sorted(set(out))


def set_schema_label(
    *,
    schema_id: str,
    label: str,
    data_root: Optional[Path] = None,
) -> None:
    sid = _sanitize_schema_id(schema_id)
    new_label = _normalize_label(label)

    index_obj = load_schema_library_index(data_root=data_root)
    schemas = index_obj.get("schemas")
    if not isinstance(schemas, list):
        raise ValueError("ui_schema_library index.json.schemas 不是 list")

    hit = False
    for entry in schemas:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("schema_id") or "").strip().lower() != sid:
            continue
        entry["label"] = new_label
        hit = True
        break

    if not hit:
        raise ValueError(f"ui_schema_library index.json 中找不到 schema_id={sid!r}，无法设置 label={new_label!r}")

    index_obj["generated_at"] = _now_iso()
    save_schema_library_index(index_obj, data_root=data_root)


def load_schema_record(schema_id: str, *, data_root: Optional[Path] = None) -> Dict[str, Any]:
    sid = _sanitize_schema_id(schema_id)
    root = _resolve_data_root(data_root)
    record_path = root / "records" / f"{sid}.record.json"
    if not record_path.is_file():
        raise FileNotFoundError(str(record_path))
    obj = json.loads(record_path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("schema record file 顶层不是 dict")
    record = obj.get("record")
    if not isinstance(record, dict):
        raise ValueError("schema record file 缺少 record(dict)")
    return record


