from __future__ import annotations

from pathlib import Path

_WEB_DIR_NAME = "local_graph_sim_web"


def get_local_sim_web_dir() -> Path:
    """返回本地测试监控面板/注入脚本所在目录。"""
    return Path(__file__).resolve().parent / _WEB_DIR_NAME


def get_monitor_html_file() -> Path:
    return get_local_sim_web_dir() / "monitor.html"


def get_local_sim_js_file() -> Path:
    return get_local_sim_web_dir() / "local_sim.js"


def ensure_local_sim_web_assets_exist() -> None:
    """启动前校验静态资源存在（避免服务启动后访问才炸）。"""
    for p in (get_monitor_html_file(), get_local_sim_js_file()):
        if not p.is_file():
            raise FileNotFoundError(str(p))


def read_monitor_html_text() -> str:
    return get_monitor_html_file().read_text(encoding="utf-8")


def read_local_sim_js_text() -> str:
    return get_local_sim_js_file().read_text(encoding="utf-8")

