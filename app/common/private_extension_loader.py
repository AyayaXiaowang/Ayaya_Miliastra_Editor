from __future__ import annotations

"""私有扩展加载器（仅导入，不包含私有实现）。

目标：
- 公开仓库只保留“扩展点 + 加载机制”，真正的私有功能代码放在本地/私有仓库/私有包中；
- 当前私有扩展默认视为启用（由 settings 强制），但仅在存在插件/配置时才会产生实际效果。

启用方式（推荐顺序）：
1) 用户设置（持久化、默认忽略不入库）：
   - `engine.configs.settings.settings.PRIVATE_EXTENSION_ENABLED` 当前会被强制为 True（不再通过设置页控制）
   - 若你希望“放进工作区即可自动加载”（不需要配置路径/模块名）：
     - 推荐：将私有插件放在 `<workspace_root>/private_extensions/<插件名>/plugin.py`
     - 兼容：也支持 `<workspace_root>/plugins/private_extensions/<插件名>/plugin.py`
     - 入口文件可实现 `install(workspace_root: Path) -> None`（可选）
   - 若你希望从工作区外的私有包加载（更通用）：
     - `settings.PRIVATE_EXTENSION_SYS_PATHS = ["D:/private/graph_generater_ext"]`
     - `settings.PRIVATE_EXTENSION_MODULES = ["my_private_pkg.graph_generater_ext"]`
   说明：这些值会落盘到 `app/runtime/cache/user_settings.json`（默认在 `.gitignore` 覆盖范围内）。
2) 环境变量（临时覆盖，不落盘）：
   - GRAPH_GENERATER_PRIVATE_PLUGIN_PATHS: 额外 sys.path 根目录列表（用 os.pathsep 分隔，Windows 为 ';'）
   - GRAPH_GENERATER_PRIVATE_PLUGIN_MODULES: 需要 import 的模块列表（用 ',' 或 ';' 分隔）

注意：不使用 try/except 吞错；导入或 install 失败直接抛出，便于快速暴露依赖/副作用问题。
"""

import importlib
from importlib.util import module_from_spec, spec_from_file_location
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Iterable, List, Sequence

from engine.configs.settings import settings
from engine.utils.logging.logger import log_info, log_warn

_ENV_PRIVATE_PATHS = "GRAPH_GENERATER_PRIVATE_PLUGIN_PATHS"
_ENV_PRIVATE_MODULES = "GRAPH_GENERATER_PRIVATE_PLUGIN_MODULES"

_DEFAULT_WORKSPACE_PLUGIN_DIRS: list[Path] = [
    # 推荐：工作区根目录下的本地私有扩展目录（默认应被 .gitignore 忽略）
    Path("private_extensions"),
    # 兼容：历史路径（放在 plugins/ 下也可；同样应被 .gitignore 忽略）
    Path("plugins/private_extensions"),
]

_loaded: bool = False
_loaded_modules: List[str] = []
_loaded_sys_paths: List[Path] = []
_loaded_source: str = "none"

_cached_workspace_plugin_modules: dict[Path, ModuleType] = {}


@dataclass(frozen=True, slots=True)
class PrivateExtensionLoadResult:
    sys_paths: list[Path]
    modules: list[str]
    source: str  # "env" | "settings" | "workspace_dir" | "none"


