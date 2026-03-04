from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _now_ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


# NOTE: This module is part of the UI domain; keep its exports stable for other subdomains.


def _resolve_ui_artifacts_dir(*, workspace_root: Path, package_id: str) -> Path:
    from engine.utils.cache.cache_paths import get_ui_artifacts_cache_dir_for_package

    out_dir = get_ui_artifacts_cache_dir_for_package(Path(workspace_root).resolve(), str(package_id)).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def resolve_ui_export_records_file(*, workspace_root: Path, package_id: str) -> Path:
    """
    运行时缓存：UI 导出记录（仅本机）。

    约定路径：
      <runtime_cache>/ui_artifacts/<package_id>/ui_export_records.json
    """
    return (_resolve_ui_artifacts_dir(workspace_root=workspace_root, package_id=package_id) / "ui_export_records.json").resolve()


def resolve_ui_guid_registry_snapshots_dir(*, workspace_root: Path, package_id: str) -> Path:
    """
    运行时缓存：UIKey→GUID registry 的快照目录（用于“回填记录可选”）。

    约定路径：
      <runtime_cache>/ui_artifacts/<package_id>/ui_guid_registry_snapshots/
    """
    p = (_resolve_ui_artifacts_dir(workspace_root=workspace_root, package_id=package_id) / "ui_guid_registry_snapshots").resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _load_json_list_file(path: Path) -> List[Dict[str, Any]]:
    p = Path(path).resolve()
    if not p.is_file():
        return []
    obj = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(obj, list):
        return []
    return [x for x in obj if isinstance(x, dict)]


def _write_json_list_file(path: Path, items: List[Dict[str, Any]]) -> None:
    p = Path(path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(list(items), ensure_ascii=False, indent=2), encoding="utf-8")


def _read_registry_updated_at(registry_path: Path) -> str:
    p = Path(registry_path).resolve()
    if not p.is_file():
        return ""
    obj = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        return ""
    updated_at = obj.get("updated_at")
    return str(updated_at or "").strip() if isinstance(updated_at, str) else ""


def _load_ui_key_to_guid_mapping(registry_path: Path) -> Dict[str, int]:
    from ugc_file_tools.ui.guid_registry_format import load_ui_guid_registry_mapping

    return dict(load_ui_guid_registry_mapping(Path(registry_path).resolve()))


def _clean_ui_key_to_guid_mapping(ui_key_to_guid: Dict[str, Any]) -> Dict[str, int]:
    """
    归一化 ui_key→guid 映射：
    - key：非空字符串
    - guid：int 且 >0（拒绝 bool；允许 "123"/123.0 这类可安全转 int 的值）
    """
    if not isinstance(ui_key_to_guid, dict):
        raise TypeError("ui_key_to_guid must be dict")
    out: Dict[str, int] = {}
    for k, v in ui_key_to_guid.items():
        key = str(k or "").strip()
        if key == "":
            continue

        if isinstance(v, bool):
            raise TypeError(f"ui_key_to_guid value cannot be bool: key={key!r} value={v!r}")

        guid: int
        if isinstance(v, int):
            guid = int(v)
        elif isinstance(v, float):
            if not v.is_integer():
                raise TypeError(f"ui_key_to_guid value must be int-like: key={key!r} value={v!r}")
            guid = int(v)
        elif isinstance(v, str):
            s = v.strip()
            if not s.isdigit():
                raise TypeError(f"ui_key_to_guid value must be int-like: key={key!r} value={v!r}")
            guid = int(s)
        else:
            raise TypeError(f"ui_key_to_guid value must be int-like: key={key!r} value={v!r}")

        if guid <= 0:
            continue
        out[key] = int(guid)
    return out


def write_ui_guid_registry_snapshot_from_mapping(
    *,
    workspace_root: Path,
    package_id: str,
    ui_key_to_guid: Dict[str, Any],
    record_id: str,
    created_at: str,
    source_registry_path: Path | None = None,
    source_registry_updated_at: str = "",
) -> tuple[Path, Dict[str, int], str]:
    """
    将给定的 ui_key→guid 映射写入运行时快照文件（不依赖 registry 文件）。

    返回：
      (snapshot_path, cleaned_mapping, source_registry_updated_at)
    """
    mapping = _clean_ui_key_to_guid_mapping(dict(ui_key_to_guid))
    updated_at = str(source_registry_updated_at or "").strip()

    snapshots_dir = resolve_ui_guid_registry_snapshots_dir(workspace_root=workspace_root, package_id=package_id)
    snapshot_path = (snapshots_dir / f"ui_guid_registry_snapshot__{str(record_id).strip()}.json").resolve()
    payload = {
        "version": 1,
        "record_id": str(record_id),
        "created_at": str(created_at),
        "source_registry_path": (str(Path(source_registry_path).resolve()) if source_registry_path is not None else ""),
        "source_registry_updated_at": str(updated_at),
        "ui_key_to_guid": {k: int(mapping[k]) for k in sorted(mapping.keys())},
    }
    snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot_path, mapping, str(updated_at)


