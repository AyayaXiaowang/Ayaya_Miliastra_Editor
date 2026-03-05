from __future__ import annotations

import html as _html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple, List, Sequence

from ugc_file_tools.auto_custom_variable_registry_bridge import OWNER_LEVEL, OWNER_PLAYER
from ugc_file_tools.auto_custom_variable_registry_bridge import (
    try_load_auto_custom_variable_registry_index_from_project_root,
)
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


def _try_infer_project_root_from_ui_source_dir(ui_source_dir: Path) -> Optional[Path]:
    d = Path(ui_source_dir).resolve()
    if d.name == "UI源码" and d.parent.name == "管理配置":
        return d.parent.parent.resolve()
    inferred = try_infer_project_ui_source_dir_from_any_path(d)
    if inferred is None:
        return None
    # inferred == <project_root>/管理配置/UI源码
    if inferred.name == "UI源码" and inferred.parent.name == "管理配置":
        return inferred.parent.parent.resolve()
    return None


def _ensure_ui_referenced_custom_variables_from_registry(
    *,
    payload_root: Dict[str, Any],
    ui_scan: UiHtmlPlaceholderScanResult,
    project_root: Path,
) -> Dict[str, Any]:
    """
    当项目存档启用了 `自定义变量注册表.py` 时：
    - UI 文本占位符 / data-ui-variable-defaults 引用到的变量必须在注册表声明；
    - 写回仅补齐缺失变量，不覆盖已存在同名变量的当前值；
    - 若同名但类型不匹配：默认不覆盖，并在报告中列出（fail-fast 由上层决定）。
    """
    from ugc_file_tools.custom_variables.apply import (
        collect_player_template_custom_variable_targets_from_payload_root,
        extract_instance_entry_name_from_root4_5_1_entry,
        find_root4_5_1_entry_by_name,
    )
    from ugc_file_tools.custom_variables.coerce import normalize_custom_variable_name_field2
    from ugc_file_tools.project_archive_importer.custom_variable_writeback import (
        build_custom_variable_item_from_level_variable_payload,
        ensure_override_variables_group1_variable_items_container,
    )
    from ugc_file_tools.var_type_map import map_server_port_type_text_to_var_type_id_or_raise

    index = try_load_auto_custom_variable_registry_index_from_project_root(project_root=Path(project_root))
    if index is None:
        raise RuntimeError("internal error: registry index expected but not found")

    # required variable roots: (group_name, var_name)
    required: set[tuple[str, str]] = set()
    for g, n, _path in set(ui_scan.variable_refs or set()):
        gg = str(g or "").strip()
        nn = str(n or "").strip()
        if gg and nn:
            required.add((gg, nn))
    for full_name in dict(ui_scan.normalized_variable_defaults or {}).keys():
        full = str(full_name or "").strip()
        if "." not in full:
            continue
        g, _, n = full.partition(".")
        if str(g).strip() and str(n).strip():
            required.add((str(g).strip(), str(n).strip()))

    group_to_owner = {"关卡": OWNER_LEVEL, "玩家自身": OWNER_PLAYER}
    missing_in_registry: list[dict[str, str]] = []
    payloads_by_group_and_name: dict[tuple[str, str], dict[str, Any]] = {}
    for group_name, var_name in sorted(required, key=lambda t: (t[0].casefold(), t[1].casefold())):
        owner = group_to_owner.get(str(group_name))
        if owner is None:
            raise ValueError(f"未知变量组名：{group_name!r}（仅支持：关卡 / 玩家自身）")
        payload0 = index.payloads_by_owner_and_name.get(str(owner), {}).get(str(var_name).casefold())
        if payload0 is None:
            missing_in_registry.append({"group": str(group_name), "variable_name": str(var_name), "owner": str(owner)})
            continue
        payload = dict(payload0)
        # 优先使用 UI 提供的默认值（与现有写回语义一致），但类型仍以注册表为准。
        ui_default_key = f"{group_name}.{var_name}"
        if ui_default_key in dict(ui_scan.normalized_variable_defaults or {}):
            payload["default_value"] = dict(ui_scan.normalized_variable_defaults).get(ui_default_key)

        # 轻量类型一致性检查（避免注册表声明与 UI 默认值形态冲突）
        type_text = str(payload.get("variable_type") or "").strip()
        vt = int(map_server_port_type_text_to_var_type_id_or_raise(type_text))
        dv = payload.get("default_value")
        if vt == 27 and dv is not None and not isinstance(dv, dict):
            raise ValueError(
                "UI 默认值与注册表变量类型冲突："
                f"{ui_default_key!r} 声明为字典(type=27)，但 UI 默认值不是 dict（type={type(dv).__name__}）。"
            )
        if vt != 27 and isinstance(dv, dict):
            raise ValueError(
                "UI 默认值与注册表变量类型冲突："
                f"{ui_default_key!r} 声明为标量(type={vt})，但 UI 默认值为 dict。"
            )

        payloads_by_group_and_name[(group_name, var_name)] = payload

    if missing_in_registry:
        raise ValueError(
            f"{str(index.registry_path)}: UI 源码引用了未在注册表声明的自定义变量：{missing_in_registry}"
        )

    # locate targets in payload_root (=root4)
    section5 = payload_root.get("5")
    if not isinstance(section5, dict):
        raise ValueError("payload_root 缺少字段 '5'（期望为 dict）。")
    entry_list = section5.get("1")
    if not isinstance(entry_list, list):
        raise ValueError("payload_root 缺少字段 '5/1'（期望为 list）。")

    level_entry = find_root4_5_1_entry_by_name(entry_list, "关卡实体")
    if level_entry is None:
        raise RuntimeError("未在 root4/5/1 中找到 name=关卡实体 的条目，无法写入关卡变量。")

    player_entity_entry = find_root4_5_1_entry_by_name(entry_list, "玩家实体")
    role_editor_entry = find_root4_5_1_entry_by_name(entry_list, "默认模版(角色编辑)")
    player_template_targets = collect_player_template_custom_variable_targets_from_payload_root(payload_root)

    def _iter_targets_for_group(group_name: str) -> list[tuple[Dict[str, Any], str, str]]:
        g = str(group_name or "").strip()
        if g == "关卡":
            return [(level_entry, "7", "关卡实体")]
        if g == "玩家自身":
            out: list[tuple[Dict[str, Any], str, str]] = []
            if player_entity_entry is not None:
                out.append((player_entity_entry, "7", "玩家实体"))
            for t in list(player_template_targets or []):
                wrappers = t.get("root5_wrappers")
                if isinstance(wrappers, list):
                    for w in wrappers:
                        if isinstance(w, dict):
                            name = extract_instance_entry_name_from_root4_5_1_entry(w) or "<玩家模板>"
                            out.append((w, "7", f"玩家模板:{name}"))
                e4 = t.get("root4_entry")
                if isinstance(e4, dict):
                    names = t.get("template_names")
                    label_name = ""
                    if isinstance(names, list) and names:
                        label_name = str(names[0])
                    label = f"玩家模板(模板段):{label_name}" if label_name else "玩家模板(模板段)"
                    out.append((e4, "8", label))
            if out:
                return out
            if role_editor_entry is not None:
                return [(role_editor_entry, "7", "默认模版(角色编辑)")]
            raise RuntimeError(
                "UI 源码引用了 玩家自身.<变量>，但存档中未找到 玩家实体 / 玩家模板(wrapper) / 默认模版(角色编辑) 条目。"
            )
        raise ValueError(f"未知变量组名：{g!r}（仅支持：关卡 / 玩家自身）")

    created_total = 0
    existed_total = 0
    type_mismatched_total = 0
    variables_report: list[dict[str, Any]] = []

    for (group_name, var_name), payload in payloads_by_group_and_name.items():
        targets = _iter_targets_for_group(group_name)
        item, report_item = build_custom_variable_item_from_level_variable_payload(payload)
        want_type = int(report_item.get("var_type_int") or 0)
        created_in: list[str] = []
        existed_in: list[str] = []
        type_mismatched_in: list[dict[str, Any]] = []

        for target_entry, group_list_key, target_label in targets:
            group_item, _view = ensure_override_variables_group1_variable_items_container(
                target_entry, group_list_key=str(group_list_key)
            )
            container = group_item.get("11")
            if not isinstance(container, dict):
                raise RuntimeError("internal error: group_item['11'] is not dict")
            items_any = container.get("1")
            if not isinstance(items_any, list):
                raise RuntimeError("internal error: group_item['11']['1'] is not list")

            existed_item: dict[str, Any] | None = None
            for it in items_any:
                if not isinstance(it, dict):
                    continue
                if normalize_custom_variable_name_field2(it.get("2")).casefold() == str(var_name).casefold():
                    existed_item = it
                    break
            if existed_item is None:
                items_any.append(dict(item))
                created_total += 1
                created_in.append(str(target_label))
                continue

            existed_total += 1
            existed_in.append(str(target_label))
            existed_type = existed_item.get("3")
            if isinstance(existed_type, int) and int(existed_type) != int(want_type) and int(want_type) != 0:
                type_mismatched_total += 1
                type_mismatched_in.append(
                    {"target": str(target_label), "existing_type_code": existed_type, "want_type_code": int(want_type)}
                )

        variables_report.append(
            {
                "group": str(group_name),
                "variable_name": str(var_name),
                "variable_id": str(payload.get("variable_id") or ""),
                "var_type_int": int(want_type),
                "created": bool(created_in),
                "created_in": created_in,
                "existed_in": existed_in,
                "type_mismatched_in": type_mismatched_in,
            }
        )

    return {
        "applied": True,
        "source": "registry",
        "registry_path": str(index.registry_path),
        "created_total": int(created_total),
        "existed_total": int(existed_total),
        "type_mismatched_total": int(type_mismatched_total),
        "variables": list(variables_report),
    }


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


