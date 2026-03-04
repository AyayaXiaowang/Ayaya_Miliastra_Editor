from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from engine.signal.definition_repository import get_default_signal_repository
from engine.utils.name_utils import sanitize_class_name
from engine.utils.workspace import init_settings_for_workspace, resolve_workspace_root

from app.runtime.engine.game_state import GameRuntime, MockEntity
from app.runtime.services.local_graph_sim_mount_catalog import (
    LocalGraphSimResourceMountSpec,
    list_mount_resources_for_package,
    resolve_resource_mounts_to_runtime_plan,
)

from .local_graph_simulator_loader import GraphSourceResult, _parse_graph_meta_from_source, load_source_graph_module_and_class
from .local_graph_simulator_ui_keys import (
    UiKeyIndexRegistry,
    _UI_KEY_PREFIX,
    _hash32,
    _iter_graph_variable_configs,
    build_ui_key_registry_from_graph_variables,
    populate_runtime_graph_variables_from_graph_variables,
    populate_runtime_graph_variables_from_ui_constants,
    resolve_ui_key_placeholders_in_graph_module,
    stable_layout_index_from_html_stem,
)


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


def _find_or_create_entity_by_name(game: GameRuntime, name: str) -> MockEntity:
    desired = str(name or "").strip()
    if not desired:
        raise ValueError("实体名称不能为空")
    # 约定（本地测试专用）：若传入纯数字字符串，则视为“GUID 实体ID”，
    # 使用 GameRuntime.get_entity(guid) 创建/复用对应实体，确保图内 `以GUID查询实体` 返回同一对象。
    # 这用于挂载“关卡实体图”等依赖 `self.owner_entity == 以GUID查询实体(...)` 的节点图。
    if desired.isdigit():
        ent = game.get_entity(desired)
        if ent is None:
            raise RuntimeError(f"无法创建 GUID 实体: {desired}")
        return ent
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
    active_package_id: str | None
    ui_registry: UiKeyIndexRegistry
    game: GameRuntime
    owner_entity: MockEntity
    player_entity: MockEntity
    graph_instance: object
    mounted_graphs: list[MountedGraph] = field(default_factory=list)
    sim_notes: dict[str, Any] = field(default_factory=dict)

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
        chosen = self._try_resolve_ui_click_ui_key(
            data_ui_key=data_ui_key,
            data_ui_state_group=data_ui_state_group,
            data_ui_state=data_ui_state,
            player_entity=player_entity,
        )
        if chosen is None:
            raw_key = str(data_ui_key or "").strip()
            group = str(data_ui_state_group or "").strip()
            state = str(data_ui_state or "").strip()
            raise ValueError(
                "无法解析 UI click 对应的 ui_key："
                f" data_ui_key={raw_key!r} data_ui_state_group={group!r} data_ui_state={state!r}"
            )

        index = int(self.ui_registry.ensure(chosen))
        return self.trigger_ui_click_index(index=index, player_entity=player_entity)

    def trigger_ui_click_index(self, *, index: int, player_entity: MockEntity | None = None) -> list[dict[str, Any]]:
        """直接用 index（稳定伪GUID/索引）触发 UI click（绕过 ui_key 解析，便于外部工具复用）。"""
        idx = int(index)
        if idx <= 0:
            raise ValueError("index 必须 > 0")
        source_player = player_entity or self.player_entity
        self.game.trigger_event(
            "界面控件组触发时",
            事件源实体=source_player,
            事件源GUID=idx,
            界面控件组组合索引=idx,
            界面控件组索引=idx,
        )
        return self.drain_ui_patches()

    def try_resolve_ui_click_ui_key(
        self,
        *,
        data_ui_key: str,
        data_ui_state_group: str = "",
        data_ui_state: str = "",
        player_entity: MockEntity | None = None,
    ) -> str | None:
        """
        尝试将浏览器侧 click payload 解析为稳定 ui_key。

        说明：
        - 返回 None 表示无法解析（由调用方决定返回结构化错误还是抛异常）。
        - 提供公开入口，避免 HTTP 层等外部调用穿透依赖 `_try_*` 私有实现。
        """
        return self._try_resolve_ui_click_ui_key(
            data_ui_key=data_ui_key,
            data_ui_state_group=data_ui_state_group,
            data_ui_state=data_ui_state,
            player_entity=player_entity,
        )

    def _try_resolve_ui_click_ui_key(
        self,
        *,
        data_ui_key: str,
        data_ui_state_group: str = "",
        data_ui_state: str = "",
        player_entity: MockEntity | None = None,
    ) -> str | None:
        raw_key = str(data_ui_key or "").strip()
        key = raw_key
        if not key:
            return None
        if key.startswith(_UI_KEY_PREFIX):
            key = key[len(_UI_KEY_PREFIX) :].strip()
        group = str(data_ui_state_group or "").strip()
        state = str(data_ui_state or "").strip()

        source_player = player_entity or self.player_entity

        # 当前布局：用于在“多个 UI 页面同时挂载”时尽量选择正确页面下的控件 key。
        player_id = getattr(source_player, "entity_id", "") if isinstance(source_player, MockEntity) else str(source_player)
        current_layout = 0
        ui_layouts = getattr(self.game, "ui_current_layout_by_player", None)
        if isinstance(ui_layouts, dict):
            current_layout = int(ui_layouts.get(str(player_id), 0) or 0)

        # 收集 registry 中出现过的 `<html_stem>_html__...` 前缀
        stems: list[str] = []
        for k in self.ui_registry.keys():
            if not isinstance(k, str):
                continue
            if "_html__" not in k:
                continue
            stem = k.split("_html__", 1)[0].strip()
            if stem and stem not in stems:
                stems.append(stem)

        # 先尝试匹配“当前布局”的 stem（若能推断）
        active_stems: list[str] = []
        if current_layout > 0 and stems:
            for stem in stems:
                if stable_layout_index_from_html_stem(stem) == current_layout:
                    active_stems.append(stem)
        preferred_stems = list(active_stems) + [s for s in stems if s not in active_stems]

        def _dedup_keep_order(items: list[str]) -> list[str]:
            out: list[str] = []
            seen: set[str] = set()
            for x in items:
                if x in seen:
                    continue
                seen.add(x)
                out.append(x)
            return out

        candidates: list[str] = []

        # 允许直接传入“完整 ui_key”
        if ("__" in key) or key.startswith("UI_STATE_GROUP__") or ("_html__" in key) or key.startswith("HTML导入_界面布局__"):
            candidates.append(key)

        # 兼容旧版 key（历史测试夹具）
        if group and state:
            candidates.append(f"HTML导入_界面布局__{group}__{state}__btn_item")
        candidates.append(f"HTML导入_界面布局__{key}__btn_item")

        # 新版 key：`<html_stem>_html__<key>__<state>__btn_item` / `...__rect`
        for stem in preferred_stems:
            if group and state:
                candidates.append(f"{stem}_html__{group}__{state}__btn_item")
                candidates.append(f"{stem}_html__{group}__{state}__rect")
            if state:
                candidates.append(f"{stem}_html__{key}__{state}__btn_item")
                candidates.append(f"{stem}_html__{key}__{state}__rect")
            candidates.append(f"{stem}_html__{key}__btn_item")
            candidates.append(f"{stem}_html__{key}__rect")

        candidates = _dedup_keep_order([c for c in candidates if str(c or "").strip()])

        chosen: str | None = None
        for c in candidates:
            if self.ui_registry.try_get_index(c) is not None:
                chosen = c
                break

        # 最后兜底：从 registry 里按子串反查（避免 exporter 细节变化导致拼装失败）
        if chosen is None:
            wants: list[str] = []
            if state:
                wants.append(f"__{key}__{state}__")
            wants.append(f"__{key}__")
            if group and state:
                wants.append(f"__{group}__{state}__")

            matches: list[str] = []
            for k in self.ui_registry.keys():
                if not isinstance(k, str):
                    continue
                if not (k.endswith("__btn_item") or k.endswith("__rect")):
                    continue
                if any(w in k for w in wants):
                    matches.append(k)

            if matches and active_stems:
                filtered: list[str] = []
                for m in matches:
                    if "_html__" in m and m.split("_html__", 1)[0] in active_stems:
                        filtered.append(m)
                if filtered:
                    matches = filtered

            if matches:
                matches = sorted(set(matches), key=lambda x: (len(x), x))
                chosen = matches[0]

        return str(chosen) if chosen is not None else None


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

    # 解析“按元件/实体挂载”的资源：加载自定义变量初值（必要时推断 resource_mounts），
    # 注意：当 resource_mounts 是“推断得到”时，仅用于预置自定义变量快照，不覆盖/替换调用方显式指定的 extra_graph_mounts 挂载关系。
    effective_resource_mounts: list[LocalGraphSimResourceMountSpec] = list(resource_mounts or ())
    resource_mounts_inferred = False
    if (not effective_resource_mounts) and isinstance(active_package_id, str) and active_package_id.strip() and extra_mounts_list:
        inferred = _infer_resource_mounts_for_extra_graph_mounts(
            workspace_root=workspace,
            active_package_id=str(active_package_id),
            extra_mounts=extra_mounts_list,
        )
        if inferred:
            effective_resource_mounts = list(inferred)
            resource_mounts_inferred = True

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
        # 若 resource_mounts 为推断得到：不使用其“挂载计划”覆盖调用方显式 extra_mounts；
        # 仅复用其 custom_vars 快照（用于避免读取到 None）。
        if resource_mounts_inferred:
            resolved_mounts = []
            resolved_graph_keys = set()
        else:
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
    seen_graph_module_ids: set[int] = set()
    for _mount, _source, module, _graph_class, _graph_variables in load_order:
        module_id = id(module)
        if module_id in seen_graph_module_ids:
            continue
        seen_graph_module_ids.add(module_id)
        resolve_ui_key_placeholders_in_graph_module(graph_module=module, ui_registry=ui_registry)

    game = GameRuntime()
    game.set_present_player_count(int(present_player_count))
    sim_notes: dict[str, Any] = {
        "ui_key_registry_size": int(len(ui_registry.keys())),
        "enable_layout_index_fallback": bool(enable_layout_index_fallback),
    }
    populate_runtime_graph_variables_from_graph_variables(
        game=game,
        graph_variables=graph_variables_all,
        ui_registry=ui_registry,
        enable_layout_index_fallback=bool(enable_layout_index_fallback),
        notes=sim_notes,
    )
    populate_runtime_graph_variables_from_ui_constants(
        game=game,
        graph_modules=[m for _mount, _source, m, _graph_class, _graph_variables in load_order],
        ui_registry=ui_registry,
        notes=sim_notes,
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
    init_entities: list[MockEntity] = []
    init_entity_ids: set[str] = set()
    for i, (mount, source, _module, graph_class, _graph_variables) in enumerate(load_order):
        ent = _find_or_create_entity_by_name(game, mount.owner_entity_name)
        ent_id = str(getattr(ent, "entity_id", "") or "")
        if ent_id and ent_id not in init_entity_ids:
            init_entity_ids.add(ent_id)
            init_entities.append(ent)
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

    # 对齐真实运行期：实体创建后会触发一次事件 `实体创建时`。
    # 离线模拟中实体由 `create_mock_entity/get_entity` 创建且不会自动触发该事件，
    # 这里在“所有图挂载完成且 handlers 已注册”后补发一次，便于门控/初始化图正常执行。
    for ent in init_entities:
        game.trigger_event("实体创建时", 事件源实体=ent, 事件源GUID=0)

    return LocalGraphSimSession(
        workspace_root=workspace,
        graph_code_file=main_graph_path,
        graph_name=main_graph_name,
        graph_type=main_graph_type,
        active_package_id=active_package_id,
        ui_registry=ui_registry,
        game=game,
        owner_entity=main_owner_entity,
        player_entity=player_entity,
        graph_instance=main_graph_instance,
        mounted_graphs=mounted_graphs,
        sim_notes=sim_notes,
    )


__all__ = [
    "GraphMountSpec",
    "MountedGraph",
    "LocalGraphSimSession",
    "build_local_graph_sim_session",
]

