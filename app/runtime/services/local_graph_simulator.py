from __future__ import annotations

import importlib.util
import re
import sys
import zlib
import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence

from engine import GraphCodeParser, get_node_registry
from engine.signal.definition_repository import get_default_signal_repository
from engine.utils.name_utils import sanitize_class_name
from engine.utils.workspace import init_settings_for_workspace, resolve_workspace_root
from engine.utils.cache.cache_paths import get_runtime_cache_root

from app.codegen import ExecutableCodeGenerator
from app.runtime.engine.game_state import GameRuntime, MockEntity
from app.runtime.services.local_graph_sim_mount_catalog import (
    LocalGraphSimResourceMountSpec,
    list_mount_resources_for_package,
    resolve_resource_mounts_to_runtime_plan,
)


_UI_KEY_PREFIX = "ui_key:"
_LAYOUT_INDEX_KEY_PREFIX = "LAYOUT_INDEX__HTML__"


_LAYOUT_INDEX_DESC_HTML_RE = re.compile(r"[（(]([^（）()]+?)\.html[)）]")


def _hash32(text: str) -> int:
    return int(zlib.adler32(text.encode("utf-8")) & 0xFFFFFFFF)


def _stable_sim_index(ui_key: str) -> int:
    """
    为本地测试生成稳定的“伪 GUID/伪索引”：
    - 保持为正整数；
    - 高位对齐到 0x4000_0000（与历史 UI GUID 风格一致，便于日志排查）；
    - 低位由 adler32 派生，确保跨进程稳定。
    """
    checksum = _hash32(ui_key)
    return int(0x40000000 | (checksum & 0x3FFFFFFF))


def extract_html_stem_from_layout_index_description(description: str) -> str:
    """从「布局索引_*」图变量的描述中提取 HTML stem（不含 `.html`）。"""
    text = str(description or "")
    m = _LAYOUT_INDEX_DESC_HTML_RE.search(text)
    if not m:
        return ""
    return str(m.group(1) or "").strip()


def stable_layout_index_from_html_stem(html_stem: str) -> int:
    """将 HTML stem 映射为稳定 layout_index（用于本地测试的多页切换）。"""
    stem = str(html_stem or "").strip()
    if not stem:
        raise ValueError("html_stem 不能为空")
    return _stable_sim_index(f"{_LAYOUT_INDEX_KEY_PREFIX}{stem}")


def _fallback_layout_index(*, variable_name: str, description: str) -> int:
    stem = extract_html_stem_from_layout_index_description(description)
    if stem:
        return stable_layout_index_from_html_stem(stem)
    return _stable_sim_index(f"LAYOUT_INDEX__VAR__{str(variable_name or '').strip()}")


@dataclass(frozen=True, slots=True)
class GraphCompileResult:
    workspace_root: Path
    graph_code_file: Path
    graph_name: str
    graph_type: str
    executable_file: Path
    module_name: str
    class_name: str


class UiKeyIndexRegistry:
    """本地测试用 ui_key <-> index(伪GUID) 注册表（稳定、可逆）。"""

    def __init__(self) -> None:
        self._index_by_key: Dict[str, int] = {}
        self._key_by_index: Dict[int, str] = {}

    def ensure(self, ui_key: str) -> int:
        key = str(ui_key or "").strip()
        if not key:
            raise ValueError("ui_key 不能为空")
        existing = self._index_by_key.get(key)
        if existing is not None:
            return int(existing)

        index = _stable_sim_index(key)
        collided = self._key_by_index.get(index)
        if collided is not None and collided != key:
            raise ValueError(f"ui_key hash 冲突：{key!r} 与 {collided!r} -> {index}")

        self._index_by_key[key] = int(index)
        self._key_by_index[int(index)] = key
        return int(index)

    def try_get_index(self, ui_key: str) -> Optional[int]:
        key = str(ui_key or "").strip()
        if not key:
            return None
        value = self._index_by_key.get(key)
        return int(value) if value is not None else None

    def try_get_key(self, index: int) -> Optional[str]:
        return self._key_by_index.get(int(index))

    def to_payload(self) -> dict[str, Any]:
        return {
            "version": 1,
            "ui_key_to_index": dict(self._index_by_key),
            "note": "本文件由本地测试模拟器生成：用于将 ui_key 映射到稳定的伪 GUID/索引（不代表真实游戏 GUID）。",
        }


