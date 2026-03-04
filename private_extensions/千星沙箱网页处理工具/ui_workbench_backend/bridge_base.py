from __future__ import annotations

import hashlib
import json
import os
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from engine.utils.logging.logger import log_info, log_warn


@dataclass(slots=True)
class _ImportResult:
    layout_id: str
    layout_name: str
    template_id: str
    template_name: str
    template_count: int
    widget_count: int


@dataclass(slots=True)
class _ImportBundleResult:
    layout_id: str
    layout_name: str
    template_count: int
    widget_count: int


@dataclass(slots=True)
class _ExportGilResult:
    output_gil_path: str
    output_file_name: str
    report: dict
    download_token: str


@dataclass(slots=True)
class _ExportGiaResult:
    output_gia_path: str
    output_file_name: str
    report: dict
    download_token: str
    output_gil_path: str


class _UiWorkbenchBridgeBase:
    # 进度条颜色（统一调色板 hex，与 ugc_file_tools.ui_patchers.web_ui_import 完全一致）
    _PROGRESSBAR_PALETTE_HEX_WHITE = "#E2DBCE"
    _PROGRESSBAR_PALETTE_HEX_GREEN = "#92CD21"
    _PROGRESSBAR_PALETTE_HEX_YELLOW = "#F3C330"
    _PROGRESSBAR_PALETTE_HEX_BLUE = "#36F3F3"
    _PROGRESSBAR_PALETTE_HEX_RED = "#F47B7B"

    def __init__(self, *, workspace_root: Path, workbench_dir: Path) -> None:
        self._workspace_root = workspace_root
        # workbench_dir：插件目录（后端真源，包含 Python 包与导出子进程入口脚本）
        self._workbench_dir = workbench_dir
        # 静态前端真源：统一指向 assets/ui_workbench（避免插件/测试/离线预览三份前端漂移）
        self._workbench_static_dir = self._resolve_workbench_static_dir(workspace_root=workspace_root, fallback_dir=workbench_dir)
        self._main_window: object | None = None
        self._server: object | None = None
        self._exported_gil_paths_by_token: dict[str, Path] = {}
        self._exported_gia_paths_by_token: dict[str, Path] = {}

    @staticmethod
    def _resolve_workbench_static_dir(*, workspace_root: Path, fallback_dir: Path) -> Path:
        """返回用于静态服务的 Workbench 前端目录。

        约定：源码仓库形态下，前端真源固定为 `assets/ui_workbench/`（单一真源）。

        注意：
        - 私有扩展目录下历史同名的前端文件不再作为运行时真源，避免“插件/测试/离线预览”三份前端漂移。
        - 若在特殊打包/裁剪环境中缺失 `assets/ui_workbench/`，应把该目录一并打包；默认不再静默回退，
          以免出现“打开页面但 JS/样式版本不一致”的隐性问题。
        """
        root = Path(workspace_root).resolve()
        static_dir = (root / "assets" / "ui_workbench").resolve()
        if static_dir.is_dir() and (static_dir / "ui_app_ui_preview.html").is_file():
            return static_dir
        raise FileNotFoundError(
            "UI Workbench 静态前端目录缺失："
            f"{static_dir}（workspace_root={root}）。"
            "请确保仓库包含 assets/ui_workbench/（单一真源）。"
        )

    def get_workbench_backend_dir(self) -> Path:
        """插件后端目录（包含 Python 包与导出子进程入口脚本）。"""
        return Path(self._workbench_dir).resolve()

    def get_workbench_static_dir(self) -> Path:
        """静态前端目录（HTTP server 的 directory 根目录）。"""
        return Path(self._workbench_static_dir).resolve()

    @staticmethod
    def _resolve_default_beyond_local_export_dir() -> Path:
        """
        原神 UGC Beyond 的默认导出目录（Windows）。

        约定路径：
          %USERPROFILE%\\AppData\\LocalLow\\miHoYo\\原神\\BeyondLocal\\Beyond_Local_Export
        """
        return (
            Path.home()
            / "AppData"
            / "LocalLow"
            / "miHoYo"
            / "原神"
            / "BeyondLocal"
            / "Beyond_Local_Export"
        ).resolve()

    # --------------------------------------------------------------------- life-cycle
    def attach_main_window(self, main_window: object) -> None:
        self._main_window = main_window

    def install_entrypoints(self) -> None:
        if self._main_window is None:
            return
        self._ensure_server_running()
        self._inject_left_nav_button()
        self._inject_management_ui_button()

    # --------------------------------------------------------------------- public helpers
    @staticmethod
    def _open_url_or_raise(*, url: str, purpose: str) -> None:
        """打开 URL（Windows 下避免 webbrowser 静默失败）。

        背景：`webbrowser.open(...)` 在部分 Windows 环境会直接返回 False 且无异常，用户体感为“点击无反应”。
        这里明确输出日志，并在失败时使用 `os.startfile(url)` 兜底唤起默认浏览器。
        """
        url_text = str(url or "").strip()
        purpose_text = str(purpose or "").strip() or "open_url"
        if not url_text:
            raise ValueError(f"URL 为空，无法打开：purpose={purpose_text}")

        log_info("[UI-WORKBENCH] open: purpose={} url={}", purpose_text, url_text)
        opened = webbrowser.open(url_text, new=2)
        if opened:
            return

        log_warn("[UI-WORKBENCH] webbrowser.open returned False: purpose={} url={}", purpose_text, url_text)
        if hasattr(os, "startfile"):
            os.startfile(url_text)  # type: ignore[attr-defined]
            return
        raise RuntimeError(f"webbrowser.open returned False and os.startfile unavailable: {url_text}")

    def open_workbench_in_browser(self) -> None:
        # Workbench 页面已下线：保留旧方法名作为兼容别名，统一打开预览页。
        url = self._get_ui_preview_url()
        self._open_url_or_raise(url=url, purpose="ui_preview")

    def open_ui_preview_in_browser(self) -> None:
        url = self._get_ui_preview_url()
        self._open_url_or_raise(url=url, purpose="ui_preview")

    def get_status_payload(self) -> dict:
        main_window = self._main_window
        package_controller = getattr(main_window, "package_controller", None) if main_window is not None else None
        current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        current_package = getattr(package_controller, "current_package", None) if package_controller is not None else None
        current_package_name = getattr(current_package, "name", "") if current_package is not None else ""

        package_id_text = str(current_package_id or "")
        package_name_text = str(current_package_name or "")
        is_global_view = package_id_text == "global_view"

        def _normalize_gil_path(p: str) -> str:
            raw = str(p or "").strip()
            if raw == "":
                return ""
            path = Path(raw).resolve()
            if not path.is_file():
                return ""
            if path.suffix.lower() != ".gil":
                return ""
            return str(path)

        def _try_pick_latest_gil_under_dir(dir_path: Path) -> tuple[str, int] | None:
            """
            在某个 BeyondLocal 根目录下，尽量选出“当前沙箱存档”的 `.gil`：
            - 优先：*/Beyond_Local_Save_Level/*.gil
            - 兜底：任意子目录下的 *.gil（只扫描 1 层 user 目录，避免全量递归过慢）
            返回：(path, mtime_ms)
            """
            root = Path(dir_path).resolve()
            if not root.is_dir():
                return None

            best_path = ""
            best_mtime_ms = 0

            # 只遍历 BeyondLocal 下的一层 user 目录（通常是数字目录）
            for user_dir in root.iterdir():
                if not user_dir.is_dir():
                    continue
                save_level_dir = (user_dir / "Beyond_Local_Save_Level").resolve()
                if save_level_dir.is_dir():
                    for f in save_level_dir.glob("*.gil"):
                        if not f.is_file():
                            continue
                        st = f.stat()
                        m = int(st.st_mtime * 1000)
                        if m > best_mtime_ms:
                            best_mtime_ms = m
                            best_path = str(f.resolve())

            # 兜底：若没找到 Save_Level，就在每个 user 目录下找 *.gil（不递归）
            if best_path == "":
                for user_dir in root.iterdir():
                    if not user_dir.is_dir():
                        continue
                    for f in user_dir.glob("*.gil"):
                        if not f.is_file():
                            continue
                        st = f.stat()
                        m = int(st.st_mtime * 1000)
                        if m > best_mtime_ms:
                            best_mtime_ms = m
                            best_path = str(f.resolve())

            if best_path == "":
                return None
            return (best_path, int(best_mtime_ms))

        # 1) 优先：从 BeyondLocal 中推导“当前沙箱的 gil”（最新保存的那份）
        sandbox_gil_path = ""
        sandbox_gil_mtime_ms = 0
        home = Path.home().resolve()
        for candidate in [
            home / "AppData" / "LocalLow" / "miHoYo" / "原神" / "BeyondLocal",
            home / "AppData" / "LocalLow" / "miHoYo" / "原神 Beta" / "BeyondLocal",
        ]:
            picked = _try_pick_latest_gil_under_dir(candidate)
            if picked is None:
                continue
            p, m = picked
            if int(m) > int(sandbox_gil_mtime_ms):
                sandbox_gil_path = str(p)
                sandbox_gil_mtime_ms = int(m)

        # 2) 兼容：从 ugc_file_tools 的导出设置中读取“用户曾选择的 .gil 路径”
        # 注意：这里不吞错；若 settings JSON 损坏会直接抛出，便于排障。
        suggested_inject_target_gil_path = ""
        suggested_base_gil_for_signal_defs_path = ""
        from ugc_file_tools.ui_integration.export_settings import load_ugc_file_tools_export_settings

        export_settings = load_ugc_file_tools_export_settings(workspace_root=self._workspace_root)
        suggested_inject_target_gil_path = _normalize_gil_path(str(export_settings.inject_target_gil_path or ""))
        # 注意：UGCFileToolsExportSettings 的字段可能随版本演进（例如旧字段 base_gil_path 已移除），
        # 这里用 getattr 做兼容读取，避免离线预览 / status 端点因缺字段直接崩溃。
        suggested_base_gil_for_signal_defs_path_raw = ""
        for attr in ("base_gil_for_signal_defs_path", "base_gil_path"):
            v = getattr(export_settings, attr, "")
            if v:
                suggested_base_gil_for_signal_defs_path_raw = str(v)
                break
        suggested_base_gil_for_signal_defs_path = _normalize_gil_path(suggested_base_gil_for_signal_defs_path_raw)

        # 对外的“一键基底 gil”：
        # - 优先沙箱当前 gil
        # - 再 fallback 到用户曾选择的路径（注入目标 / 信号基底）
        suggested_base_gil_path = str(sandbox_gil_path or "").strip() or (
            suggested_inject_target_gil_path or suggested_base_gil_for_signal_defs_path
        )

        # debug: 用于确认“当前进程实际在用哪一份 workbench 静态目录”
        # 以及关键静态资源是否为最新版本（避免浏览器/多进程导致的错觉）。
        backend_root = self.get_workbench_backend_dir()
        static_root = self.get_workbench_static_dir()
        debug_static_probe: dict[str, dict[str, object]] = {}
        for rel in [
            "ui_app_ui_preview.js",
            "src/flatten/layer_data.js",
            "src/flatten/dom_extract.js",
        ]:
            p = (static_root / rel).resolve()
            if p.is_file():
                data = p.read_bytes()
                debug_static_probe[rel] = {
                    "path": str(p),
                    "size": int(len(data)),
                    "sha256_12": hashlib.sha256(data).hexdigest()[:12],
                }
            else:
                debug_static_probe[rel] = {"path": str(p), "exists": False}

        return {
            "ok": True,
            "connected": True,
            "workspace_root": str(self._workspace_root),
            # 兼容字段：workbench_dir 表示“当前静态服务的前端根目录”（浏览器看到的那份）
            "workbench_dir": str(static_root),
            "workbench_static_dir": str(static_root),
            "workbench_backend_dir": str(backend_root),
            "current_package_id": package_id_text,
            "current_package_name": package_name_text,
            "is_global_view": is_global_view,
            # Web 端一键选择基底 GIL（无需上传大文件）
            "suggested_gil_paths": {
                "sandbox_current_gil_path": str(sandbox_gil_path or "").strip(),
                "sandbox_current_gil_mtime_ms": int(sandbox_gil_mtime_ms),
                "inject_target_gil_path": suggested_inject_target_gil_path,
                "base_gil_for_signal_defs_path": suggested_base_gil_for_signal_defs_path,
            },
            "suggested_base_gil_path": suggested_base_gil_path,
            # 便于前端/排障确认当前服务端能力开关（无需看源码）
            "features": {
                "ui_text_placeholder_validation": True,
                # 方案 S：不再提供写盘式 autofix；缺失变量/字段路径必须在注册表补齐后重试
                "autofix_missing_lv_variables": False,
            },
            "debug_static_probe": debug_static_probe,
        }

    def _get_current_management_or_raise(self) -> tuple[str, object, object]:
        """返回 (current_package_id, package, management)。

        约定：不吞错，缺失上下文直接抛出，便于定位问题。
        """
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("主窗口未绑定，无法读取 UI 控件组数据")

        package_controller = getattr(main_window, "package_controller", None)
        if package_controller is None:
            raise RuntimeError("主窗口缺少 package_controller，无法读取 UI 控件组数据")

        current_package_id = str(getattr(package_controller, "current_package_id", "") or "")
        if not current_package_id or current_package_id == "global_view":
            raise RuntimeError("请先切换到某个【项目存档】再查看/导入（当前为 <共享资源>/未选择）。")

        package = getattr(package_controller, "current_package", None)
        if package is None:
            raise RuntimeError("当前项目存档为空，无法读取 UI 控件组数据")

        management = getattr(package, "management", None)
        if management is None:
            raise RuntimeError("当前项目存档缺少 management，无法读取 UI 控件组数据")

        return current_package_id, package, management

    # --------------------------------------------------------------------- cache: ui preview base gil
    # 说明：
    # - 浏览器侧的 IndexedDB / localStorage 都是按 origin（含端口）隔离；
    # - 插件静态服务端口通常为随机端口，因此仅靠浏览器缓存无法跨进程/跨端口稳定恢复。
    # - 这里提供“后端缓存到磁盘”的兜底：前端选择一次基底 .gil 后，POST 到后端；
    #   下次打开页面（即使端口变化）也能从后端 GET 取回并恢复为 File 对象。
    _UI_PREVIEW_BASE_GIL_CACHE_MAX_BYTES = 60 * 1024 * 1024  # 60MB hard cap（与前端一致）

    def _get_ui_preview_base_gil_cache_paths(self) -> tuple[Path, Path]:
        cache_dir = (self._workspace_root / "app" / "runtime" / "cache" / "ui_converter").resolve()
        cache_dir.mkdir(parents=True, exist_ok=True)
        meta_path = (cache_dir / "ui_preview_base_gil.meta.json").resolve()
        data_path = (cache_dir / "ui_preview_base_gil.bin").resolve()
        return meta_path, data_path

    def save_ui_preview_base_gil_cache(self, *, file_name: str, last_modified_ms: int, data: bytes) -> dict:
        name = str(file_name or "").strip() or "base.gil"
        lm = int(last_modified_ms) if int(last_modified_ms) > 0 else 0
        raw = bytes(data or b"")
        if not raw:
            raise ValueError("base_gil_cache: data is empty")
        if len(raw) > self._UI_PREVIEW_BASE_GIL_CACHE_MAX_BYTES:
            raise ValueError(f"base_gil_cache: too large: {len(raw)} bytes")

        meta_path, data_path = self._get_ui_preview_base_gil_cache_paths()
        data_path.write_bytes(raw)
        meta = {
            "file_name": name,
            "last_modified_ms": lm,
            "bytes_len": int(len(raw)),
            "saved_at_ms": int(time.time() * 1000),
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return meta

    def try_load_ui_preview_base_gil_cache(self) -> tuple[dict, bytes] | None:
        meta_path, data_path = self._get_ui_preview_base_gil_cache_paths()
        if (not meta_path.is_file()) or (not data_path.is_file()):
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        data = data_path.read_bytes()
        return (meta, data)

    # 注意：不要在 Base 里提供 `_ensure_server_running()` / `_inject_*()` 的 NotImplementedError stub。
    # 因为 `_UiWorkbenchBridge` 是多继承 mixin 聚合，若 Base 里定义了同名方法，
    # Python MRO 会优先命中 Base，从而在运行期抛 NotImplementedError（即使 mixin 提供了实现）。
    # 这些方法应仅由 mixin 提供实现。

