from __future__ import annotations

import functools
import http.server
import os
import socket
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .ui_converter_routes import handle_ui_converter_get, handle_ui_converter_post


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


def _choose_local_http_port(*, host: str, scan_count: int = 50) -> int:
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


class StaticRequestHandler(http.server.SimpleHTTPRequestHandler):
    """
    本地静态服务的通用基础能力（唯一实现）：
    - 强制 ES Module 相关文件的 MIME（避免 Windows 注册表导致 .js= text/plain -> 白屏）
    - 开发期对关键资源统一 no-store，避免模块缓存导致“改了但没生效”的错觉

    说明：
    - 该类只提供“静态服务层”的公共能力，不包含 /api 路由；
      具体业务 handler（插件运行时的 /api/ui_converter/*、或离线 mock）应继承该类。
    """

    extensions_map = http.server.SimpleHTTPRequestHandler.extensions_map | {
        ".js": "text/javascript; charset=utf-8",
        ".mjs": "text/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".map": "application/json; charset=utf-8",
        ".svg": "image/svg+xml",
    }

    def end_headers(self) -> None:
        # 开发期强制禁用缓存：
        # - Workbench/Preview 采用 ES Module，浏览器会缓存模块图；
        # - 若静态资源被缓存，用户会遇到“页面已更新但 JS 仍旧”，常见表现为 API 缺失 / 白屏无交互。
        try_path = str(getattr(self, "path", "") or "")
        parsed = urlsplit(try_path)
        path_only = str(parsed.path or "")
        lowered = path_only.lower()
        if lowered.endswith((".html", ".js", ".mjs", ".json", ".map")):
            self.send_header("Cache-Control", "no-store")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        return super().end_headers()


class _WorkbenchHttpServer:
    def __init__(self, *, workbench_dir: Path, bridge: object) -> None:
        # workbench_dir：静态前端根目录（HTTP server.directory）
        self._workbench_dir = workbench_dir
        self._bridge = bridge
        self._httpd: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int = 0

    def start(self) -> None:
        if self._httpd is not None:
            return

        handler_factory = functools.partial(_WorkbenchRequestHandler, directory=str(self._workbench_dir), bridge=self._bridge)
        host = "127.0.0.1"
        port = _choose_local_http_port(host=host)
        httpd = http.server.ThreadingHTTPServer((host, port), handler_factory)
        self._httpd = httpd
        self.port = int(httpd.server_address[1])
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        self._thread = thread
        thread.start()


class _WorkbenchRequestHandler(StaticRequestHandler):
    def __init__(self, *args: Any, directory: str | None = None, bridge: object | None = None, **kwargs: Any):
        self._bridge = bridge
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        # 静态资源请求较多，默认不输出到控制台，避免刷屏；
        # 但 /api/ui_converter/* 属于“用户动作”，必须有可见日志用于排障。
        path_text = str(getattr(self, "path", "") or "")
        if path_text.startswith("/api/ui_converter/"):
            msg = format % args
            print(f"[ui_converter] {self.command} {path_text} -> {msg}")
        return

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)

        # 统一入口策略（主程序运行时）：
        # - 用户侧只允许使用 ui_app_ui_preview.html（唯一入口）
        # - ui_html_workbench.html 仅用于测试/自动化（通过 tests 的临时静态服务器访问），
        #   因此在插件静态服务中强制跳转，避免用户误入产生困惑。
        if parsed.path in ("", "/"):
            self.send_response(302)
            self.send_header("Location", "/ui_app_ui_preview.html")
            self.end_headers()
            return
        if parsed.path == "/ui_html_workbench.html":
            self.send_response(302)
            self.send_header("Location", "/ui_app_ui_preview.html")
            self.end_headers()
            return
        if handle_ui_converter_get(
            handler=self,
            bridge=self._bridge,
            path=str(parsed.path or ""),
            query_text=str(parsed.query or ""),
        ):
            return
        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        if handle_ui_converter_post(handler=self, bridge=self._bridge, path=str(parsed.path or "")):
            return
        self.send_error(404, "Not Found")