def _iter_graph_variable_entries(graph_model: object) -> Iterable[dict[str, Any]]:
    raw = getattr(graph_model, "graph_variables", None)
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, dict)]


def _iter_graph_variable_configs(graph_module: object) -> Iterable[object]:
    raw = getattr(graph_module, "GRAPH_VARIABLES", None)
    if not isinstance(raw, list):
        return []
    return [x for x in raw if hasattr(x, "name") and hasattr(x, "variable_type")]


def _maybe_coerce_scalar_default(*, variable_type: str, default_value: object) -> object:
    vt = str(variable_type or "").strip()
    if isinstance(default_value, bool):
        return default_value
    if isinstance(default_value, (int, float, tuple, list, dict)):
        return default_value
    if default_value is None:
        return None
    if not isinstance(default_value, str):
        return default_value

    text = default_value.strip()
    if text == "":
        return default_value

    if vt in {"整数", "GUID"}:
        if re.fullmatch(r"-?\d+", text):
            return int(text)
        return default_value
    if vt == "浮点数":
        if re.fullmatch(r"-?\d+\.\d+", text) or re.fullmatch(r"-?\d+", text):
            return float(text)
        return default_value
    return default_value


def build_ui_key_registry_from_graph(*, graph_model: object) -> UiKeyIndexRegistry:
    """从图变量默认值里收集所有 `ui_key:` 占位符并注册为稳定 index。"""
    registry = UiKeyIndexRegistry()
    for entry in _iter_graph_variable_entries(graph_model):
        default_value = entry.get("default_value")
        if not isinstance(default_value, str):
            continue
        text = default_value.strip()
        if not text.startswith(_UI_KEY_PREFIX):
            continue
        ui_key = text[len(_UI_KEY_PREFIX) :].strip()
        if ui_key:
            registry.ensure(ui_key)
    return registry


def build_ui_key_registry_from_graph_variables(*, graph_variables: Iterable[object]) -> UiKeyIndexRegistry:
    registry = UiKeyIndexRegistry()
    for cfg in graph_variables:
        default_value = getattr(cfg, "default_value", None)
        if not isinstance(default_value, str):
            continue
        text = default_value.strip()
        if not text.startswith(_UI_KEY_PREFIX):
            continue
        ui_key = text[len(_UI_KEY_PREFIX) :].strip()
        if ui_key:
            registry.ensure(ui_key)
    return registry


def populate_runtime_graph_variables_from_graph_variables(
    *,
    game: GameRuntime,
    graph_variables: Iterable[object],
    ui_registry: UiKeyIndexRegistry,
    enable_layout_index_fallback: bool,
) -> None:
    """
    将节点图源码中的 GRAPH_VARIABLES.default_value 写入 GameRuntime.graph_variables。
    用途与约束同 populate_runtime_graph_variables（但数据源为 GraphVariableConfig 列表）。
    """
    if not isinstance(getattr(game, "graph_variables", None), dict):
        game.graph_variables = {}

    for cfg in graph_variables:
        name = str(getattr(cfg, "name", "") or "").strip()
        if not name:
            continue
        variable_type = str(getattr(cfg, "variable_type", "") or "").strip()
        default_value = getattr(cfg, "default_value", None)
        description = str(getattr(cfg, "description", "") or "")

        if isinstance(default_value, str):
            text = default_value.strip()
            if text.startswith(_UI_KEY_PREFIX):
                ui_key = text[len(_UI_KEY_PREFIX) :].strip()
                if ui_key:
                    game.graph_variables[name] = ui_registry.ensure(ui_key)
                    continue

        value = _maybe_coerce_scalar_default(variable_type=variable_type, default_value=default_value)

        if (
            enable_layout_index_fallback
            and str(name).startswith("布局索引_")
            and variable_type == "整数"
            and value == 0
        ):
            game.graph_variables[name] = _fallback_layout_index(variable_name=name, description=description)
            continue

        game.graph_variables[name] = value


