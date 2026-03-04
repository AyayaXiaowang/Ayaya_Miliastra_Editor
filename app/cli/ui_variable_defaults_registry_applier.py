from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.resources.auto_custom_variable_registry import (
    load_auto_custom_variable_registry_from_code,
)

from app.cli.registry_declaration_editor import replace_auto_custom_variable_default_value
from app.cli.ui_variable_defaults_extractor import (
    extract_ui_variable_defaults_from_html,
    try_extract_ui_variable_defaults_from_html,
)


@dataclass(frozen=True, slots=True)
class ApplyUiDefaultsAction:
    file_path: Path
    summary: str


def _normalize_one_level_value(value: Any) -> Any:
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def _normalize_one_level_dict(source: dict[str, Any]) -> dict[str, Any]:
    return {str(k): _normalize_one_level_value(v) for k, v in source.items()}


def _merge_defaults_shallow(*, existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(existing)
    merged.update(dict(incoming))
    return merged


def _discover_html_files_with_defaults(ui_source_dir: Path) -> list[Path]:
    found: list[Path] = []
    for p in sorted([x for x in ui_source_dir.glob("*.html") if x.is_file()], key=lambda x: x.as_posix().casefold()):
        result = try_extract_ui_variable_defaults_from_html(p)
        if result is None:
            continue
        found.append(p)
    return found


def apply_ui_defaults_to_registry(
    *,
    workspace_root: Path,
    package_id: str,
    html_path: Path | None,
    apply_all: bool,
    dry_run: bool,
) -> list[ApplyUiDefaultsAction]:
    pkg = str(package_id or "").strip()
    if not pkg:
        raise ValueError("package_id 不能为空")
    workspace = Path(workspace_root).resolve()
    package_root = (workspace / "assets" / "资源库" / "项目存档" / pkg).resolve()
    if not package_root.is_dir():
        raise ValueError(f"未知项目存档目录：{package_root}")

    registry_path = (package_root / "管理配置" / "关卡变量" / "自定义变量注册表.py").resolve()
    if not registry_path.is_file():
        raise FileNotFoundError(f"未找到自定义变量注册表文件：{registry_path}")

    ui_source_dir = (package_root / "管理配置" / "UI源码").resolve()
    html_files: list[Path]
    if apply_all:
        html_files = _discover_html_files_with_defaults(ui_source_dir)
    else:
        target = html_path or (ui_source_dir / "ceshi_rect.html")
        html_files = [Path(target).resolve()]

    merged_by_var: dict[str, dict[str, Any]] = {}
    for p in html_files:
        result = extract_ui_variable_defaults_from_html(p)
        for var_name, defaults in (result.split_defaults or {}).items():
            name = str(var_name or "").strip()
            if not name:
                continue
            incoming = _normalize_one_level_dict(dict(defaults))
            existing = merged_by_var.get(name, {})
            merged_by_var[name] = _merge_defaults_shallow(existing=existing, incoming=incoming)

    decls = load_auto_custom_variable_registry_from_code(registry_path)
    name_to_id: dict[str, str] = {}
    name_to_default: dict[str, Any] = {}
    for d in list(decls or []):
        name = str(getattr(d, "variable_name", "") or "").strip()
        vid = str(getattr(d, "variable_id", "") or "").strip()
        if name and vid and name not in name_to_id:
            name_to_id[name] = vid
            name_to_default[name] = getattr(d, "default_value", None)

    actions: list[ApplyUiDefaultsAction] = []
    for var_name, incoming_dict in sorted(merged_by_var.items(), key=lambda kv: kv[0].casefold()):
        if var_name not in name_to_id:
            raise ValueError(f"{registry_path}: 注册表中未找到 UI defaults 对应变量：{var_name!r}")
        old_default = name_to_default.get(var_name)
        if isinstance(old_default, dict):
            new_default = _merge_defaults_shallow(existing=dict(old_default), incoming=dict(incoming_dict))
        else:
            new_default = dict(incoming_dict)
        if dry_run:
            actions.append(
                ApplyUiDefaultsAction(
                    file_path=registry_path,
                    summary=f"[DRY-RUN] 将更新 {var_name!r} default_value（keys={len(new_default)}）",
                )
            )
            continue
        edit = replace_auto_custom_variable_default_value(
            registry_path=registry_path,
            variable_id=name_to_id[var_name],
            new_default_value=new_default,
        )
        actions.append(
            ApplyUiDefaultsAction(
                file_path=registry_path,
                summary=f"更新 {var_name!r} default_value（{len(new_default)} keys；old={len(edit.old_literal)} chars new={len(edit.new_literal)} chars）",
            )
        )

    return actions


__all__ = [
    "ApplyUiDefaultsAction",
    "apply_ui_defaults_to_registry",
]

