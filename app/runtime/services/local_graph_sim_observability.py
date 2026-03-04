from __future__ import annotations

"""
Local Graph Sim 可观测性工具：
- runtime state snapshot（JSON-safe 的稳定结构）
- state diff（用于判断一次 click/signal 到底改变了什么）
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


def json_safe(value: Any) -> Any:
    """将运行时对象转换为 JSON 可序列化结构（用于本地测试/监控面板）。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    entity_id = getattr(value, "entity_id", None)
    name = getattr(value, "name", None)
    if entity_id is not None and name is not None:
        return {"__type": "entity", "entity_id": str(entity_id), "name": str(name)}
    return str(value)


def build_entities_payload(game: Any) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for entity_id, ent in getattr(game, "entities", {}).items():
        entities.append(
            {
                "entity_id": str(entity_id),
                "name": str(getattr(ent, "name", "")),
                "position": list(getattr(ent, "position", [])),
                "rotation": list(getattr(ent, "rotation", [])),
            }
        )
    entities.sort(key=lambda x: (x.get("name", ""), x.get("entity_id", "")))
    return entities


def build_attached_graphs_payload(game: Any) -> dict[str, list[str]]:
    attached_graphs: dict[str, list[str]] = {}
    raw_attached = getattr(game, "attached_graphs", None)
    if isinstance(raw_attached, dict):
        for entity_id, graphs in raw_attached.items():
            items: list[str] = []
            if isinstance(graphs, list):
                for inst in graphs:
                    items.append(str(getattr(getattr(inst, "__class__", None), "__name__", "Graph")))
            attached_graphs[str(entity_id)] = items
    return attached_graphs


def build_ui_payload(game: Any) -> dict[str, Any]:
    ui_active_groups_by_player = getattr(game, "ui_active_groups_by_player", {}) or {}
    if isinstance(ui_active_groups_by_player, dict):
        ui_active_groups_by_player = {k: sorted(list(v)) for k, v in ui_active_groups_by_player.items()}
    return {
        "ui_current_layout_by_player": json_safe(getattr(game, "ui_current_layout_by_player", {})),
        "ui_widget_state_by_player": json_safe(getattr(game, "ui_widget_state_by_player", {})),
        "ui_active_groups_by_player": json_safe(ui_active_groups_by_player),
        "ui_binding_root_entity_id": str(getattr(game, "ui_binding_root_entity_id", "") or ""),
        "ui_lv_defaults": json_safe(getattr(game, "ui_lv_defaults", {})),
    }


def build_session_snapshot(session: Any, *, include_entities: bool = True) -> dict[str, Any]:
    game = getattr(session, "game", None)
    if game is None:
        raise RuntimeError("session.game is missing")

    mounted_graphs_payload: list[dict[str, Any]] = []
    mounted = getattr(session, "mounted_graphs", None)
    if isinstance(mounted, list) and mounted:
        for g in mounted:
            mounted_graphs_payload.append(
                {
                    "graph_name": str(getattr(g, "graph_name", "")),
                    "graph_type": str(getattr(g, "graph_type", "")),
                    "graph_code_file": str(getattr(g, "graph_code_file", "")),
                    "owner_entity_id": str(getattr(g, "owner_entity_id", "")),
                    "owner_entity_name": str(getattr(g, "owner_entity_name", "")),
                }
            )

    payload: dict[str, Any] = {
        "graph": {
            "graph_name": str(getattr(session, "graph_name", "")),
            "graph_type": str(getattr(session, "graph_type", "")),
            "graph_code_file": str(getattr(session, "graph_code_file", "")),
            "active_package_id": getattr(session, "active_package_id", None),
        },
        "variables": {
            "custom_variables": json_safe(getattr(game, "custom_variables", {})),
            "graph_variables": json_safe(getattr(game, "graph_variables", {})),
            "local_variables": json_safe(getattr(game, "local_variables", {})),
        },
        "mounted_graphs": json_safe(mounted_graphs_payload),
        "ui": build_ui_payload(game),
        "sim_notes": json_safe(getattr(session, "sim_notes", {})),
    }

    if include_entities:
        payload["entities"] = build_entities_payload(game)
        payload["attached_graphs"] = json_safe(build_attached_graphs_payload(game))
    return payload


@dataclass(frozen=True, slots=True)
class DiffChange:
    op: str  # add|remove|replace
    path: str
    before: Any
    after: Any

    def to_dict(self) -> dict[str, Any]:
        return {"op": self.op, "path": self.path, "before": self.before, "after": self.after}


def _escape_path_token(token: str) -> str:
    # JSON Pointer style escaping
    return str(token).replace("~", "~0").replace("/", "~1")


def _join_path(parts: Iterable[str]) -> str:
    out = ""
    for p in parts:
        out += "/" + _escape_path_token(str(p))
    return out or "/"


def diff_json(
    before: Any,
    after: Any,
    *,
    max_changes: int = 2000,
    max_depth: int = 10,
) -> list[DiffChange]:
    changes: list[DiffChange] = []

    def walk(b: Any, a: Any, path_parts: list[str], depth: int) -> None:
        if len(changes) >= int(max_changes):
            return
        if depth > int(max_depth):
            if b != a:
                changes.append(DiffChange("replace", _join_path(path_parts), json_safe(b), json_safe(a)))
            return

        if b is a:
            return
        if type(b) != type(a):
            changes.append(DiffChange("replace", _join_path(path_parts), json_safe(b), json_safe(a)))
            return

        if isinstance(b, dict) and isinstance(a, dict):
            b_keys = set(str(k) for k in b.keys())
            a_keys = set(str(k) for k in a.keys())
            for k in sorted(b_keys - a_keys):
                changes.append(DiffChange("remove", _join_path([*path_parts, k]), json_safe(b.get(k)), None))
                if len(changes) >= int(max_changes):
                    return
            for k in sorted(a_keys - b_keys):
                changes.append(DiffChange("add", _join_path([*path_parts, k]), None, json_safe(a.get(k))))
                if len(changes) >= int(max_changes):
                    return
            for k in sorted(b_keys & a_keys):
                walk(b.get(k), a.get(k), [*path_parts, k], depth + 1)
            return

        if isinstance(b, list) and isinstance(a, list):
            if len(b) != len(a):
                changes.append(DiffChange("replace", _join_path(path_parts), json_safe(b), json_safe(a)))
                return
            for i in range(len(b)):
                walk(b[i], a[i], [*path_parts, str(i)], depth + 1)
            return

        if b != a:
            changes.append(DiffChange("replace", _join_path(path_parts), json_safe(b), json_safe(a)))

    walk(before, after, [], 0)
    return changes


def summarize_changes(changes: list[DiffChange]) -> dict[str, Any]:
    add = sum(1 for c in changes if c.op == "add")
    remove = sum(1 for c in changes if c.op == "remove")
    replace = sum(1 for c in changes if c.op == "replace")
    return {
        "total": int(len(changes)),
        "add": int(add),
        "remove": int(remove),
        "replace": int(replace),
    }

