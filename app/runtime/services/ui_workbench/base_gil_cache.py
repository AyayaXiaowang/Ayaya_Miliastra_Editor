from __future__ import annotations

import json
from pathlib import Path

from .utils import encode_utf8_b64


def get_ui_workbench_cache_dir(*, workspace_root: Path) -> Path:
    """UI Workbench 的运行期缓存目录（按工程约定落在 app/runtime/cache/）。"""
    cache_dir = (Path(workspace_root).resolve() / "app" / "runtime" / "cache" / "ui_workbench").resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def save_base_gil_cache(
    *,
    workspace_root: Path,
    file_name: str,
    last_modified: int,
    content: bytes,
) -> None:
    cache_dir = get_ui_workbench_cache_dir(workspace_root=workspace_root)
    data_path = (cache_dir / "base_gil_cache.bin").resolve()
    meta_path = (cache_dir / "base_gil_cache.meta.json").resolve()

    data_path.write_bytes(bytes(content))
    meta_path.write_text(
        json.dumps(
            {
                "file_name": str(file_name or "base.gil"),
                "file_name_b64": encode_utf8_b64(str(file_name or "base.gil")),
                "last_modified": int(last_modified),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def load_base_gil_cache(*, workspace_root: Path) -> tuple[str, int, bytes] | None:
    cache_dir = get_ui_workbench_cache_dir(workspace_root=workspace_root)
    data_path = (cache_dir / "base_gil_cache.bin").resolve()
    meta_path = (cache_dir / "base_gil_cache.meta.json").resolve()
    if (not data_path.is_file()) or (not meta_path.is_file()):
        return None

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if not isinstance(meta, dict):
        raise RuntimeError("base_gil_cache.meta.json 不是对象")

    file_name = str(meta.get("file_name") or "base.gil")
    last_modified_value = meta.get("last_modified")
    if not isinstance(last_modified_value, int):
        last_modified_value = int(last_modified_value) if str(last_modified_value or "").strip().isdigit() else 0
    return file_name, int(last_modified_value), data_path.read_bytes()


__all__ = [
    "get_ui_workbench_cache_dir",
    "load_base_gil_cache",
    "save_base_gil_cache",
]