def scan_ui_html_files_for_placeholder_variable_refs_and_defaults(html_files: Sequence[Path]) -> UiHtmlPlaceholderScanResult:
    """
    从指定的 UI HTML 文件集合扫描占位符引用与 data-ui-variable-defaults 默认值。

    用途：导出中心左侧资源树允许按文件勾选 UI 源码，因此“UI→自定义变量联动”应按本次选中的 HTML 文件集计算，
    而不是扫描整个 UI源码 目录。
    """
    files0: list[Path] = []
    for p in list(html_files or []):
        pp = Path(p).resolve()
        if not pp.is_file():
            continue
        if pp.name.lower().endswith(".flattened.html"):
            continue
        if pp.suffix.lower() not in {".html", ".htm"}:
            continue
        files0.append(pp)
    # 去重稳定排序
    seen: set[str] = set()
    files: list[Path] = []
    for p in files0:
        k = p.as_posix().casefold()
        if k in seen:
            continue
        seen.add(k)
        files.append(p)
    files.sort(key=lambda p: p.as_posix().casefold())

    refs: set[tuple[str, str, tuple[str, ...]]] = set()
    merged_defaults: Dict[str, Any] = {}
    for p in files:
        text = p.read_text(encoding="utf-8")
        refs.update(extract_variable_refs_from_text_placeholders(text))
        m = _extract_variable_defaults_from_html_text(text)
        if m:
            merged_defaults.update(m)
    normalized_defaults = normalize_variable_defaults_map(merged_defaults) if merged_defaults else {}
    return UiHtmlPlaceholderScanResult(
        html_files=tuple(files),
        variable_refs=set(refs),
        raw_variable_defaults=dict(merged_defaults),
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

    project_root = _try_infer_project_root_from_ui_source_dir(Path(ui_source_dir))
    registry_index = (
        try_load_auto_custom_variable_registry_index_from_project_root(project_root=project_root)
        if project_root is not None
        else None
    )

    raw_dump_object = {"4": payload_root}
    if registry_index is None:
        defaults_report = ensure_custom_variables_from_variable_defaults(
            raw_dump_object,
            variable_defaults=dict(scan.normalized_variable_defaults),
        )
        placeholders_report = ensure_text_placeholder_referenced_custom_variables(
            raw_dump_object,
            variable_refs=set(scan.variable_refs),
            variable_defaults=dict(scan.normalized_variable_defaults),
        )
        registry_report: dict[str, Any] = {"applied": False, "reason": "registry_not_found"}
    else:
        # 注册表存在：以注册表声明为单一真源（类型/owner），UI 默认值仅作为 default_value 来源。
        registry_report = _ensure_ui_referenced_custom_variables_from_registry(
            payload_root=payload_root,
            ui_scan=scan,
            project_root=Path(project_root),
        )
        defaults_report = {"applied": False, "reason": "skipped_by_registry"}
        placeholders_report = {"applied": False, "reason": "skipped_by_registry"}
    return {
        "applied": True,
        "ui_source_dir": str(Path(ui_source_dir).resolve()),
        "html_files_total": int(len(scan.html_files)),
        "html_files": [str(p) for p in scan.html_files],
        "placeholder_variable_refs_total": int(len(scan.variable_refs)),
        "variable_defaults_total": int(len(scan.normalized_variable_defaults)),
        "registry_sync_report": dict(registry_report),
        "variable_defaults_created_custom_variables_report": dict(defaults_report),
        "text_placeholder_created_custom_variables_report": dict(placeholders_report),
    }


__all__ = [
    "apply_ui_placeholder_custom_variables_to_payload_root",
    "scan_ui_html_files_for_placeholder_variable_refs_and_defaults",
    "scan_ui_source_dir_for_placeholder_variable_refs_and_defaults",
    "try_infer_project_ui_source_dir_from_any_path",
    "UiHtmlPlaceholderScanResult",
]

