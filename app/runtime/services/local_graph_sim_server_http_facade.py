from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.runtime.services.local_graph_sim_observability import (
    build_session_snapshot,
    diff_json,
    json_safe,
    summarize_changes,
)
from app.runtime.services.local_graph_sim_server_web_assets import get_local_sim_flatten_overlay_module_file


@dataclass(frozen=True, slots=True)
class HttpStaticBytesResult:
    ok: bool
    status: int
    message: str
    data: bytes
    content_type: str


@dataclass(frozen=True, slots=True)
class LocalGraphSimHttpFacade:
    """
    HTTP 层的稳定门面：将 BaseHTTPRequestHandler 与 LocalGraphSimServer/Session 的耦合收敛到单点。

    约束：
    - RequestHandler 不应直接访问 server 的私有字段（如 `_lock/_config/_clock/_capture_*`）。
    - 领域逻辑与 IO（导出复现包等）集中在本门面，便于后续隔离测试与替换 HTTP 实现。
    """

    server: Any

    # ------------------------------ static assets / html
    def read_flatten_overlay_module_text(self) -> str:
        p = get_local_sim_flatten_overlay_module_file()
        if not p.is_file():
            return ""
        return p.read_text(encoding="utf-8")

    @staticmethod
    def inject_flatten_overlay_module(html_text: str) -> str:
        text = str(html_text or "")
        injection = '\n<script type="module" src="/local_sim_flatten_overlay.mjs"></script>\n'
        marker = "</body>"
        if marker in text:
            return text.replace(marker, injection + marker, 1)
        return text + injection

    def get_ui_html_payload(self, *, entry_ui_html_file: Path, layout_index: int, flatten_enabled: bool) -> str:
        html_file = Path(entry_ui_html_file)
        if int(layout_index) != 0:
            candidate = self.server.get_layout_html_file(int(layout_index))
            if candidate is not None:
                html_file = Path(candidate)
                self.server.set_current_layout_index(int(layout_index))

        text = html_file.read_text(encoding="utf-8")
        from app.runtime.services.local_graph_sim_server_html import _inject_local_sim_script

        injected = _inject_local_sim_script(text)
        if bool(flatten_enabled):
            injected = self.inject_flatten_overlay_module(injected)
        return injected

    def read_ui_workbench_static_bytes(self, *, url_path: str, entry_ui_html_file: Path) -> HttpStaticBytesResult:
        """
        提供 `assets/ui_workbench/` 下的静态资源（仅供本地测试扁平化预览使用）。
        返回结构化结果（不抛异常），供 HTTP handler 决定 send_error/发送 body。
        """
        workspace_root = self.server.get_workspace_root() if hasattr(self.server, "get_workspace_root") else None

        def _find_repo_root_from(start: Path) -> Path | None:
            here = Path(start).resolve()
            for parent in [here, *list(here.parents)]:
                if (parent / "assets").is_dir() and (parent / "app").is_dir() and (parent / "engine").is_dir():
                    return parent
            return None

        ws: Path | None = None
        if workspace_root is not None:
            ws = Path(workspace_root).resolve()
        else:
            # 兼容“未传 workspace_root”的启动方式：从 entry_ui_html_file 向上推断仓库根目录
            ws = _find_repo_root_from(Path(entry_ui_html_file))
        if ws is None:
            return HttpStaticBytesResult(
                ok=False,
                status=404,
                message="workspace_root not set and repo_root not found",
                data=b"",
                content_type="text/plain; charset=utf-8",
            )
        root_dir = (ws / "assets" / "ui_workbench").resolve()
        if not root_dir.is_dir():
            return HttpStaticBytesResult(
                ok=False,
                status=404,
                message="ui_workbench dir not found",
                data=b"",
                content_type="text/plain; charset=utf-8",
            )

        prefix = "/__ui_workbench__/"
        rel = str(url_path or "")
        if not rel.startswith(prefix):
            return HttpStaticBytesResult(
                ok=False,
                status=404,
                message="Not Found",
                data=b"",
                content_type="text/plain; charset=utf-8",
            )
        rel = rel[len(prefix) :]
        rel = rel.replace("\\", "/").lstrip("/")
        if not rel:
            return HttpStaticBytesResult(
                ok=False,
                status=404,
                message="Not Found",
                data=b"",
                content_type="text/plain; charset=utf-8",
            )

        parts = [p for p in rel.split("/") if p]
        for p in parts:
            if p in {".", ".."}:
                return HttpStaticBytesResult(
                    ok=False,
                    status=400,
                    message="invalid path",
                    data=b"",
                    content_type="text/plain; charset=utf-8",
                )

        file_path = (root_dir / Path(*parts)).resolve()
        if not _is_under_directory(file_path, root_dir):
            return HttpStaticBytesResult(
                ok=False,
                status=403,
                message="Forbidden",
                data=b"",
                content_type="text/plain; charset=utf-8",
            )
        if not file_path.is_file():
            return HttpStaticBytesResult(
                ok=False,
                status=404,
                message="Not Found",
                data=b"",
                content_type="text/plain; charset=utf-8",
            )

        data = file_path.read_bytes()
        content_type = _guess_content_type(file_path)
        return HttpStaticBytesResult(ok=True, status=200, message="OK", data=data, content_type=content_type)

    # ------------------------------ api: status/trace/entities/snapshot
    def build_status_payload(self, *, entry_ui_html_file: Path) -> dict[str, Any]:
        session = self.server.session
        cur_idx = self.server.current_layout_index
        cur_file = self.server.get_layout_html_file(cur_idx) or Path(entry_ui_html_file)

        graphs_payload: list[dict[str, Any]] = []
        mounted = getattr(session, "mounted_graphs", None)
        if isinstance(mounted, list) and mounted:
            for g in mounted:
                graphs_payload.append(
                    {
                        "graph_name": str(getattr(g, "graph_name", "")),
                        "graph_type": str(getattr(g, "graph_type", "")),
                        "graph_code_file": str(getattr(g, "graph_code_file", "")),
                        "owner_entity_id": str(getattr(g, "owner_entity_id", "")),
                        "owner_entity_name": str(getattr(g, "owner_entity_name", "")),
                    }
                )
        else:
            graphs_payload.append(
                {
                    "graph_name": session.graph_name,
                    "graph_type": session.graph_type,
                    "graph_code_file": str(session.graph_code_file),
                    "owner_entity_id": str(getattr(session.owner_entity, "entity_id", "")),
                    "owner_entity_name": str(getattr(session.owner_entity, "name", "")),
                }
            )

        players_payload: list[dict[str, Any]] = []
        for p in session.game.get_present_player_entities():
            players_payload.append({"entity_id": str(getattr(p, "entity_id", "")), "name": str(getattr(p, "name", ""))})

        validation_report = self.server.get_last_validation_report() if hasattr(self.server, "get_last_validation_report") else None
        validation_summary = None
        if isinstance(validation_report, dict):
            validation_summary = validation_report.get("summary")

        payload = {
            "ok": True,
            "graph": {
                "graph_name": session.graph_name,
                "graph_type": session.graph_type,
                "graph_code_file": str(session.graph_code_file),
                "active_package_id": getattr(session, "active_package_id", None),
                "workspace_root": str(getattr(session, "workspace_root", "")),
            },
            "graphs": graphs_payload,
            "players": players_payload,
            "default_player_entity_id": str(getattr(getattr(session, "player_entity", None), "entity_id", "")),
            "ui": {
                "ui_html_file": str(entry_ui_html_file),
                "current_layout_index": int(cur_idx),
                "current_ui_html_file": str(cur_file),
                "layouts": self.server.get_all_layouts(),
            },
            "server": {
                "host": str(self.server.get_host()),
                "port": int(getattr(self.server, "port", 0)),
                "auto_emit_signal_id": str(self.server.get_auto_emit_signal_id()),
                "auto_emit_signal_pending": bool(self.server.is_auto_emit_signal_pending()),
                "paused": bool(self.server.is_paused()),
                "sim_time": float(self.server.get_sim_time()),
            },
            "sim_notes": json_safe(getattr(session, "sim_notes", {})),
            "validation": {"has_report": bool(validation_report), "summary": json_safe(validation_summary)},
        }
        return payload

    def build_trace_payload(self, *, since: int) -> dict[str, Any]:
        session = self.server.session
        events = session.game.trace_recorder.as_list()
        since2 = max(0, int(since))
        out: list[dict[str, Any]] = []
        for ev in events[since2:]:
            if hasattr(ev, "to_dict"):
                out.append(json_safe(ev.to_dict()))
            else:
                out.append(json_safe(ev))
        return {"ok": True, "since": int(since2), "next": int(len(events)), "events": out}

    def build_entities_payload(self) -> dict[str, Any]:
        session = self.server.session
        game = session.game

        entities: list[dict[str, Any]] = []
        for entity_id, ent in game.entities.items():
            entities.append(
                {
                    "entity_id": str(entity_id),
                    "name": str(getattr(ent, "name", "")),
                    "position": list(getattr(ent, "position", [])),
                    "rotation": list(getattr(ent, "rotation", [])),
                }
            )
        entities.sort(key=lambda x: (x.get("name", ""), x.get("entity_id", "")))

        attached_graphs: dict[str, list[str]] = {}
        raw_attached = getattr(game, "attached_graphs", None)
        if isinstance(raw_attached, dict):
            for entity_id, graphs in raw_attached.items():
                items: list[str] = []
                if isinstance(graphs, list):
                    for inst in graphs:
                        items.append(str(getattr(getattr(inst, "__class__", None), "__name__", "Graph")))
                attached_graphs[str(entity_id)] = items

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

        payload = {
            "ok": True,
            "entities": entities,
            "custom_variables": json_safe(game.custom_variables),
            "graph_variables": json_safe(game.graph_variables),
            "local_variables": json_safe(game.local_variables),
            "attached_graphs": json_safe(attached_graphs),
            "mounted_graphs": json_safe(mounted_graphs_payload),
            "ui_current_layout_by_player": json_safe(game.ui_current_layout_by_player),
            "ui_widget_state_by_player": json_safe(game.ui_widget_state_by_player),
            "ui_active_groups_by_player": json_safe({k: sorted(list(v)) for k, v in game.ui_active_groups_by_player.items()}),
        }
        return payload

    def build_snapshot_payload(self, *, include_entities: bool) -> dict[str, Any]:
        with self.server.locked():
            session = self.server.session
            snap = build_session_snapshot(session, include_entities=bool(include_entities))
        return {"ok": True, "snapshot": json_safe(snap)}

    # ------------------------------ api: patches / control
    def drain_bootstrap_patches(self) -> list[dict[str, Any]]:
        with self.server.locked():
            patches = self.server.drain_bootstrap_patches()
            self.server.capture_layout_switch_from_patches(patches)
        return list(patches)

    def build_sync_payload(self) -> dict[str, Any]:
        with self.server.locked():
            session = self.server.session
            game = session.game
            patches: list[dict[str, Any]] = []

            layout_index = int(self.server.current_layout_index)
            if layout_index:
                patches.append({"op": "switch_layout", "layout_index": int(layout_index)})

            for player_id, groups in sorted(game.ui_active_groups_by_player.items(), key=lambda kv: str(kv[0])):
                for group_index in sorted(groups):
                    p: dict[str, Any] = {
                        "op": "activate_widget_group",
                        "player_id": str(player_id),
                        "group_index": int(group_index),
                    }
                    ui_key = session.ui_registry.try_get_key(int(group_index))
                    if ui_key:
                        p["ui_key"] = ui_key
                    patches.append(p)

            for player_id, states in sorted(game.ui_widget_state_by_player.items(), key=lambda kv: str(kv[0])):
                for widget_index, state in sorted(states.items(), key=lambda kv: (int(kv[0]), str(kv[1]))):
                    p = {
                        "op": "set_widget_state",
                        "player_id": str(player_id),
                        "widget_index": int(widget_index),
                        "state": str(state),
                    }
                    ui_key = session.ui_registry.try_get_key(int(widget_index))
                    if ui_key:
                        p["ui_key"] = ui_key
                        # UI_STATE_GROUP__<base_key>__<state>__group
                        if ui_key.startswith("UI_STATE_GROUP__"):
                            parts = ui_key.split("__")
                            if len(parts) >= 4:
                                p["ui_state_group_key"] = parts[1]
                                p["ui_state"] = parts[2]
                            # 与前端约定：state=界面控件组状态_开启 => visible=True
                            p["visible"] = str(state) == "界面控件组状态_开启"
                    patches.append(p)

        return {"ok": True, "current_layout_index": int(layout_index), "patches": patches}

    def poll(self) -> dict[str, Any]:
        """轮询：推进定时器 + drain UI patches + 回传 UI 绑定数据（用于倒计时等文本刷新）。"""
        with self.server.locked():
            session = self.server.session
            game = session.game

            paused = bool(self.server.is_paused())
            timer_fired = 0
            if not paused:
                sim_now = float(self.server.get_sim_time())
                timer_fired = int(game.tick(now=sim_now))
            patches = session.drain_ui_patches()

            lv: dict[str, Any] = {}
            root_entity_id = str(getattr(game, "ui_binding_root_entity_id", "") or "").strip()
            if root_entity_id:
                raw = game.custom_variables.get(root_entity_id, {})
                if isinstance(raw, dict):
                    lv = dict(raw)

        return {
            "ok": True,
            "paused": bool(paused),
            "timer_fired": int(timer_fired),
            "patches": patches,
            "bindings": {"lv": lv},
        }

    def pause(self, *, paused: bool) -> dict[str, Any]:
        with self.server.locked():
            self.server.set_paused(bool(paused))
            session = self.server.session
            session.game.record_trace_event(kind="control", message="pause" if paused else "resume", paused=bool(paused))
        return {"ok": True, "paused": bool(paused)}

    def pause_status(self) -> dict[str, Any]:
        paused = bool(self.server.is_paused())
        sim_now = float(self.server.get_sim_time())
        return {"ok": True, "paused": bool(paused), "sim_time": float(sim_now)}

    def step(self, *, dt: float) -> dict[str, Any]:
        paused = bool(self.server.is_paused())
        if not paused:
            return {"ok": False, "error": {"code": "not_paused", "message": "单步执行仅允许在暂停状态下使用"}}

        with self.server.locked():
            session = self.server.session
            self.server.advance_sim_time(float(dt))
            sim_now = float(self.server.get_sim_time())

            game = session.game
            timer_fired = int(game.tick(now=sim_now, max_fires=1))
            patches = session.drain_ui_patches()
            self.server.capture_layout_switch_from_patches(patches)

            lv: dict[str, Any] = {}
            root_entity_id = str(getattr(game, "ui_binding_root_entity_id", "") or "").strip()
            if root_entity_id:
                raw_lv = game.custom_variables.get(root_entity_id, {})
                if isinstance(raw_lv, dict):
                    lv = dict(raw_lv)

            session.game.record_trace_event(
                kind="control",
                message="step",
                dt=float(dt),
                sim_time=float(sim_now or 0.0),
                timer_fired=int(timer_fired),
                patch_count=int(len(patches)),
            )

        return {
            "ok": True,
            "paused": True,
            "dt": float(dt),
            "sim_time": float(sim_now or 0.0),
            "timer_fired": int(timer_fired),
            "patches": list(patches),
            "bindings": {"lv": lv},
        }

    # ------------------------------ api: actions / validate / export
    def get_last_action(self) -> dict[str, Any] | None:
        return self.server.get_last_action() if hasattr(self.server, "get_last_action") else None

    def get_last_validation_report(self) -> dict[str, Any] | None:
        return self.server.get_last_validation_report() if hasattr(self.server, "get_last_validation_report") else None

    def clear_trace(self) -> None:
        with self.server.locked():
            session = self.server.session
            session.game.trace_recorder.clear()

    def restart(self) -> None:
        self.server.restart()

    def validate_now(
        self,
        *,
        strict_entity_wire_only: bool = False,
        disable_cache: bool = False,
        disable_composite_struct_check: bool = False,
    ) -> dict[str, Any]:
        return self.server.validate_now(
            strict_entity_wire_only=bool(strict_entity_wire_only),
            disable_cache=bool(disable_cache),
            disable_composite_struct_check=bool(disable_composite_struct_check),
        )

    def export_repro(
        self,
        *,
        include_entities: bool,
        include_snapshot: bool,
        include_trace: bool,
        include_validation: bool,
        include_last_action: bool,
        recorded_actions: list[Any],
        note_text: str,
    ) -> dict[str, Any]:
        started = time.time()
        with self.server.locked():
            session = self.server.session

            snapshot = None
            if include_snapshot:
                snapshot = build_session_snapshot(session, include_entities=bool(include_entities))

            last_action = None
            if include_last_action:
                last_action = self.get_last_action()

            validation_report = None
            if include_validation and hasattr(self.server, "get_last_validation_report"):
                validation_report = self.server.get_last_validation_report()

            trace_events = None
            if include_trace:
                events = session.game.trace_recorder.as_list()
                out: list[dict[str, Any]] = []
                for ev in list(events or []):
                    if hasattr(ev, "to_dict"):
                        out.append(json_safe(ev.to_dict()))
                    else:
                        out.append(json_safe(ev))
                trace_events = out

            from engine.utils.cache.cache_paths import get_runtime_cache_root

            cache_root = get_runtime_cache_root(Path(session.workspace_root).resolve())
            out_dir = (cache_root / "local_graph_sim" / "repros").resolve()
            out_dir.mkdir(parents=True, exist_ok=True)

            graph_stem = Path(session.graph_code_file).stem
            graph_stem = re.sub(r"[^0-9a-zA-Z_\-\.]+", "_", str(graph_stem or "").strip()) or "graph"

            timestamp_ms = int(time.time() * 1000.0)
            export_id = f"{timestamp_ms}__{graph_stem}.local_sim.repro.json"
            export_file = (out_dir / export_id).resolve()

            export_payload: dict[str, Any] = {
                "version": 1,
                "generated_at": float(time.time()),
                "note": str(note_text or "").strip(),
                "graph": {
                    "graph_name": str(getattr(session, "graph_name", "")),
                    "graph_type": str(getattr(session, "graph_type", "")),
                    "graph_code_file": str(getattr(session, "graph_code_file", "")),
                    "active_package_id": getattr(session, "active_package_id", None),
                    "workspace_root": str(getattr(session, "workspace_root", "")),
                },
                "server": {
                    "host": str(self.server.get_host()),
                    "port": int(getattr(self.server, "port", 0)),
                },
                "includes": {
                    "include_entities": bool(include_entities),
                    "include_snapshot": bool(include_snapshot),
                    "include_trace": bool(include_trace),
                    "include_validation": bool(include_validation),
                    "include_last_action": bool(include_last_action),
                },
                "snapshot": json_safe(snapshot),
                "last_action": json_safe(last_action),
                "validation_report": json_safe(validation_report),
                "trace": json_safe(trace_events),
                "recorded_actions": json_safe(recorded_actions),
            }

            text = json.dumps(json_safe(export_payload), ensure_ascii=False, indent=2)
            export_file.write_text(text, encoding="utf-8")

            duration_ms = int((time.time() - started) * 1000.0)
            return {
                "ok": True,
                "export_id": str(export_id),
                "export_file": str(export_file),
                "bytes": int(len(text.encode("utf-8"))),
                "duration_ms": int(duration_ms),
                "download_url": f"/api/local_sim/export_repro?id={export_id}",
            }

    def export_repro_download_result(self, *, export_id: str) -> HttpStaticBytesResult:
        if not re.fullmatch(r"[0-9A-Za-z._\-]+\.json", str(export_id or "")):
            return HttpStaticBytesResult(
                ok=False,
                status=400,
                message="invalid id",
                data=b"",
                content_type="text/plain; charset=utf-8",
            )
        session = self.server.session
        from engine.utils.cache.cache_paths import get_runtime_cache_root

        cache_root = get_runtime_cache_root(Path(session.workspace_root).resolve())
        root_dir = (cache_root / "local_graph_sim" / "repros").resolve()
        file_path = (root_dir / str(export_id)).resolve()
        if not _is_under_directory(file_path, root_dir):
            return HttpStaticBytesResult(
                ok=False,
                status=403,
                message="Forbidden",
                data=b"",
                content_type="text/plain; charset=utf-8",
            )
        if not file_path.is_file():
            return HttpStaticBytesResult(
                ok=False,
                status=404,
                message="Not Found",
                data=b"",
                content_type="text/plain; charset=utf-8",
            )
        body = file_path.read_bytes()
        return HttpStaticBytesResult(
            ok=True,
            status=200,
            message="OK",
            data=body,
            content_type="application/json; charset=utf-8",
        )

    # ------------------------------ api: click / emit_signal
    def click(
        self,
        *,
        data_ui_key: str,
        data_ui_state_group: str,
        data_ui_state: str,
        player_entity_id: str,
        player_entity_name: str,
    ) -> dict[str, Any]:
        paused = bool(self.server.is_paused())
        if paused:
            return {
                "ok": False,
                "error": {"code": "paused", "message": "当前处于暂停状态：已冻结世界，click 被拒绝（可使用单步执行）"},
            }

        started = time.time()
        with self.server.locked():
            session = self.server.session
            player_entity = None
            if str(player_entity_id or "").strip():
                player_entity = session.game.get_entity(str(player_entity_id))
                if player_entity is None:
                    return {"ok": False, "error": {"code": "player_not_found", "message": f"player_entity_id 不存在: {player_entity_id}"}}
            elif str(player_entity_name or "").strip():
                player_entity = session.game.find_entity_by_name(str(player_entity_name))
                if player_entity is None:
                    return {
                        "ok": False,
                        "error": {"code": "player_not_found", "message": f"player_entity_name 不存在: {player_entity_name}"},
                    }

            before = build_session_snapshot(session, include_entities=False)
            chosen_ui_key = session.try_resolve_ui_click_ui_key(
                data_ui_key=str(data_ui_key or "").strip(),
                data_ui_state_group=str(data_ui_state_group or "").strip(),
                data_ui_state=str(data_ui_state or "").strip(),
                player_entity=player_entity,
            )
            if chosen_ui_key is None:
                return {
                    "ok": False,
                    "error": {
                        "code": "ui_key_unresolved",
                        "message": "无法解析 UI click 对应的 ui_key",
                        "data_ui_key": str(data_ui_key or "").strip(),
                        "data_ui_state_group": str(data_ui_state_group or "").strip(),
                        "data_ui_state": str(data_ui_state or "").strip(),
                    },
                }

            index = int(session.ui_registry.ensure(chosen_ui_key))
            patches = session.trigger_ui_click_index(index=index, player_entity=player_entity)
            self.server.capture_layout_switch_from_patches(patches)
            after = build_session_snapshot(session, include_entities=False)
            changes = diff_json(before, after)
            summary = summarize_changes(changes)
            duration_ms = int((time.time() - started) * 1000.0)

            action = {
                "kind": "ui_click",
                "input": {
                    "data_ui_key": str(data_ui_key or "").strip(),
                    "data_ui_state_group": str(data_ui_state_group or "").strip(),
                    "data_ui_state": str(data_ui_state or "").strip(),
                    "chosen_ui_key": str(chosen_ui_key),
                    "index": int(index),
                    "player_entity_id": str(getattr(player_entity, "entity_id", "")) if player_entity is not None else str(getattr(session.player_entity, "entity_id", "")),
                    "player_entity_name": str(getattr(player_entity, "name", "")) if player_entity is not None else str(getattr(session.player_entity, "name", "")),
                },
                "patches": list(patches),
                "diff_summary": summary,
                "diff_changes": [c.to_dict() for c in changes],
                "duration_ms": int(duration_ms),
                "timestamp": float(time.time()),
            }
            if hasattr(self.server, "set_last_action"):
                self.server.set_last_action(action)

            session.game.record_trace_event(
                kind="ui_click",
                message="ui_click",
                data_ui_key=str(data_ui_key or "").strip(),
                data_ui_state_group=str(data_ui_state_group or "").strip(),
                data_ui_state=str(data_ui_state or "").strip(),
                chosen_ui_key=str(chosen_ui_key),
                index=int(index),
                player_entity_id=str(getattr(player_entity, "entity_id", "")) if player_entity is not None else str(getattr(session.player_entity, "entity_id", "")),
                player_entity_name=str(getattr(player_entity, "name", "")) if player_entity is not None else str(getattr(session.player_entity, "name", "")),
                patch_count=len(patches),
                duration_ms=int(duration_ms),
                diff_summary=summary,
            )

        return {"ok": True, "patches": patches, "last_action": action}

    def emit_signal(self, *, signal_id: str, params: dict[str, Any]) -> dict[str, Any]:
        paused = bool(self.server.is_paused())
        if paused:
            return {
                "ok": False,
                "error": {"code": "paused", "message": "当前处于暂停状态：已冻结世界，emit_signal 被拒绝（可使用单步执行）"},
            }

        started = time.time()
        with self.server.locked():
            session = self.server.session
            from engine.signal.definition_repository import get_default_signal_repository

            repo = get_default_signal_repository()
            raw_id = str(signal_id or "").strip()
            resolved_signal_id = str(raw_id)
            meta = repo.get_payload(resolved_signal_id)
            if meta is None:
                resolved = repo.resolve_id_by_name(resolved_signal_id)
                if resolved:
                    resolved_signal_id = str(resolved)
                    meta = repo.get_payload(resolved_signal_id)
            if meta is None:
                return {"ok": False, "error": {"code": "unknown_signal", "message": f"未知 signal_id: {raw_id}"}, "signal_id": raw_id}

            before = build_session_snapshot(session, include_entities=False)
            patches = session.emit_signal(signal_id=resolved_signal_id, params=dict(params))
            self.server.capture_layout_switch_from_patches(patches)
            after = build_session_snapshot(session, include_entities=False)
            changes = diff_json(before, after)
            summary = summarize_changes(changes)
            duration_ms = int((time.time() - started) * 1000.0)

            action = {
                "kind": "emit_signal",
                "input": {"signal_id": raw_id, "resolved_signal_id": resolved_signal_id, "params": json_safe(params)},
                "patches": list(patches),
                "diff_summary": summary,
                "diff_changes": [c.to_dict() for c in changes],
                "duration_ms": int(duration_ms),
                "timestamp": float(time.time()),
            }
            if hasattr(self.server, "set_last_action"):
                self.server.set_last_action(action)

            session.game.record_trace_event(
                kind="emit_signal",
                message="emit_signal",
                signal_id=raw_id,
                resolved_signal_id=resolved_signal_id,
                params=json_safe(params),
                patch_count=len(patches),
                duration_ms=int(duration_ms),
                diff_summary=summary,
            )

        return {"ok": True, "patches": patches, "last_action": action}

    def resolve_ui_key(
        self,
        *,
        data_ui_key: str,
        data_ui_state_group: str,
        data_ui_state: str,
        player_entity_id: str,
        player_entity_name: str,
    ) -> dict[str, Any]:
        """
        解析浏览器侧 click payload（或直接传入完整 ui_key）为稳定 ui_key/index，但不执行事件。

        用途：
        - UI 合约检查：验证 HTML 的 data-ui-key / state_group / state 是否可解析到 registry；
        - 断言/用例：允许前端在不污染运行态的前提下做“可解析性检查”。
        """
        session = self.server.session
        player_entity = None
        if str(player_entity_id or "").strip():
            player_entity = session.game.get_entity(str(player_entity_id))
            if player_entity is None:
                return {"ok": False, "error": {"code": "player_not_found", "message": f"player_entity_id 不存在: {player_entity_id}"}}
        elif str(player_entity_name or "").strip():
            player_entity = session.game.find_entity_by_name(str(player_entity_name))
            if player_entity is None:
                return {
                    "ok": False,
                    "error": {"code": "player_not_found", "message": f"player_entity_name 不存在: {player_entity_name}"},
                }

        chosen_ui_key = session.try_resolve_ui_click_ui_key(
            data_ui_key=str(data_ui_key or "").strip(),
            data_ui_state_group=str(data_ui_state_group or "").strip(),
            data_ui_state=str(data_ui_state or "").strip(),
            player_entity=player_entity,
        )
        if chosen_ui_key is None:
            return {
                "ok": False,
                "error": {
                    "code": "ui_key_unresolved",
                    "message": "无法解析为已注册的 ui_key（registry 不包含对应 key）",
                    "data_ui_key": str(data_ui_key or "").strip(),
                    "data_ui_state_group": str(data_ui_state_group or "").strip(),
                    "data_ui_state": str(data_ui_state or "").strip(),
                },
            }

        index = int(session.ui_registry.ensure(str(chosen_ui_key)))
        return {
            "ok": True,
            "input": {
                "data_ui_key": str(data_ui_key or "").strip(),
                "data_ui_state_group": str(data_ui_state_group or "").strip(),
                "data_ui_state": str(data_ui_state or "").strip(),
                "player_entity_id": str(getattr(player_entity, "entity_id", "")) if player_entity is not None else "",
                "player_entity_name": str(getattr(player_entity, "name", "")) if player_entity is not None else "",
            },
            "resolved": {
                "chosen_ui_key": str(chosen_ui_key),
                "index": int(index),
            },
        }


def _is_under_directory(child: Path, parent: Path) -> bool:
    child_parts = Path(child).resolve().parts
    parent_parts = Path(parent).resolve().parts
    if len(child_parts) < len(parent_parts):
        return False
    return child_parts[: len(parent_parts)] == parent_parts


def _guess_content_type(path: Path) -> str:
    ext = str(path.suffix or "").lower()
    if ext in {".js", ".mjs"}:
        return "text/javascript; charset=utf-8"
    if ext == ".css":
        return "text/css; charset=utf-8"
    if ext in {".html", ".htm"}:
        return "text/html; charset=utf-8"
    if ext == ".json":
        return "application/json; charset=utf-8"
    if ext == ".map":
        return "application/json; charset=utf-8"
    if ext == ".svg":
        return "image/svg+xml"
    if ext == ".png":
        return "image/png"
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext == ".gif":
        return "image/gif"
    if ext == ".webp":
        return "image/webp"
    return "application/octet-stream"

