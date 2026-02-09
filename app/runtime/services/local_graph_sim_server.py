from __future__ import annotations

import functools
import http.server
import os
import socket
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.runtime.services.local_graph_sim_server_html import (
    _build_layout_html_map,
    _extract_lv_defaults_from_ui_html,
    _extract_merged_lv_defaults,
)
from app.runtime.services.local_graph_sim_server_http import _LocalSimRequestHandler
from app.runtime.services.local_graph_sim_server_web_assets import ensure_local_sim_web_assets_exist
from app.runtime.services.local_graph_simulator import (
    GraphMountSpec,
    LocalGraphSimResourceMountSpec,
    LocalGraphSimSession,
    build_local_graph_sim_session,
    stable_layout_index_from_html_stem,
)

_DEFAULT_LOCAL_HTTP_PORT = 17890
_LOCAL_HTTP_PORT_ENV = "AYAYA_LOCAL_HTTP_PORT"
_LOCAL_HTTP_PORT_ENV_ALIAS = "AYAYA_LOCAL_SIM_PORT"


def _parse_preferred_local_http_port() -> int:
    for env_name in (_LOCAL_HTTP_PORT_ENV_ALIAS, _LOCAL_HTTP_PORT_ENV):
        raw = str(os.environ.get(env_name, "") or "").strip()
        if raw.isdigit():
            value = int(raw)
            if 0 <= value <= 65535:
                return int(value)
    return int(_DEFAULT_LOCAL_HTTP_PORT)


def get_preferred_local_sim_http_port() -> int:
    """返回本地测试 HTTP server 的“首选端口”。

    说明：
    - 默认端口为 17890（与 UI Workbench / shape-editor 一致）；
    - 可通过环境变量 `AYAYA_LOCAL_HTTP_PORT` 覆盖；
    - 兼容 `AYAYA_LOCAL_SIM_PORT` 作为别名覆盖（优先级更高）；
    - 返回值允许为 0（表示“让系统分配临时端口”）。
    """
    return int(_parse_preferred_local_http_port())


def _is_port_listening(*, host: str, port: int) -> bool:
    if port <= 0:
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.05)
        return sock.connect_ex((host, int(port))) == 0


def _choose_local_http_port(*, host: str, preferred_port: int, scan_count: int = 50) -> int:
    """
    端口策略（与 UI Workbench / shape-editor 一致）：
    - 优先使用固定端口（默认 17890，可用环境变量 AYAYA_LOCAL_HTTP_PORT 覆盖；兼容 AYAYA_LOCAL_SIM_PORT 别名）
    - 若端口已被占用（已有服务在监听），则向上顺延扫描一段端口
    - 扫描不到则回退为 0（让系统分配临时端口）
    """
    preferred = int(preferred_port) if int(preferred_port) > 0 else int(get_preferred_local_sim_http_port())
    if preferred <= 0:
        return 0
    max_port = min(65535, preferred + max(1, int(scan_count)))
    for port in range(preferred, max_port + 1):
        if not _is_port_listening(host=host, port=port):
            return int(port)
    return 0


@dataclass(slots=True)
class LocalGraphSimServerConfig:
    workspace_root: Path | None
    graph_code_file: Path
    ui_html_file: Path
    owner_entity_name: str = "自身实体"
    player_entity_name: str = "玩家1"
    present_player_count: int = 1
    host: str = "127.0.0.1"
    port: int = 0
    auto_emit_signal_id: str = ""
    auto_emit_signal_params: dict[str, Any] = field(default_factory=dict)
    extra_graph_mounts: list[GraphMountSpec] = field(default_factory=list)
    resource_mounts: list[LocalGraphSimResourceMountSpec] = field(default_factory=list)


class _LocalSimThreadingHttpServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    # Windows 下 `SO_REUSEADDR` 可能导致“多个进程同时绑定同一端口”，从而出现请求被随机分发、
    # “一键重启 404 / 状态离线”等诡异现象；因此优先使用独占绑定。
    #
    # 非 Windows（无 SO_EXCLUSIVEADDRUSE）时允许复用地址，便于快速 stop/start。
    allow_reuse_address = not hasattr(socket, "SO_EXCLUSIVEADDRUSE")

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class LocalGraphSimServer:
    """本地测试 HTTP Server（浏览器预览 + 点击注入 + UI patch 回显）。"""

    def __init__(self, config: LocalGraphSimServerConfig) -> None:
        self._config = config
        self._lock = threading.RLock()
        self._session: LocalGraphSimSession | None = None
        self._bootstrap_patches: list[dict[str, Any]] = []
        self._layout_html_by_index: dict[int, Path] = {}
        self._current_layout_index: int = 0
        self._auto_emit_signal_pending: bool = False
        # 会话代数：用于避免“重启后旧线程写入 bootstrap_patches / 清 pending”造成状态污染
        self._session_generation: int = 0
        self._httpd: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int = 0

    @property
    def session(self) -> LocalGraphSimSession:
        if self._session is None:
            raise RuntimeError("LocalGraphSimSession 未初始化")
        return self._session

    def start(self) -> None:
        if self._httpd is not None:
            return

        ensure_local_sim_web_assets_exist()

        ui_file = Path(self._config.ui_html_file).resolve()
        if not ui_file.is_file():
            raise FileNotFoundError(str(ui_file))

        self._bootstrap_patches = []
        self._auto_emit_signal_pending = False
        self._layout_html_by_index = _build_layout_html_map(ui_file)
        self._current_layout_index = int(stable_layout_index_from_html_stem(ui_file.stem))

        self._session = build_local_graph_sim_session(
            workspace_root=self._config.workspace_root,
            graph_code_file=Path(self._config.graph_code_file).resolve(),
            owner_entity_name=self._config.owner_entity_name,
            player_entity_name=self._config.player_entity_name,
            present_player_count=int(self._config.present_player_count),
            extra_graph_mounts=list(self._config.extra_graph_mounts or []),
            resource_mounts=list(self._config.resource_mounts or []),
        )
        self._session_generation += 1

        # UI HTML 默认值：用于在本地测试中补齐 lv.* 对应的“关卡实体自定义变量”默认结构，
        # 避免节点图对字典写 key 时因为变量不存在而变成 no-op（导致倒计时/文本不刷新）。
        lv_defaults = _extract_merged_lv_defaults(entry_ui_file=ui_file, layout_html_by_index=self._layout_html_by_index)
        if lv_defaults:
            self._session.game.set_ui_lv_defaults(lv_defaults)

        handler_factory = functools.partial(
            _LocalSimRequestHandler,
            ui_html_file=ui_file,
            server_impl=self,
        )
        host = str(self._config.host or "127.0.0.1")
        preferred_port = int(self._config.port or 0)
        if preferred_port < 0:
            preferred_port = 0
        port = _choose_local_http_port(host=host, preferred_port=preferred_port)
        httpd = _LocalSimThreadingHttpServer((host, port), handler_factory)
        self._httpd = httpd
        self.port = int(httpd.server_address[1])
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        self._thread = thread
        thread.start()

        auto_sid = str(self._config.auto_emit_signal_id or "").strip()
        if auto_sid:
            self._auto_emit_signal_pending = True
            session_gen = int(self._session_generation)

            def _emit_auto_signal() -> None:
                with self._lock:
                    if session_gen != self._session_generation:
                        return
                    patches = self.session.emit_signal(
                        signal_id=auto_sid,
                        params=dict(self._config.auto_emit_signal_params or {}),
                    )
                    self._bootstrap_patches = list(patches)
                    self._capture_layout_switch_from_patches(patches)
                    self._auto_emit_signal_pending = False

            threading.Thread(target=_emit_auto_signal, daemon=True).start()

    def restart(self) -> None:
        """重建模拟会话（相当于“重新启动”本地测试），并重置面板相关状态。"""
        if self._httpd is None:
            raise RuntimeError("server 未启动")

        ui_file = Path(self._config.ui_html_file).resolve()
        if not ui_file.is_file():
            raise FileNotFoundError(str(ui_file))

        with self._lock:
            self._bootstrap_patches = []
            self._auto_emit_signal_pending = False
            self._layout_html_by_index = _build_layout_html_map(ui_file)
            self._current_layout_index = int(stable_layout_index_from_html_stem(ui_file.stem))

            self._session = build_local_graph_sim_session(
                workspace_root=self._config.workspace_root,
                graph_code_file=Path(self._config.graph_code_file).resolve(),
                owner_entity_name=self._config.owner_entity_name,
                player_entity_name=self._config.player_entity_name,
                present_player_count=int(self._config.present_player_count),
                extra_graph_mounts=list(self._config.extra_graph_mounts or []),
                resource_mounts=list(self._config.resource_mounts or []),
            )
            self._session_generation += 1

            lv_defaults = _extract_merged_lv_defaults(entry_ui_file=ui_file, layout_html_by_index=self._layout_html_by_index)
            if lv_defaults:
                self._session.game.set_ui_lv_defaults(lv_defaults)

            auto_sid = str(self._config.auto_emit_signal_id or "").strip()
            if not auto_sid:
                return

            self._auto_emit_signal_pending = True
            session_gen = int(self._session_generation)

            def _emit_auto_signal() -> None:
                with self._lock:
                    if session_gen != self._session_generation:
                        return
                    patches = self.session.emit_signal(
                        signal_id=auto_sid,
                        params=dict(self._config.auto_emit_signal_params or {}),
                    )
                    self._bootstrap_patches = list(patches)
                    self._capture_layout_switch_from_patches(patches)
                    self._auto_emit_signal_pending = False

            threading.Thread(target=_emit_auto_signal, daemon=True).start()

    def stop(self) -> None:
        httpd = self._httpd
        thread = self._thread
        if httpd is None:
            return
        httpd.shutdown()
        httpd.server_close()
        self._httpd = None
        self._thread = None
        self.port = 0
        if thread is not None:
            thread.join(timeout=1.0)

    def drain_bootstrap_patches(self) -> list[dict[str, Any]]:
        with self._lock:
            patches = list(self._bootstrap_patches)
            self._bootstrap_patches = []
            return patches

    @property
    def current_layout_index(self) -> int:
        return int(self._current_layout_index)

    def set_current_layout_index(self, layout_index: int) -> None:
        self._current_layout_index = int(layout_index)

    def get_layout_html_file(self, layout_index: int) -> Path | None:
        return self._layout_html_by_index.get(int(layout_index))

    def get_all_layouts(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for idx, path in sorted(self._layout_html_by_index.items(), key=lambda kv: (kv[0], str(kv[1]))):
            items.append(
                {
                    "layout_index": int(idx),
                    "html_stem": str(Path(path).stem),
                    "html_file": str(Path(path)),
                }
            )
        return items

    def _capture_layout_switch_from_patches(self, patches: list[dict[str, Any]]) -> None:
        for p in patches:
            if not isinstance(p, dict):
                continue
            if str(p.get("op") or "") != "switch_layout":
                continue
            idx = p.get("layout_index", None)
            if isinstance(idx, int):
                self._current_layout_index = int(idx)

    def get_url(self) -> str:
        if self.port <= 0:
            raise RuntimeError("server 未启动")
        return f"http://{self._config.host}:{self.port}/"


__all__ = [
    "get_preferred_local_sim_http_port",
    "LocalGraphSimServerConfig",
    "LocalGraphSimServer",
]

