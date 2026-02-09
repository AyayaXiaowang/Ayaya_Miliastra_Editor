from __future__ import annotations

import http.server
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from app.runtime.services.local_graph_sim_server_html import _inject_local_sim_script, _parse_int
from app.runtime.services.local_graph_sim_server_web_assets import read_local_sim_js_text, read_monitor_html_text


def _json_safe(value: Any) -> Any:
    """将运行时对象转换为 JSON 可序列化结构（用于本地测试的监控面板）。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    # MockEntity / 其它“像实体”的对象
    entity_id = getattr(value, "entity_id", None)
    name = getattr(value, "name", None)
    if entity_id is not None and name is not None:
        return {"__type": "entity", "entity_id": str(entity_id), "name": str(name)}
    return str(value)


class _LocalSimRequestHandler(http.server.BaseHTTPRequestHandler):
    def __init__(
        self,
        *args: Any,
        ui_html_file: Path,
        server_impl: Any,
        **kwargs: Any,
    ) -> None:
        self._ui_html_file = ui_html_file
        self._server_impl = server_impl
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        # 静态资源与点击请求较多，默认不输出到控制台，避免刷屏
        return

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/":
            self._handle_index()
            return
        if parsed.path == "/ui.html":
            self._handle_ui_html(parsed)
            return
        if parsed.path == "/local_sim.js":
            self._send_text(read_local_sim_js_text(), content_type="text/javascript; charset=utf-8")
            return
        if parsed.path == "/api/local_sim/status":
            self._handle_status()
            return
        if parsed.path == "/api/local_sim/bootstrap":
            self._handle_bootstrap()
            return
        if parsed.path == "/api/local_sim/sync":
            self._handle_sync()
            return
        if parsed.path == "/api/local_sim/poll":
            self._handle_poll()
            return
        if parsed.path == "/api/local_sim/trace":
            self._handle_trace(parsed)
            return
        if parsed.path == "/api/local_sim/entities":
            self._handle_entities()
            return
        self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/api/local_sim/click":
            self._handle_click()
            return
        if parsed.path == "/api/local_sim/emit_signal":
            self._handle_emit_signal()
            return
        if parsed.path == "/api/local_sim/restart":
            self._handle_restart()
            return
        if parsed.path == "/api/local_sim/clear_trace":
            self._handle_clear_trace()
            return
        self.send_error(404, "Not Found")

    # ------------------------------------------------------------------ handlers
    def _handle_index(self) -> None:
        html = read_monitor_html_text()
        self._send_text(html, content_type="text/html; charset=utf-8")

    def _handle_ui_html(self, parsed: Any) -> None:
        qs = parse_qs(parsed.query)
        layout_raw = ""
        if "layout" in qs and qs["layout"]:
            layout_raw = str(qs["layout"][0] or "")
        layout_index = _parse_int(layout_raw) or 0

        html_file = self._ui_html_file
        if layout_index:
            candidate = self._server_impl.get_layout_html_file(layout_index)
            if candidate is not None:
                html_file = candidate
                self._server_impl.set_current_layout_index(layout_index)

        text = html_file.read_text(encoding="utf-8")
        injected = _inject_local_sim_script(text)
        self._send_text(injected, content_type="text/html; charset=utf-8")

    def _handle_status(self) -> None:
        session = self._server_impl.session
        cur_idx = self._server_impl.current_layout_index
        cur_file = self._server_impl.get_layout_html_file(cur_idx) or self._ui_html_file
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

        payload = {
            "ok": True,
            "graph": {
                "graph_name": session.graph_name,
                "graph_type": session.graph_type,
                "graph_code_file": str(session.graph_code_file),
            },
            "graphs": graphs_payload,
            "ui": {
                "ui_html_file": str(self._ui_html_file),
                "current_layout_index": int(cur_idx),
                "current_ui_html_file": str(cur_file),
                "layouts": self._server_impl.get_all_layouts(),
            },
            "server": {
                "host": str(getattr(self._server_impl, "_config").host),
                "port": int(getattr(self._server_impl, "port", 0)),
                "auto_emit_signal_id": str(getattr(self._server_impl, "_config").auto_emit_signal_id or ""),
                "auto_emit_signal_pending": bool(getattr(self._server_impl, "_auto_emit_signal_pending", False)),
            },
        }
        self._send_json(payload, status=200)

    def _handle_bootstrap(self) -> None:
        with self._server_impl._lock:
            patches = self._server_impl.drain_bootstrap_patches()
            self._server_impl._capture_layout_switch_from_patches(patches)
        self._send_json({"ok": True, "patches": patches}, status=200)

    def _handle_sync(self) -> None:
        with self._server_impl._lock:
            session = self._server_impl.session
            game = session.game
            patches: list[dict[str, Any]] = []

            layout_index = int(self._server_impl.current_layout_index)
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

        self._send_json(
            {
                "ok": True,
                "current_layout_index": int(layout_index),
                "patches": patches,
            },
            status=200,
        )

    def _handle_poll(self) -> None:
        """轮询：推进定时器 + drain UI patches + 回传 UI 绑定数据（用于倒计时等文本刷新）。"""
        with self._server_impl._lock:
            session = self._server_impl.session
            game = session.game

            timer_fired = int(game.tick())
            patches = session.drain_ui_patches()

            lv: dict[str, Any] = {}
            root_entity_id = str(getattr(game, "ui_binding_root_entity_id", "") or "").strip()
            if root_entity_id:
                raw = game.custom_variables.get(root_entity_id, {})
                if isinstance(raw, dict):
                    lv = dict(raw)

            self._send_json(
                {
                    "ok": True,
                    "timer_fired": int(timer_fired),
                    "patches": patches,
                    "bindings": {
                        "lv": lv,
                    },
                },
                status=200,
            )

    def _handle_trace(self, parsed: Any) -> None:
        session = self._server_impl.session
        qs = parse_qs(parsed.query)
        since = 0
        if "since" in qs and qs["since"]:
            since = _parse_int(str(qs["since"][0] or "")) or 0
        since = max(0, int(since))

        events = session.game.trace_recorder.as_list()
        out: list[dict[str, Any]] = []
        for ev in events[since:]:
            if hasattr(ev, "to_dict"):
                out.append(_json_safe(ev.to_dict()))
            else:
                out.append(_json_safe(ev))

        self._send_json(
            {
                "ok": True,
                "since": int(since),
                "next": int(len(events)),
                "events": out,
            },
            status=200,
        )

    def _handle_entities(self) -> None:
        session = self._server_impl.session
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
            "custom_variables": _json_safe(game.custom_variables),
            "graph_variables": _json_safe(game.graph_variables),
            "local_variables": _json_safe(game.local_variables),
            "attached_graphs": _json_safe(attached_graphs),
            "mounted_graphs": _json_safe(mounted_graphs_payload),
            "ui_current_layout_by_player": _json_safe(game.ui_current_layout_by_player),
            "ui_widget_state_by_player": _json_safe(game.ui_widget_state_by_player),
            "ui_active_groups_by_player": _json_safe({k: sorted(list(v)) for k, v in game.ui_active_groups_by_player.items()}),
        }
        self._send_json(payload, status=200)

    def _handle_click(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("click payload 必须是对象")

        data_ui_key = str(payload.get("data_ui_key") or "").strip()
        data_ui_state_group = str(payload.get("data_ui_state_group") or "").strip()
        data_ui_state = str(payload.get("data_ui_state") or "").strip()

        with self._server_impl._lock:
            patches = self._server_impl.session.trigger_ui_click(
                data_ui_key=data_ui_key,
                data_ui_state_group=data_ui_state_group,
                data_ui_state=data_ui_state,
            )
            self._server_impl._capture_layout_switch_from_patches(patches)
            self._server_impl.session.game.record_trace_event(
                kind="ui_click",
                message="ui_click",
                data_ui_key=data_ui_key,
                data_ui_state_group=data_ui_state_group,
                data_ui_state=data_ui_state,
                patch_count=len(patches),
            )
        self._send_json({"ok": True, "patches": patches}, status=200)

    def _handle_emit_signal(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("emit_signal payload 必须是对象")

        signal_id = str(payload.get("signal_id") or "").strip()
        params = payload.get("params") or {}
        if not isinstance(params, dict):
            raise ValueError("emit_signal.params 必须是对象")

        with self._server_impl._lock:
            patches = self._server_impl.session.emit_signal(signal_id=signal_id, params=dict(params))
            self._server_impl._capture_layout_switch_from_patches(patches)
            self._server_impl.session.game.record_trace_event(
                kind="emit_signal",
                message="emit_signal",
                signal_id=signal_id,
                params=_json_safe(params),
                patch_count=len(patches),
            )
        self._send_json({"ok": True, "patches": patches}, status=200)

    def _handle_clear_trace(self) -> None:
        with self._server_impl._lock:
            session = self._server_impl.session
            session.game.trace_recorder.clear()
        self._send_json({"ok": True}, status=200)

    def _handle_restart(self) -> None:
        # 读取并忽略 body（兼容未来扩展参数）
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 0:
            self.rfile.read(length)
        self._server_impl.restart()
        self._send_json({"ok": True}, status=200)

    # ------------------------------------------------------------------ utils
    def _send_json(self, payload: dict, *, status: int) -> None:
        body = json.dumps(_json_safe(payload), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, *, content_type: str) -> None:
        body = str(text).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


__all__ = ["_LocalSimRequestHandler"]