def write_ui_guid_registry_snapshot(
    *,
    workspace_root: Path,
    package_id: str,
    source_registry_path: Path,
    record_id: str,
    created_at: str,
) -> tuple[Path, Dict[str, int], str]:
    """
    将当前 registry 内容写入运行时快照（无历史备份；快照文件一经写入即视为不可变）。

    返回：
      (snapshot_path, mapping, registry_updated_at)
    """
    mapping = _load_ui_key_to_guid_mapping(Path(source_registry_path))
    registry_updated_at = _read_registry_updated_at(Path(source_registry_path))

    snapshots_dir = resolve_ui_guid_registry_snapshots_dir(workspace_root=workspace_root, package_id=package_id)
    snapshot_path = (snapshots_dir / f"ui_guid_registry_snapshot__{record_id}.json").resolve()
    payload = {
        "version": 1,
        "record_id": str(record_id),
        "created_at": str(created_at),
        "source_registry_path": str(Path(source_registry_path).resolve()),
        "source_registry_updated_at": str(registry_updated_at),
        "ui_key_to_guid": {k: int(mapping[k]) for k in sorted(mapping.keys())},
    }
    snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot_path, mapping, str(registry_updated_at)


def load_ui_guid_registry_snapshot(snapshot_path: Path) -> Dict[str, int]:
    p = Path(snapshot_path).resolve()
    obj = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise TypeError(f"ui_guid_registry snapshot root must be dict: {p}")
    mapping = obj.get("ui_key_to_guid")
    if not isinstance(mapping, dict):
        raise TypeError(f"ui_guid_registry snapshot missing ui_key_to_guid: {p}")
    out: Dict[str, int] = {}
    for k, v in mapping.items():
        key = str(k or "").strip()
        if key == "":
            continue
        if isinstance(v, bool):
            raise TypeError(f"ui_guid_registry snapshot value cannot be bool: key={key!r} value={v!r} path={p}")
        if isinstance(v, (int, float)):
            vv = int(v)
        elif isinstance(v, str) and v.strip().isdigit():
            vv = int(v.strip())
        else:
            raise TypeError(f"ui_guid_registry snapshot value must be int: key={key!r} value={v!r} path={p}")
        if vv <= 0:
            continue
        out[key] = int(vv)
    return out


@dataclass(frozen=True, slots=True)
class UIExportRecord:
    record_id: str
    created_at: str
    title: str
    payload: Dict[str, Any]


def load_ui_export_records(*, workspace_root: Path, package_id: str) -> List[UIExportRecord]:
    path = resolve_ui_export_records_file(workspace_root=workspace_root, package_id=package_id)
    items = _load_json_list_file(path)
    records: List[UIExportRecord] = []
    for item in items:
        rid = str(item.get("record_id") or "").strip()
        ts = str(item.get("created_at") or item.get("ts") or "").strip()
        title = str(item.get("title") or "").strip()
        if rid == "" or ts == "" or title == "":
            continue
        records.append(UIExportRecord(record_id=rid, created_at=ts, title=title, payload=dict(item)))
    records.sort(key=lambda r: r.created_at, reverse=True)
    return records


def try_get_ui_export_record_by_id(*, workspace_root: Path, package_id: str, record_id: str) -> Optional[UIExportRecord]:
    rid = str(record_id or "").strip()
    if rid == "":
        return None
    for r in load_ui_export_records(workspace_root=workspace_root, package_id=package_id):
        if r.record_id == rid:
            return r
    return None


