from __future__ import annotations

import functools
import http.server
import json
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def _list_html_files(dir_path: Path) -> list[str]:
    if not dir_path.is_dir():
        return []
    out: list[str] = []
    for p in dir_path.iterdir():
        if not p.is_file():
            continue
        name = p.name
        if name.lower().endswith(".html") or name.lower().endswith(".htm"):
            out.append(name)
    out.sort(key=lambda x: x.lower())
    return out


def _read_text_utf8(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def start_ui_preview_mock_server(
    *,
    repo_root: Path,
    package_id: str,
    host: str = "127.0.0.1",
    port: int = 0,
) -> tuple[http.server.ThreadingHTTPServer, int]:
    """
    启动一个“脱离主程序”的 mock /api/ui_converter 服务，使 ui_app_ui_preview.html 可直接运行并读取项目 UI源码。

    设计目标：
    - 只覆盖预览页所需的最小 API：
      - GET  /api/ui_converter/status
      - GET  /api/ui_converter/ui_source_catalog
      - GET  /api/ui_converter/ui_source?scope=...&rel_path=...
      - GET  /api/ui_converter/ui_source_raw?scope=...&rel_path=...
    - 静态资源：直接从 `assets/ui_workbench/` 提供（强制 JS MIME + no-store）。
    - 不做 try/except 吞错：出错直接抛出，便于测试定位。
    """

    repo_root = Path(repo_root).resolve()
    package_id = str(package_id).strip()
    assert package_id, "package_id is required"

    workbench_dir = (repo_root / "assets" / "ui_workbench").resolve()
    assert workbench_dir.is_dir(), f"workbench dir not found: {workbench_dir}"
    assert (workbench_dir / "ui_app_ui_preview.html").is_file(), f"ui_app_ui_preview.html missing: {workbench_dir}"

    project_ui_dir = (repo_root / "assets" / "资源库" / "项目存档" / package_id / "管理配置" / "UI源码").resolve()
    shared_ui_dir = (repo_root / "assets" / "资源库" / "共享" / "管理配置" / "UI源码").resolve()

    # 预览页会尝试走 /api/ui_converter/base_gil_cache 做跨端口缓存（即便 mock status=未连接，也可能被某些路径触发）。
    # 因此这里实现一个最小可用的内存缓存，避免返回 JSON 导致前端误把“错误响应”当二进制 GIL 还原。
    base_gil_cache: dict[str, object] = {
        "name_b64": "",
        "last_modified": 0,
        "bytes": b"",
    }

    def _resolve_ui_source_path(scope: str, rel_path: str) -> Path:
        s = str(scope or "project").strip()
        rp = str(rel_path or "").replace("\\", "/").strip().lstrip("/")
        assert rp, "rel_path is required"
        if "/" in rp:
            # 预览页的 rel_path 目前只应为文件名；禁止目录穿越
            raise ValueError(f"rel_path must be a file name: {rp}")
        if s == "shared":
            return (shared_ui_dir / rp).resolve()
        return (project_ui_dir / rp).resolve()

    def _json_response(handler: http.server.BaseHTTPRequestHandler, obj: dict, status_code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        handler.send_response(status_code)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(body)

    class _Handler(http.server.SimpleHTTPRequestHandler):
        # 强制 MIME：避免 Windows 注册表导致 `.js -> text/plain`（ESM 白屏）
        extensions_map = http.server.SimpleHTTPRequestHandler.extensions_map | {
            ".js": "text/javascript; charset=utf-8",
            ".mjs": "text/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".map": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
        }

        def end_headers(self) -> None:
            path = str(getattr(self, "path", "") or "").lower()
            if (
                path.endswith(".html")
                or path.endswith(".js")
                or path.endswith(".mjs")
                or path.endswith(".json")
                or path.endswith(".map")
            ):
                self.send_header("Cache-Control", "no-store")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
            super().end_headers()

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path or ""
            if not path.startswith("/api/ui_converter/"):
                return super().do_GET()

            q = parse_qs(parsed.query or "")

            if path == "/api/ui_converter/status":
                return _json_response(
                    self,
                    {
                        "ok": True,
                        "connected": False,
                        "current_package_id": package_id,
                        "features": {"mock_api": True},
                        "workbench_dir": str(workbench_dir),
                        "suggested_base_gil_path": "",
                        "suggested_gil_paths": [],
                    },
                )

            if path == "/api/ui_converter/ui_source_catalog":
                project_files = _list_html_files(project_ui_dir)
                shared_files = _list_html_files(shared_ui_dir)
                items = []
                for name in project_files:
                    items.append({"scope": "project", "file_name": name, "is_shared": False})
                for name in shared_files:
                    items.append({"scope": "shared", "file_name": name, "is_shared": True})
                return _json_response(self, {"ok": True, "items": items, "current_package_id": package_id})

            if path == "/api/ui_converter/ui_source":
                scope = (q.get("scope") or ["project"])[0]
                rel_path = (q.get("rel_path") or [""])[0]
                file_path = _resolve_ui_source_path(scope, rel_path)
                if not file_path.is_file():
                    return _json_response(self, {"ok": False, "error": f"file not found: {file_path}"}, status_code=404)
                return _json_response(
                    self,
                    {
                        "ok": True,
                        "scope": str(scope),
                        "rel_path": str(rel_path),
                        "file_name": str(rel_path),
                        "is_shared": (str(scope) == "shared"),
                        "content": _read_text_utf8(file_path),
                    },
                )

            if path == "/api/ui_converter/ui_source_raw":
                scope = (q.get("scope") or ["project"])[0]
                rel_path = (q.get("rel_path") or [""])[0]
                file_path = _resolve_ui_source_path(scope, rel_path)
                if not file_path.is_file():
                    return _json_response(self, {"ok": False, "error": f"file not found: {file_path}"}, status_code=404)
                body = file_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return

            if path == "/api/ui_converter/base_gil_cache":
                b = base_gil_cache.get("bytes") or b""
                if not isinstance(b, (bytes, bytearray)) or len(b) <= 0:
                    return _json_response(self, {"ok": False, "error": "mock: base_gil_cache empty"}, status_code=404)
                name_b64 = str(base_gil_cache.get("name_b64") or "")
                lm = int(base_gil_cache.get("last_modified") or 0)
                body = bytes(b)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                if name_b64:
                    self.send_header("X-Ui-Base-Gil-Name-B64", name_b64)
                self.send_header("X-Ui-Base-Gil-Last-Modified", str(lm))
                self.end_headers()
                self.wfile.write(body)
                return

            if path in ("/api/ui_converter/export_gil", "/api/ui_converter/export_gia"):
                return _json_response(self, {"ok": False, "error": "mock: export not supported"})

            return _json_response(self, {"ok": False, "error": f"mock api not implemented: {path}"}, status_code=404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path or ""
            if not path.startswith("/api/ui_converter/"):
                self.send_response(404)
                self.end_headers()
                return
            if path == "/api/ui_converter/base_gil_cache":
                name_b64 = str(self.headers.get("X-Ui-Base-Gil-Name-B64", "") or "").strip()
                lm_text = str(self.headers.get("X-Ui-Base-Gil-Last-Modified", "") or "").strip()
                lm = int(lm_text) if lm_text.isdigit() else 0
                length = int(self.headers.get("Content-Length", "0") or "0")
                body = self.rfile.read(length) if length > 0 else b""
                if not body:
                    return _json_response(self, {"ok": False, "error": "mock: empty base gil body"}, status_code=400)
                base_gil_cache["name_b64"] = name_b64
                base_gil_cache["last_modified"] = lm
                base_gil_cache["bytes"] = body
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            if path in ("/api/ui_converter/export_gil", "/api/ui_converter/export_gia"):
                return _json_response(self, {"ok": False, "error": "mock: POST not supported"})
            return _json_response(self, {"ok": False, "error": f"mock api not implemented: {path}"}, status_code=404)

    handler_class = functools.partial(_Handler, directory=str(workbench_dir))
    httpd = http.server.ThreadingHTTPServer((host, int(port)), handler_class)
    chosen_port = int(httpd.server_address[1])
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, chosen_port