def populate_runtime_graph_variables(
    *,
    game: GameRuntime,
    graph_model: object,
    ui_registry: UiKeyIndexRegistry,
    enable_layout_index_fallback: bool,
) -> None:
    """
    将 GraphModel.graph_variables 的 default_value 写入 GameRuntime.graph_variables。

    说明：
    - 本函数用于“本地测试”初始化，不应产生大量日志，因此不走 set_graph_variable 的打印路径；
    - `ui_key:` 形式会在此处解析为稳定 index（伪 GUID）；
    - 布局索引（布局索引_*）若默认值为 0，且启用 fallback，则填入 1（让图逻辑能继续跑）。
    """
    if not isinstance(getattr(game, "graph_variables", None), dict):
        game.graph_variables = {}

    for entry in _iter_graph_variable_entries(graph_model):
        name = str(entry.get("name") or "").strip()
        if not name:
            continue

        variable_type = str(entry.get("variable_type") or "").strip()
        default_value = entry.get("default_value", None)

        # ui_key:... -> 伪 GUID index
        if isinstance(default_value, str):
            text = default_value.strip()
            if text.startswith(_UI_KEY_PREFIX):
                ui_key = text[len(_UI_KEY_PREFIX) :].strip()
                if ui_key:
                    game.graph_variables[name] = ui_registry.ensure(ui_key)
                    continue

        value = _maybe_coerce_scalar_default(variable_type=variable_type, default_value=default_value)
        description = str(entry.get("description") or "")

        # 布局索引（写回阶段会回填，MVP 本地测试给个非 0 兜底，让逻辑不因“索引=0”短路）
        if (
            enable_layout_index_fallback
            and str(name).startswith("布局索引_")
            and variable_type == "整数"
            and value == 0
        ):
            game.graph_variables[name] = _fallback_layout_index(variable_name=name, description=description)
            continue

        game.graph_variables[name] = value


def compile_graph_to_executable(*, workspace_root: Path, graph_code_file: Path) -> GraphCompileResult:
    """
    将节点图源码编译为“可运行节点图类”（生成到 runtime cache），并返回编译结果信息。

    注意：
    - 生成文件属于运行时缓存，不落资源库；
    - 生成代码仍然是 Python 源码：便于 diff/排查/断点。
    """
    workspace = Path(workspace_root).resolve()
    graph_path = Path(graph_code_file).resolve()
    if not graph_path.is_file():
        raise FileNotFoundError(str(graph_path))

    init_settings_for_workspace(workspace_root=workspace, load_user_settings=False)

    registry = get_node_registry(workspace, include_composite=True)
    node_library = registry.get_library()

    parser = GraphCodeParser(workspace, node_library)
    graph_model, metadata = parser.parse_file(graph_path)

    graph_name = str(metadata.get("graph_name") or getattr(graph_model, "graph_name", "") or "").strip()
    graph_type = str(metadata.get("graph_type") or "server").strip() or "server"
    if not graph_name:
        graph_name = str(getattr(graph_model, "graph_name", "") or "").strip() or graph_path.stem

    generator = ExecutableCodeGenerator(workspace, node_library)
    executable_code = generator.generate_code(graph_model, metadata)

    cache_root = get_runtime_cache_root(workspace)
    out_dir = (cache_root / "local_graph_sim" / "executable_graphs").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    mtime = float(graph_path.stat().st_mtime)
    key = f"{graph_path.as_posix()}:{mtime}"
    digest = _hash32(key)
    out_file = (out_dir / f"{graph_path.stem}__exec_{digest:08x}.py").resolve()
    out_file.write_text(executable_code, encoding="utf-8")

    module_name = f"runtime.local_graph_sim.{graph_path.stem}_{digest:08x}"
    class_name = sanitize_class_name(graph_name)
    if not class_name:
        class_name = sanitize_class_name(graph_path.stem) or "Graph"

    return GraphCompileResult(
        workspace_root=workspace,
        graph_code_file=graph_path,
        graph_name=graph_name,
        graph_type=graph_type,
        executable_file=out_file,
        module_name=module_name,
        class_name=class_name,
    )


