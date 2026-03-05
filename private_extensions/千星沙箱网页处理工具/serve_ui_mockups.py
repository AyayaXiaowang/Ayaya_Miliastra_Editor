"""
本地静态服务器（仅标准库）

用途：
- 在浏览器里以 http://127.0.0.1:<port>/ 的方式打开 **assets/ui_workbench/** 下的静态页面，
  避免 file:// 模式下的资源引用/同源限制带来的问题。

使用方式（在项目根目录执行）：
    python 千星沙箱网页处理工具\\serve_ui_mockups.py
    python 千星沙箱网页处理工具\\serve_ui_mockups.py --port 8001
    python 千星沙箱网页处理工具\\serve_ui_mockups.py --no-open
"""

import argparse
import functools
import http.server
import sys
import webbrowser
from pathlib import Path


def _ensure_backend_importable() -> None:
    # 兼容两种运行方式：
    # - 直接运行：python private_extensions/千星沙箱网页处理工具/serve_ui_mockups.py
    # - 模块运行：python -m private_extensions.千星沙箱网页处理工具.serve_ui_mockups
    #
    # 模块运行时 sys.path 通常只有 repo_root，无法直接 import `ui_workbench_backend`，
    # 因此这里与 `plugin.py` 保持一致：把插件目录注入 sys.path 作为“后端包根”。
    plugin_dir = Path(__file__).resolve().parent
    plugin_dir_text = str(plugin_dir)
    if plugin_dir_text not in sys.path:
        sys.path.insert(0, plugin_dir_text)


_ensure_backend_importable()

from ui_workbench_backend.http_server import StaticRequestHandler  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description="Serve 千星沙箱网页处理工具 as a local static site.")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=8000, help="监听端口，默认 8000")
    parser.add_argument("--open", dest="should_open_browser", action="store_true", help="启动后自动打开预览页面（默认开启）")
    parser.add_argument("--no-open", dest="should_open_browser", action="store_false", help="启动后不自动打开浏览器")
    parser.set_defaults(should_open_browser=True)
    return parser.parse_args()


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "assets").is_dir() and (parent / "app").is_dir() and (parent / "engine").is_dir():
            return parent
    raise RuntimeError(f"无法定位仓库根目录（from={here}）")


def main():
    args = parse_args()

    repo_root = _find_repo_root()
    ui_mockups_dir = (repo_root / "assets" / "ui_workbench").resolve()
    if not ui_mockups_dir.is_dir():
        raise FileNotFoundError(str(ui_mockups_dir))
    if not (ui_mockups_dir / "ui_app_ui_preview.html").is_file():
        raise FileNotFoundError(str((ui_mockups_dir / "ui_app_ui_preview.html").resolve()))

    handler_class = functools.partial(StaticRequestHandler, directory=str(ui_mockups_dir))
    httpd = http.server.ThreadingHTTPServer((args.host, args.port), handler_class)

    actual_port = int(httpd.server_address[1])
    base_url = f"http://{args.host}:{actual_port}"
    entry_url = base_url + "/ui_app_ui_preview.html"

    print("静态服务器已启动：")
    print("  - 根目录:", ui_mockups_dir)
    print("  - 地址:", base_url)
    print("  - 预览页:", entry_url)
    print("按 Ctrl+C 结束。")

    if args.should_open_browser:
        webbrowser.open(entry_url)

    httpd.serve_forever()


if __name__ == "__main__":
    main()


