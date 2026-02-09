"""
内置 Web Workbench（UI 工作台）桥接与本地静态服务器。

目标：
- 不依赖 private_extensions（无插件用户也可用）；
- 通过浏览器承载“界面控件组/布局/模板”的查看与 HTML 导入；
- 提供与 Workbench 前端约定一致的 `/api/ui_converter/*` 接口。

约束：
- 不导入 PyQt6（由 UI 侧负责打开浏览器 URL）；
- 不吞错：关键错误直接抛出，便于定位问题；
- 写盘走 PackageController 的增量保存链路（mark_* + save_dirty_blocks）。
"""

from __future__ import annotations

import functools
import base64
import http.server
import json
import os
import socket
import threading
import zlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from engine.configs.resource_types import ResourceType
from engine.resources.custom_variable_file_refs import (
    normalize_custom_variable_file_refs,
    serialize_custom_variable_file_refs,
)
from engine.resources.level_variable_schema_view import (
    LevelVariableSchemaView,
    invalidate_default_level_variable_cache,
)
from app.cli.ui_variable_quickfixes import apply_ui_variable_quickfixes

__all__ = [
    "UiWorkbenchBridge",
]

_DEFAULT_LOCAL_HTTP_PORT = 17890
_LOCAL_HTTP_PORT_ENV = "AYAYA_LOCAL_HTTP_PORT"


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


def _decode_utf8_b64(text: str) -> str:
    raw = base64.b64decode(str(text or "").strip() or b"")
    return raw.decode("utf-8")


def _encode_utf8_b64(text: str) -> str:
    raw = str(text or "").encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _crc32_hex(text: str) -> str:
    v = zlib.crc32(str(text).encode("utf-8")) & 0xFFFFFFFF
    return f"{v:08x}"


@dataclass(frozen=True, slots=True)
class _ImportedVariable:
    scope: str  # "lv" | "ps"
    variable_name: str
    variable_type: str
    default_value: object


def _variable_id_for(package_id: str, *, scope: str, variable_name: str) -> str:
    digest = _crc32_hex(f"{package_id}:{scope}:{variable_name}")
    return f"ui_{digest}__{package_id}"


def _ensure_dict_one_level(value: dict, *, key: str) -> dict:
    out: dict = {}
    for k, v in value.items():
        k2 = str(k)
        if isinstance(v, dict):
            raise ValueError(f"不支持嵌套字典默认值：{key} -> {k2}")
        out[k2] = v
    return out


def _infer_variable_type_and_default(value: object, *, key: str) -> tuple[str, object]:
    # 注意：bool 是 int 的子类，必须先判断 bool
    if isinstance(value, bool):
        return "布尔值", bool(value)
    if isinstance(value, int):
        return "整数", int(value)
    if isinstance(value, float):
        return "浮点数", float(value)
    if isinstance(value, str):
        return "字符串", str(value)
    if isinstance(value, dict):
        return "字典", _ensure_dict_one_level(value, key=key)
    if isinstance(value, list):
        if len(value) <= 0:
            # 空列表无法推断，默认按字符串列表（最安全的可显示/可编辑类型）
            return "字符串列表", []
        kinds = set(type(x) for x in value)
        # 统一转成 bool/int/float/str 检查
        if kinds.issubset({bool}):
            return "布尔值列表", [bool(x) for x in value]
        if kinds.issubset({int}) or kinds.issubset({int, bool}):
            # 注意：如果 list 里混入 bool，仍按整数列表处理会让 True/False 变 1/0
            # 这里严格：混入 bool 视为混合类型，拒绝自动推断（避免静默改变语义）
            if bool in kinds and int in kinds:
                raise ValueError(f"列表默认值类型混合（int/bool），请手动拆分：{key}")
            return "整数列表", [int(x) for x in value]
        if kinds.issubset({float}) or kinds.issubset({int, float}):
            return "浮点数列表", [float(x) for x in value]
        if kinds.issubset({str}):
            return "字符串列表", [str(x) for x in value]
        raise ValueError(f"列表默认值类型不受支持或混合：{key} -> {sorted([t.__name__ for t in kinds])}")

    raise ValueError(f"默认值类型不受支持：{key} -> {type(value)!r}")


def _extract_import_items(variable_defaults: dict) -> list[_ImportedVariable]:
    items: list[_ImportedVariable] = []
    for raw_key, raw_value in variable_defaults.items():
        full_key = str(raw_key or "").strip()
        if not full_key:
            continue
        if full_key.startswith("lv."):
            name = str(full_key[3:]).strip()
            if not name:
                continue
            vtype, dv = _infer_variable_type_and_default(raw_value, key=full_key)
            items.append(_ImportedVariable(scope="lv", variable_name=name, variable_type=vtype, default_value=dv))
            continue
        if full_key.startswith("ps."):
            name = str(full_key[3:]).strip()
            if not name:
                continue
            vtype, dv = _infer_variable_type_and_default(raw_value, key=full_key)
            items.append(_ImportedVariable(scope="ps", variable_name=name, variable_type=vtype, default_value=dv))
            continue
    return items


