from __future__ import annotations

"""server_查询节点的实现（shared helpers）。

注意：
- 本模块仅提供 helper，不包含 `@node_spec` 节点实现；
- 禁止在导入时读取外部资源（仅允许在函数调用时按需读取）。
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from engine.configs.settings import settings


@dataclass(frozen=True, slots=True)
class UiClickActionRecord:
    guid: int
    ui_key: str
    widget_name: str
    action_key: str
    action_args: str


_UI_ACTIONS_CACHE: Dict[str, Tuple[float, Dict[int, UiClickActionRecord]]] = {}


def _get_workspace_root() -> Path:
    workspace_root = getattr(settings, "_workspace_root", None)
    if not isinstance(workspace_root, Path):
        raise ValueError("workspace_root 未注入：请先在入口调用 Settings.set_config_path(workspace_path)")
    return workspace_root


def _get_last_opened_package_id(workspace_root: Path) -> str:
    package_state_path = workspace_root / "app" / "runtime" / "package_state.json"
    payload = json.loads(package_state_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("package_state.json 结构不合法：期望 dict")
    package_id = payload.get("last_opened_package_id")
    if not isinstance(package_id, str) or not package_id.strip():
        raise ValueError("package_state.json 缺少 last_opened_package_id 或为空")
    return package_id.strip()


def _resolve_latest_ui_actions_file(workspace_root: Path, package_id: str) -> Path:
    from engine.utils.cache.cache_paths import get_ui_actions_cache_dir

    folder = get_ui_actions_cache_dir(workspace_root, package_id).resolve()
    candidates = [p for p in folder.glob("*.ui_actions.json") if p.is_file()]
    if not candidates:
        raise ValueError(f"未找到 UI交互映射 文件：{folder}")
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def load_ui_click_actions_by_guid(*, ui_actions_file_path: Path) -> Dict[int, UiClickActionRecord]:
    """读取并缓存 `*.ui_actions.json`，返回 guid -> record 的映射。"""

    cache_key = str(ui_actions_file_path.resolve())
    mtime = ui_actions_file_path.stat().st_mtime
    cached = _UI_ACTIONS_CACHE.get(cache_key)
    if cached is not None:
        cached_mtime, cached_mapping = cached
        if cached_mtime == mtime:
            return cached_mapping

    payload = json.loads(ui_actions_file_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("ui_actions.json 结构不合法：期望 dict")
    click_actions = payload.get("click_actions")
    if not isinstance(click_actions, list):
        raise ValueError("ui_actions.json 结构不合法：缺少 click_actions list")

    mapping: Dict[int, UiClickActionRecord] = {}
    for item in click_actions:
        if not isinstance(item, dict):
            continue
        guid = item.get("guid")
        if not isinstance(guid, int):
            continue

        ui_key = item.get("ui_key")
        widget_name = item.get("widget_name")
        action_key = item.get("action_key")
        action_args = item.get("action_args")
        if not isinstance(ui_key, str):
            ui_key = ""
        if not isinstance(widget_name, str):
            widget_name = ""
        if not isinstance(action_key, str):
            action_key = ""
        if not isinstance(action_args, str):
            action_args = ""

        mapping[int(guid)] = UiClickActionRecord(
            guid=int(guid),
            ui_key=ui_key.strip(),
            widget_name=widget_name.strip(),
            action_key=action_key.strip(),
            action_args=action_args.strip(),
        )

    _UI_ACTIONS_CACHE[cache_key] = (mtime, mapping)
    return mapping


def resolve_ui_click_action_record_for_current_package(*, source_guid: int) -> UiClickActionRecord | None:
    """按“当前打开的项目存档”解析事件源GUID对应的 UI 动作记录。"""

    workspace_root = _get_workspace_root()
    package_id = _get_last_opened_package_id(workspace_root)
    ui_actions_file = _resolve_latest_ui_actions_file(workspace_root, package_id)
    mapping = load_ui_click_actions_by_guid(ui_actions_file_path=ui_actions_file)
    return mapping.get(int(source_guid))