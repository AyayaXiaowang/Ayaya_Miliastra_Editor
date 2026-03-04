from __future__ import annotations

import functools
import http.server
import json
import os
import socket
import threading
from typing import Any, TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

from app.runtime.services.ui_workbench.utils import decode_utf8_b64, encode_utf8_b64

if TYPE_CHECKING:
    from app.ui.workbench.bridge import UiWorkbenchBridge


_DEFAULT_LOCAL_HTTP_PORT = 17890
_LOCAL_HTTP_PORT_ENV = "AYAYA_LOCAL_HTTP_PORT"


def _parse_preferred_local_http_port() -> int:
    raw = str(os.environ.get(_LOCAL_HTTP_PORT_ENV, "") or "").strip()
    if raw.isdigit():
        value = int(raw)
        if 0 <= value <= 65535:
            return value
    return _DEFAULT_LOCAL_HTTP_PORT


def _is_port_listening(*, host: str, port: int) -> bool:
    if port <= 0:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.05)
        return sock.connect_ex((host, int(port))) == 0


def choose_local_http_port(*, host: str, scan_count: int = 50) -> int:
    """
    端口策略：
    - 优先使用固定端口（默认 17890，可用环境变量 AYAYA_LOCAL_HTTP_PORT 覆盖）
    - 若端口已被占用（已有服务在监听），则向上顺延扫描一段端口
    - 扫描不到则回退为 0（让系统分配临时端口）
    """
    preferred = int(_parse_preferred_local_http_port())
    if preferred <= 0:
        return 0
    max_port = min(65535, preferred + max(1, int(scan_count)))
    for port in range(preferred, max_port + 1):
        if not _is_port_listening(host=host, port=port):
            return int(port)
    return 0


class _WorkbenchHttpServer:
    def __init__(self, *, workbench_dir: os.PathLike[str] | str, bridge: "UiWorkbenchBridge") -> None:
        self._workbench_dir = str(workbench_dir)
        self._bridge = bridge
        self._httpd: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int = 0

    def start(self) -> None:
        if self._httpd is not None:
            return

        handler_factory = functools.partial(
            _WorkbenchRequestHandler,
            directory=str(self._workbench_dir),
            bridge=self._bridge,
        )
        host = "127.0.0.1"
        port = choose_local_http_port(host=host)
        httpd = http.server.ThreadingHTTPServer((host, port), handler_factory)
        self._httpd = httpd
        self.port = int(httpd.server_address[1])
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        self._thread = thread
        thread.start()