def append_ui_export_record(
    *,
    workspace_root: Path,
    package_id: str,
    title: str,
    kind: str,
    output_gil_file: Path,
    ui_guid_registry_path: Path,
    base_gil_path: Optional[Path],
    base_gil_file_name_hint: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    追加一条 UI 导出记录，并写入一份 ui_guid_registry 快照供后续 GIA 导出回填选择。

    返回 record dict（同写入内容）。
    """
    workspace_root = Path(workspace_root).resolve()
    package_id_text = str(package_id or "").strip()
    if package_id_text == "":
        raise ValueError("package_id 不能为空")

    created_at = _now_ts()
    record_id = str(uuid4())

    snapshot_path, mapping, registry_updated_at = write_ui_guid_registry_snapshot(
        workspace_root=workspace_root,
        package_id=package_id_text,
        source_registry_path=Path(ui_guid_registry_path).resolve(),
        record_id=record_id,
        created_at=created_at,
    )

    base_path_text = str(Path(base_gil_path).resolve()) if base_gil_path is not None else ""
    if base_gil_path is not None and not Path(base_gil_path).is_file():
        base_path_text = ""

    output_gil_path = Path(output_gil_file).resolve()
    if not output_gil_path.is_file():
        raise FileNotFoundError(str(output_gil_path))

    record: Dict[str, Any] = {
        "version": 1,
        "record_id": record_id,
        "created_at": created_at,
        "package_id": package_id_text,
        "kind": str(kind or "").strip() or "export_gil",
        "title": str(title or "").strip() or output_gil_path.name,
        "output_gil_file": str(output_gil_path),
        "output_gil_name": str(output_gil_path.name),
        "base_gil_path": base_path_text,
        "base_gil_name": str(base_gil_file_name_hint or "").strip()
        or (str(Path(base_path_text).name) if base_path_text else ""),
        "ui_guid_registry_path": str(Path(ui_guid_registry_path).resolve()),
        "ui_guid_registry_snapshot_path": str(Path(snapshot_path).resolve()),
        "ui_guid_registry_updated_at": str(registry_updated_at),
        "ui_guid_mapping_total": int(len(mapping)),
    }
    if extra is not None:
        record["extra"] = dict(extra)

    path = resolve_ui_export_records_file(workspace_root=workspace_root, package_id=package_id_text)
    items = _load_json_list_file(path)
    items.append(dict(record))
    if len(items) > 200:
        items = items[-200:]
    _write_json_list_file(path, items)

    return record


def append_ui_export_record_from_mapping(
    *,
    workspace_root: Path,
    package_id: str,
    title: str,
    kind: str,
    output_gil_file: Path,
    ui_key_to_guid: Dict[str, Any],
    base_gil_path: Optional[Path],
    base_gil_file_name_hint: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    追加一条 UI 导出记录，但快照来源为“内存映射”（不要求存在 ui_guid_registry.json 文件）。

    典型用途：
    - 导出中心/CLI 的 project writeback 在 UI 写回阶段已经得到 ui_key→guid 映射（用于同次节点图回填），
      但该链路不再落盘 registry 文件；此函数用于把映射沉淀为 UI 回填记录，供后续 `.gia` 导出选择。
    """
    workspace_root = Path(workspace_root).resolve()
    package_id_text = str(package_id or "").strip()
    if package_id_text == "":
        raise ValueError("package_id 不能为空")

    created_at = _now_ts()
    record_id = str(uuid4())

    snapshot_path, mapping, registry_updated_at = write_ui_guid_registry_snapshot_from_mapping(
        workspace_root=workspace_root,
        package_id=package_id_text,
        ui_key_to_guid=dict(ui_key_to_guid),
        record_id=record_id,
        created_at=created_at,
        source_registry_path=None,
        source_registry_updated_at="",
    )

    base_path_text = str(Path(base_gil_path).resolve()) if base_gil_path is not None else ""
    if base_gil_path is not None and not Path(base_gil_path).is_file():
        base_path_text = ""

    output_gil_path = Path(output_gil_file).resolve()
    if not output_gil_path.is_file():
        raise FileNotFoundError(str(output_gil_path))

    record: Dict[str, Any] = {
        "version": 1,
        "record_id": record_id,
        "created_at": created_at,
        "package_id": package_id_text,
        "kind": str(kind or "").strip() or "export_gil",
        "title": str(title or "").strip() or output_gil_path.name,
        "output_gil_file": str(output_gil_path),
        "output_gil_name": str(output_gil_path.name),
        "base_gil_path": base_path_text,
        "base_gil_name": str(base_gil_file_name_hint or "").strip()
        or (str(Path(base_path_text).name) if base_path_text else ""),
        # 注意：该链路不依赖 registry 文件；仍保留字段以便 UI 侧统一展示
        "ui_guid_registry_path": "",
        "ui_guid_registry_snapshot_path": str(Path(snapshot_path).resolve()),
        "ui_guid_registry_updated_at": str(registry_updated_at),
        "ui_guid_mapping_total": int(len(mapping)),
    }
    if extra is not None:
        record["extra"] = dict(extra)

    path = resolve_ui_export_records_file(workspace_root=workspace_root, package_id=package_id_text)
    items = _load_json_list_file(path)
    items.append(dict(record))
    if len(items) > 200:
        items = items[-200:]
    _write_json_list_file(path, items)

    return record


__all__ = [
    "resolve_ui_export_records_file",
    "resolve_ui_guid_registry_snapshots_dir",
    "write_ui_guid_registry_snapshot",
    "write_ui_guid_registry_snapshot_from_mapping",
    "load_ui_guid_registry_snapshot",
    "UIExportRecord",
    "load_ui_export_records",
    "try_get_ui_export_record_by_id",
    "append_ui_export_record",
    "append_ui_export_record_from_mapping",
]


