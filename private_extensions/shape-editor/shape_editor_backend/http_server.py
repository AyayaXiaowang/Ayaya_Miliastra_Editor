from __future__ import annotations

import functools
import http.server
import json
import os
import socket
import threading
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit


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
    本地静态服务基础能力：
    - 强制 ES Module 相关文件的 MIME（避免 Windows 环境 .js= text/plain 导致白屏）
    - 开发期关键资源统一 no-store，避免模块缓存导致“改了但没生效”
    """

    extensions_map = http.server.SimpleHTTPRequestHandler.extensions_map | {
        ".js": "text/javascript; charset=utf-8",
        ".mjs": "text/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".map": "application/json; charset=utf-8",
        ".svg": "image/svg+xml",
    }

    def end_headers(self) -> None:
        path_text = str(getattr(self, "path", "") or "")
        lowered = str(urlsplit(path_text).path or "").lower()
        if lowered.endswith((".html", ".js", ".mjs", ".json", ".map", ".css")):
            self.send_header("Cache-Control", "no-store")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        return super().end_headers()


class _ShapeEditorHttpServer:
    def __init__(self, *, workspace_root: Path, bridge: object) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._bridge = bridge
        self._httpd: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int = 0

    def start(self) -> None:
        if self._httpd is not None:
            return
        handler_factory = functools.partial(
            _ShapeEditorRequestHandler,
            directory=str(self._workspace_root),
            bridge=self._bridge,
        )
        host = "127.0.0.1"
        port = _choose_local_http_port(host=host)
        httpd = http.server.ThreadingHTTPServer((host, port), handler_factory)
        self._httpd = httpd
        self.port = int(httpd.server_address[1])
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        self._thread = thread
        thread.start()


class _ShapeEditorRequestHandler(StaticRequestHandler):
    def __init__(self, *args: Any, directory: str | None = None, bridge: object | None = None, **kwargs: Any):
        self._bridge = bridge
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        path_text = str(getattr(self, "path", "") or "")
        if path_text.startswith("/api/shape_editor/"):
            msg = format % args
            print(f"[shape_editor] {self.command} {path_text} -> {msg}")
        return

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/api/shape_editor/status":
            self._handle_status()
            return
        if parsed.path == "/api/shape_editor/project_state":
            self._handle_project_state_get()
            return
        if parsed.path == "/api/shape_editor/pixel_workbench_state":
            self._handle_pixel_workbench_state_get()
            return
        if parsed.path == "/api/shape_editor/project_canvas":
            self._handle_project_canvas_get()
            return
        if parsed.path == "/api/shape_editor/placement_catalog":
            self._handle_placement_catalog()
            return
        if parsed.path == "/api/shape_editor/placement":
            self._handle_placement_get(parsed.query)
            return
        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/api/shape_editor/frontend_log":
            self._handle_frontend_log()
            return
        if parsed.path == "/api/shape_editor/perfect_pixel":
            self._handle_perfect_pixel()
            return
        if parsed.path == "/api/shape_editor/export_gia":
            self._handle_export_gia()
            return
        if parsed.path == "/api/shape_editor/export_gia_entity":
            self._handle_export_gia_entity()
            return
        if parsed.path == "/api/shape_editor/export_gia_template":
            self._handle_export_gia_template()
            return
        if parsed.path == "/api/shape_editor/project_canvas":
            self._handle_project_canvas_post()
            return
        if parsed.path == "/api/shape_editor/project_state":
            self._handle_project_state_post()
            return
        if parsed.path == "/api/shape_editor/pixel_workbench_state":
            self._handle_pixel_workbench_state_post()
            return
        if parsed.path == "/api/shape_editor/entities/new":
            self._handle_entities_new()
            return
        if parsed.path == "/api/shape_editor/entities/save_as":
            self._handle_entities_save_as()
            return
        if parsed.path == "/api/shape_editor/entities/duplicate":
            self._handle_entities_duplicate()
            return
        if parsed.path == "/api/shape_editor/entities/delete":
            self._handle_entities_delete()
            return
        if parsed.path == "/api/shape_editor/entities/rename":
            self._handle_entities_rename()
            return
        self.send_error(404, "Not Found")

    # ------------------------------------------------------------------ api handlers
    def _send_json(self, payload: dict, *, status: int) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b""
        text = raw.decode("utf-8") if raw else "{}"
        obj = json.loads(text)
        if not isinstance(obj, dict):
            raise ValueError("request body 必须是 JSON object")
        return obj

    def _handle_status(self) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "connected": False, "error": "bridge not ready"}, status=503)
            return
        get_status = getattr(self._bridge, "get_status_payload", None)
        if not callable(get_status):
            self._send_json({"ok": False, "connected": False, "error": "bridge missing get_status_payload"}, status=503)
            return
        self._send_json(get_status(), status=200)

    def _handle_export_gia(self) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "error": "bridge not ready"}, status=503)
            return
        export_fn = getattr(self._bridge, "export_gia_from_canvas_payload", None)
        if not callable(export_fn):
            self._send_json({"ok": False, "error": "bridge missing export_gia_from_canvas_payload"}, status=503)
            return
        payload = self._read_json_body()
        result = export_fn(payload)
        if not isinstance(result, dict):
            raise TypeError("export_gia_from_canvas_payload 必须返回 dict")
        self._send_json(result, status=200)

    def _handle_export_gia_entity(self) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "error": "bridge not ready"}, status=503)
            return
        export_fn = getattr(self._bridge, "export_gia_entity_from_canvas_payload", None)
        if not callable(export_fn):
            self._send_json({"ok": False, "error": "bridge missing export_gia_entity_from_canvas_payload"}, status=503)
            return
        payload = self._read_json_body()
        result = export_fn(payload)
        if not isinstance(result, dict):
            raise TypeError("export_gia_entity_from_canvas_payload 必须返回 dict")
        status = 200 if bool(result.get("ok", True)) else 400
        self._send_json(result, status=status)

    def _handle_export_gia_template(self) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "error": "bridge not ready"}, status=503)
            return
        export_fn = getattr(self._bridge, "export_gia_template_from_canvas_payload", None)
        if not callable(export_fn):
            self._send_json({"ok": False, "error": "bridge missing export_gia_template_from_canvas_payload"}, status=503)
            return
        payload = self._read_json_body()
        result = export_fn(payload)
        if not isinstance(result, dict):
            raise TypeError("export_gia_template_from_canvas_payload 必须返回 dict")
        status = 200 if bool(result.get("ok", True)) else 400
        self._send_json(result, status=status)

    def _handle_project_canvas_get(self) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "error": "bridge not ready"}, status=503)
            return
        fn = getattr(self._bridge, "load_project_canvas_payload", None)
        if not callable(fn):
            self._send_json({"ok": False, "error": "bridge missing load_project_canvas_payload"}, status=503)
            return
        result = fn()
        if not isinstance(result, dict):
            raise TypeError("load_project_canvas_payload 必须返回 dict")
        self._send_json(result, status=200)

    def _handle_project_state_get(self) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "error": "bridge not ready"}, status=503)
            return
        fn = getattr(self._bridge, "get_project_state_payload", None)
        if not callable(fn):
            self._send_json({"ok": False, "error": "bridge missing get_project_state_payload"}, status=503)
            return
        result = fn()
        if not isinstance(result, dict):
            raise TypeError("get_project_state_payload 必须返回 dict")
        self._send_json(result, status=200)

    def _handle_pixel_workbench_state_get(self) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "error": "bridge not ready"}, status=503)
            return
        fn = getattr(self._bridge, "get_pixel_workbench_state_payload", None)
        if not callable(fn):
            self._send_json({"ok": False, "error": "bridge missing get_pixel_workbench_state_payload"}, status=503)
            return
        result = fn()
        if not isinstance(result, dict):
            raise TypeError("get_pixel_workbench_state_payload 必须返回 dict")
        self._send_json(result, status=200)

    def _handle_project_canvas_post(self) -> None:
        # 手动保存：将当前画布写入当前项目存档（实体摆放 + 元件库）。
        # 注意：导出 GIA 时也会自动保存；此接口用于“只保存不导出”的场景。
        if self._bridge is None:
            self._send_json({"ok": False, "error": "bridge not ready"}, status=503)
            return
        payload = self._read_json_body()
        fn = getattr(self._bridge, "save_project_canvas_payload", None)
        if not callable(fn):
            self._send_json({"ok": False, "error": "bridge missing save_project_canvas_payload"}, status=503)
            return
        result = fn(payload)
        if not isinstance(result, dict):
            raise TypeError("save_project_canvas_payload 必须返回 dict")
        self._send_json(result, status=200)

    def _handle_project_state_post(self) -> None:
        # 项目级状态：记录最近打开的实体摆放 rel_path，用于下次启动自动恢复。
        if self._bridge is None:
            self._send_json({"ok": False, "error": "bridge not ready"}, status=503)
            return
        payload = self._read_json_body()
        fn = getattr(self._bridge, "set_project_state_payload", None)
        if not callable(fn):
            self._send_json({"ok": False, "error": "bridge missing set_project_state_payload"}, status=503)
            return
        result = fn(payload)
        if not isinstance(result, dict):
            raise TypeError("set_project_state_payload 必须返回 dict")
        self._send_json(result, status=200)

    def _handle_pixel_workbench_state_post(self) -> None:
        # 像素工作台项目级持久化：保存“标准化像素矩阵（含改色）”与素材列表状态。
        if self._bridge is None:
            self._send_json({"ok": False, "error": "bridge not ready"}, status=503)
            return
        payload = self._read_json_body()
        fn = getattr(self._bridge, "set_pixel_workbench_state_payload", None)
        if not callable(fn):
            self._send_json({"ok": False, "error": "bridge missing set_pixel_workbench_state_payload"}, status=503)
            return
        result = fn(payload)
        if not isinstance(result, dict):
            raise TypeError("set_pixel_workbench_state_payload 必须返回 dict")
        self._send_json(result, status=200)

    def _handle_placement_catalog(self) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "error": "bridge not ready"}, status=503)
            return
        fn = getattr(self._bridge, "get_project_placements_catalog_payload", None)
        if not callable(fn):
            self._send_json({"ok": False, "error": "bridge missing get_project_placements_catalog_payload"}, status=503)
            return
        result = fn()
        if not isinstance(result, dict):
            raise TypeError("get_project_placements_catalog_payload 必须返回 dict")
        self._send_json(result, status=200)

    def _handle_placement_get(self, query_text: str) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "error": "bridge not ready"}, status=503)
            return
        query = parse_qs(query_text or "")
        rel_path = (query.get("rel_path", [""])[0] or "").strip()
        if not rel_path:
            self._send_json({"ok": False, "error": "rel_path is required"}, status=400)
            return
        fn = getattr(self._bridge, "read_project_placement_payload", None)
        if not callable(fn):
            self._send_json({"ok": False, "error": "bridge missing read_project_placement_payload"}, status=503)
            return
        result = fn(rel_path=rel_path)
        if not isinstance(result, dict):
            raise TypeError("read_project_placement_payload 必须返回 dict")
        self._send_json(result, status=200)

    def _handle_entities_new(self) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "error": "bridge not ready"}, status=503)
            return
        payload = self._read_json_body()
        fn = getattr(self._bridge, "create_blank_entity", None)
        if not callable(fn):
            self._send_json({"ok": False, "error": "bridge missing create_blank_entity"}, status=503)
            return
        result = fn(payload)
        if not isinstance(result, dict):
            raise TypeError("create_blank_entity 必须返回 dict")
        self._send_json(result, status=200)

    def _handle_entities_save_as(self) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "error": "bridge not ready"}, status=503)
            return
        payload = self._read_json_body()
        fn = getattr(self._bridge, "save_as_new_entity", None)
        if not callable(fn):
            self._send_json({"ok": False, "error": "bridge missing save_as_new_entity"}, status=503)
            return
        result = fn(payload)
        if not isinstance(result, dict):
            raise TypeError("save_as_new_entity 必须返回 dict")
        self._send_json(result, status=200)

    def _handle_entities_delete(self) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "error": "bridge not ready"}, status=503)
            return
        payload = self._read_json_body()
        fn = getattr(self._bridge, "delete_entity", None)
        if not callable(fn):
            self._send_json({"ok": False, "error": "bridge missing delete_entity"}, status=503)
            return
        result = fn(payload)
        if not isinstance(result, dict):
            raise TypeError("delete_entity 必须返回 dict")
        self._send_json(result, status=200)

    def _handle_entities_rename(self) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "error": "bridge not ready"}, status=503)
            return
        payload = self._read_json_body()
        fn = getattr(self._bridge, "rename_entity", None)
        if not callable(fn):
            self._send_json({"ok": False, "error": "bridge missing rename_entity"}, status=503)
            return
        result = fn(payload)
        if not isinstance(result, dict):
            raise TypeError("rename_entity 必须返回 dict")
        self._send_json(result, status=200)

    def _handle_entities_duplicate(self) -> None:
        if self._bridge is None:
            self._send_json({"ok": False, "error": "bridge not ready"}, status=503)
            return
        payload = self._read_json_body()
        fn = getattr(self._bridge, "duplicate_entity", None)
        if not callable(fn):
            self._send_json({"ok": False, "error": "bridge missing duplicate_entity"}, status=503)
            return
        result = fn(payload)
        if not isinstance(result, dict):
            raise TypeError("duplicate_entity 必须返回 dict")
        self._send_json(result, status=200)

    def _handle_perfect_pixel(self) -> None:
        from .pixel_art import refine_image_data_url_with_perfect_pixel

        payload = self._read_json_body()
        image_data_url = str(payload.get("image_data_url") or "").strip()
        sample_method = str(payload.get("sample_method") or "center").strip() or "center"
        refine_raw = payload.get("refine_intensity", 0.30)
        if isinstance(refine_raw, (int, float)) and not isinstance(refine_raw, bool):
            refine_intensity = float(refine_raw)
        else:
            refine_intensity = float(str(refine_raw))
        fix_square = bool(payload.get("fix_square", True))

        # 调色板预量化：前端传入支持色列表，后端在 PerfectPixel 之前统一颜色
        palette_raw = payload.get("palette_hex")
        palette_hex: list[str] | None = None
        if isinstance(palette_raw, list) and palette_raw:
            palette_hex = [str(c).strip() for c in palette_raw if str(c).strip()]

        result = refine_image_data_url_with_perfect_pixel(
            image_data_url=image_data_url,
            sample_method=sample_method,
            refine_intensity=refine_intensity,
            fix_square=fix_square,
            palette_hex=palette_hex,
        )
        status = 200 if bool(result.get("ok", True)) else 400
        self._send_json(result, status=status)

    def _handle_frontend_log(self) -> None:
        payload = self._read_json_body()
        level = str(payload.get("level", "ERROR") or "ERROR").strip().upper()
        kind = str(payload.get("kind", "") or "").strip()
        message = str(payload.get("message", "") or "").strip()
        href = str(payload.get("href", "") or "").strip()
        filename = str(payload.get("filename", "") or "").strip()
        lineno = int(payload.get("lineno", 0) or 0)
        colno = int(payload.get("colno", 0) or 0)
        stack = str(payload.get("stack", "") or "")

        prefix = f"[shape_editor][frontend][{level}]"
        if kind:
            prefix = f"{prefix}[{kind}]"

        loc = ""
        if filename:
            loc = f"{filename}:{lineno}:{colno}"
        elif href:
            loc = href

        if loc:
            print(f"{prefix} {message} @ {loc}")
        else:
            print(f"{prefix} {message}")

        if stack.strip():
            # 前端已截断，这里再做一次上限保护，避免刷屏
            text = stack.strip()
            if len(text) > 8000:
                text = text[:8000] + "…(truncated)"
            print(text)

        self._send_json({"ok": True}, status=200)