def _write_level_variable_file(
    path: Path,
    *,
    file_id: str,
    file_name: str,
    variables: list[dict],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("from engine.graph.models.package_model import LevelVariableDefinition")
    lines.append("")
    lines.append(f'VARIABLE_FILE_ID = "{file_id}"')
    lines.append(f'VARIABLE_FILE_NAME = "{file_name}"')
    lines.append("")
    lines.append("LEVEL_VARIABLES: list[LevelVariableDefinition] = [")
    for item in variables:
        payload = {
            "variable_id": item.get("variable_id"),
            "variable_name": item.get("variable_name"),
            "variable_type": item.get("variable_type"),
            "default_value": item.get("default_value"),
            "is_global": item.get("is_global", True),
            "description": item.get("description", ""),
            "metadata": item.get("metadata", {}),
        }
        lines.append("    LevelVariableDefinition(")
        lines.append(f"        variable_id={repr(payload['variable_id'])},")
        lines.append(f"        variable_name={repr(payload['variable_name'])},")
        lines.append(f"        variable_type={repr(payload['variable_type'])},")
        lines.append(f"        default_value={repr(payload['default_value'])},")
        lines.append(f"        is_global={repr(payload['is_global'])},")
        lines.append(f"        description={repr(payload['description'])},")
        lines.append(f"        metadata={repr(payload['metadata'])},")
        lines.append("    ),")
    lines.append("]")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _discover_player_templates(package_root: Path) -> list[Path]:
    template_dir = (package_root / "战斗预设" / "玩家模板").resolve()
    if not template_dir.is_dir():
        return []
    return sorted([p for p in template_dir.glob("*.json") if p.is_file()], key=lambda p: p.as_posix())


def _get_player_custom_variable_file_ids_from_template(template_json: dict) -> list[str]:
    metadata = template_json.get("metadata")
    if not isinstance(metadata, dict):
        return []
    return normalize_custom_variable_file_refs(metadata.get("custom_variable_file"))


def _set_player_custom_variable_file_ids(template_json: dict, file_ids: list[str]) -> None:
    metadata = template_json.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        template_json["metadata"] = metadata
    metadata["custom_variable_file"] = serialize_custom_variable_file_refs(file_ids)


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


@dataclass(slots=True)
class ImportResult:
    layout_id: str
    layout_name: str
    template_id: str
    template_name: str
    template_count: int
    widget_count: int


@dataclass(slots=True)
class ImportBundleResult:
    layout_id: str
    layout_name: str
    template_count: int
    widget_count: int


class UiWorkbenchBridge:
    """将主程序当前上下文（PackageController/PackageView）暴露给 Web Workbench。"""

    def __init__(self, *, workspace_root: Path, workbench_dir: Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._workbench_dir = Path(workbench_dir).resolve()
        self._main_window: object | None = None
        self._server: _WorkbenchHttpServer | None = None

    # --------------------------------------------------------------------- life-cycle
    def attach_main_window(self, main_window: object) -> None:
        self._main_window = main_window

    def ensure_server_running(self) -> None:
        if self._server is not None:
            return
        self._server = _WorkbenchHttpServer(workbench_dir=self._workbench_dir, bridge=self)
        self._server.start()

    def get_workbench_url(self) -> str:
        self.ensure_server_running()
        if self._server is None:
            raise RuntimeError("Workbench server 未启动")
        # Workbench 页面已下线，所有入口统一导向预览页。
        return f"http://127.0.0.1:{self._server.port}/ui_app_ui_preview.html"

    def get_ui_preview_url(self) -> str:
        """UI 控件组预览页（布局/模板浏览与预览）。"""
        self.ensure_server_running()
        if self._server is None:
            raise RuntimeError("Workbench server 未启动")
        return f"http://127.0.0.1:{self._server.port}/ui_app_ui_preview.html"

    # --------------------------------------------------------------------- api payloads
    def get_status_payload(self) -> dict:
        main_window = self._main_window
        package_controller = getattr(main_window, "package_controller", None) if main_window is not None else None
        current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        current_package = getattr(package_controller, "current_package", None) if package_controller is not None else None
        current_package_name = getattr(current_package, "name", "") if current_package is not None else ""

        package_id_text = str(current_package_id or "")
        package_name_text = str(current_package_name or "")
        is_global_view = package_id_text == "global_view"

        return {
            "ok": True,
            "connected": True,
            "workspace_root": str(self._workspace_root),
            "workbench_dir": str(self._workbench_dir),
            "current_package_id": package_id_text,
            "current_package_name": package_name_text,
            "is_global_view": is_global_view,
            # 预览页 UX：用于“设为基底：当前沙箱”按钮（若为空则按钮禁用）
            "suggested_base_gil_path": "",
            "suggested_gil_paths": [],
            # 能力声明：Web 前端可据此展示/隐藏按钮或给出解释（当前仍以“存在 API=connected”作为主判断）
            "features": {
                "builtin_workbench": True,
                "ui_source_api": True,
                "ui_catalog_api": True,
                "ui_import_layout_api": True,
                "fix_ui_variables_api": True,
                # UGC 写回能力属于私有工具链；内置 Workbench 不提供（前端会显示明确错误提示）
                "export_gil": False,
                "export_gia": False,
            },
        }

    def get_ui_source_catalog_payload(self) -> dict:
        """返回 UI源码（HTML）清单：项目 + 共享。"""
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("主窗口未绑定，无法读取 UI源码 清单")
        package_controller = getattr(main_window, "package_controller", None)
        if package_controller is None:
            raise RuntimeError("主窗口缺少 package_controller，无法读取 UI源码 清单")

        current_package_id = str(getattr(package_controller, "current_package_id", "") or "").strip()
        is_global_view = (not current_package_id) or current_package_id == "global_view"

        shared_ui_dir = (self._workspace_root / "assets" / "资源库" / "共享" / "管理配置" / "UI源码").resolve()
        project_ui_dir = (
            (self._workspace_root / "assets" / "资源库" / "项目存档" / current_package_id / "管理配置" / "UI源码").resolve()
            if (not is_global_view)
            else None
        )

        items: list[dict[str, object]] = []
        if project_ui_dir is not None:
            for name in _list_html_files(project_ui_dir):
                items.append({"scope": "project", "file_name": name, "is_shared": False})
        for name in _list_html_files(shared_ui_dir):
            items.append({"scope": "shared", "file_name": name, "is_shared": True})

        return {"ok": True, "items": items, "current_package_id": current_package_id}

    def _resolve_ui_source_path(self, *, scope: str, rel_path: str) -> Path:
        """将 Web 侧的 (scope, rel_path) 解析为磁盘路径。"""
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("主窗口未绑定，无法读取 UI源码")
        package_controller = getattr(main_window, "package_controller", None)
        if package_controller is None:
            raise RuntimeError("主窗口缺少 package_controller，无法读取 UI源码")

        s = str(scope or "project").strip()
        rp = str(rel_path or "").replace("\\", "/").strip().lstrip("/")
        if not rp:
            raise ValueError("rel_path is required")
        if "/" in rp:
            # 预览页的 rel_path 目前只应为文件名；禁止目录穿越
            raise ValueError(f"rel_path must be a file name: {rp}")

        if s == "shared":
            return (self._workspace_root / "assets" / "资源库" / "共享" / "管理配置" / "UI源码" / rp).resolve()

        current_package_id = str(getattr(package_controller, "current_package_id", "") or "").strip()
        if (not current_package_id) or current_package_id == "global_view":
            raise RuntimeError("请先切换到某个【项目存档】再读取项目 UI源码（当前为 <共享资源>/未选择）。")
        return (self._workspace_root / "assets" / "资源库" / "项目存档" / current_package_id / "管理配置" / "UI源码" / rp).resolve()

    def read_ui_source_payload(self, *, scope: str, rel_path: str) -> dict:
        file_path = self._resolve_ui_source_path(scope=scope, rel_path=rel_path)
        if not file_path.is_file():
            return {"ok": False, "error": f"file not found: {file_path}"}
        scope_text = str(scope or "project").strip() or "project"
        rel_text = str(rel_path or "").strip()
        return {
            "ok": True,
            "scope": scope_text,
            "rel_path": rel_text,
            "file_name": rel_text,
            "is_shared": scope_text == "shared",
            "content": file_path.read_text(encoding="utf-8"),
        }

    def _get_ui_workbench_cache_dir(self) -> Path:
        # 按工程约定：运行期缓存统一落在 app/runtime/cache/（默认应被忽略）
        cache_dir = (self._workspace_root / "app" / "runtime" / "cache" / "ui_workbench").resolve()
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def save_base_gil_cache(self, *, file_name: str, last_modified: int, content: bytes) -> None:
        cache_dir = self._get_ui_workbench_cache_dir()
        data_path = (cache_dir / "base_gil_cache.bin").resolve()
        meta_path = (cache_dir / "base_gil_cache.meta.json").resolve()

        data_path.write_bytes(bytes(content))
        meta_path.write_text(
            json.dumps(
                {
                    "file_name": str(file_name or "base.gil"),
                    "file_name_b64": _encode_utf8_b64(str(file_name or "base.gil")),
                    "last_modified": int(last_modified),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def load_base_gil_cache(self) -> tuple[str, int, bytes] | None:
        cache_dir = self._get_ui_workbench_cache_dir()
        data_path = (cache_dir / "base_gil_cache.bin").resolve()
        meta_path = (cache_dir / "base_gil_cache.meta.json").resolve()
        if (not data_path.is_file()) or (not meta_path.is_file()):
            return None

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(meta, dict):
            raise RuntimeError("base_gil_cache.meta.json 不是对象")

        file_name = str(meta.get("file_name") or "base.gil")
        last_modified_value = meta.get("last_modified")
        if not isinstance(last_modified_value, int):
            last_modified_value = int(last_modified_value) if str(last_modified_value or "").strip().isdigit() else 0
        return file_name, int(last_modified_value), data_path.read_bytes()

    def get_ui_catalog_payload(self) -> dict:
        """返回当前项目存档的 UI 布局/模板清单（用于 Web 侧浏览与预览）。"""
        current_package_id, _package, management = self._get_current_management_or_raise()

        layouts: list[dict[str, object]] = []
        templates: list[dict[str, object]] = []

        ui_layouts: dict = getattr(management, "ui_layouts", {}) or {}
        for layout_id, payload in ui_layouts.items():
            if not isinstance(payload, dict):
                continue
            layout_name = str(payload.get("layout_name", "") or payload.get("name", "") or layout_id)
            builtin = payload.get("builtin_widgets", [])
            custom = payload.get("custom_groups", [])
            layouts.append(
                {
                    "layout_id": str(layout_id),
                    "layout_name": layout_name,
                    "builtin_count": len(builtin) if isinstance(builtin, list) else 0,
                    "custom_count": len(custom) if isinstance(custom, list) else 0,
                }
            )

        ui_templates: dict = getattr(management, "ui_widget_templates", {}) or {}
        for template_id, payload in ui_templates.items():
            if not isinstance(payload, dict):
                continue
            template_name = str(payload.get("template_name", "") or payload.get("name", "") or template_id)
            widgets = payload.get("widgets", [])
            templates.append(
                {
                    "template_id": str(template_id),
                    "template_name": template_name,
                    "widget_count": len(widgets) if isinstance(widgets, list) else 0,
                    "is_combination": bool(payload.get("is_combination", False)),
                    "is_builtin": str(template_id).startswith("builtin_"),
                }
            )

        layouts.sort(key=lambda item: str(item.get("layout_name", "")).casefold())
        templates.sort(key=lambda item: str(item.get("template_name", "")).casefold())

        return {
            "ok": True,
            "current_package_id": current_package_id,
            "layouts": layouts,
            "templates": templates,
        }

    def get_ui_layout_payload(self, layout_id: str) -> dict:
        current_package_id, _package, management = self._get_current_management_or_raise()
        ui_layouts: dict = getattr(management, "ui_layouts", {}) or {}
        payload = ui_layouts.get(layout_id)
        if not isinstance(payload, dict):
            raise RuntimeError(f"未找到 UI 布局: {layout_id}")
        return {"ok": True, "current_package_id": current_package_id, "layout": payload}

    def get_ui_template_payload(self, template_id: str) -> dict:
        current_package_id, _package, management = self._get_current_management_or_raise()
        ui_templates: dict = getattr(management, "ui_widget_templates", {}) or {}
        payload = ui_templates.get(template_id)
        if not isinstance(payload, dict):
            raise RuntimeError(f"未找到 UI 控件模板: {template_id}")
        return {"ok": True, "current_package_id": current_package_id, "template": payload}

    def fix_ui_variables_from_ui_source(self, *, dry_run: bool) -> dict:
        """根据当前项目存档的 管理配置/UI源码 扫描占位符并自动补齐变量定义与引用。

        说明：
        - 本方法复用 CLI 的 `validate-ui --fix/--fix-dry-run` quickfix 逻辑；
        - 主要用于 Web Workbench/导入器在导出/导入前提供“一键修复变量”能力；
        - 写盘范围：项目存档内 `管理配置/关卡变量/自定义变量/*.py` 与 `战斗预设/玩家模板/*.json`。
        """
        current_package_id, _package, _management = self._get_current_management_or_raise()
        actions = apply_ui_variable_quickfixes(
            workspace_root=self._workspace_root,
            package_id=current_package_id,
            dry_run=bool(dry_run),
        )
        return {
            "ok": True,
            "current_package_id": current_package_id,
            "dry_run": bool(dry_run),
            "action_count": len(actions),
            "actions": [
                {"path": str(a.file_path), "summary": str(a.summary)}
                for a in actions
            ],
        }

    def import_variable_defaults_to_current_project(self, *, source_rel_path: str, variable_defaults: dict) -> dict:
        """
        将前端解析出的 `variable_defaults`（来自 HTML 的 data-ui-variable-defaults）同步写入当前项目的变量库：
        - lv.* -> 关卡变量文件（管理配置/关卡变量/自定义变量/UI_关卡变量_网页默认值.py）
        - ps.* -> 玩家变量文件（管理配置/关卡变量/自定义变量/UI_玩家变量_网页默认值.py）并更新玩家模板引用

        注意：
        - 仅处理 lv/ps 前缀；其它（如 关卡./玩家自身.）不在此处导入（它们属于 .gil 的实体自定义变量范畴）。
        - 不覆盖“其它文件”中已有的同名变量；若同名变量已存在但不在本文件内，则跳过并在报告中返回冲突信息。
        """
        if not isinstance(variable_defaults, dict):
            raise ValueError("variable_defaults must be dict")

        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("主窗口未绑定，无法导入变量默认值。")
        package_controller = getattr(main_window, "package_controller", None)
        if package_controller is None:
            raise RuntimeError("主窗口缺少 package_controller，无法导入变量默认值。")
        current_package_id = str(getattr(package_controller, "current_package_id", "") or "")
        if not current_package_id or current_package_id == "global_view":
            raise RuntimeError("请先切换到某个【项目存档】再导入变量默认值（当前为 <共享资源>/未选择）。")

        package_root = (self._workspace_root / "assets" / "资源库" / "项目存档" / current_package_id).resolve()
        var_dir = (package_root / "管理配置" / "关卡变量" / "自定义变量").resolve()

        schema_view = LevelVariableSchemaView()
        schema_view.set_active_package_id(current_package_id)

        name_to_payloads: dict[str, list[dict]] = {}
        for _var_id, payload in (schema_view.get_all_variables() or {}).items():
            if not isinstance(payload, dict):
                continue
            name = str(payload.get("variable_name") or "").strip()
            if not name:
                continue
            name_to_payloads.setdefault(name, []).append(payload)

        imported_items = _extract_import_items(variable_defaults)
        lv_items = [it for it in imported_items if it.scope == "lv"]
        ps_items = [it for it in imported_items if it.scope == "ps"]

        report: dict[str, object] = {
            "ok": True,
            "package_id": current_package_id,
            "source_rel_path": str(source_rel_path or ""),
            "input_variable_defaults_total": int(len(variable_defaults)),
            "imported_candidates_total": int(len(imported_items)),
            "imported_lv_total": int(len(lv_items)),
            "imported_ps_total": int(len(ps_items)),
            "lv": {"created": [], "updated": [], "skipped_conflicts": []},
            "ps": {"created": [], "updated": [], "skipped_conflicts": [], "player_templates_updated": []},
            "notes": [
                "仅导入 lv.* / ps.* 到项目变量库；关卡./玩家自身. 等“实体自定义变量”仍由导出 .gil 写回端处理。",
            ],
        }

        def _merge_into_file(*, scope: str, file_id: str, file_name: str, file_path: Path, items: list[_ImportedVariable]) -> dict:
            existing_in_file = {
                str(p.get("variable_name") or ""): dict(p)
                for p in (schema_view.get_variables_by_file_id(file_id) or [])
            }
            merged_by_name: dict[str, dict] = dict(existing_in_file)

            created: list[dict] = []
            updated: list[dict] = []
            skipped_conflicts: list[dict] = []

            for it in items:
                name = it.variable_name
                payloads = name_to_payloads.get(name, [])
                if payloads:
                    # 冲突（不唯一或不在本文件）：不覆盖用户已存在的定义
                    # 允许：若唯一且就在本文件内，则作为更新处理
                    if len(payloads) == 1:
                        only = payloads[0]
                        if str(only.get("variable_file_id") or "") == file_id:
                            # 可更新
                            pass
                        else:
                            skipped_conflicts.append(
                                {
                                    "variable_name": name,
                                    "reason": "same_name_exists_in_other_file",
                                    "existing_variable_id": str(only.get("variable_id") or ""),
                                    "existing_file_id": str(only.get("variable_file_id") or ""),
                                }
                            )
                            continue
                    else:
                        skipped_conflicts.append(
                            {
                                "variable_name": name,
                                "reason": "ambiguous_name_conflict",
                                "existing_payloads_total": int(len(payloads)),
                            }
                        )
                        continue

                if name in merged_by_name:
                    cur = merged_by_name[name]
                    cur_type = str(cur.get("variable_type") or "").strip()
                    if cur_type and cur_type != it.variable_type:
                        raise ValueError(
                            f"变量类型冲突：{scope}.{name} existing={cur_type!r} imported={it.variable_type!r}"
                        )
                    cur["variable_type"] = it.variable_type
                    cur["default_value"] = it.default_value
                    meta = cur.get("metadata")
                    if not isinstance(meta, dict):
                        meta = {}
                        cur["metadata"] = meta
                    meta.setdefault("category", "UI网页默认值")
                    # 记录来源：用于协作排查（不影响运行）
                    sources = meta.get("sources")
                    if not isinstance(sources, list):
                        sources = []
                        meta["sources"] = sources
                    src_text = str(source_rel_path or "").strip()
                    if src_text and src_text not in sources:
                        sources.append(src_text)
                    updated.append({"variable_name": name, "variable_type": it.variable_type})
                    continue

                merged_by_name[name] = {
                    "variable_id": _variable_id_for(current_package_id, scope=scope, variable_name=name),
                    "variable_name": name,
                    "variable_type": it.variable_type,
                    "default_value": it.default_value,
                    "is_global": True,
                    "description": "由 UI 网页 data-ui-variable-defaults 导入（默认值来源于页面）",
                    "metadata": {
                        "category": "UI网页默认值",
                        "sources": [str(source_rel_path or "").strip()] if str(source_rel_path or "").strip() else [],
                    },
                }
                created.append({"variable_name": name, "variable_type": it.variable_type})

            # 稳定排序：按名称排序（便于 diff 与协作）
            ordered = sorted(merged_by_name.values(), key=lambda p: str(p.get("variable_name") or ""))
            _write_level_variable_file(file_path, file_id=file_id, file_name=file_name, variables=ordered)
            return {"created": created, "updated": updated, "skipped_conflicts": skipped_conflicts}

        # lv: 关卡变量网页默认值文件
        lv_file_id = f"ui_level_variable_web_defaults__{current_package_id}"
        lv_file_name = f"UI_关卡变量_网页默认值__{current_package_id}"
        lv_file_path = (var_dir / "UI_关卡变量_网页默认值.py").resolve()
        if lv_items:
            report["lv"] = _merge_into_file(
                scope="lv",
                file_id=lv_file_id,
                file_name=lv_file_name,
                file_path=lv_file_path,
                items=lv_items,
            )

        # ps: 玩家变量网页默认值文件 + 更新玩家模板引用
        ps_file_id = f"ui_player_variable_web_defaults__{current_package_id}"
        ps_file_name = f"UI_玩家变量_网页默认值__{current_package_id}"
        ps_file_path = (var_dir / "UI_玩家变量_网页默认值.py").resolve()
        if ps_items:
            report["ps"] = _merge_into_file(
                scope="ps",
                file_id=ps_file_id,
                file_name=ps_file_name,
                file_path=ps_file_path,
                items=ps_items,
            )

            player_templates = _discover_player_templates(package_root)
            updated_templates: list[str] = []
            for tpl_path in player_templates:
                tpl = _read_json(tpl_path)
                old_refs = _get_player_custom_variable_file_ids_from_template(tpl)
                new_refs = list(old_refs)
                if ps_file_id not in new_refs:
                    new_refs.append(ps_file_id)
                if new_refs != old_refs:
                    _set_player_custom_variable_file_ids(tpl, new_refs)
                    _write_json(tpl_path, tpl)
                    updated_templates.append(tpl_path.name)

            report_ps = report.get("ps")
            if isinstance(report_ps, dict):
                report_ps["player_templates_updated"] = updated_templates
                report_ps["player_templates_total"] = int(len(_discover_player_templates(package_root)))
                if not updated_templates and int(len(_discover_player_templates(package_root))) <= 0:
                    report_ps["note"] = (
                        "未找到玩家模板：ps 变量已写入变量文件，但不会出现在 variable_catalog（需要玩家模板引用）"
                    )

        invalidate_default_level_variable_cache()
        return report

    # --------------------------------------------------------------------- import
    def import_layout_from_template_payload(self, *, layout_name: str, template_payload: dict) -> ImportResult:
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("主窗口未绑定，无法导入")

        package_controller = getattr(main_window, "package_controller", None)
        if package_controller is None:
            raise RuntimeError("主窗口缺少 package_controller，无法导入")

        current_package_id = str(getattr(package_controller, "current_package_id", "") or "")
        if not current_package_id or current_package_id == "global_view":
            raise RuntimeError("请先切换到某个【项目存档】再执行导入（当前为 <共享资源>/未选择）。")

        package = getattr(package_controller, "current_package", None)
        if package is None:
            raise RuntimeError("当前项目存档为空，无法导入")

        management = getattr(package, "management", None)
        if management is None:
            raise RuntimeError("当前项目存档缺少 management，无法导入")

        resource_manager = getattr(package_controller, "resource_manager", None)
        if resource_manager is None:
            raise RuntimeError("package_controller 缺少 resource_manager，无法导入")

        # 写入当前包的 management 缓存（后续由 PackageController 统一落盘并同步索引）
        if not isinstance(getattr(management, "ui_widget_templates", None), dict):
            management.ui_widget_templates = {}
        if not isinstance(getattr(management, "ui_layouts", None), dict):
            management.ui_layouts = {}

        # --- 生成新 ID（全库同类型唯一）
        existing_layout_ids = set(resource_manager.list_resource_file_paths(ResourceType.UI_LAYOUT).keys())
        existing_template_ids = set(resource_manager.list_resource_file_paths(ResourceType.UI_WIDGET_TEMPLATE).keys())

        layout_id = self._generate_unique_id(prefix="layout_html", existing=existing_layout_ids)
        template_id = self._generate_unique_id(prefix="ui_widget_template_html", existing=existing_template_ids)

        # --- 规范化名称（避免 UI 列表中同名混淆）
        normalized_layout_name = self._ensure_unique_name(
            desired=str(layout_name or "").strip() or "HTML导入_界面布局",
            existing_names=self._collect_existing_names(getattr(management, "ui_layouts", None), "layout_name"),
        )
        normalized_template_name = self._ensure_unique_name(
            desired=f"{normalized_layout_name}（HTML组合）",
            existing_names=self._collect_existing_names(getattr(management, "ui_widget_templates", None), "template_name"),
        )

        now = datetime.now().isoformat()

        # --- 解析 Workbench 导出的 UIControlGroupTemplate，并重写 ID/名称/控件ID（避免跨模板 widget_id 冲突）
        from engine.configs.components.ui_control_group_model import (
            BUILTIN_WIDGET_TYPES,
            UIControlGroupTemplate,
            UIWidgetConfig,
            UILayout,
            create_builtin_widget_templates,
        )

        template_obj = UIControlGroupTemplate.deserialize(template_payload)
        if template_obj is None:
            raise RuntimeError("导入失败：模板 JSON 缺少 template_id（不是合法的 UIControlGroupTemplate）。")

        template_obj.template_id = template_id
        template_obj.template_name = normalized_template_name
        template_obj.created_at = now
        template_obj.updated_at = now

        # 保留原始 widget_id（便于排查），并重写为全局唯一
        for idx, widget in enumerate(list(template_obj.widgets)):
            old_widget_id = str(getattr(widget, "widget_id", "") or "")
            if old_widget_id:
                widget.extra.setdefault("__source_widget_id", old_widget_id)
            widget.widget_id = f"{template_id}_w{idx:03d}"
            widget.is_builtin = False

        # --- 固有内容：优先使用“按包后缀化”的 builtin 模板（与资源库内约定一致）
        existing_ui_templates: dict = management.ui_widget_templates
        builtin_base_templates = create_builtin_widget_templates()

        builtin_widgets: list[str] = []
        for widget_type in list(BUILTIN_WIDGET_TYPES):
            preferred_template_id = f"builtin_{widget_type}__{current_package_id}"
            legacy_template_id = f"builtin_{widget_type}"

            if preferred_template_id in existing_ui_templates:
                builtin_widgets.append(preferred_template_id)
                continue
            if legacy_template_id in existing_ui_templates:
                builtin_widgets.append(legacy_template_id)
                continue

            # 缺失时补齐：用引擎内建默认位置/大小作为兜底，并将 ID 后缀化为 __<package_id>
            base_template = builtin_base_templates.get(legacy_template_id)
            if base_template is None:
                continue

            payload = base_template.serialize()
            payload["template_id"] = preferred_template_id
            payload["template_name"] = widget_type
            payload["created_at"] = now
            payload["updated_at"] = now

            widgets_payload = payload.get("widgets")
            if isinstance(widgets_payload, list):
                for widget_payload_item in widgets_payload:
                    if not isinstance(widget_payload_item, dict):
                        continue
                    widget_payload_item["widget_id"] = f"builtin_{widget_type}_widget__{current_package_id}"
                    widget_payload_item["widget_type"] = widget_type
                    widget_payload_item["widget_name"] = widget_type
                    widget_payload_item["is_builtin"] = True

            existing_ui_templates[preferred_template_id] = payload
            builtin_widgets.append(preferred_template_id)

        # --- 写入组合模板（用于溯源/整体预览），但布局默认引用“拆分后的单控件模板”
        existing_ui_templates[template_id] = template_obj.serialize()

        # --- 拆分导入（增强）：优先将“按钮”打组为组合模板（一个按钮 = 多控件组合），其余仍按单控件拆分。
        #
        # 设计动机：
        # - HTML 中一个 <button> 往往只需样式即可表达；
        # - 但在 UGC UI 中按钮通常由“文本框 + 进度条底色 + 进度条阴影 + 交互层(道具展示)”堆叠实现；
        # - 若完全按控件拆分，布局自定义列表会非常长且难以维护。
        #
        # 约定（与现有导出一致）：
        # - Workbench 会为每个 <button> 生成一个“道具展示”控件（交互层）；
        # - 并为其底色/阴影/边框生成若干“进度条”，文本生成“文本框”。
        existing_template_names = self._collect_existing_names(existing_ui_templates, "template_name")
        custom_group_entries: list[tuple[int, str]] = []  # (sort_key(min_layer_index), template_id)

        def _rect_of_widget(widget_obj: UIWidgetConfig) -> tuple[float, float, float, float]:
            x, y = widget_obj.position
            w, h = widget_obj.size
            return float(x), float(y), float(w), float(h)

        def _rect_area(rect: tuple[float, float, float, float]) -> float:
            _x, _y, w, h = rect
            if w <= 0 or h <= 0:
                return 0.0
            return float(w) * float(h)

        def _rect_intersection_area(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
            ax, ay, aw, ah = a
            bx, by, bw, bh = b
            left = max(ax, bx)
            top = max(ay, by)
            right = min(ax + aw, bx + bw)
            bottom = min(ay + ah, by + bh)
            iw = right - left
            ih = bottom - top
            if iw <= 0 or ih <= 0:
                return 0.0
            return float(iw) * float(ih)

        def _rect_contains_point(rect: tuple[float, float, float, float], px: float, py: float) -> bool:
            x, y, w, h = rect
            return (px >= x) and (py >= y) and (px <= x + w) and (py <= y + h)

        def _rect_center(rect: tuple[float, float, float, float]) -> tuple[float, float]:
            x, y, w, h = rect
            return x + w / 2.0, y + h / 2.0

        def _bounds_of_widgets(widget_list: list[UIWidgetConfig]) -> tuple[float, float, float, float]:
            if not widget_list:
                return 0.0, 0.0, 0.0, 0.0
            min_x = min(float(w.position[0]) for w in widget_list)
            min_y = min(float(w.position[1]) for w in widget_list)
            max_x = max(float(w.position[0] + w.size[0]) for w in widget_list)
            max_y = max(float(w.position[1] + w.size[1]) for w in widget_list)
            return min_x, min_y, max(0.0, max_x - min_x), max(0.0, max_y - min_y)

        def _clone_widget_with_new_id(source_widget: UIWidgetConfig, *, new_widget_id: str) -> UIWidgetConfig:
            widget_payload = source_widget.serialize()
            widget_payload["widget_id"] = new_widget_id
            widget_payload["is_builtin"] = False
            return UIWidgetConfig.deserialize(widget_payload)

        # 以 layer_index 升序稳定排序（背景→前景），避免导入后列表顺序随机
        source_widgets = sorted(
            list(template_obj.widgets),
            key=lambda w: int(getattr(w, "layer_index", 0) or 0),
        )

        # 1) “按钮打组”：以 <button> 导出的交互层（道具展示）作为锚点，将其底色/阴影/边框/文本聚合成一个组合模板。
        button_anchors = [
            w
            for w in source_widgets
            if (str(getattr(w, "widget_type", "") or "") == "道具展示") and (not bool(getattr(w, "is_builtin", False)))
        ]
        widgets_in_button_groups: set[str] = set()
        group_members_by_anchor_id: dict[str, list[UIWidgetConfig]] = {}
        for anchor in button_anchors:
            group_members_by_anchor_id[anchor.widget_id] = [anchor]
            widgets_in_button_groups.add(anchor.widget_id)

        # 将进度条/文本框按几何关系归属到某个按钮锚点（只聚合 Workbench 约定前缀，避免把大背景误并入按钮组）
        progress_prefixes = ("按钮_", "阴影_", "边框_")
        text_prefix = "文本_"

        anchor_rect_cache: dict[str, tuple[float, float, float, float]] = {}
        anchor_area_cache: dict[str, float] = {}
        for anchor in button_anchors:
            rect = _rect_of_widget(anchor)
            anchor_rect_cache[anchor.widget_id] = rect
            anchor_area_cache[anchor.widget_id] = _rect_area(rect)

        for w in source_widgets:
            if w.widget_id in widgets_in_button_groups:
                continue
            if bool(getattr(w, "is_builtin", False)):
                continue

            widget_type = str(getattr(w, "widget_type", "") or "")
            widget_name = str(getattr(w, "widget_name", "") or "")
            if widget_type not in {"进度条", "文本框"}:
                continue

            w_rect = _rect_of_widget(w)
            if _rect_area(w_rect) <= 0:
                continue

            # 候选筛选：仅考虑“看起来是按钮堆叠的一部分”的控件
            if widget_type == "进度条":
                if not widget_name.startswith(progress_prefixes):
                    continue
            if widget_type == "文本框":
                if not widget_name.startswith(text_prefix):
                    continue

            best_anchor: UIWidgetConfig | None = None
            best_intersection = 0.0
            for anchor in button_anchors:
                a_rect = anchor_rect_cache.get(anchor.widget_id)
                if a_rect is None:
                    continue
                area = _rect_intersection_area(w_rect, a_rect)
                if area <= best_intersection:
                    continue
                best_intersection = area
                best_anchor = anchor

            if best_anchor is None or best_intersection <= 0:
                continue

            a_rect = anchor_rect_cache.get(best_anchor.widget_id)
            if a_rect is None:
                continue

            # 几何约束（避免误分组）：
            # - 文本：中心点必须落在按钮范围内
            # - 进度条：中心点在按钮内（底色/边框），或按钮中心点在其内（阴影）
            wx, wy = _rect_center(w_rect)
            ax, ay = _rect_center(a_rect)
            if widget_type == "文本框":
                if not _rect_contains_point(a_rect, wx, wy):
                    continue
            else:
                if not (_rect_contains_point(a_rect, wx, wy) or _rect_contains_point(w_rect, ax, ay)):
                    continue
                # 阴影允许略大，但禁止“超大背景”被并入按钮组
                button_area = anchor_area_cache.get(best_anchor.widget_id, 0.0)
                if button_area > 0:
                    if _rect_area(w_rect) > button_area * 6.0:
                        continue

            group_members_by_anchor_id[best_anchor.widget_id].append(w)
            widgets_in_button_groups.add(w.widget_id)

        # 生成按钮组合模板（一个按钮 = 一个模板）
        for button_index, anchor in enumerate(button_anchors):
            members = group_members_by_anchor_id.get(anchor.widget_id, [])
            if not members:
                continue

            desired_template_id_prefix = f"{template_id}_btn"
            new_template_id = self._generate_unique_id(prefix=desired_template_id_prefix, existing=existing_template_ids)
            existing_template_ids.add(new_template_id)

            # 模板名：尽量使用 aria-label / data-debug-label；否则回退 widget_name
            debug_label = ""
            if isinstance(getattr(anchor, "extra", None), dict):
                debug_label = str(
                    anchor.extra.get("_html_data_debug_label")
                    or anchor.extra.get("_html_button_aria_label")
                    or ""
                ).strip()
            fallback_name = str(getattr(anchor, "widget_name", "") or "").strip()
            label_text = debug_label or fallback_name or f"按钮_{button_index:03d}"
            if label_text.startswith("按钮_道具展示_"):
                label_text = label_text[len("按钮_道具展示_") :]
            desired_template_name = f"{normalized_layout_name}_按钮_{label_text}" if label_text else f"{normalized_layout_name}_按钮_{button_index:03d}"
            normalized_child_name = self._ensure_unique_name(desired=desired_template_name, existing_names=existing_template_names)
            existing_template_names.add(normalized_child_name)

            # 组内 widget 也按 layer_index 排序，保证点击/遮挡顺序稳定
            members_sorted = sorted(members, key=lambda w: int(getattr(w, "layer_index", 0) or 0))
            cloned_widgets: list[UIWidgetConfig] = []
            for idx, src_widget in enumerate(members_sorted):
                widget_obj = _clone_widget_with_new_id(src_widget, new_widget_id=f"{new_template_id}_w{idx:03d}")
                cloned_widgets.append(widget_obj)

            gx, gy, gw, gh = _bounds_of_widgets(cloned_widgets)
            child_template = UIControlGroupTemplate(
                template_id=new_template_id,
                template_name=normalized_child_name,
                is_combination=True,
                widgets=cloned_widgets,
                group_position=(gx, gy),
                group_size=(gw, gh),
                supports_layout_visibility_override=True,
                description="由 UI 工作台（HTML）导入生成：按钮已打组（道具展示+底色+阴影+文本等）。",
                created_at=now,
                updated_at=now,
                extra={"__html_import_group_template_id": template_id, "__html_group_kind": "button"},
            )
            existing_ui_templates[new_template_id] = child_template.serialize()
            min_layer = min(int(getattr(w, "layer_index", 0) or 0) for w in members_sorted) if members_sorted else 0
            custom_group_entries.append((min_layer, new_template_id))

        # 2) 其余控件：保持“单控件模板”语义，便于在布局详情中逐项查看与调整
        for widget_index, source_widget in enumerate(source_widgets):
            if source_widget.widget_id in widgets_in_button_groups:
                continue
            desired_template_id_prefix = f"{template_id}_part"
            new_template_id = self._generate_unique_id(prefix=desired_template_id_prefix, existing=existing_template_ids)
            existing_template_ids.add(new_template_id)

            widget_obj = _clone_widget_with_new_id(source_widget, new_widget_id=f"{new_template_id}_w000")
            base_name = str(getattr(widget_obj, "widget_name", "") or "").strip() or str(getattr(widget_obj, "widget_type", "") or "").strip()
            desired_template_name = f"{normalized_layout_name}_{base_name}" if base_name else f"{normalized_layout_name}_控件_{widget_index:03d}"
            normalized_child_name = self._ensure_unique_name(desired=desired_template_name, existing_names=existing_template_names)
            existing_template_names.add(normalized_child_name)

            child_template = UIControlGroupTemplate(
                template_id=new_template_id,
                template_name=normalized_child_name,
                is_combination=False,
                widgets=[widget_obj],
                group_position=tuple(widget_obj.position),
                group_size=tuple(widget_obj.size),
                supports_layout_visibility_override=True,
                description="由 UI 工作台（HTML）拆分导入生成（单控件模板）。",
                created_at=now,
                updated_at=now,
                extra={"__html_import_group_template_id": template_id, "__html_group_kind": "single"},
            )
            existing_ui_templates[new_template_id] = child_template.serialize()
            custom_group_entries.append((int(getattr(widget_obj, "layer_index", 0) or 0), new_template_id))

        # 稳定排序：背景→前景
        custom_group_entries.sort(key=lambda pair: (pair[0], pair[1]))
        custom_group_template_ids = [template_id for _layer, template_id in custom_group_entries]

        layout_obj = UILayout(
            layout_id=layout_id,
            layout_name=normalized_layout_name,
            builtin_widgets=builtin_widgets,
            custom_groups=custom_group_template_ids,
            default_for_player="所有玩家",
            description="由 UI 工作台（HTML）导入生成（按钮已打组，其余控件为单控件模板）。",
            created_at=now,
            updated_at=now,
            visibility_overrides={},
        )
        management.ui_layouts[layout_id] = layout_obj.serialize()

        # 触发增量落盘：只同步 ui_layouts + ui_widget_templates
        mark_management_dirty = getattr(package_controller, "mark_management_dirty", None)
        if callable(mark_management_dirty):
            mark_management_dirty({"ui_layouts", "ui_widget_templates"})
        mark_index_dirty = getattr(package_controller, "mark_index_dirty", None)
        if callable(mark_index_dirty):
            mark_index_dirty()

        save_dirty_blocks = getattr(package_controller, "save_dirty_blocks", None)
        if callable(save_dirty_blocks):
            save_dirty_blocks()

        return ImportResult(
            layout_id=layout_id,
            layout_name=normalized_layout_name,
            template_id=template_id,
            template_name=normalized_template_name,
            template_count=len(custom_group_template_ids),
            widget_count=len(template_obj.widgets),
        )

    def import_layout_from_bundle_payload(self, *, layout_name: str, bundle_payload: dict) -> ImportBundleResult:
        """导入 Workbench 导出的 bundle（UILayout + 多个 UIControlGroupTemplate）。

        约定：
        - Web 侧负责“HTML → 扁平层 → widgets → 打组 → bundle”；
        - Python 侧负责：生成全库唯一 ID、写入 management、触发增量落盘与 UI 刷新。
        """
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("主窗口未绑定，无法导入")

        package_controller = getattr(main_window, "package_controller", None)
        if package_controller is None:
            raise RuntimeError("主窗口缺少 package_controller，无法导入")

        current_package_id = str(getattr(package_controller, "current_package_id", "") or "")
        if not current_package_id or current_package_id == "global_view":
            raise RuntimeError("请先切换到某个【项目存档】再执行导入（当前为 <共享资源>/未选择）。")

        package = getattr(package_controller, "current_package", None)
        if package is None:
            raise RuntimeError("当前项目存档为空，无法导入")

        management = getattr(package, "management", None)
        if management is None:
            raise RuntimeError("当前项目存档缺少 management，无法导入")

        resource_manager = getattr(package_controller, "resource_manager", None)
        if resource_manager is None:
            raise RuntimeError("package_controller 缺少 resource_manager，无法导入")

        # 写入当前包的 management 缓存（后续由 PackageController 统一落盘并同步索引）
        if not isinstance(getattr(management, "ui_widget_templates", None), dict):
            management.ui_widget_templates = {}
        if not isinstance(getattr(management, "ui_layouts", None), dict):
            management.ui_layouts = {}

        if not isinstance(bundle_payload, dict):
            raise RuntimeError("导入失败：bundle 必须是对象")

        bundle_layout = bundle_payload.get("layout", None)
        if not isinstance(bundle_layout, dict):
            raise RuntimeError("导入失败：bundle.layout 必须是对象（UILayout）。")

        raw_templates = bundle_payload.get("templates", None)
        templates_payload_list: list[dict] = []
        if isinstance(raw_templates, list):
            for item in raw_templates:
                if isinstance(item, dict):
                    templates_payload_list.append(item)
        elif isinstance(raw_templates, dict):
            for _key, item in raw_templates.items():
                if isinstance(item, dict):
                    templates_payload_list.append(item)
        else:
            raise RuntimeError("导入失败：bundle.templates 必须是数组或对象（template_id -> payload）。")

        if not templates_payload_list:
            raise RuntimeError("导入失败：bundle.templates 为空。")

        # --- 生成新 ID（全库同类型唯一）
        existing_layout_ids = set(resource_manager.list_resource_file_paths(ResourceType.UI_LAYOUT).keys())
        existing_template_ids = set(resource_manager.list_resource_file_paths(ResourceType.UI_WIDGET_TEMPLATE).keys())
        layout_id = self._generate_unique_id(prefix="layout_html", existing=existing_layout_ids)

        now = datetime.now().isoformat()

        # --- 规范化名称（避免 UI 列表中同名混淆）
        desired_layout_name = str(layout_name or "").strip()
        if not desired_layout_name:
            desired_layout_name = str(bundle_layout.get("layout_name", "") or bundle_layout.get("name", "") or "").strip()
        if not desired_layout_name:
            desired_layout_name = "HTML导入_界面布局"
        normalized_layout_name = self._ensure_unique_name(
            desired=desired_layout_name,
            existing_names=self._collect_existing_names(getattr(management, "ui_layouts", None), "layout_name"),
        )

        # --- 引擎模型
        from engine.configs.components.ui_control_group_model import (
            BUILTIN_WIDGET_TYPES,
            UIControlGroupTemplate,
            UILayout,
            create_builtin_widget_templates,
        )

        existing_ui_templates: dict = management.ui_widget_templates

        # --- 固有内容：优先使用“按包后缀化”的 builtin 模板（与资源库内约定一致）
        builtin_base_templates = create_builtin_widget_templates()
        builtin_widgets: list[str] = []
        for widget_type in list(BUILTIN_WIDGET_TYPES):
            preferred_template_id = f"builtin_{widget_type}__{current_package_id}"
            legacy_template_id = f"builtin_{widget_type}"

            if preferred_template_id in existing_ui_templates:
                builtin_widgets.append(preferred_template_id)
                continue
            if legacy_template_id in existing_ui_templates:
                builtin_widgets.append(legacy_template_id)
                continue

            base_template = builtin_base_templates.get(legacy_template_id)
            if base_template is None:
                continue

            payload = base_template.serialize()
            payload["template_id"] = preferred_template_id
            payload["template_name"] = widget_type
            payload["created_at"] = now
            payload["updated_at"] = now

            widgets_payload = payload.get("widgets")
            if isinstance(widgets_payload, list):
                for widget_payload_item in widgets_payload:
                    if not isinstance(widget_payload_item, dict):
                        continue
                    widget_payload_item["widget_id"] = f"builtin_{widget_type}_widget__{current_package_id}"
                    widget_payload_item["widget_type"] = widget_type
                    widget_payload_item["widget_name"] = widget_type
                    widget_payload_item["is_builtin"] = True

            existing_ui_templates[preferred_template_id] = payload
            builtin_widgets.append(preferred_template_id)

        existing_template_names = self._collect_existing_names(existing_ui_templates, "template_name")
        template_id_map: dict[str, str] = {}
        imported_widget_count = 0

        # --- 写入 bundle templates
        for raw_template_payload in templates_payload_list:
            template_obj = UIControlGroupTemplate.deserialize(raw_template_payload)
            if template_obj is None:
                raise RuntimeError("导入失败：bundle.templates 内存在缺少 template_id 的条目。")

            old_template_id = str(getattr(template_obj, "template_id", "") or "")
            new_template_id = self._generate_unique_id(prefix="ui_widget_template_html", existing=existing_template_ids)
            existing_template_ids.add(new_template_id)

            template_obj.template_id = new_template_id

            desired_template_name = str(getattr(template_obj, "template_name", "") or "").strip() or old_template_id or new_template_id
            normalized_template_name = self._ensure_unique_name(desired=desired_template_name, existing_names=existing_template_names)
            existing_template_names.add(normalized_template_name)
            template_obj.template_name = normalized_template_name

            template_obj.created_at = now
            template_obj.updated_at = now

            # 保留原始 widget_id（便于排查），并重写为全局唯一
            for idx, widget in enumerate(list(template_obj.widgets)):
                old_widget_id = str(getattr(widget, "widget_id", "") or "")
                if old_widget_id:
                    widget.extra.setdefault("__source_widget_id", old_widget_id)
                widget.widget_id = f"{new_template_id}_w{idx:03d}"
                widget.is_builtin = False

            imported_widget_count += len(template_obj.widgets)
            existing_ui_templates[new_template_id] = template_obj.serialize()
            if old_template_id:
                template_id_map[old_template_id] = new_template_id

        # --- 生成 layout.custom_groups（优先用 bundle 的顺序）
        raw_custom_groups = bundle_layout.get("custom_groups", [])
        if not isinstance(raw_custom_groups, list):
            raw_custom_groups = []

        custom_groups: list[str] = []
        if raw_custom_groups:
            for old_id_value in raw_custom_groups:
                old_id = str(old_id_value or "").strip()
                if not old_id:
                    continue
                new_id = template_id_map.get(old_id)
                if not new_id:
                    raise RuntimeError(f"导入失败：layout.custom_groups 引用了不存在的模板: {old_id}")
                custom_groups.append(new_id)
        else:
            custom_groups = list(template_id_map.values())

        default_for_player = str(bundle_layout.get("default_for_player") or "所有玩家")
        description = str(bundle_layout.get("description") or "由 UI 工作台（HTML）导入生成（bundle）。")

        layout_obj = UILayout(
            layout_id=layout_id,
            layout_name=normalized_layout_name,
            builtin_widgets=builtin_widgets,
            custom_groups=custom_groups,
            default_for_player=default_for_player,
            description=description,
            created_at=now,
            updated_at=now,
            visibility_overrides={},
        )
        management.ui_layouts[layout_id] = layout_obj.serialize()

        # 触发增量落盘：只同步 ui_layouts + ui_widget_templates
        mark_management_dirty = getattr(package_controller, "mark_management_dirty", None)
        if callable(mark_management_dirty):
            mark_management_dirty({"ui_layouts", "ui_widget_templates"})
        mark_index_dirty = getattr(package_controller, "mark_index_dirty", None)
        if callable(mark_index_dirty):
            mark_index_dirty()

        save_dirty_blocks = getattr(package_controller, "save_dirty_blocks", None)
        if callable(save_dirty_blocks):
            save_dirty_blocks()

        return ImportBundleResult(
            layout_id=layout_id,
            layout_name=normalized_layout_name,
            template_count=len(template_id_map),
            widget_count=imported_widget_count,
        )

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

    # --------------------------------------------------------------------- internal: helpers
    @staticmethod
    def _generate_unique_id(*, prefix: str, existing: set[str]) -> str:
        while True:
            candidate = f"{prefix}_{uuid4().hex[:8]}"
            if candidate not in existing:
                return candidate

    @staticmethod
    def _ensure_unique_name(*, desired: str, existing_names: set[str]) -> str:
        base = str(desired or "").strip() or "未命名"
        if base not in existing_names:
            return base
        index = 2
        while True:
            candidate = f"{base}_{index}"
            if candidate not in existing_names:
                return candidate
            index += 1

    @staticmethod
    def _collect_existing_names(container: object, field_name: str) -> set[str]:
        out: set[str] = set()
        if not isinstance(container, dict):
            return out
        for _rid, payload in container.items():
            if not isinstance(payload, dict):
                continue
            value = payload.get(field_name) or payload.get("name") or ""
            if isinstance(value, str) and value.strip():
                out.add(value.strip())
        return out


class _WorkbenchHttpServer:
    def __init__(self, *, workbench_dir: Path, bridge: UiWorkbenchBridge) -> None:
        self._workbench_dir = workbench_dir
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
        port = _choose_local_http_port(host=host)
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
        bridge: UiWorkbenchBridge | None = None,
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
        file_path = self._bridge._resolve_ui_source_path(scope=scope, rel_path=rel_path)
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
        self.send_header("X-Ui-Base-Gil-Name-B64", _encode_utf8_b64(file_name))
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
        file_name = _decode_utf8_b64(name_b64) if name_b64 else "base.gil"
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
            source_rel_path=source_rel_path, variable_defaults=variable_defaults if isinstance(variable_defaults, dict) else {}
        )
        self._send_json({"ok": True, **result}, status=200)

    def _handle_export_gil(self) -> None:
        # 内置 Workbench 不包含 UGC 写回工具链：明确返回“未实现”，避免前端拿到 404 或 HTML 导致报错。
        self._send_json(
            {"ok": False, "error": "export_gil is not supported in builtin workbench (requires private ugc_file_tools)."},
            status=501,
        )

    def _handle_export_gia(self) -> None:
        self._send_json(
            {"ok": False, "error": "export_gia is not supported in builtin workbench (requires private ugc_file_tools)."},
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


