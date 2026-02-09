from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set, Tuple, List

from ..context import ValidationContext
from .code_structure.resource_scope_utils import GraphResourceScope, try_build_graph_resource_scope


_UI_SOURCE_RELATIVE_PATH_PARTS = ("管理配置", "UI源码")

# data-ui-key="xxx" / data-ui-key='xxx'
_UI_KEY_ATTR_RE = re.compile(
    r"""\bdata-ui-key\s*=\s*(?P<quote>["'])(?P<key>[^"']+)(?P=quote)""",
    flags=re.IGNORECASE,
)

# data-ui-state-group="xxx" / data-ui-state-group='xxx'
_UI_STATE_GROUP_ATTR_RE = re.compile(
    r"""\bdata-ui-state-group\s*=\s*(?P<quote>["'])(?P<key>[^"']+)(?P=quote)""",
    flags=re.IGNORECASE,
)


def parse_ui_key_placeholder(text: str) -> Optional[str]:
    """
    解析 ui_key/ui: 占位符，返回其中的 ui_key。

    允许：
    - ui_key:HUD_HP_BAR
    - ui:HUD_HP_BAR
    """
    raw = str(text or "").strip()
    lowered = raw.lower()
    if lowered.startswith("ui_key:"):
        key = raw[len("ui_key:") :].strip()
        if not key:
            return None
        # 兼容“Workbench 导出后生成的长 ui_key”（例如 `HTML导入_界面布局__btn_unselect__btn_item`）：
        # 对校验器而言，只要其中的“关键标识”在 UI源码(HTML) 中存在即可：
        # - data-ui-key（如 `btn_unselect`）
        # - 或 data-ui-state-group（如 `help_btn_state`）
        # 这里提取 `__` 分段后的第 2 段作为标识（形态：<layout>__<key_or_state_group>__...）。
        if "__" in key:
            parts = [p for p in key.split("__") if str(p)]
            if len(parts) >= 2:
                return str(parts[1]).strip() or None
        return key
    if lowered.startswith("ui:"):
        key = raw[len("ui:") :].strip()
        if not key:
            return None
        if "__" in key:
            parts = [p for p in key.split("__") if str(p)]
            if len(parts) >= 2:
                return str(parts[1]).strip() or None
        return key
    return None


@dataclass(frozen=True)
class UiHtmlUiKeyView:
    scope: GraphResourceScope
    ui_source_dirs: Tuple[Path, ...]
    html_files: Tuple[Path, ...]
    ui_keys: Tuple[str, ...]


def infer_ui_source_dirs_for_ctx(ctx: ValidationContext) -> Optional[Tuple[Path, ...]]:
    """根据 ctx.file_path 推断“当前作用域”的 UI源码目录列表（共享 + 当前项目）。"""
    if ctx.file_path is None:
        return None
    scope = try_build_graph_resource_scope(ctx.workspace_path, ctx.file_path)
    if scope is None:
        return None
    dirs: List[Path] = []

    shared_ui_dir = (scope.shared_root_dir / Path(*_UI_SOURCE_RELATIVE_PATH_PARTS)).resolve()
    if shared_ui_dir.is_dir():
        dirs.append(shared_ui_dir)

    project_ui_dir = (scope.graph_resource_root_dir / Path(*_UI_SOURCE_RELATIVE_PATH_PARTS)).resolve()
    if project_ui_dir.is_dir():
        dirs.append(project_ui_dir)

    uniq: List[Path] = []
    seen: set[str] = set()
    for d in dirs:
        key = str(d.resolve())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(d)
    return tuple(uniq)


def _iter_html_files_under_dir(ui_source_dir: Path) -> List[Path]:
    if not ui_source_dir.exists() or not ui_source_dir.is_dir():
        return []
    results: List[Path] = []
    for dirpath, _dirnames, filenames in os.walk(ui_source_dir):
        current_dir = Path(dirpath)
        for name in filenames:
            if not name.lower().endswith(".html"):
                continue
            if name.lower().endswith(".flattened.html"):
                continue
            p = (current_dir / name).resolve()
            if p.is_file():
                results.append(p)
    results.sort(key=lambda p: p.as_posix().casefold())
    return results