class _WorkbenchRequestHandler(http.server.SimpleHTTPRequestHandler):
    # NOTE:
    # - 浏览器的 `<script type="module">` 对 JS 的 MIME type 更严格；
    # - Windows 上 `mimetypes` 可能受注册表影响把 `.js` 识别为 `text/plain`；
    #   会导致模块脚本直接不执行，页面看起来像“预览一片白/无交互”。
    #
    # 因此这里强制覆盖关键后缀的 Content-Type，避免环境差异。
    extensions_map = http.server.SimpleHTTPRequestHandler.extensions_map | {
        ".js": "text/javascript; charset=utf-8",
        ".mjs": "text/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".map": "application/json; charset=utf-8",
        ".svg": "image/svg+xml",
    }

    def __init__(
        self,
        *args: Any,
        directory: str | None = None,
        bridge: "UiWorkbenchBridge | None" = None,
        **kwargs: Any,
    ):
        self._bridge = bridge
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        # 静态资源请求较多，默认不输出到控制台，避免刷屏
        return

    def end_headers(self) -> None:
        path = str(getattr(self, "path", "") or "").lower()
        if (
            path.endswith(".html")
            or path.endswith(".js")
            or path.endswith(".mjs")
            or path.endswith(".json")
            or path.endswith(".map")
        ):
            # 开发期禁用缓存：避免 ES Module 缓存导致“改了但没生效”的错觉
            self.send_header("Cache-Control", "no-store")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/api/ui_converter/status":
            self._handle_status()
            return
        if parsed.path == "/api/ui_converter/ui_source_catalog":
            self._handle_ui_source_catalog()
            return
        if parsed.path == "/api/ui_converter/ui_source":
            self._handle_ui_source(parsed.query)
            return
        if parsed.path == "/api/ui_converter/ui_source_raw":
            self._handle_ui_source_raw(parsed.query)
            return
        if parsed.path == "/api/ui_converter/base_gil_cache":
            self._handle_base_gil_cache_get()
            return
        if parsed.path == "/api/ui_converter/ui_catalog":
            self._handle_ui_catalog()
            return
        if parsed.path == "/api/ui_converter/ui_layout":
            self._handle_ui_layout(parsed.query)
            return
        if parsed.path == "/api/ui_converter/ui_template":
            self._handle_ui_template(parsed.query)
            return
        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/api/ui_converter/base_gil_cache":
            self._handle_base_gil_cache_post()
            return
        if parsed.path == "/api/ui_converter/import_layout":
            self._handle_import_layout()
            return
        if parsed.path == "/api/ui_converter/fix_ui_variables":
            self._handle_fix_ui_variables()
            return
        if parsed.path == "/api/ui_converter/import_variable_defaults":
            self._handle_import_variable_defaults()
            return
        if parsed.path == "/api/ui_converter/export_gil":
            self._handle_export_gil()
            return
        if parsed.path == "/api/ui_converter/export_gia":
            self._handle_export_gia()
            return
        self.send_error(404, "Not Found")

    # ------------------------------------------------------------------ api handlers
    def _handle_status(self) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "connected": False, "error": "bridge not ready"}, status=503)
            return
        self._send_json(self._bridge.get_status_payload(), status=200)

    def _handle_ui_source_catalog(self) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "connected": False, "error": "bridge not ready"}, status=503)
            return
        self._send_json(self._bridge.get_ui_source_catalog_payload(), status=200)

    def _handle_ui_source(self, query_text: str) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "connected": False, "error": "bridge not ready"}, status=503)
            return
        query = parse_qs(query_text or "")
        scope = (query.get("scope", ["project"])[0] or "").strip() or "project"
        rel_path = (query.get("rel_path", [""])[0] or "").strip()
        if not rel_path:
            self._send_json({"ok": False, "error": "rel_path is required"}, status=400)
            return
        payload = self._bridge.read_ui_source_payload(scope=scope, rel_path=rel_path)
        if not payload.get("ok", False):
            self._send_json(payload, status=404)
            return
        self._send_json(payload, status=200)

    def _handle_ui_source_raw(self, query_text: str) -> None:
        if self._bridge is None:
            self.send_response(503)
            self.end_headers()
            return
        query = parse_qs(query_text or "")
        scope = (query.get("scope", ["project"])[0] or "").strip() or "project"
        rel_path = (query.get("rel_path", [""])[0] or "").strip()
        if not rel_path:
            self.send_response(400)
            self.end_headers()
            return
        file_path = self._bridge.resolve_ui_source_path(scope=scope, rel_path=rel_path)
        if not file_path.is_file():
            self.send_response(404)
            self.end_headers()
            return
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _handle_base_gil_cache_get(self) -> None:
        if self._bridge is None:
            self.send_response(503)
            self.end_headers()
            return
        entry = self._bridge.load_base_gil_cache()
        if entry is None:
            self.send_response(404)
            self.end_headers()
            return
        file_name, last_modified, body = entry
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Ui-Base-Gil-Name-B64", encode_utf8_b64(file_name))
        self.send_header("X-Ui-Base-Gil-Last-Modified", str(int(last_modified)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_base_gil_cache_post(self) -> None:
        if self._bridge is None:
            self.send_response(503)
            self.end_headers()
            return
        name_b64 = str(self.headers.get("X-Ui-Base-Gil-Name-B64", "") or "").strip()
        last_modified_text = str(self.headers.get("X-Ui-Base-Gil-Last-Modified", "") or "").strip()
        file_name = decode_utf8_b64(name_b64) if name_b64 else "base.gil"
        last_modified = int(last_modified_text) if last_modified_text.isdigit() else 0

        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length > 0 else b""
        if not body:
            self.send_response(400)
            self.end_headers()
            return
        self._bridge.save_base_gil_cache(file_name=file_name, last_modified=last_modified, content=body)
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _handle_ui_catalog(self) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "connected": False, "error": "bridge not ready"}, status=503)
            return
        self._send_json(self._bridge.get_ui_catalog_payload(), status=200)

    def _handle_ui_layout(self, query_text: str) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "connected": False, "error": "bridge not ready"}, status=503)
            return
        query = parse_qs(query_text or "")
        layout_id = (query.get("layout_id", [""])[0] or "").strip()
        if not layout_id:
            self._send_json({"ok": False, "error": "layout_id is required"}, status=400)
            return
        self._send_json(self._bridge.get_ui_layout_payload(layout_id), status=200)

    def _handle_ui_template(self, query_text: str) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "connected": False, "error": "bridge not ready"}, status=503)
            return
        query = parse_qs(query_text or "")
        template_id = (query.get("template_id", [""])[0] or "").strip()
        if not template_id:
            self._send_json({"ok": False, "error": "template_id is required"}, status=400)
            return
        self._send_json(self._bridge.get_ui_template_payload(template_id), status=200)

    def _handle_import_layout(self) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "error": "bridge not ready"}, status=503)
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b""
        text = raw.decode("utf-8") if raw else "{}"
        payload = json.loads(text)

        layout_name = str(payload.get("layout_name", "") or "")
        bundle = payload.get("bundle", None)
        if isinstance(bundle, dict):
            result = self._bridge.import_layout_from_bundle_payload(layout_name=layout_name, bundle_payload=bundle)
            self._send_json(
                {
                    "ok": True,
                    "layout_id": result.layout_id,
                    "layout_name": result.layout_name,
                    "template_count": result.template_count,
                    "widget_count": result.widget_count,
                    "import_mode": "bundle",
                },
                status=200,
            )
            return

        template = payload.get("template", None)
        if not isinstance(template, dict):
            self._send_json({"ok": False, "error": "bundle/template is required"}, status=400)
            return

        result = self._bridge.import_layout_from_template_payload(layout_name=layout_name, template_payload=template)
        self._send_json(
            {
                "ok": True,
                "layout_id": result.layout_id,
                "layout_name": result.layout_name,
                "template_id": result.template_id,
                "template_name": result.template_name,
                "template_count": result.template_count,
                "widget_count": result.widget_count,
                "import_mode": "template",
            },
            status=200,
        )

    def _handle_fix_ui_variables(self) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "error": "bridge not ready"}, status=503)
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b""
        text = raw.decode("utf-8") if raw else "{}"
        payload = json.loads(text)

        dry_run = bool(payload.get("dry_run", False))
        result = self._bridge.fix_ui_variables_from_ui_source(dry_run=dry_run)
        self._send_json(result, status=200)

    def _handle_import_variable_defaults(self) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "error": "bridge not ready"}, status=503)
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b""
        text = raw.decode("utf-8") if raw else "{}"
        payload = json.loads(text)

        source_rel_path = str(payload.get("source_rel_path", "") or "")
        variable_defaults = payload.get("variable_defaults", {})
        result = self._bridge.import_variable_defaults_to_current_project(
            source_rel_path=source_rel_path,
            variable_defaults=variable_defaults if isinstance(variable_defaults, dict) else {},
        )
        self._send_json({"ok": True, **result}, status=200)

    def _handle_export_gil(self) -> None:
        # 内置 Workbench 不包含 UGC 写回工具链：明确返回“未实现”，避免前端拿到 404 或 HTML 导致报错。
        self._send_json(
            {
                "ok": False,
                "error": "export_gil is not supported in builtin workbench (requires private ugc_file_tools).",
            },
            status=501,
        )

    def _handle_export_gia(self) -> None:
        self._send_json(
            {
                "ok": False,
                "error": "export_gia is not supported in builtin workbench (requires private ugc_file_tools).",
            },
            status=501,
        )

    # ------------------------------------------------------------------ utils
    def _send_json(self, payload: dict, *, status: int) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


__all__ = [
    "_WorkbenchHttpServer",
    "_WorkbenchRequestHandler",
    "choose_local_http_port",
]