def _split_non_empty(items: Iterable[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def _parse_module_list(text: str) -> list[str]:
    normalized = str(text or "").replace("\n", ",").replace("\r", ",").replace(";", ",")
    return _split_non_empty(normalized.split(","))


def _parse_sys_path_list(text: str) -> list[str]:
    # os.pathsep 在 Windows 为 ';'，Linux/macOS 为 ':'
    return _split_non_empty(str(text or "").split(os.pathsep))


def _resolve_paths(*, workspace_root: Path, raw_paths: Sequence[str]) -> list[Path]:
    resolved: list[Path] = []
    for raw in raw_paths:
        raw_text = str(raw or "").strip().strip('"').strip("'")
        if not raw_text:
            continue
        p = Path(raw_text)
        abs_path = (workspace_root / p) if not p.is_absolute() else p
        resolved.append(abs_path.resolve())
    return resolved


def _load_module_from_path(*, module_id: str, file_path: Path) -> ModuleType:
    cached = _cached_workspace_plugin_modules.get(file_path)
    if cached is not None:
        return cached

    spec = spec_from_file_location(module_id, str(file_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法为私有扩展创建模块说明：{file_path}")
    module = module_from_spec(spec)
    # 关键：按文件路径执行模块时也要写入 sys.modules，保持与 import 语义一致。
    # 否则 dataclasses/typing 等依赖 `sys.modules[__module__]` 的逻辑会失败。
    sys.modules[str(module_id)] = module
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    _cached_workspace_plugin_modules[file_path] = module
    return module


def _iter_workspace_plugin_entry_files(*, workspace_root: Path) -> list[Path]:
    """枚举工作区内的私有插件入口文件（每个插件一个目录，入口为 plugin.py）。"""
    entry_files: list[Path] = []
    for rel_dir in list(_DEFAULT_WORKSPACE_PLUGIN_DIRS):
        base_dir = (workspace_root / rel_dir).resolve()
        if not base_dir.is_dir():
            continue
        for child in sorted(base_dir.iterdir(), key=lambda p: p.name.lower()):
            if not child.is_dir():
                continue
            plugin_py = (child / "plugin.py").resolve()
            if plugin_py.is_file():
                entry_files.append(plugin_py)
    return entry_files


def _load_workspace_private_plugins(*, workspace_root: Path) -> list[str]:
    """从 `<workspace_root>/plugins/private_extensions/<plugin>/plugin.py` 加载插件。"""
    entry_files = _iter_workspace_plugin_entry_files(workspace_root=workspace_root)
    if not entry_files:
        return []

    loaded_ids: list[str] = []
    for entry in entry_files:
        plugin_name = entry.parent.name
        module_id = f"private_extensions.{plugin_name}"
        module = _load_module_from_path(module_id=module_id, file_path=entry)
        install_fn = getattr(module, "install", None)
        if callable(install_fn):
            install_fn(workspace_root)
        loaded_ids.append(module_id)
    return loaded_ids


def _parse_settings_paths(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return _parse_sys_path_list(value)
    if isinstance(value, list):
        return _split_non_empty([str(x) for x in value])
    raise ValueError("settings.PRIVATE_EXTENSION_SYS_PATHS 必须是 list[str] 或 str")


def _parse_settings_modules(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return _parse_module_list(value)
    if isinstance(value, list):
        return _split_non_empty([str(x) for x in value])
    raise ValueError("settings.PRIVATE_EXTENSION_MODULES 必须是 list[str] 或 str")


def _build_load_plan(*, workspace_root: Path) -> PrivateExtensionLoadResult:
    env_paths_text = str(os.environ.get(_ENV_PRIVATE_PATHS, "") or "").strip()
    env_modules_text = str(os.environ.get(_ENV_PRIVATE_MODULES, "") or "").strip()

    if env_paths_text or env_modules_text:
        sys_paths = _resolve_paths(workspace_root=workspace_root, raw_paths=_parse_sys_path_list(env_paths_text))
        modules = _parse_module_list(env_modules_text)
        return PrivateExtensionLoadResult(sys_paths=sys_paths, modules=modules, source="env")

    enabled = bool(getattr(settings, "PRIVATE_EXTENSION_ENABLED", False))
    if not enabled:
        return PrivateExtensionLoadResult(sys_paths=[], modules=[], source="none")

    cfg_paths = _parse_settings_paths(getattr(settings, "PRIVATE_EXTENSION_SYS_PATHS", []))
    cfg_modules = _parse_settings_modules(getattr(settings, "PRIVATE_EXTENSION_MODULES", []))

    sys_paths = _resolve_paths(workspace_root=workspace_root, raw_paths=cfg_paths)
    modules = _split_non_empty(cfg_modules)

    if sys_paths or modules:
        return PrivateExtensionLoadResult(sys_paths=sys_paths, modules=modules, source="settings")

    # 当用户已启用私有扩展但未提供 sys_path/modules 时：
    # 采用约定目录自动发现并加载（优先 `<workspace_root>/private_extensions/<plugin>/plugin.py`）。
    has_any_dir = False
    for rel_dir in list(_DEFAULT_WORKSPACE_PLUGIN_DIRS):
        if (workspace_root / rel_dir).is_dir():
            has_any_dir = True
            break
    if has_any_dir:
        return PrivateExtensionLoadResult(sys_paths=[], modules=[], source="workspace_dir")
    return PrivateExtensionLoadResult(sys_paths=[], modules=[], source="none")


def ensure_private_extensions_loaded(*, workspace_root: Path) -> PrivateExtensionLoadResult:
    """按 env/本地配置加载私有扩展模块（幂等）。"""
    global _loaded, _loaded_modules, _loaded_sys_paths, _loaded_source
    if _loaded:
        return PrivateExtensionLoadResult(
            sys_paths=list(_loaded_sys_paths),
            modules=list(_loaded_modules),
            source=str(_loaded_source or "none"),
        )

    plan = _build_load_plan(workspace_root=workspace_root)
    _loaded = True
    _loaded_source = plan.source

    # 先注入 sys.path，确保后续 import 能找到私有包
    added_paths: list[Path] = []
    for path in plan.sys_paths:
        if not path.exists():
            log_warn("[EXT] 私有扩展 sys.path 不存在，已跳过: {}", str(path))
            continue
        text = str(path)
        if text in sys.path:
            continue
        sys.path.insert(0, text)
        added_paths.append(path)

    imported_modules: list[str] = []
    if plan.source in {"env", "settings"}:
        for module_name in plan.modules:
            imported_modules.append(module_name)
            module = importlib.import_module(module_name)

            install_fn = getattr(module, "install", None)
            if callable(install_fn):
                install_fn(workspace_root)
    elif plan.source == "workspace_dir":
        imported_modules.extend(_load_workspace_private_plugins(workspace_root=workspace_root))

    _loaded_sys_paths = added_paths
    _loaded_modules = imported_modules

    if added_paths or imported_modules:
        log_info(
            "[EXT] 私有扩展已加载：sys_path_count={}, module_count={}, source={}",
            len(added_paths),
            len(imported_modules),
            plan.source,
        )

    return plan


