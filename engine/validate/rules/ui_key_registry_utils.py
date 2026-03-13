from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set, Tuple, List

from ..context import ValidationContext
from .code_structure.resource_scope_utils import GraphResourceScope, try_build_graph_resource_scope


_UI_SOURCE_RELATIVE_PATH_PARTS = ("管理配置", "UI源码")
_UI_WORKBENCH_OUT_DIRNAME = "__workbench_out__"

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

# state pair within the same tag: data-ui-state-group + data-ui-state (order-insensitive)
_UI_STATE_PAIR_RE_GROUP_FIRST = re.compile(
    r"""<[^>]*\bdata-ui-state-group\s*=\s*(?P<q1>["'])(?P<group>[^"']+)(?P=q1)[^>]*\bdata-ui-state\s*=\s*(?P<q2>["'])(?P<state>[^"']+)(?P=q2)""",
    flags=re.IGNORECASE | re.DOTALL,
)
_UI_STATE_PAIR_RE_STATE_FIRST = re.compile(
    r"""<[^>]*\bdata-ui-state\s*=\s*(?P<q1>["'])(?P<state>[^"']+)(?P=q1)[^>]*\bdata-ui-state-group\s*=\s*(?P<q2>["'])(?P<group>[^"']+)(?P=q2)""",
    flags=re.IGNORECASE | re.DOTALL,
)

_UI_STATE_GROUP_PREFIX = "UI_STATE_GROUP"


def _parse_ui_state_group_key_or_none(raw_ui_key: str) -> Optional[Tuple[str, str]]:
    key = str(raw_ui_key or "").strip()
    if not key.startswith("UI_STATE_GROUP__"):
        return None
    parts = [p for p in key.split("__") if str(p).strip() != ""]
    if len(parts) != 4:
        return None
    if parts[0] != "UI_STATE_GROUP" or parts[-1] != "group":
        return None
    group_name = str(parts[1]).strip()
    state_name = str(parts[2]).strip()
    if group_name == "" or state_name == "":
        return None
    return group_name, state_name