def load_compiled_graph_class(result: GraphCompileResult) -> type:
    spec = importlib.util.spec_from_file_location(result.module_name, str(result.executable_file))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载可执行图模块: {result.executable_file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[result.module_name] = module
    spec.loader.exec_module(module)  # type: ignore[attr-defined]

    graph_class = getattr(module, result.class_name, None)
    if not isinstance(graph_class, type):
        raise RuntimeError(f"可执行图模块缺少类: {result.class_name} ({result.executable_file})")
    return graph_class


@dataclass(frozen=True, slots=True)
class GraphSourceResult:
    workspace_root: Path
    graph_code_file: Path
    graph_name: str
    graph_type: str
    module_name: str
    class_name: str


@dataclass(frozen=True, slots=True)
class GraphMountSpec:
    """本地测试：额外挂载的节点图（源码）。"""

    graph_code_file: Path
    owner_entity_name: str = "自身实体"


@dataclass(frozen=True, slots=True)
class MountedGraph:
    """本地测试：已挂载的节点图信息（用于监控面板/调试输出）。"""

    graph_code_file: Path
    graph_name: str
    graph_type: str
    module_name: str
    class_name: str
    owner_entity_id: str
    owner_entity_name: str


def _parse_graph_meta_from_source(graph_code_file: Path) -> tuple[str, str]:
    """
    读取源码顶部注释块中的 graph_name / graph_type（若不存在则回退）。

    约定：Graph Code 文件开头 docstring 常含：
      graph_name: xxx
      graph_type: server
    """
    text = Path(graph_code_file).read_text(encoding="utf-8")
    # 只扫描前 200 行足够（但这里直接扫描全文也没副作用）
    name_match = re.search(r"^graph_name:\s*(.+?)\s*$", text, flags=re.MULTILINE)
    type_match = re.search(r"^graph_type:\s*(.+?)\s*$", text, flags=re.MULTILINE)
    graph_name = (name_match.group(1).strip() if name_match else "") or Path(graph_code_file).stem
    graph_type = (type_match.group(1).strip() if type_match else "") or "server"
    return graph_name, graph_type


def load_source_graph_module_and_class(*, result: GraphSourceResult) -> tuple[object, type]:
    spec = importlib.util.spec_from_file_location(result.module_name, str(result.graph_code_file))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载节点图源码模块: {result.graph_code_file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[result.module_name] = module
    spec.loader.exec_module(module)  # type: ignore[attr-defined]

    graph_class = getattr(module, result.class_name, None)
    if not isinstance(graph_class, type):
        raise RuntimeError(f"节点图源码模块缺少类: {result.class_name} ({result.graph_code_file})")
    return module, graph_class


def _find_or_create_entity_by_name(game: GameRuntime, name: str) -> MockEntity:
    desired = str(name or "").strip()
    if not desired:
        raise ValueError("实体名称不能为空")
    for entity in game.get_all_entities():
        if getattr(entity, "name", None) == desired:
            return entity
    return game.create_mock_entity(desired)


@dataclass(slots=True)
class LocalGraphSimSession:
    workspace_root: Path
    graph_code_file: Path
    graph_name: str
    graph_type: str
    ui_registry: UiKeyIndexRegistry
    game: GameRuntime
    owner_entity: MockEntity
    player_entity: MockEntity
    graph_instance: object
    mounted_graphs: list[MountedGraph] = field(default_factory=list)

    def drain_ui_patches(self) -> list[dict[str, Any]]:
        raw = self.game.drain_ui_patches()
        enriched: list[dict[str, Any]] = []
        for item in raw:
            patch = dict(item) if isinstance(item, dict) else {"op": "unknown", "raw": item}
            widget_index = patch.get("widget_index", None)
            if isinstance(widget_index, int):
                ui_key = self.ui_registry.try_get_key(widget_index)
                if ui_key:
                    patch["ui_key"] = ui_key
                    if ui_key.startswith("UI_STATE_GROUP__"):
                        # UI_STATE_GROUP__<group>__<state>__group
                        parts = ui_key.split("__")
                        if len(parts) >= 4:
                            patch["ui_state_group_key"] = parts[1]
                            patch["ui_state"] = parts[2]
            state = str(patch.get("state") or "").strip()
            if state:
                patch["visible"] = state == "界面控件组状态_开启"
            enriched.append(patch)
        return enriched

    def emit_signal(self, *, signal_id: str, params: Optional[Dict[str, Any]] = None) -> list[dict[str, Any]]:
        sid = str(signal_id or "").strip()
        if not sid:
            raise ValueError("signal_id 不能为空")
        repo = get_default_signal_repository()
        payload = repo.get_payload(sid)
        if payload is None:
            # 兼容：允许直接传入 signal_name（更贴近节点图侧的“显示名称”）
            resolved = repo.resolve_id_by_name(sid)
            if resolved:
                sid = resolved
                payload = repo.get_payload(sid)
        if payload is None:
            raise ValueError(f"未知 signal_id: {sid}")
        signal_name = str(payload.get("signal_name") or "").strip()
        if not signal_name:
            raise ValueError(f"信号定义缺少 signal_name: {sid}")

        event_kwargs = {
            "事件源实体": self.owner_entity,
            "事件源GUID": 0,
            "信号来源实体": self.owner_entity,
            **(params or {}),
        }

        # 兼容两种注册口径：
        # - 源码图通常按 signal_name 注册；
        # - 部分导出/生成代码可能按 signal_id 注册。
        if signal_name in getattr(self.game, "event_handlers", {}):
            self.game.trigger_event(signal_name, **event_kwargs)
        else:
            self.game.trigger_event(sid, **event_kwargs)
        return self.drain_ui_patches()

    def trigger_ui_click(
        self,
        *,
        data_ui_key: str,
        data_ui_state_group: str = "",
        data_ui_state: str = "",
        player_entity: MockEntity | None = None,
    ) -> list[dict[str, Any]]:
        key = str(data_ui_key or "").strip()
        if not key:
            raise ValueError("data_ui_key 不能为空")
        group = str(data_ui_state_group or "").strip()
        state = str(data_ui_state or "").strip()

        candidates: list[str] = []
        if group and state:
            candidates.append(f"HTML导入_界面布局__{group}__{state}__btn_item")
        candidates.append(f"HTML导入_界面布局__{key}__btn_item")

        chosen: str | None = None
        for c in candidates:
            if self.ui_registry.try_get_index(c) is not None:
                chosen = c
                break
        if chosen is None:
            chosen = candidates[0]

        index = self.ui_registry.ensure(chosen)

        source_player = player_entity or self.player_entity
        self.game.trigger_event(
            "界面控件组触发时",
            事件源实体=source_player,
            事件源GUID=index,
            界面控件组组合索引=index,
            界面控件组索引=index,
        )
        return self.drain_ui_patches()


def _path_key(path: Path) -> str:
    return Path(path).resolve().as_posix().casefold()


def _infer_resource_mounts_for_extra_graph_mounts(
    *,
    workspace_root: Path,
    active_package_id: str,
    extra_mounts: Sequence[GraphMountSpec],
) -> list[LocalGraphSimResourceMountSpec]:
    """
    当调用方没有显式传入 resource_mounts 时，尝试为「额外挂载的图」推断一个合适的资源挂载：
    - 目标：在挂载图前预置实体自定义变量默认值（变量文件 + 组件默认值 + override），避免读取到 None；
    - 策略：在 active_package_id 对应的项目存档中扫描可挂载资源（模板/实体摆放/关卡实体），
      找到包含该 graph_code_file 的资源并选取一个“无歧义”的候选项。

    说明：
    - 仅对 extra_mounts 推断（主图仍按调用方 owner_entity_name 挂载），避免 UI 预览默认行为变化过大；
    - 优先选择「元件模板」资源（稳定、通常携带自定义变量默认值），其次关卡实体、实体摆放；
    - 若同一 graph_code_file 对应多个同类候选（例如多个实例都包含同一模板图），则跳过自动推断。
    """
    pkg = str(active_package_id or "").strip()
    if not pkg:
        return []
    mounts = list(extra_mounts or ())
    if not mounts:
        return []

    graph_keys = sorted({_path_key(Path(m.graph_code_file)) for m in mounts}, key=lambda x: str(x))
    if not graph_keys:
        return []

    resources = list_mount_resources_for_package(workspace_root=Path(workspace_root).resolve(), package_id=pkg)

    candidates_by_graph: dict[str, list[object]] = {}
    for info in list(resources or []):
        # 没有自定义变量快照的资源挂载通常无法解决“读取到 None”的问题，这里跳过以减少副作用。
        custom_names = getattr(info, "custom_variable_names", None)
        if not isinstance(custom_names, list) or not custom_names:
            continue
        graphs = getattr(info, "graphs", None)
        if not isinstance(graphs, list) or not graphs:
            continue
        for g in graphs:
            graph_file = getattr(g, "graph_code_file", None)
            if not isinstance(graph_file, str) or not graph_file.strip():
                continue
            candidates_by_graph.setdefault(_path_key(Path(graph_file)), []).append(info)

    out: list[LocalGraphSimResourceMountSpec] = []
    seen: set[tuple[str, str]] = set()
    for key in graph_keys:
        cands = list(candidates_by_graph.get(key, []) or [])
        if not cands:
            continue

        def _rtype(x: object) -> str:
            spec = getattr(x, "spec", None)
            return str(getattr(spec, "resource_type", "") or "").strip()

        chosen: object | None = None

        templates = [c for c in cands if _rtype(c) == "template"]
        if len(templates) == 1:
            chosen = templates[0]
        elif len(templates) > 1:
            continue
        else:
            level_entities = [c for c in cands if _rtype(c) == "level_entity"]
            if len(level_entities) == 1:
                chosen = level_entities[0]
            elif len(level_entities) > 1:
                continue
            else:
                instances = [c for c in cands if _rtype(c) == "instance"]
                if len(instances) == 1:
                    chosen = instances[0]
                elif len(instances) > 1:
                    continue

        if chosen is None:
            continue

        spec = getattr(chosen, "spec", None)
        if not isinstance(spec, LocalGraphSimResourceMountSpec):
            continue
        spec_key = (str(spec.resource_type), str(spec.resource_id))
        if spec_key in seen:
            continue
        seen.add(spec_key)
        out.append(spec)

    return out


def build_local_graph_sim_session(
    *,
    workspace_root: Path | None,
    graph_code_file: Path,
    owner_entity_name: str = "自身实体",
    player_entity_name: str = "玩家1",
    present_player_count: int = 1,
    enable_layout_index_fallback: bool = True,
    extra_graph_mounts: Sequence[GraphMountSpec] = (),
    resource_mounts: Sequence[LocalGraphSimResourceMountSpec] = (),
) -> LocalGraphSimSession:
    workspace = (
        Path(workspace_root).resolve()
        if workspace_root is not None
        else resolve_workspace_root(start_paths=[Path(__file__).resolve()])
    )

    # 关键：在导入节点图源码前注入 settings 的 workspace_root（graph_prelude_server 会校验定义资源）
    init_settings_for_workspace(workspace_root=workspace, load_user_settings=False)

    # 推断并应用 active_package_id（共享 / 共享+当前项目存档），确保信号/结构体/关卡变量 Schema 与图文件作用域一致。
    def _apply_active_scope_for_file(file_path: Path) -> str | None:
        from engine.utils.resource_library_layout import (
            PROJECT_ARCHIVE_LIBRARY_DIRNAME,
            SHARED_LIBRARY_DIRNAME,
            find_containing_resource_root,
        )
        from engine.utils.runtime_scope import get_active_package_id, set_active_package_id as set_runtime_active_package_id
        from engine.resources.definition_schema_view import set_default_definition_schema_view_active_package_id
        from engine.resources.level_variable_schema_view import set_default_level_variable_schema_view_active_package_id
        from engine.resources.ingame_save_template_schema_view import set_default_ingame_save_template_schema_view_active_package_id
        from engine.signal import invalidate_default_signal_repository_cache
        from engine.struct import invalidate_default_struct_repository_cache

        resource_library_root = (workspace / "assets" / "资源库").resolve()
        resource_root = find_containing_resource_root(resource_library_root, Path(file_path).resolve())
        if resource_root is None:
            active_package_id = get_active_package_id()
        elif resource_root.name == SHARED_LIBRARY_DIRNAME:
            active_package_id = None
        elif resource_root.parent.name == PROJECT_ARCHIVE_LIBRARY_DIRNAME:
            active_package_id = resource_root.name
        else:
            active_package_id = None

        set_runtime_active_package_id(active_package_id)
        set_default_definition_schema_view_active_package_id(active_package_id)
        set_default_level_variable_schema_view_active_package_id(active_package_id)
        set_default_ingame_save_template_schema_view_active_package_id(active_package_id)
        invalidate_default_signal_repository_cache()
        invalidate_default_struct_repository_cache()
        return active_package_id

    main_graph_path = Path(graph_code_file).resolve()
    active_package_id = _apply_active_scope_for_file(main_graph_path)

    extra_mounts_list: list[GraphMountSpec] = []
    for m in list(extra_graph_mounts or ()):
        extra_mounts_list.append(
            GraphMountSpec(
                graph_code_file=Path(getattr(m, "graph_code_file")).resolve(),
                owner_entity_name=str(getattr(m, "owner_entity_name", "") or owner_entity_name).strip() or owner_entity_name,
            )
        )

    # 解析“按元件/实体挂载”的资源：加载自定义变量初值，并扩展挂载图列表。
    effective_resource_mounts: list[LocalGraphSimResourceMountSpec] = list(resource_mounts or ())
    if (not effective_resource_mounts) and isinstance(active_package_id, str) and active_package_id.strip() and extra_mounts_list:
        inferred = _infer_resource_mounts_for_extra_graph_mounts(
            workspace_root=workspace,
            active_package_id=str(active_package_id),
            extra_mounts=extra_mounts_list,
        )
        if inferred:
            effective_resource_mounts = list(inferred)

    custom_vars_by_owner: dict[str, dict[str, Any]] = {}
    resolved_mounts: list[tuple[Path, str]] = []
    resolved_graph_keys: set[str] = set()
    if effective_resource_mounts:
        resolved_mounts, resolved_custom_vars = resolve_resource_mounts_to_runtime_plan(
            workspace_root=workspace,
            active_package_id=active_package_id,
            mount_specs=list(effective_resource_mounts or ()),
        )
        if isinstance(resolved_custom_vars, dict) and resolved_custom_vars:
            custom_vars_by_owner.update(resolved_custom_vars)
        resolved_graph_keys = {_path_key(Path(graph_file)) for graph_file, _ in list(resolved_mounts)}

    # 最终挂载列表：主图优先；若某 extra_graph 已由 resource_mounts 挂载（带自定义变量快照），则跳过它的显式 extra_mount，
    # 避免同一图被挂到“错误 owner”上导致运行时报错（以及重复 handler 处理事件）。
    mounts: list[GraphMountSpec] = [GraphMountSpec(graph_code_file=main_graph_path, owner_entity_name=owner_entity_name)]
    for m in extra_mounts_list:
        if _path_key(Path(m.graph_code_file)) in resolved_graph_keys:
            continue
        mounts.append(m)
    for graph_file, owner_name in list(resolved_mounts or []):
        mounts.append(GraphMountSpec(graph_code_file=Path(graph_file).resolve(), owner_entity_name=str(owner_name)))

    # 去重：同一 (图文件, owner实体名) 只挂一次，保持稳定顺序（主图优先）。
    seen_mount_keys: set[tuple[str, str]] = set()
    mounts_unique: list[GraphMountSpec] = []
    for m in mounts:
        graph_path = Path(getattr(m, "graph_code_file")).resolve()
        owner = str(getattr(m, "owner_entity_name", "") or "").strip() or owner_entity_name
        key = (graph_path.as_posix(), owner)
        if key in seen_mount_keys:
            continue
        seen_mount_keys.add(key)
        mounts_unique.append(GraphMountSpec(graph_code_file=graph_path, owner_entity_name=owner))
    mounts = mounts_unique

    loaded_by_path: dict[Path, tuple[GraphSourceResult, object, type, list[object]]] = {}
    graph_variables_all: list[object] = []
    load_order: list[tuple[GraphMountSpec, GraphSourceResult, object, type, list[object]]] = []
    for mount in mounts:
        graph_path = Path(mount.graph_code_file).resolve()
        cached = loaded_by_path.get(graph_path)
        if cached is not None:
            source, module, graph_class, graph_variables = cached
            load_order.append((mount, source, module, graph_class, graph_variables))
            graph_variables_all.extend(list(graph_variables))
            continue

        graph_name, graph_type = _parse_graph_meta_from_source(graph_path)
        digest = _hash32(f"{graph_path.as_posix()}:{float(graph_path.stat().st_mtime)}")
        class_name = graph_name if str(graph_name).isidentifier() else ""
        if not class_name:
            class_name = sanitize_class_name(graph_name) or sanitize_class_name(graph_path.stem) or "Graph"
        source = GraphSourceResult(
            workspace_root=workspace,
            graph_code_file=graph_path,
            graph_name=graph_name,
            graph_type=graph_type,
            module_name=f"runtime.local_graph_source.{graph_path.stem}_{digest:08x}",
            class_name=class_name,
        )

        module, graph_class = load_source_graph_module_and_class(result=source)
        graph_variables = list(_iter_graph_variable_configs(module))
        loaded_by_path[graph_path] = (source, module, graph_class, graph_variables)
        load_order.append((mount, source, module, graph_class, graph_variables))
        graph_variables_all.extend(list(graph_variables))

    ui_registry = build_ui_key_registry_from_graph_variables(graph_variables=graph_variables_all)

    game = GameRuntime()
    game.set_present_player_count(int(present_player_count))
    populate_runtime_graph_variables_from_graph_variables(
        game=game,
        graph_variables=graph_variables_all,
        ui_registry=ui_registry,
        enable_layout_index_fallback=bool(enable_layout_index_fallback),
    )

    player_entity = _find_or_create_entity_by_name(game, player_entity_name)

    # 先创建并初始化“元件/实体”的自定义变量快照，再挂载节点图（避免 on_实体创建时 或信号初始化期读取到 None）。
    if isinstance(custom_vars_by_owner, dict) and custom_vars_by_owner:
        for owner_name, vars_map in sorted(custom_vars_by_owner.items(), key=lambda kv: str(kv[0]).casefold()):
            ent = _find_or_create_entity_by_name(game, str(owner_name))
            if not isinstance(vars_map, dict):
                continue
            for var_name, value in vars_map.items():
                name = str(var_name or "").strip()
                if not name:
                    continue
                game.set_custom_variable(ent, name, copy.deepcopy(value), trigger_event=False)

    mounted_graphs: list[MountedGraph] = []
    main_owner_entity: MockEntity | None = None
    main_graph_instance: object | None = None
    main_graph_name: str = ""
    main_graph_type: str = ""
    for i, (mount, source, _module, graph_class, _graph_variables) in enumerate(load_order):
        ent = _find_or_create_entity_by_name(game, mount.owner_entity_name)
        inst = game.attach_graph(graph_class, ent)
        mounted_graphs.append(
            MountedGraph(
                graph_code_file=Path(source.graph_code_file).resolve(),
                graph_name=str(source.graph_name),
                graph_type=str(source.graph_type),
                module_name=str(source.module_name),
                class_name=str(source.class_name),
                owner_entity_id=str(getattr(ent, "entity_id", "")),
                owner_entity_name=str(getattr(ent, "name", "")),
            )
        )
        if i == 0:
            main_owner_entity = ent
            main_graph_instance = inst
            main_graph_name = str(source.graph_name)
            main_graph_type = str(source.graph_type)

    if main_owner_entity is None or main_graph_instance is None:
        raise RuntimeError("未能挂载主节点图（mounts 为空）")

    return LocalGraphSimSession(
        workspace_root=workspace,
        graph_code_file=main_graph_path,
        graph_name=main_graph_name,
        graph_type=main_graph_type,
        ui_registry=ui_registry,
        game=game,
        owner_entity=main_owner_entity,
        player_entity=player_entity,
        graph_instance=main_graph_instance,
        mounted_graphs=mounted_graphs,
    )


__all__ = [
    "GraphCompileResult",
    "GraphSourceResult",
    "GraphMountSpec",
    "MountedGraph",
    "LocalGraphSimResourceMountSpec",
    "UiKeyIndexRegistry",
    "LocalGraphSimSession",
    "extract_html_stem_from_layout_index_description",
    "stable_layout_index_from_html_stem",
    "build_local_graph_sim_session",
]