def _extract_ui_keys_from_html_text(text: str) -> Set[str]:
    out: Set[str] = set()
    for match in _UI_KEY_ATTR_RE.finditer(str(text or "")):
        key = str(match.group("key") or "").strip()
        if key:
            out.add(key)
    # 状态组 key：用于 UI_STATE_GROUP / state 相关占位符校验
    for match in _UI_STATE_GROUP_ATTR_RE.finditer(str(text or "")):
        key = str(match.group("key") or "").strip()
        if key:
            out.add(key)
    return out


def _compute_html_fingerprint(html_files: List[Path]) -> Tuple[int, float]:
    count = 0
    latest = 0.0
    for p in html_files:
        if not p.exists() or not p.is_file():
            continue
        count += 1
        mtime = float(p.stat().st_mtime)
        if mtime > latest:
            latest = mtime
    return int(count), float(latest)


# cache_key -> (fingerprint, dirs, files, ui_keys)
_UI_HTML_KEYS_CACHE: Dict[str, Tuple[Tuple[int, float], Tuple[Path, ...], Tuple[Path, ...], Tuple[str, ...]]] = {}


def try_load_ui_html_ui_keys_for_ctx(ctx: ValidationContext) -> Optional[UiHtmlUiKeyView]:
    """若 ctx.file_path 位于资源库目录结构下，则尝试从 UI源码(HTML) 汇总可用于 ui_key 校验的 key 集合：
    - data-ui-key
    - data-ui-state-group
    """
    if ctx.file_path is None:
        return None
    scope = try_build_graph_resource_scope(ctx.workspace_path, ctx.file_path)
    if scope is None:
        return None
    ui_source_dirs = infer_ui_source_dirs_for_ctx(ctx)
    if not ui_source_dirs:
        return UiHtmlUiKeyView(scope=scope, ui_source_dirs=tuple(), html_files=tuple(), ui_keys=tuple())

    all_html_files: List[Path] = []
    for d in ui_source_dirs:
        all_html_files.extend(_iter_html_files_under_dir(d))

    unique_files: List[Path] = []
    seen_files: set[str] = set()
    for p in all_html_files:
        key = str(p.resolve())
        if key in seen_files:
            continue
        seen_files.add(key)
        unique_files.append(p)
    unique_files.sort(key=lambda p: p.as_posix().casefold())

    fingerprint = _compute_html_fingerprint(unique_files)
    cache_key = "|".join(str(d.resolve()) for d in ui_source_dirs)
    cached = _UI_HTML_KEYS_CACHE.get(cache_key)
    if cached is not None:
        cached_fp, cached_dirs, cached_files, cached_keys = cached
        if cached_fp == fingerprint:
            return UiHtmlUiKeyView(
                scope=scope,
                ui_source_dirs=cached_dirs,
                html_files=cached_files,
                ui_keys=cached_keys,
            )

    keys: Set[str] = set()
    for html_file in unique_files:
        text = html_file.read_text(encoding="utf-8")
        keys.update(_extract_ui_keys_from_html_text(text))

    keys_sorted = tuple(sorted(keys, key=lambda s: s.casefold()))
    dirs_tuple = tuple(ui_source_dirs)
    files_tuple = tuple(unique_files)

    _UI_HTML_KEYS_CACHE[cache_key] = (fingerprint, dirs_tuple, files_tuple, keys_sorted)
    return UiHtmlUiKeyView(
        scope=scope,
        ui_source_dirs=dirs_tuple,
        html_files=files_tuple,
        ui_keys=keys_sorted,
    )


__all__ = [
    "UiHtmlUiKeyView",
    "infer_ui_source_dirs_for_ctx",
    "parse_ui_key_placeholder",
    "try_load_ui_html_ui_keys_for_ctx",
]

