from __future__ import annotations

from pathlib import Path

_WEB_DIR_NAME = "local_graph_sim_web"
_MONITOR_JS_PARTS = (
    "monitor_parts/monitor_00_core.js",
    "monitor_parts/monitor_10_snapshot_assertions.js",
    "monitor_parts/monitor_20_pytest_gen.js",
    "monitor_parts/monitor_30_ui_contract_api.js",
    "monitor_parts/monitor_40_ui_status_init.js",
)


def get_local_sim_web_dir() -> Path:
    """返回本地测试监控面板/注入脚本所在目录。"""
    return Path(__file__).resolve().parent / _WEB_DIR_NAME


def get_monitor_html_file() -> Path:
    return get_local_sim_web_dir() / "monitor.html"


def get_local_sim_js_file() -> Path:
    return get_local_sim_web_dir() / "local_sim.js"


def get_local_sim_shared_js_file() -> Path:
    return get_local_sim_web_dir() / "local_sim_shared.js"


def get_monitor_js_file() -> Path:
    return get_local_sim_web_dir() / "monitor.js"


def get_monitor_js_part_files() -> tuple[Path, ...]:
    """返回 monitor.js 的拆分片段文件列表（按顺序拼接即为完整脚本）。"""
    root = get_local_sim_web_dir()
    return tuple((root / rel) for rel in _MONITOR_JS_PARTS)


def get_local_sim_flatten_overlay_module_file() -> Path:
    return get_local_sim_web_dir() / "local_sim_flatten_overlay.mjs"


def ensure_local_sim_web_assets_exist() -> None:
    """启动前校验静态资源存在（避免服务启动后访问才炸）。"""
    # 注意：/monitor.js 由多个 part 拼接生成（见 read_monitor_js_text）。
    for p in (
        get_monitor_html_file(),
        *get_monitor_js_part_files(),
        get_local_sim_shared_js_file(),
        get_local_sim_js_file(),
        get_local_sim_flatten_overlay_module_file(),
    ):
        if not p.is_file():
            raise FileNotFoundError(str(p))


def read_monitor_html_text() -> str:
    return get_monitor_html_file().read_text(encoding="utf-8")


def read_monitor_js_text() -> str:
    # /monitor.js 由拆分片段按顺序拼接，便于维护与定位。
    parts: list[str] = []
    for p in get_monitor_js_part_files():
        parts.append(p.read_text(encoding="utf-8"))
    return "\n".join(parts) + "\n"


def read_local_sim_shared_js_text() -> str:
    return get_local_sim_shared_js_file().read_text(encoding="utf-8")


def read_local_sim_js_text() -> str:
    return get_local_sim_js_file().read_text(encoding="utf-8")

def read_local_sim_flatten_overlay_module_text() -> str:
    return get_local_sim_flatten_overlay_module_file().read_text(encoding="utf-8")
