from __future__ import annotations

"""UI HTML bundle 导入器（运行时缓存链路，**不落资源库**）。

定位：
- HTML 本体存放在项目存档目录（建议：管理配置/UI源码/）。
- 私有扩展负责把 HTML 转成 bundle（layout + templates 等）。
- 本模块负责把 bundle 写入运行时缓存（`app/runtime/cache/ui_artifacts/...`），供预览/工具链使用。

约束：
- 不依赖私有实现；不引入 PyQt6（由调用方负责在 UI 线程调度）。
- 不使用 try/except 吞错：转换/导入失败直接抛出，便于定位问题。
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from engine.utils.cache.cache_paths import get_ui_html_bundle_cache_dir
from engine.utils.cache.cache_paths import get_ui_states_cache_dir
from engine.utils.resource_library_layout import get_packages_root_dir


@dataclass(frozen=True, slots=True)
class UiHtmlImportSummary:
    source_html_relpath: str
    layout_id: str
    template_ids: list[str]
    template_count: int
    widget_count: int
    cache_file: str


def _hash8(text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return digest[:8]


def _iter_templates_payload(bundle_payload: dict) -> list[dict]:
    raw = bundle_payload.get("templates", None)
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        # dict 形式无稳定顺序，按 key 排序以保证导入结果稳定
        items: list[dict] = []
        for key in sorted(raw.keys(), key=lambda v: str(v).casefold()):
            value = raw.get(key)
            if isinstance(value, dict):
                items.append(value)
        return items
    return []


def _iter_widget_payloads_from_bundle(bundle_payload: dict) -> list[dict[str, Any]]:
    templates_payload_list = _iter_templates_payload(bundle_payload)
    out: list[dict[str, Any]] = []
    for t in templates_payload_list:
        widgets_value = t.get("widgets", [])
        if not isinstance(widgets_value, list):
            continue
        for w in widgets_value:
            if isinstance(w, dict):
                out.append(w)
    return out


def _build_ui_states_payload_from_bundle(
    *,
    workspace_root: Path,
    package_id: str,
    source_html_relpath: str,
    layout_id: str,
    layout_name: str,
    bundle_payload: dict,
) -> dict[str, Any]:
    """
    从 Workbench bundle JSON 的 widgets 中抽取 UI 多状态信息（__ui_state_*），输出结构化映射。

    目的：
    - 让节点图作者不再手工维护“状态名 -> ui_key 列表/字典”，而是从缓存产物中查阅/复制。
    - 该文件属于运行时缓存（不落资源库），与 ui_guid_registry/ui_actions 同级。
    """
    # group -> state -> entry
    groups: dict[str, dict[str, dict[str, Any]]] = {}
    for w in _iter_widget_payloads_from_bundle(bundle_payload):
        group = str(w.get("__ui_state_group") or "").strip()
        if group == "":
            continue
        state = str(w.get("__ui_state") or "").strip()
        is_default = bool(w.get("__ui_state_default"))
        ui_key = str(w.get("ui_key") or "").strip()
        if ui_key == "":
            ui_key = str(w.get("widget_id") or "").strip()
        if ui_key == "":
            continue

        by_state = groups.get(group)
        if by_state is None:
            by_state = {}
            groups[group] = by_state
        entry = by_state.get(state)
        if entry is None:
            entry = {
                "state": state,
                "is_default": False,
                "ui_keys": [],
            }
            by_state[state] = entry
        if is_default:
            entry["is_default"] = True
        ui_keys = entry.get("ui_keys")
        if isinstance(ui_keys, list) and ui_key not in ui_keys:
            ui_keys.append(ui_key)

    # 稳定排序：便于 diff 与复制
    groups_out: list[dict[str, Any]] = []
    for group_name in sorted(groups.keys(), key=lambda x: str(x).casefold()):
        by_state = groups[group_name]
        states_out: list[dict[str, Any]] = []
        for state_name in sorted(by_state.keys(), key=lambda x: str(x).casefold()):
            entry = by_state[state_name]
            ui_keys = entry.get("ui_keys")
            if isinstance(ui_keys, list):
                ui_keys.sort(key=lambda x: str(x).casefold())
            states_out.append(entry)
        groups_out.append({"group": group_name, "states": states_out})

    return {
        "version": 1,
        "package_id": str(package_id),
        "source_html": str(source_html_relpath),
        "layout_id": str(layout_id),
        "layout_name": str(layout_name),
        "ui_state_groups": groups_out,
        "note": (
            "本文件由 UI HTML bundle 导入链路自动生成：用于汇总 UI 多状态（data-ui-state-* -> __ui_state_*）的 ui_key 列表，"
            "便于节点图侧做互斥显隐切换。该文件属于运行时缓存（不落资源库）。"
        ),
        "cache_root_hint": str(get_ui_states_cache_dir(workspace_root, package_id).parent),
    }


def apply_ui_html_bundle_to_resource_manager(
    *,
    resource_manager: object,
    package_id: str,
    source_html_file: Path,
    bundle_payload: dict,
    layout_name: str | None = None,
) -> UiHtmlImportSummary:
    """将 bundle 写入运行时缓存（不落资源库，不依赖 PackageController）。"""
    if not isinstance(bundle_payload, dict):
        raise ValueError("bundle_payload 必须为 dict")

    package_id_text = str(package_id or "").strip()
    if not package_id_text or package_id_text in {"global_view", "unclassified_view"}:
        raise ValueError("package_id 无效，无法导入 UI bundle")

    resource_library_root: Path = getattr(resource_manager, "resource_library_dir", None)
    if not isinstance(resource_library_root, Path):
        raise RuntimeError("resource_manager.resource_library_dir 缺失或不是 Path")
    packages_root = get_packages_root_dir(resource_library_root)
    package_root_dir = (packages_root / package_id_text).resolve()

    source_abs = Path(source_html_file).resolve()
    if not source_abs.exists() or not source_abs.is_file():
        raise RuntimeError(f"HTML 文件不存在或不是文件：{source_abs}")
    source_mtime = float(source_abs.stat().st_mtime)

    source_parts = source_abs.parts
    root_parts = package_root_dir.parts
    if len(source_parts) < len(root_parts) or source_parts[: len(root_parts)] != root_parts:
        raise RuntimeError(
            f"HTML 文件不属于当前项目存档目录：{source_abs} (package_root={package_root_dir})"
        )
    source_html_relpath = Path(*source_parts[len(root_parts) :]).as_posix()

    source_key = f"{package_id_text}:{source_html_relpath}"
    layout_id = f"layout_html__{_hash8(source_key)}"

    now = bundle_payload.get("_imported_at") or ""  # 允许私有扩展注入时间戳
    if not isinstance(now, str) or not now.strip():
        from datetime import datetime

        now = datetime.now().isoformat()

    desired_layout_name = str(layout_name or "").strip()
    if not desired_layout_name:
        bundle_layout = bundle_payload.get("layout", None)
        if isinstance(bundle_layout, dict):
            desired_layout_name = str(
                bundle_layout.get("layout_name", "") or bundle_layout.get("name", "") or ""
            ).strip()
    if not desired_layout_name:
        desired_layout_name = Path(source_html_relpath).stem or "HTML导入_界面布局"

    templates_payload_list = _iter_templates_payload(bundle_payload)
    template_ids: list[str] = []
    widget_count = 0
    for t in templates_payload_list:
        tid = str(t.get("template_id") or "").strip()
        if tid:
            template_ids.append(tid)
        widgets_value = t.get("widgets", [])
        if isinstance(widgets_value, list):
            widget_count += len([w for w in widgets_value if isinstance(w, dict)])

    workspace_root = getattr(resource_manager, "workspace_path", None)
    if not isinstance(workspace_root, Path):
        raise RuntimeError("resource_manager.workspace_path 缺失或不是 Path")

    cache_dir = get_ui_html_bundle_cache_dir(workspace_root, package_id_text).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = (cache_dir / f"{layout_id}.ui_bundle.json").resolve()

    cache_payload: dict[str, Any] = {
        "version": 1,
        "package_id": package_id_text,
        "source_html": source_html_relpath,
        "layout_id": layout_id,
        "layout_name": str(desired_layout_name),
        "bundle": dict(bundle_payload),
        "created_at": now,
        "updated_at": now,
        "extra": {
            "__source_html_relpath": source_html_relpath,
            "__source_html_mtime": float(source_mtime),
        },
    }
    cache_file.write_text(json.dumps(cache_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # UI 多状态映射：写入运行时缓存（不落资源库）
    # 说明：
    # - Workbench 导出的 widgets 已包含 __ui_state_group/__ui_state/__ui_state_default
    # - 节点图作者可从该文件复制生成“状态 -> ui_key”映射，避免手工维护易错字典
    ui_states_dir = get_ui_states_cache_dir(workspace_root, package_id_text).resolve()
    ui_states_dir.mkdir(parents=True, exist_ok=True)
    ui_states_file = (ui_states_dir / f"{layout_id}.ui_states.json").resolve()
    ui_states_payload = _build_ui_states_payload_from_bundle(
        workspace_root=workspace_root,
        package_id=package_id_text,
        source_html_relpath=source_html_relpath,
        layout_id=layout_id,
        layout_name=str(desired_layout_name),
        bundle_payload=bundle_payload,
    )
    ui_states_file.write_text(json.dumps(ui_states_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return UiHtmlImportSummary(
        source_html_relpath=source_html_relpath,
        layout_id=layout_id,
        template_ids=template_ids,
        template_count=len(templates_payload_list),
        widget_count=int(widget_count),
        cache_file=str(cache_file),
    )


def apply_ui_html_bundle_to_current_package(
    *,
    package_controller: object,
    source_html_file: Path,
    bundle_payload: dict,
    layout_name: str | None = None,
) -> UiHtmlImportSummary:
    """将 bundle 写入当前项目存档的运行时缓存（不落资源库）。"""
    if not isinstance(bundle_payload, dict):
        raise ValueError("bundle_payload 必须为 dict")

    resource_manager = getattr(package_controller, "resource_manager", None)
    if resource_manager is None:
        raise RuntimeError("package_controller 缺少 resource_manager，无法导入 UI bundle")

    current_package_id = str(getattr(package_controller, "current_package_id", "") or "").strip()
    if not current_package_id or current_package_id in {"global_view", "unclassified_view"}:
        raise RuntimeError("当前未选择项目存档（或处于共享视图），无法导入 UI bundle")

    return apply_ui_html_bundle_to_resource_manager(
        resource_manager=resource_manager,
        package_id=current_package_id,
        source_html_file=source_html_file,
        bundle_payload=bundle_payload,
        layout_name=layout_name,
    )


__all__ = [
    "UiHtmlImportSummary",
    "apply_ui_html_bundle_to_resource_manager",
    "apply_ui_html_bundle_to_current_package",
]

