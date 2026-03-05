"""
离线测试服务器（标准库）：静态资源 + mock /api/ui_converter

用途：
- 不启动主程序，也能直接打开 `ui_app_ui_preview.html`，并读取指定项目存档下的 `管理配置/UI源码/*.html`；
- 用于复现/验证“画布点选 -> 左下导出控件联动”的行为（尤其是选择映射问题）。

使用方式（在仓库根目录执行）：
  python -X utf8 -m private_extensions.千星沙箱网页处理工具.serve_ui_preview_mock_api --package-id 测试项目

也支持直接运行：
  python private_extensions/千星沙箱网页处理工具/serve_ui_preview_mock_api.py --package-id 测试项目

说明：
- 只实现预览页所需的最小 API：
  - GET /api/ui_converter/status
  - GET /api/ui_converter/ui_source_catalog
  - GET /api/ui_converter/ui_source?scope=...&rel_path=...
  - GET /api/ui_converter/ui_source_raw?scope=...&rel_path=...
- 导出/写回相关接口在 mock 环境下返回“not supported”（避免误导）。
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import sys
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def _ensure_backend_importable() -> None:
    # 兼容：
    # - python private_extensions/千星沙箱网页处理工具/serve_ui_preview_mock_api.py
    # - python -m private_extensions.千星沙箱网页处理工具.serve_ui_preview_mock_api
    plugin_dir = Path(__file__).resolve().parent
    plugin_dir_text = str(plugin_dir)
    if plugin_dir_text not in sys.path:
        sys.path.insert(0, plugin_dir_text)


_ensure_backend_importable()

from ui_workbench_backend.http_server import StaticRequestHandler  # noqa: E402


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "assets").is_dir() and (parent / "app").is_dir() and (parent / "engine").is_dir():
            return parent
    raise RuntimeError(f"无法定位仓库根目录（from={here}）")


def _list_html_files(dir_path: Path) -> list[str]:
    if not dir_path.is_dir():
        return []
    out: list[str] = []
    for p in dir_path.iterdir():
        if not p.is_file():
            continue
        if p.name.lower().endswith(".html") or p.name.lower().endswith(".htm"):
            out.append(p.name)
    out.sort(key=lambda x: x.lower())
    return out


def _json_bytes(obj: dict) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve ui_app_ui_preview.html with mock /api/ui_converter.")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=8000, help="监听端口，默认 8000")
    parser.add_argument("--package-id", default="测试项目", help="项目存档 package_id，默认 测试项目")
    parser.add_argument("--open", dest="should_open_browser", action="store_true", help="启动后自动打开预览页面（默认开启）")
    parser.add_argument("--no-open", dest="should_open_browser", action="store_false", help="启动后不自动打开浏览器")
    parser.set_defaults(should_open_browser=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = _find_repo_root()
    package_id = str(args.package_id or "").strip()
    if not package_id:
        raise ValueError("--package-id 不能为空")

    # 静态前端统一使用 assets/ui_workbench（与测试/插件保持一致）
    workbench_dir = (repo_root / "assets" / "ui_workbench").resolve()
    if not workbench_dir.is_dir():
        raise FileNotFoundError(f"workbench dir not found: {workbench_dir}")

    project_ui_dir = (repo_root / "assets" / "资源库" / "项目存档" / package_id / "管理配置" / "UI源码").resolve()
    shared_ui_dir = (repo_root / "assets" / "资源库" / "共享" / "管理配置" / "UI源码").resolve()

    def _resolve_ui_source_path(scope: str, rel_path: str) -> Path:
        s = str(scope or "project").strip()
        rp = str(rel_path or "").replace("\\", "/").strip().lstrip("/")
        if not rp:
            raise ValueError("rel_path is required")
        if "/" in rp:
            raise ValueError(f"rel_path must be a file name: {rp}")
        if s == "shared":
            return (shared_ui_dir / rp).resolve()
        return (project_ui_dir / rp).resolve()

    class _Handler(StaticRequestHandler):
        def _send_json(self, obj: dict, status_code: int = 200) -> None:
            body = _json_bytes(obj)
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path or ""
            if not path.startswith("/api/ui_converter/"):
                return super().do_GET()

            q = parse_qs(parsed.query or "")

            if path == "/api/ui_converter/status":
                return self._send_json(
                    {
                        "ok": True,
                        "current_package_id": package_id,
                        "features": {"mock_api": True},
                        "workbench_dir": str(workbench_dir),
                        "suggested_base_gil_path": "",
                        "suggested_gil_paths": [],
                    }
                )

            if path == "/api/ui_converter/ui_source_catalog":
                items = []
                for name in _list_html_files(project_ui_dir):
                    items.append({"scope": "project", "file_name": name, "is_shared": False})
                for name in _list_html_files(shared_ui_dir):
                    items.append({"scope": "shared", "file_name": name, "is_shared": True})
                return self._send_json({"ok": True, "items": items, "current_package_id": package_id})

            if path == "/api/ui_converter/ui_source":
                scope = (q.get("scope") or ["project"])[0]
                rel_path = (q.get("rel_path") or [""])[0]
                file_path = _resolve_ui_source_path(scope, rel_path)
                if not file_path.is_file():
                    return self._send_json({"ok": False, "error": f"file not found: {file_path}"}, status_code=404)
                return self._send_json(
                    {
                        "ok": True,
                        "scope": str(scope),
                        "rel_path": str(rel_path),
                        "file_name": str(rel_path),
                        "is_shared": (str(scope) == "shared"),
                        "content": file_path.read_text(encoding="utf-8"),
                    }
                )

            if path == "/api/ui_converter/ui_source_raw":
                scope = (q.get("scope") or ["project"])[0]
                rel_path = (q.get("rel_path") or [""])[0]
                file_path = _resolve_ui_source_path(scope, rel_path)
                if not file_path.is_file():
                    return self._send_json({"ok": False, "error": f"file not found: {file_path}"}, status_code=404)
                body = file_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.end_headers()
                self.wfile.write(body)
                return

            if path == "/api/ui_converter/base_gil_cache":
                return self._send_json({"ok": False, "error": "mock: base_gil_cache not supported"})

            if path in ("/api/ui_converter/export_gil", "/api/ui_converter/export_gia"):
                return self._send_json({"ok": False, "error": "mock: export not supported"})

            return self._send_json({"ok": False, "error": f"mock api not implemented: {path}"}, status_code=404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path or ""
            if not path.startswith("/api/ui_converter/"):
                self.send_response(404)
                self.end_headers()
                return
            if path in ("/api/ui_converter/export_gil", "/api/ui_converter/export_gia", "/api/ui_converter/base_gil_cache"):
                return self._send_json({"ok": False, "error": "mock: POST not supported"})
            return self._send_json({"ok": False, "error": f"mock api not implemented: {path}"}, status_code=404)

    handler_class = functools.partial(_Handler, directory=str(workbench_dir))
    httpd = http.server.ThreadingHTTPServer((args.host, args.port), handler_class)
    base_url = f"http://{args.host}:{int(httpd.server_address[1])}"
    entry_url = base_url + "/ui_app_ui_preview.html"

    print("Mock UI Preview Server 已启动：")
    print("  - repo_root:", repo_root)
    print("  - workbench_dir:", workbench_dir)
    print("  - project_ui_dir:", project_ui_dir)
    print("  - shared_ui_dir:", shared_ui_dir)
    print("  - address:", base_url)
    print("  - entry:", entry_url)
    print("按 Ctrl+C 结束。")

    if args.should_open_browser:
        webbrowser.open(entry_url)

    httpd.serve_forever()


if __name__ == "__main__":
    main()

