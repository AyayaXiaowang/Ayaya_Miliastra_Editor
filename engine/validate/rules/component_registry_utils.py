from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set, Tuple, List

from ..context import ValidationContext
from .code_structure.resource_scope_utils import GraphResourceScope, try_build_graph_resource_scope


_COMPONENT_LIBRARY_RELATIVE_PATH_PARTS = ("元件库",)


def parse_component_key_placeholder(text: str) -> Optional[str]:
    """
    解析 component_key/component: 占位符，返回其中的“元件名”。

    允许：
    - component_key:第七关展示元件
    - component:第七关展示元件
    """
    raw = str(text or "").strip()
    lowered = raw.lower()
    if lowered.startswith("component_key:"):
        key = raw[len("component_key:") :].strip()
        return key if key else None
    if lowered.startswith("component:"):
        key = raw[len("component:") :].strip()
        return key if key else None
    return None


@dataclass(frozen=True)
class ComponentLibraryNameView:
    scope: GraphResourceScope
    component_library_dirs: Tuple[Path, ...]
    json_files: Tuple[Path, ...]
    component_names: Tuple[str, ...]


def _iter_json_files_under_dir(component_library_dir: Path) -> List[Path]:
    if not component_library_dir.exists() or not component_library_dir.is_dir():
        return []
    results: List[Path] = []
    for dirpath, _dirnames, filenames in os.walk(component_library_dir):
        current_dir = Path(dirpath)
        for name in filenames:
            if not name.lower().endswith(".json"):
                continue
            p = (current_dir / name).resolve()
            if p.is_file():
                results.append(p)
    results.sort(key=lambda p: p.as_posix().casefold())
    return results


def _compute_json_fingerprint(json_files: List[Path]) -> Tuple[int, float]:
    count = 0
    latest = 0.0
    for p in json_files:
        if not p.exists() or not p.is_file():
            continue
        count += 1
        mtime = float(p.stat().st_mtime)
        if mtime > latest:
            latest = mtime
    return int(count), float(latest)


def _extract_component_name_from_template_json(obj: object, *, fallback_name: str) -> Optional[str]:
    if not isinstance(obj, dict):
        return None
    name = obj.get("name")
    if isinstance(name, str) and name.strip() != "":
        return str(name).strip()
    # 兼容：少量历史文件可能用 template_name 字段
    name2 = obj.get("template_name")
    if isinstance(name2, str) and name2.strip() != "":
        return str(name2).strip()
    fb = str(fallback_name or "").strip()
    return fb if fb != "" else None


# cache_key -> (fingerprint, dirs, files, names)
_COMPONENT_LIBRARY_CACHE: Dict[str, Tuple[Tuple[int, float], Tuple[Path, ...], Tuple[Path, ...], Tuple[str, ...]]] = {}


def try_load_component_library_names_for_ctx(ctx: ValidationContext) -> Optional[ComponentLibraryNameView]:
    """若 ctx.file_path 位于资源库目录结构下，则尝试从 元件库 JSON 汇总可用于 component_key 校验的“元件名”集合。"""
    if ctx.file_path is None:
        return None
    scope = try_build_graph_resource_scope(ctx.workspace_path, ctx.file_path)
    if scope is None:
        return None

    dirs: List[Path] = []
    shared_dir = (scope.shared_root_dir / Path(*_COMPONENT_LIBRARY_RELATIVE_PATH_PARTS)).resolve()
    if shared_dir.is_dir():
        dirs.append(shared_dir)

    project_dir = (scope.graph_resource_root_dir / Path(*_COMPONENT_LIBRARY_RELATIVE_PATH_PARTS)).resolve()
    if project_dir.is_dir():
        dirs.append(project_dir)

    uniq_dirs: List[Path] = []
    seen_dirs: set[str] = set()
    for d in dirs:
        key = str(d.resolve())
        if key in seen_dirs:
            continue
        seen_dirs.add(key)
        uniq_dirs.append(d)

    if not uniq_dirs:
        return ComponentLibraryNameView(
            scope=scope,
            component_library_dirs=tuple(),
            json_files=tuple(),
            component_names=tuple(),
        )

    all_json_files: List[Path] = []
    for d in uniq_dirs:
        all_json_files.extend(_iter_json_files_under_dir(d))

    unique_files: List[Path] = []
    seen_files: set[str] = set()
    for p in all_json_files:
        key = str(p.resolve())
        if key in seen_files:
            continue
        seen_files.add(key)
        unique_files.append(p)
    unique_files.sort(key=lambda p: p.as_posix().casefold())

    fingerprint = _compute_json_fingerprint(unique_files)
    cache_key = "|".join(str(d.resolve()) for d in uniq_dirs)
    cached = _COMPONENT_LIBRARY_CACHE.get(cache_key)
    if cached is not None:
        cached_fp, cached_dirs, cached_files, cached_names = cached
        if cached_fp == fingerprint:
            return ComponentLibraryNameView(
                scope=scope,
                component_library_dirs=cached_dirs,
                json_files=cached_files,
                component_names=cached_names,
            )

    names: Set[str] = set()
    for json_file in unique_files:
        text = json_file.read_text(encoding="utf-8")
        obj = json.loads(text)
        extracted = _extract_component_name_from_template_json(obj, fallback_name=json_file.stem)
        if extracted:
            names.add(extracted)

    names_sorted = tuple(sorted(names, key=lambda s: s.casefold()))
    dirs_tuple = tuple(uniq_dirs)
    files_tuple = tuple(unique_files)

    _COMPONENT_LIBRARY_CACHE[cache_key] = (fingerprint, dirs_tuple, files_tuple, names_sorted)
    return ComponentLibraryNameView(
        scope=scope,
        component_library_dirs=dirs_tuple,
        json_files=files_tuple,
        component_names=names_sorted,
    )


__all__ = [
    "ComponentLibraryNameView",
    "parse_component_key_placeholder",
    "try_load_component_library_names_for_ctx",
]

