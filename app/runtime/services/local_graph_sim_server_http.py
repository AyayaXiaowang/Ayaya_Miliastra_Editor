from __future__ import annotations

import http.server
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from app.runtime.services.local_graph_sim_server_html import _parse_int
from app.runtime.services.local_graph_sim_server_http_facade import LocalGraphSimHttpFacade
from app.runtime.services.local_graph_sim_protocol import (
    LOCAL_SIM_API,
    LOCAL_SIM_PROTOCOL_VERSION,
    LOCAL_SIM_SCHEMA_VERSION,
    build_local_sim_protocol_payload,
)
from app.runtime.services.local_graph_sim_server_web_assets import (
    read_local_sim_js_text,
    read_local_sim_shared_js_text,
    read_monitor_html_text,
    read_monitor_js_text,
)


class _LocalSimRequestHandler(http.server.BaseHTTPRequestHandler):
    """
    HTTP Handler（薄层）：
    - 只负责：路由、请求解析、HTTP 响应编码
    - 领域逻辑/IO：委托给 `LocalGraphSimHttpFacade`
    """

    def __init__(
        self,
        *args: Any,
        entry_ui_html_file: Path,
        http_facade: LocalGraphSimHttpFacade,
        **kwargs: Any,
    ) -> None:
        self._entry_ui_html_file = Path(entry_ui_html_file)
        self._api = http_facade
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        # 静态资源与点击请求较多，默认不输出到控制台，避免刷屏
        return

    def do_GET(self) -> None:
        api = LOCAL_SIM_API
        parsed = urlsplit(self.path)
        if parsed.path == "/":
            self._send_text(read_monitor_html_text(), content_type="text/html; charset=utf-8")
            return
        if parsed.path == "/ui.html":
            self._handle_ui_html(parsed)
            return
        if parsed.path.startswith("/__ui_workbench__/"):
            self._handle_ui_workbench_static(parsed.path)
            return
        if parsed.path == "/local_sim_shared.js":
            self._send_text(read_local_sim_shared_js_text(), content_type="text/javascript; charset=utf-8")
            return
        if parsed.path == "/local_sim.js":
            self._send_text(read_local_sim_js_text(), content_type="text/javascript; charset=utf-8")
            return
        if parsed.path == "/monitor.js":
            self._send_text(read_monitor_js_text(), content_type="text/javascript; charset=utf-8")
            return
        if parsed.path == "/local_sim_flatten_overlay.mjs":
            text = self._api.read_flatten_overlay_module_text()
            if not text:
                self.send_error(404, "local_sim_flatten_overlay.mjs not found")
                return
            self._send_text(text, content_type="text/javascript; charset=utf-8")
            return
        if parsed.path == api.status:
            self._send_json(self._api.build_status_payload(entry_ui_html_file=self._entry_ui_html_file), status=200)
            return
        if parsed.path == api.protocol:
            self._send_json(build_local_sim_protocol_payload(), status=200)
            return
        if parsed.path == api.bootstrap:
            patches = self._api.drain_bootstrap_patches()
            self._send_json({"ok": True, "patches": patches}, status=200)
            return
        if parsed.path == api.sync:
            self._send_json(self._api.build_sync_payload(), status=200)
            return
        if parsed.path == api.poll:
            self._send_json(self._api.poll(), status=200)
            return
        if parsed.path == api.trace:
            self._handle_trace(parsed)
            return
        if parsed.path == api.entities:
            self._send_json(self._api.build_entities_payload(), status=200)
            return
        if parsed.path == api.last_action:
            self._send_json({"ok": True, "last_action": self._api.get_last_action()}, status=200)
            return
        if parsed.path == api.snapshot:
            self._handle_snapshot(parsed)
            return
        if parsed.path == api.validation_status:
            self._send_json({"ok": True, "report": self._api.get_last_validation_report()}, status=200)
            return
        if parsed.path == api.export_repro:
            self._handle_export_repro_download(parsed)
            return
        if parsed.path == api.pause_status:
            self._send_json(self._api.pause_status(), status=200)
            return
        self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        api = LOCAL_SIM_API
        parsed = urlsplit(self.path)
        if parsed.path == api.click:
            self._handle_click()
            return
        if parsed.path == api.emit_signal:
            self._handle_emit_signal()
            return
        if parsed.path == api.resolve_ui_key:
            self._handle_resolve_ui_key()
            return
        if parsed.path == api.restart:
            self._read_json_body_ignored()
            self._api.restart()
            self._send_json({"ok": True}, status=200)
            return
        if parsed.path == api.clear_trace:
            self._read_json_body_ignored()
            self._api.clear_trace()
            self._send_json({"ok": True}, status=200)
            return
        if parsed.path == api.validate:
            self._handle_validate(parsed)
            return
        if parsed.path == api.export_repro:
            self._handle_export_repro()
            return
        if parsed.path == api.pause:
            self._handle_pause()
            return
        if parsed.path == api.step:
            self._handle_step()
            return
        self.send_error(404, "Not Found")

    # ------------------------------------------------------------------ handlers
    def _handle_ui_html(self, parsed: Any) -> None:
        qs = parse_qs(parsed.query)
        layout_raw = ""
        if "layout" in qs and qs["layout"]:
            layout_raw = str(qs["layout"][0] or "")
        layout_index = _parse_int(layout_raw) or 0

        flatten_enabled = False
        flatten_raw = ""
        if "flatten" in qs and qs["flatten"]:
            flatten_raw = str(qs["flatten"][0] or "")
        elif "flat" in qs and qs["flat"]:
            flatten_raw = str(qs["flat"][0] or "")
        if flatten_raw:
            t = flatten_raw.strip().lower()
            flatten_enabled = t in {"1", "true", "yes", "on"}

        injected = self._api.get_ui_html_payload(
            entry_ui_html_file=self._entry_ui_html_file,
            layout_index=int(layout_index),
            flatten_enabled=bool(flatten_enabled),
        )
        self._send_text(injected, content_type="text/html; charset=utf-8")

    def _handle_ui_workbench_static(self, url_path: str) -> None:
        result = self._api.read_ui_workbench_static_bytes(
            url_path=str(url_path or ""),
            entry_ui_html_file=self._entry_ui_html_file,
        )
        if not result.ok:
            self.send_error(int(result.status), str(result.message or "Not Found"))
            return
        self._send_bytes(result.data, content_type=result.content_type)

    def _handle_trace(self, parsed: Any) -> None:
        qs = parse_qs(parsed.query)
        since = 0
        if "since" in qs and qs["since"]:
            since = _parse_int(str(qs["since"][0] or "")) or 0
        payload = self._api.build_trace_payload(since=int(max(0, int(since))))
        self._send_json(payload, status=200)

    def _handle_snapshot(self, parsed: Any) -> None:
        qs = parse_qs(parsed.query)
        include_entities = True
        if "entities" in qs and qs["entities"]:
            raw = str(qs["entities"][0] or "").strip().lower()
            include_entities = raw in {"1", "true", "yes", "on"}
        payload = self._api.build_snapshot_payload(include_entities=bool(include_entities))
        self._send_json(payload, status=200)

    def _handle_click(self) -> None:
        payload = self._read_json_body()
        if not isinstance(payload, dict):
            raise ValueError("click payload 必须是对象")

        result = self._api.click(
            data_ui_key=str(payload.get("data_ui_key") or "").strip(),
            data_ui_state_group=str(payload.get("data_ui_state_group") or "").strip(),
            data_ui_state=str(payload.get("data_ui_state") or "").strip(),
            player_entity_id=str(payload.get("player_entity_id") or "").strip(),
            player_entity_name=str(payload.get("player_entity_name") or "").strip(),
        )
        if not bool(result.get("ok", False)):
            code = str(((result.get("error") or {}) if isinstance(result.get("error"), dict) else {}).get("code") or "")
            status = 400
            if code == "paused":
                status = 409
            self._send_json(result, status=status)
            return
        self._send_json(result, status=200)

    def _handle_emit_signal(self) -> None:
        payload = self._read_json_body()
        if not isinstance(payload, dict):
            raise ValueError("emit_signal payload 必须是对象")

        signal_id = str(payload.get("signal_id") or "").strip()
        params = payload.get("params") or {}
        if not isinstance(params, dict):
            raise ValueError("emit_signal.params 必须是对象")

        result = self._api.emit_signal(signal_id=str(signal_id), params=dict(params))
        if not bool(result.get("ok", False)):
            code = str(((result.get("error") or {}) if isinstance(result.get("error"), dict) else {}).get("code") or "")
            status = 400
            if code == "paused":
                status = 409
            self._send_json(result, status=status)
            return
        self._send_json(result, status=200)

    def _handle_resolve_ui_key(self) -> None:
        payload = self._read_json_body()
        if not isinstance(payload, dict):
            raise ValueError("resolve_ui_key payload 必须是对象")

        result = self._api.resolve_ui_key(
            data_ui_key=str(payload.get("data_ui_key") or "").strip(),
            data_ui_state_group=str(payload.get("data_ui_state_group") or "").strip(),
            data_ui_state=str(payload.get("data_ui_state") or "").strip(),
            player_entity_id=str(payload.get("player_entity_id") or "").strip(),
            player_entity_name=str(payload.get("player_entity_name") or "").strip(),
        )
        if not bool(result.get("ok", False)):
            self._send_json(result, status=400)
            return
        self._send_json(result, status=200)

    def _handle_validate(self, parsed: Any) -> None:
        qs = parse_qs(parsed.query)

        def _truthy(name: str) -> bool:
            if name not in qs or not qs[name]:
                return False
            raw = str(qs[name][0] or "").strip().lower()
            return raw in {"1", "true", "yes", "on"}

        report = self._api.validate_now(
            strict_entity_wire_only=_truthy("strict"),
            disable_cache=_truthy("no_cache"),
            disable_composite_struct_check=_truthy("no_composite_struct"),
        )
        self._send_json(report, status=200)

    def _handle_export_repro(self) -> None:
        payload = self._read_json_body()
        if not isinstance(payload, dict):
            raise ValueError("export_repro payload 必须是对象")

        def _truthy(v: object, default: bool) -> bool:
            if v is None:
                return bool(default)
            if isinstance(v, bool):
                return bool(v)
            if isinstance(v, (int, float)):
                return bool(int(v) != 0)
            text = str(v).strip().lower()
            if text == "":
                return bool(default)
            return text in {"1", "true", "yes", "on"}

        include_entities = _truthy(payload.get("include_entities"), False)
        include_snapshot = _truthy(payload.get("include_snapshot"), True)
        include_trace = _truthy(payload.get("include_trace"), True)
        include_validation = _truthy(payload.get("include_validation"), True)
        include_last_action = _truthy(payload.get("include_last_action"), True)

        recorded_actions = payload.get("recorded_actions", None)
        if recorded_actions is None:
            recorded_actions = []
        if not isinstance(recorded_actions, list):
            raise ValueError("recorded_actions 必须是数组")

        note = payload.get("note", "")
        note_text = str(note or "").strip()

        response = self._api.export_repro(
            include_entities=bool(include_entities),
            include_snapshot=bool(include_snapshot),
            include_trace=bool(include_trace),
            include_validation=bool(include_validation),
            include_last_action=bool(include_last_action),
            recorded_actions=list(recorded_actions),
            note_text=str(note_text),
        )
        self._send_json(response, status=200)

    def _handle_export_repro_download(self, parsed: Any) -> None:
        qs = parse_qs(parsed.query)
        export_id = ""
        if "id" in qs and qs["id"]:
            export_id = str(qs["id"][0] or "").strip()
        if not export_id:
            self.send_error(400, "missing id")
            return

        result = self._api.export_repro_download_result(export_id=str(export_id))
        if not result.ok:
            self.send_error(int(result.status), str(result.message or "Not Found"))
            return

        body = result.data
        self.send_response(200)
        self.send_header("Content-Type", result.content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition", f'attachment; filename="{export_id}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_pause(self) -> None:
        payload = self._read_json_body()
        if not isinstance(payload, dict):
            raise ValueError("pause payload 必须是对象")
        if "paused" not in payload:
            raise ValueError("pause payload 缺少 paused 字段")
        paused = payload.get("paused")
        if not isinstance(paused, bool):
            raise ValueError("pause.paused 必须是布尔值")
        self._send_json(self._api.pause(paused=bool(paused)), status=200)

    def _handle_step(self) -> None:
        payload = self._read_json_body()
        if not isinstance(payload, dict):
            raise ValueError("step payload 必须是对象")

        dt = payload.get("dt", 0.1)
        if not isinstance(dt, (int, float)):
            raise ValueError("step.dt 必须是数字")
        dt2 = float(dt)
        if dt2 < 0:
            raise ValueError("step.dt 必须 >= 0")

        result = self._api.step(dt=float(dt2))
        if not bool(result.get("ok", False)):
            self._send_json(result, status=400)
            return
        self._send_json(result, status=200)

    # ------------------------------------------------------------------ utils
    def _read_json_body(self) -> Any:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _read_json_body_ignored(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 0:
            self.rfile.read(length)

    def _send_json(self, payload: Any, *, status: int) -> None:
        p = payload
        if isinstance(p, dict):
            p = dict(p)
            p.setdefault("protocol_version", int(LOCAL_SIM_PROTOCOL_VERSION))
            p.setdefault("schema_version", int(LOCAL_SIM_SCHEMA_VERSION))
        body = json.dumps(p, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
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

    def _send_bytes(self, body: bytes, *, content_type: str) -> None:
        data = bytes(body or b"")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


__all__ = ["_LocalSimRequestHandler"]

