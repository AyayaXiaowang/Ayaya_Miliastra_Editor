from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _cache_dir(*, workspace_root: Path) -> Path:
    cache_dir = (Path(workspace_root).resolve() / "app" / "runtime" / "cache").resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _recent_exported_gils_file(*, workspace_root: Path) -> Path:
    return (_cache_dir(workspace_root=workspace_root) / "ugc_file_tools_recent_exported_gils.json").resolve()


def now_ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _normalize_existing_gil_path(path: str | Path) -> str | None:
    raw = str(path or "").strip()
    if raw == "":
        return None
    p = Path(raw).resolve()
    if not p.is_file():
        return None
    if p.suffix.lower() != ".gil":
        return None
    return str(p)


@dataclass(frozen=True, slots=True)
class RecentExportedGil:
    ts: str
    path: str
    source: str
    title: str


def append_recent_exported_gil(
    *,
    workspace_root: Path,
    gil_path: str | Path,
    source: str,
    title: str,
    ts: str | None = None,
    max_items: int = 50,
) -> None:
    """
    记录“最近导出的 .gil”（只记录存在且后缀为 .gil 的文件）。

    - 去重：同一路径只保留最新一条
    - 截断：最多保留 max_items 条
    """
    normalized = _normalize_existing_gil_path(gil_path)
    if normalized is None:
        return

    entry: Dict[str, Any] = {
        "ts": str(ts or now_ts()),
        "path": str(normalized),
        "source": str(source or "").strip() or "unknown",
        "title": str(title or "").strip() or "exported_gil",
    }

    file_path = _recent_exported_gils_file(workspace_root=Path(workspace_root))
    items: List[Dict[str, Any]] = []
    if file_path.is_file():
        obj = json.loads(file_path.read_text(encoding="utf-8"))
        if isinstance(obj, list):
            items = [x for x in obj if isinstance(x, dict)]

    # 去重（按 path）
    deduped: List[Dict[str, Any]] = [x for x in items if str(x.get("path") or "") != str(entry["path"])]
    deduped.append(dict(entry))
    if int(max_items) > 0 and len(deduped) > int(max_items):
        deduped = deduped[-int(max_items) :]
    file_path.write_text(json.dumps(deduped, ensure_ascii=False, indent=2), encoding="utf-8")


def load_recent_exported_gils(
    *,
    workspace_root: Path,
    keep_missing: bool = False,
    limit: int = 12,
) -> List[RecentExportedGil]:
    """
    读取“最近导出的 .gil”列表（默认只返回仍存在的文件）。
    返回按时间倒序（最新在前）。
    """
    file_path = _recent_exported_gils_file(workspace_root=Path(workspace_root))
    if not file_path.is_file():
        return []
    obj = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(obj, list):
        return []

    out: List[RecentExportedGil] = []
    for it in obj:
        if not isinstance(it, dict):
            continue
        ts = str(it.get("ts") or "").strip()
        p = str(it.get("path") or "").strip()
        source = str(it.get("source") or "").strip()
        title = str(it.get("title") or "").strip()
        if ts == "" or p == "":
            continue
        if not keep_missing:
            norm = _normalize_existing_gil_path(p)
            if norm is None:
                continue
            p = norm
        out.append(RecentExportedGil(ts=ts, path=p, source=source or "unknown", title=title or "exported_gil"))

    out.reverse()
    if isinstance(limit, int) and int(limit) > 0:
        out = out[: int(limit)]
    return out


__all__ = [
    "RecentExportedGil",
    "append_recent_exported_gil",
    "load_recent_exported_gils",
]

