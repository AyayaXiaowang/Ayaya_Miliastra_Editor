from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set, Tuple, List

from ..context import ValidationContext
from .ui_key_registry_utils import infer_ui_source_dirs_for_ctx


_MOUSTACHE_PLACEHOLDER_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_BRACED_PLACEHOLDER_RE = re.compile(r"\{(\d+)\s*:\s*([^{}]+?)\}")


def _iter_html_files_under_dir(ui_source_dir: Path) -> List[Path]:
    if not ui_source_dir.exists() or not ui_source_dir.is_dir():
        return []
    results: List[Path] = []
    for p in ui_source_dir.rglob("*.html"):
        if not p.is_file():
            continue
        if p.name.lower().endswith(".flattened.html"):
            continue
        results.append(p.resolve())
    results.sort(key=lambda p: p.as_posix().casefold())
    return results


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


def _extract_level_and_player_scoped_var_names_from_html_text(text: str) -> tuple[Set[str], Set[str]]:
    """从 HTML 文本中提取“关卡/玩家”作用域占位符引用到的根变量名集合。

    约定：
    - 关卡作用域：lv
    - 玩家作用域：ps / p1..p8（以及未来可能出现的 p<number>）
    """
    level_vars: Set[str] = set()
    player_vars: Set[str] = set()

    def _accept_expr(expr: str) -> None:
        e = str(expr or "").strip()
        if not e or any(ch.isspace() for ch in e):
            return
        scope, sep, rest = e.partition(".")
        if sep != ".":
            return
        scope_lower = scope.strip().lower()
        segments = [s.strip() for s in str(rest or "").split(".") if s.strip()]
        if not segments:
            return
        var_name = segments[0]
        if var_name:
            if scope_lower == "lv":
                level_vars.add(var_name)
            elif scope_lower == "ps" or (scope_lower.startswith("p") and scope_lower[1:].isdigit()):
                player_vars.add(var_name)

    raw_text = str(text or "")
    for match in _MOUSTACHE_PLACEHOLDER_RE.finditer(raw_text):
        _accept_expr(match.group(1))
    for match in _BRACED_PLACEHOLDER_RE.finditer(raw_text):
        # {1:lv.xxx} -> lv.xxx
        _accept_expr(match.group(2))

    return level_vars, player_vars


@dataclass(frozen=True)
class UiHtmlLevelPlaceholderVarView:
    ui_source_dirs: Tuple[Path, ...]
    html_files: Tuple[Path, ...]
    level_scoped_var_names: Tuple[str, ...]


# cache_key -> (fingerprint, dirs, files, var_names)
_UI_HTML_LEVEL_PLACEHOLDER_VARS_CACHE: Dict[
    str, Tuple[Tuple[int, float], Tuple[Path, ...], Tuple[Path, ...], Tuple[str, ...]]
] = {}


def try_load_ui_html_level_placeholder_vars_for_ctx(
    ctx: ValidationContext,
) -> Optional[UiHtmlLevelPlaceholderVarView]:
    """尝试从当前作用域 UI源码(HTML) 中汇总 lv 占位符引用到的变量名集合。"""
    ui_source_dirs = infer_ui_source_dirs_for_ctx(ctx)
    if not ui_source_dirs:
        # 兜底：不依赖“资源根枚举”（packages_root 扫描）推断 UI源码 位置，
        # 直接从当前文件的父目录向上尝试找到同级的 `管理配置/UI源码`。
        # 该路径形态在资源库中稳定存在（共享/项目存档均适用）。
        if ctx.file_path is None:
            return None
        candidates: List[Path] = []
        for parent in Path(ctx.file_path).resolve().parents:
            cand = (parent / "管理配置" / "UI源码").resolve()
            if cand.is_dir():
                candidates.append(cand)
                break
            # 到资源库根就停止
            if parent.name == "资源库":
                break
        ui_source_dirs = tuple(candidates)
        if not ui_source_dirs:
            return None

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
    cached = _UI_HTML_LEVEL_PLACEHOLDER_VARS_CACHE.get(cache_key)
    if cached is not None:
        cached_fp, cached_dirs, cached_files, cached_names = cached
        if cached_fp == fingerprint:
            return UiHtmlLevelPlaceholderVarView(
                ui_source_dirs=cached_dirs,
                html_files=cached_files,
                level_scoped_var_names=cached_names,
            )

    names: Set[str] = set()
    for html_file in unique_files:
        text = html_file.read_text(encoding="utf-8")
        level_vars, _player_vars = _extract_level_and_player_scoped_var_names_from_html_text(text)
        names.update(level_vars)

    names_sorted = tuple(sorted(names, key=lambda s: s.casefold()))
    dirs_tuple = tuple(ui_source_dirs)
    files_tuple = tuple(unique_files)
    _UI_HTML_LEVEL_PLACEHOLDER_VARS_CACHE[cache_key] = (fingerprint, dirs_tuple, files_tuple, names_sorted)
    return UiHtmlLevelPlaceholderVarView(
        ui_source_dirs=dirs_tuple,
        html_files=files_tuple,
        level_scoped_var_names=names_sorted,
    )


