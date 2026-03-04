from __future__ import annotations

import html as _html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple, List

from ugc_file_tools.custom_variables.apply import (
    ensure_custom_variables_from_variable_defaults,
    ensure_text_placeholder_referenced_custom_variables,
)
from ugc_file_tools.custom_variables.defaults import normalize_variable_defaults_map
from ugc_file_tools.custom_variables.refs import extract_variable_refs_from_text_placeholders


_HTML_VARIABLE_DEFAULTS_SINGLE_QUOTE_RE = re.compile(r"data-ui-variable-defaults\s*=\s*'([^']*)'", re.IGNORECASE)
_HTML_VARIABLE_DEFAULTS_DOUBLE_QUOTE_RE = re.compile(r'data-ui-variable-defaults\s*=\s*"([^"]*)"', re.IGNORECASE)


def _iter_ui_source_html_files(ui_source_dir: Path) -> List[Path]:
    d = Path(ui_source_dir).resolve()
    if not d.is_dir():
        return []
    files: List[Path] = []
    for p in d.rglob("*.html"):
        if not p.is_file():
            continue
        if p.name.lower().endswith(".flattened.html"):
            continue
        files.append(p.resolve())
    files.sort(key=lambda p: p.as_posix().casefold())
    return files


def _extract_variable_defaults_from_html_text(html_text: str) -> Dict[str, Any]:
    raw = str(html_text or "")
    if raw.strip() == "":
        return {}

    merged: Dict[str, Any] = {}
    matches: List[str] = []
    matches.extend([m.group(1) for m in _HTML_VARIABLE_DEFAULTS_SINGLE_QUOTE_RE.finditer(raw)])
    matches.extend([m.group(1) for m in _HTML_VARIABLE_DEFAULTS_DOUBLE_QUOTE_RE.finditer(raw)])
    if not matches:
        return {}

    for text in matches:
        decoded = _html.unescape(str(text or "").strip())
        if decoded == "":
            continue
        obj = json.loads(decoded)
        if not isinstance(obj, dict):
            raise ValueError("data-ui-variable-defaults 必须是 JSON object（dict）。")
        for k, v in obj.items():
            key = str(k or "").strip()
            if key == "":
                continue
            merged[key] = v
    return merged


def _merge_variable_defaults_from_ui_html_files(html_files: List[Path]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for p in list(html_files):
        text = p.read_text(encoding="utf-8")
        m = _extract_variable_defaults_from_html_text(text)
        if not m:
            continue
        # 后者覆盖前者同名 key（与 Workbench 导出一致）
        merged.update(m)
    return merged


@dataclass(frozen=True)
class UiHtmlPlaceholderScanResult:
    html_files: Tuple[Path, ...]
    variable_refs: Set[tuple[str, str, tuple[str, ...]]]
    raw_variable_defaults: Dict[str, Any]
    normalized_variable_defaults: Dict[str, Any]


def scan_ui_source_dir_for_placeholder_variable_refs_and_defaults(ui_source_dir: Path) -> UiHtmlPlaceholderScanResult:
    html_files = _iter_ui_source_html_files(Path(ui_source_dir))
    refs: set[tuple[str, str, tuple[str, ...]]] = set()
    for p in html_files:
        text = p.read_text(encoding="utf-8")
        refs.update(extract_variable_refs_from_text_placeholders(text))
    raw_defaults = _merge_variable_defaults_from_ui_html_files(html_files)
    normalized_defaults = normalize_variable_defaults_map(raw_defaults) if raw_defaults else {}
    return UiHtmlPlaceholderScanResult(
        html_files=tuple(html_files),
        variable_refs=set(refs),
        raw_variable_defaults=dict(raw_defaults),
        normalized_variable_defaults=dict(normalized_defaults),
    )


def try_infer_project_ui_source_dir_from_any_path(path: Path) -> Optional[Path]:
    """从任意路径推断其所属项目存档的 UI源码 目录：assets/资源库/项目存档/<package_id>/管理配置/UI源码"""
    p = Path(path).resolve()
    parts = list(p.parts)
    assets_index: Optional[int] = None
    for i, part in enumerate(parts):
        if str(part) == "assets":
            assets_index = int(i)
            break
    project_index: Optional[int] = None
    for i, part in enumerate(parts):
        if str(part) == "项目存档":
            project_index = int(i)
            break
    if assets_index is None or project_index is None:
        return None
    if project_index + 1 >= len(parts):
        return None
    workspace_root = Path(*parts[:assets_index]).resolve()
    package_id = str(parts[project_index + 1]).strip()
    if not package_id:
        return None
    ui_dir = (workspace_root / "assets" / "资源库" / "项目存档" / package_id / "管理配置" / "UI源码").resolve()
    return ui_dir if ui_dir.is_dir() else None


def apply_ui_placeholder_custom_variables_to_payload_root(
    *,
    payload_root: Dict[str, Any],
    ui_source_dir: Path,
) -> Dict[str, Any]:
    """将 UI源码(HTML) 中的占位符引用与默认值写入 payload_root(=root4)。"""
    if not isinstance(payload_root, dict):
        raise TypeError("payload_root must be dict")

    scan = scan_ui_source_dir_for_placeholder_variable_refs_and_defaults(Path(ui_source_dir))
    if not scan.variable_refs and not scan.normalized_variable_defaults:
        return {
            "applied": False,
            "reason": "no_placeholders_and_no_variable_defaults",
            "ui_source_dir": str(Path(ui_source_dir).resolve()),
            "html_files_total": int(len(scan.html_files)),
        }

    raw_dump_object = {"4": payload_root}
    defaults_report = ensure_custom_variables_from_variable_defaults(
        raw_dump_object,
        variable_defaults=dict(scan.normalized_variable_defaults),
    )
    placeholders_report = ensure_text_placeholder_referenced_custom_variables(
        raw_dump_object,
        variable_refs=set(scan.variable_refs),
        variable_defaults=dict(scan.normalized_variable_defaults),
    )
    return {
        "applied": True,
        "ui_source_dir": str(Path(ui_source_dir).resolve()),
        "html_files_total": int(len(scan.html_files)),
        "html_files": [str(p) for p in scan.html_files],
        "placeholder_variable_refs_total": int(len(scan.variable_refs)),
        "variable_defaults_total": int(len(scan.normalized_variable_defaults)),
        "variable_defaults_created_custom_variables_report": dict(defaults_report),
        "text_placeholder_created_custom_variables_report": dict(placeholders_report),
    }


__all__ = [
    "apply_ui_placeholder_custom_variables_to_payload_root",
    "scan_ui_source_dir_for_placeholder_variable_refs_and_defaults",
    "try_infer_project_ui_source_dir_from_any_path",
    "UiHtmlPlaceholderScanResult",
]

