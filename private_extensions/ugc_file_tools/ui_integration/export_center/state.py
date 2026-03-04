from __future__ import annotations

from pathlib import Path


def _export_center_state_file_path(*, workspace_root: Path) -> Path:
    cache_dir = (Path(workspace_root).resolve() / "app" / "runtime" / "cache").resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return (cache_dir / "ugc_file_tools_export_center_state.json").resolve()


_EXPORT_CENTER_ALLOWED_FORMATS: frozenset[str] = frozenset({"gia", "gil", "repair_signals", "merge_signal_entries"})


def _load_export_center_state(*, workspace_root: Path) -> dict[str, object]:
    state_path = _export_center_state_file_path(workspace_root=Path(workspace_root))
    if not state_path.is_file():
        return {}
    import json

    text = state_path.read_text(encoding="utf-8").strip()
    if text == "":
        return {}
    obj = json.loads(text)
    return obj if isinstance(obj, dict) else {}


def _save_export_center_state(*, workspace_root: Path, state: dict[str, object]) -> None:
    state_path = _export_center_state_file_path(workspace_root=Path(workspace_root))
    payload = dict(state or {})
    import json

    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _update_export_center_state(*, workspace_root: Path, updates: dict[str, str]) -> None:
    """
    以“合并更新”的方式写入导出中心 state，避免后写入的字段覆盖掉其它字段。
    """
    state = _load_export_center_state(workspace_root=Path(workspace_root))
    for k, v in dict(updates or {}).items():
        kk = str(k or "").strip()
        vv = str(v or "").strip()
        if kk == "" or vv == "":
            continue
        state[kk] = vv
    _save_export_center_state(workspace_root=Path(workspace_root), state=state)


def _update_export_center_state_obj(*, workspace_root: Path, updates: dict[str, object]) -> None:
    """
    以“合并更新”的方式写入导出中心 state（支持非字符串字段）。
    """
    state = _load_export_center_state(workspace_root=Path(workspace_root))
    for k, v in dict(updates or {}).items():
        kk = str(k or "").strip()
        if kk == "":
            continue
        state[kk] = v
    _save_export_center_state(workspace_root=Path(workspace_root), state=state)


def _load_last_base_gil_path(*, workspace_root: Path) -> str:
    obj = _load_export_center_state(workspace_root=Path(workspace_root))
    return str(obj.get("last_base_gil_path") or "").strip()


def _save_last_base_gil_path(*, workspace_root: Path, base_gil_path: Path | str) -> None:
    raw = str(base_gil_path or "").strip()
    if raw == "":
        return
    normalized = str(Path(raw).resolve())
    _update_export_center_state(
        workspace_root=Path(workspace_root),
        updates={"last_base_gil_path": normalized},
    )


def _load_last_base_player_template_gia_path(*, workspace_root: Path) -> str:
    obj = _load_export_center_state(workspace_root=Path(workspace_root))
    return str(obj.get("last_base_player_template_gia_path") or "").strip()


def _save_last_base_player_template_gia_path(*, workspace_root: Path, base_gia_path: Path | str) -> None:
    raw = str(base_gia_path or "").strip()
    if raw == "":
        return
    normalized = str(Path(raw).resolve())
    _update_export_center_state(
        workspace_root=Path(workspace_root),
        updates={"last_base_player_template_gia_path": normalized},
    )


def _load_last_use_builtin_empty_base_gil(*, workspace_root: Path) -> bool:
    obj = _load_export_center_state(workspace_root=Path(workspace_root))
    raw = obj.get("last_use_builtin_empty_base_gil")
    return bool(raw) if isinstance(raw, bool) else False


def _save_last_use_builtin_empty_base_gil(*, workspace_root: Path, enabled: bool) -> None:
    _update_export_center_state_obj(
        workspace_root=Path(workspace_root),
        updates={"last_use_builtin_empty_base_gil": bool(enabled)},
    )


def _load_last_export_format(*, workspace_root: Path) -> str:
    obj = _load_export_center_state(workspace_root=Path(workspace_root))
    raw = str(obj.get("last_format") or "").strip()
    if raw not in _EXPORT_CENTER_ALLOWED_FORMATS:
        return ""
    return raw


def _save_last_export_format(*, workspace_root: Path, export_format: str) -> None:
    fmt = str(export_format or "").strip()
    if fmt not in _EXPORT_CENTER_ALLOWED_FORMATS:
        return
    _update_export_center_state(
        workspace_root=Path(workspace_root),
        updates={"last_format": fmt},
    )


def _load_last_repair_input_gil_path(*, workspace_root: Path) -> str:
    obj = _load_export_center_state(workspace_root=Path(workspace_root))
    return str(obj.get("last_repair_input_gil_path") or "").strip()


def _save_last_repair_input_gil_path(*, workspace_root: Path, input_gil_path: Path | str) -> None:
    raw = str(input_gil_path or "").strip()
    if raw == "":
        return
    normalized = str(Path(raw).resolve())
    _update_export_center_state(
        workspace_root=Path(workspace_root),
        updates={"last_repair_input_gil_path": normalized},
    )


def _load_last_resource_picker_expanded_node_ids(*, workspace_root: Path) -> list[str]:
    """
    资源选择器（左侧树）的“展开状态”持久化。

    语义：仅保存可展开节点（分类/来源/目录）的稳定 node_id 列表。
    """
    obj = _load_export_center_state(workspace_root=Path(workspace_root))
    raw = obj.get("resource_picker_expanded_node_ids")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for x in raw:
        s = str(x or "").strip()
        if s == "":
            continue
        out.append(s)
    # 去重并稳定排序
    seen: set[str] = set()
    dedup: list[str] = []
    for s in out:
        if s in seen:
            continue
        seen.add(s)
        dedup.append(s)
    dedup.sort(key=lambda t: t.casefold())
    return dedup


def _save_last_resource_picker_expanded_node_ids(*, workspace_root: Path, node_ids: list[str]) -> None:
    ids: list[str] = []
    for x in list(node_ids or []):
        s = str(x or "").strip()
        if s == "":
            continue
        ids.append(s)
    # 去重并稳定排序
    seen: set[str] = set()
    dedup: list[str] = []
    for s in ids:
        if s in seen:
            continue
        seen.add(s)
        dedup.append(s)
    dedup.sort(key=lambda t: t.casefold())
    _update_export_center_state_obj(
        workspace_root=Path(workspace_root),
        updates={"resource_picker_expanded_node_ids": dedup},
    )