@dataclass(frozen=True)
class UiHtmlPlaceholderVarContractView:
    ui_source_dirs: Tuple[Path, ...]
    html_files: Tuple[Path, ...]
    level_scoped_var_names: Tuple[str, ...]
    player_scoped_var_names: Tuple[str, ...]


# cache_key -> (fingerprint, dirs, files, level_names, player_names)
_UI_HTML_PLACEHOLDER_VAR_CONTRACT_CACHE: Dict[
    str, Tuple[Tuple[int, float], Tuple[Path, ...], Tuple[Path, ...], Tuple[str, ...], Tuple[str, ...]]
] = {}


def try_load_ui_html_placeholder_var_contract_for_ctx(
    ctx: ValidationContext,
) -> Optional[UiHtmlPlaceholderVarContractView]:
    """尝试从当前作用域 UI源码(HTML) 中汇总 lv/ps 等占位符引用到的变量“归属契约”。

    返回的集合只包含“根变量名”（字典字段路径只保留根变量名）。
    """
    ui_source_dirs = infer_ui_source_dirs_for_ctx(ctx)
    if not ui_source_dirs:
        if ctx.file_path is None:
            return None
        candidates: List[Path] = []
        for parent in Path(ctx.file_path).resolve().parents:
            cand = (parent / "管理配置" / "UI源码").resolve()
            if cand.is_dir():
                candidates.append(cand)
                break
            if parent.name == "资源库":
                break
        ui_source_dirs = tuple(candidates)
        if not ui_source_dirs:
            return None

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
    cached = _UI_HTML_PLACEHOLDER_VAR_CONTRACT_CACHE.get(cache_key)
    if cached is not None:
        cached_fp, cached_dirs, cached_files, cached_level, cached_player = cached
        if cached_fp == fingerprint:
            return UiHtmlPlaceholderVarContractView(
                ui_source_dirs=cached_dirs,
                html_files=cached_files,
                level_scoped_var_names=cached_level,
                player_scoped_var_names=cached_player,
            )

    level_names: Set[str] = set()
    player_names: Set[str] = set()
    for html_file in unique_files:
        text = html_file.read_text(encoding="utf-8")
        lv, pv = _extract_level_and_player_scoped_var_names_from_html_text(text)
        level_names.update(lv)
        player_names.update(pv)

    level_sorted = tuple(sorted(level_names, key=lambda s: s.casefold()))
    player_sorted = tuple(sorted(player_names, key=lambda s: s.casefold()))
    dirs_tuple = tuple(ui_source_dirs)
    files_tuple = tuple(unique_files)
    _UI_HTML_PLACEHOLDER_VAR_CONTRACT_CACHE[cache_key] = (fingerprint, dirs_tuple, files_tuple, level_sorted, player_sorted)
    return UiHtmlPlaceholderVarContractView(
        ui_source_dirs=dirs_tuple,
        html_files=files_tuple,
        level_scoped_var_names=level_sorted,
        player_scoped_var_names=player_sorted,
    )


__all__ = [
    "UiHtmlLevelPlaceholderVarView",
    "UiHtmlPlaceholderVarContractView",
    "try_load_ui_html_level_placeholder_vars_for_ctx",
    "try_load_ui_html_placeholder_var_contract_for_ctx",
]