def try_format_invalid_ui_state_group_placeholder_message(text: str) -> Optional[str]:
    """
    若 `ui_key:` 占位符使用了 UI_STATE_GROUP 但格式不合法，返回更明确的错误提示文本。
    """
    raw = str(text or "").strip()
    lowered = raw.lower()
    if lowered.startswith("ui_key:"):
        key = raw[len("ui_key:") :].strip()
    elif lowered.startswith("ui:"):
        key = raw[len("ui:") :].strip()
    else:
        return None

    key = str(key or "").strip()
    if not key.startswith(_UI_STATE_GROUP_PREFIX):
        return None

    if _parse_ui_state_group_key_or_none(key) is not None:
        return None

    if key.startswith("UI_STATE_GROUP__"):
        return (
            "UI_STATE_GROUP 占位符格式不正确：期望 `ui_key:UI_STATE_GROUP__<group_name>__<state_name>__group`（必须包含 state_name）。"
        )
    return (
        "UI_STATE_GROUP 占位符格式不正确：期望 `ui_key:UI_STATE_GROUP__<group_name>__<state_name>__group`（注意双下划线 `__`）。"
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
        # UI_STATE_GROUP：严格保留完整 key，用于校验 state 是否存在。
        if key.startswith("UI_STATE_GROUP__"):
            return key if _parse_ui_state_group_key_or_none(key) is not None else key
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
        if key.startswith("UI_STATE_GROUP__"):
            return key if _parse_ui_state_group_key_or_none(key) is not None else key
        if "__" in key:
            parts = [p for p in key.split("__") if str(p)]
            if len(parts) >= 2:
                return str(parts[1]).strip() or None
        return key
    return None


def extract_ui_key_placeholder_raw_key(text: str) -> Optional[str]:
    """Extract raw ui_key text after `ui_key:` or `ui:` prefix."""
    raw = str(text or "").strip()
    lowered = raw.lower()
    if lowered.startswith("ui_key:"):
        key = raw[len("ui_key:") :].strip()
        return key if key else None
    if lowered.startswith("ui:"):
        key = raw[len("ui:") :].strip()
        return key if key else None
    return None


@dataclass(frozen=True)
class UiHtmlUiKeyView:
    scope: GraphResourceScope
    ui_source_dirs: Tuple[Path, ...]
    html_files: Tuple[Path, ...]
    ui_keys: Tuple[str, ...]


@dataclass(frozen=True)
class UiWorkbenchUiKeyView:
    scope: GraphResourceScope
    ui_source_dirs: Tuple[Path, ...]
    workbench_out_dirs: Tuple[Path, ...]
    ui_bundle_files: Tuple[Path, ...]
    ui_keys: Tuple[str, ...]
    ui_keys_by_data_ui_key: Dict[str, Tuple[str, ...]]


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


def _infer_workbench_out_dirs(ui_source_dirs: Tuple[Path, ...]) -> Tuple[Path, ...]:
    """Infer UI Workbench output directories under ui_source_dirs."""
    dirs: List[Path] = []
    for d in list(ui_source_dirs or ()):
        out_dir = (Path(d).resolve() / _UI_WORKBENCH_OUT_DIRNAME).resolve()
        if out_dir.is_dir():
            dirs.append(out_dir)
    uniq: List[Path] = []
    seen: set[str] = set()
    for d2 in dirs:
        key = str(d2.resolve())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(d2)
    return tuple(uniq)


def _iter_ui_bundle_files_under_dir(workbench_out_dir: Path) -> List[Path]:
    """Iterate ui_bundle.json files under a workbench output directory."""
    d = Path(workbench_out_dir).resolve()
    if not d.is_dir():
        return []
    files = [p.resolve() for p in d.glob("*.ui_bundle.json") if p.is_file()]
    files.sort(key=lambda p: p.as_posix().casefold())
    return files


def _extract_ui_keys_from_ui_bundle_obj(obj: object) -> Set[str]:
    """Extract ui_key fields from a UI Workbench bundle JSON object."""
    if not isinstance(obj, dict):
        return set()
    templates = obj.get("templates")
    if not isinstance(templates, list):
        return set()
    out: Set[str] = set()
    for tpl in templates:
        if not isinstance(tpl, dict):
            continue
        widgets = tpl.get("widgets")
        if not isinstance(widgets, list):
            continue
        for w in widgets:
            if not isinstance(w, dict):
                continue
            key = w.get("ui_key")
            if isinstance(key, str):
                s = key.strip()
                if s:
                    out.add(s)
    return out


def _compute_bundle_fingerprint(bundle_files: List[Path]) -> Tuple[int, float]:
    """Compute a cheap fingerprint for bundle files by count and latest mtime."""
    count = 0
    latest = 0.0
    for p in bundle_files:
        if not p.exists() or not p.is_file():
            continue
        count += 1
        mtime = float(p.stat().st_mtime)
        if mtime > latest:
            latest = mtime
    return int(count), float(latest)


# cache_key -> (fingerprint, ui_source_dirs, workbench_out_dirs, bundle_files, ui_keys, ui_keys_by_data_ui_key)
_UI_WORKBENCH_KEYS_CACHE: Dict[
    str,
    Tuple[
        Tuple[int, float],
        Tuple[Path, ...],
        Tuple[Path, ...],
        Tuple[Path, ...],
        Tuple[str, ...],
        Dict[str, Tuple[str, ...]],
    ],
] = {}


def try_load_ui_workbench_ui_keys_for_ctx(ctx: ValidationContext) -> Optional[UiWorkbenchUiKeyView]:
    """Try loading ui_key set from UI Workbench bundles for current ctx scope."""
    if ctx.file_path is None:
        return None
    scope = try_build_graph_resource_scope(ctx.workspace_path, ctx.file_path)
    if scope is None:
        return None

    ui_source_dirs = infer_ui_source_dirs_for_ctx(ctx)
    if not ui_source_dirs:
        return UiWorkbenchUiKeyView(
            scope=scope,
            ui_source_dirs=tuple(),
            workbench_out_dirs=tuple(),
            ui_bundle_files=tuple(),
            ui_keys=tuple(),
            ui_keys_by_data_ui_key={},
        )

    workbench_out_dirs = _infer_workbench_out_dirs(tuple(ui_source_dirs))
    all_bundle_files: List[Path] = []
    for d in list(workbench_out_dirs or ()):
        all_bundle_files.extend(_iter_ui_bundle_files_under_dir(Path(d)))

    unique_files: List[Path] = []
    seen_files: set[str] = set()
    for p in all_bundle_files:
        key = str(p.resolve())
        if key in seen_files:
            continue
        seen_files.add(key)
        unique_files.append(p)
    unique_files.sort(key=lambda p: p.as_posix().casefold())

    fingerprint = _compute_bundle_fingerprint(unique_files)
    cache_key = "|".join(str(d.resolve()) for d in ui_source_dirs)
    cached = _UI_WORKBENCH_KEYS_CACHE.get(cache_key)
    if cached is not None:
        cached_fp, cached_ui_dirs, cached_out_dirs, cached_files, cached_keys, cached_map = cached
        if cached_fp == fingerprint:
            return UiWorkbenchUiKeyView(
                scope=scope,
                ui_source_dirs=cached_ui_dirs,
                workbench_out_dirs=cached_out_dirs,
                ui_bundle_files=cached_files,
                ui_keys=cached_keys,
                ui_keys_by_data_ui_key=dict(cached_map),
            )

    key_set: Set[str] = set()
    for bundle_file in unique_files:
        obj = json.loads(bundle_file.read_text(encoding="utf-8"))
        key_set.update(_extract_ui_keys_from_ui_bundle_obj(obj))

    keys_sorted = tuple(sorted(key_set, key=lambda s: s.casefold()))
    ui_dirs_tuple = tuple(ui_source_dirs)
    out_dirs_tuple = tuple(workbench_out_dirs)
    files_tuple = tuple(unique_files)

    by_data: Dict[str, Set[str]] = {}
    for k in keys_sorted:
        parts = [p for p in str(k).split("__") if str(p)]
        if len(parts) >= 3:
            data_ui_key = str(parts[1]).strip()
            if data_ui_key:
                by_data.setdefault(data_ui_key, set()).add(str(k))
    by_data_sorted: Dict[str, Tuple[str, ...]] = {
        str(k): tuple(sorted(v, key=lambda s: s.casefold())) for k, v in by_data.items()
    }

    _UI_WORKBENCH_KEYS_CACHE[cache_key] = (
        fingerprint,
        ui_dirs_tuple,
        out_dirs_tuple,
        files_tuple,
        keys_sorted,
        dict(by_data_sorted),
    )
    return UiWorkbenchUiKeyView(
        scope=scope,
        ui_source_dirs=ui_dirs_tuple,
        workbench_out_dirs=out_dirs_tuple,
        ui_bundle_files=files_tuple,
        ui_keys=keys_sorted,
        ui_keys_by_data_ui_key=dict(by_data_sorted),
    )


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

    # state pairs：用于 `UI_STATE_GROUP__<group>__<state>__group` 的存在性校验
    pairs: Set[Tuple[str, str]] = set()
    raw_text = str(text or "")
    for m in _UI_STATE_PAIR_RE_GROUP_FIRST.finditer(raw_text):
        g = str(m.group("group") or "").strip()
        s = str(m.group("state") or "").strip()
        if g and s:
            pairs.add((g, s))
    for m2 in _UI_STATE_PAIR_RE_STATE_FIRST.finditer(raw_text):
        g2 = str(m2.group("group") or "").strip()
        s2 = str(m2.group("state") or "").strip()
        if g2 and s2:
            pairs.add((g2, s2))
    for g3, s3 in pairs:
        out.add(f"UI_STATE_GROUP__{g3}__{s3}__group")
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
    "UiWorkbenchUiKeyView",
    "infer_ui_source_dirs_for_ctx",
    "extract_ui_key_placeholder_raw_key",
    "parse_ui_key_placeholder",
    "try_format_invalid_ui_state_group_placeholder_message",
    "try_load_ui_html_ui_keys_for_ctx",
    "try_load_ui_workbench_ui_keys_for_ctx",
]

