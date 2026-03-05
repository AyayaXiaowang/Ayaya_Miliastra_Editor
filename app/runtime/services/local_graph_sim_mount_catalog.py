from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Sequence

from engine.configs.resource_types import ResourceType
from engine.resources.resource_context import build_resource_index_context
from engine.utils.resource_library_layout import (
    PROJECT_ARCHIVE_LIBRARY_DIRNAME,
    SHARED_LIBRARY_DIRNAME,
    find_containing_resource_root,
)
from engine.utils.workspace import init_settings_for_workspace


@dataclass(frozen=True, slots=True)
class LocalGraphSimResourceMountSpec:
    """本地测试：按“元件模板/实体摆放/关卡实体”挂载并加载自定义变量。"""

    resource_type: str  # template | instance | level_entity
    resource_id: str
    owner_entity_name: str = ""  # 为空则使用资源自身 name
    include_template_graphs: bool = True  # instance/level_entity: 是否同时挂载模板 default_graphs


@dataclass(frozen=True, slots=True)
class LocalGraphSimGraphInfo:
    graph_id: str
    graph_name: str
    graph_type: str
    graph_code_file: str


@dataclass(frozen=True, slots=True)
class LocalGraphSimMountResourceInfo:
    """UI 展示用：一个可勾选的“挂载资源”（元件/实体）行。"""

    spec: LocalGraphSimResourceMountSpec
    display_type: str  # 元件模板 / 实体摆放 / 关卡实体
    resource_name: str
    graphs: List[LocalGraphSimGraphInfo]
    custom_variable_names: List[str]


def infer_active_package_id_for_resource_file(*, workspace_root: Path, file_path: Path) -> str | None:
    """根据 file_path 推断其所属项目存档作用域（None=共享根）。"""
    workspace = Path(workspace_root).resolve()
    resource_library_root = (workspace / "assets" / "资源库").resolve()
    resource_root = find_containing_resource_root(resource_library_root, Path(file_path).resolve())
    if resource_root is None:
        return None
    if resource_root.name == SHARED_LIBRARY_DIRNAME:
        return None
    if resource_root.parent.name == PROJECT_ARCHIVE_LIBRARY_DIRNAME:
        return resource_root.name
    return None


def _iter_graph_ids(values: object) -> Iterator[str]:
    if not isinstance(values, list):
        return
    for v in values:
        if isinstance(v, str):
            gid = v.strip()
            if gid:
                yield gid


def _safe_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _extract_custom_variable_file_refs(payload: dict) -> list[str]:
    """读取 metadata.custom_variable_file 的引用列表（兼容字符串/列表/空值）。"""
    from engine.resources.custom_variable_file_refs import normalize_custom_variable_file_refs

    metadata = _safe_dict(payload.get("metadata"))
    return normalize_custom_variable_file_refs(metadata.get("custom_variable_file"))


def _extract_default_values_from_variable_files(
    *,
    variable_file_ids: Sequence[str],
    active_package_id: str | None,
) -> Dict[str, Any]:
    """按变量文件引用读取 LevelVariableDefinition.default_value（以 variable_name 作为 key）。"""
    ids = [str(x or "").strip() for x in list(variable_file_ids or []) if str(x or "").strip()]
    if not ids:
        return {}

    from engine.resources.level_variable_schema_view import get_default_level_variable_schema_view

    schema = get_default_level_variable_schema_view()
    schema.set_active_package_id(active_package_id)

    out: Dict[str, Any] = {}
    for file_id in ids:
        for payload in list(schema.get_variables_by_file_id(str(file_id)) or []):
            if not isinstance(payload, dict):
                continue
            name = str(payload.get("variable_name") or "").strip()
            if not name:
                continue
            out[name] = copy.deepcopy(payload.get("default_value"))
    return out


def _extract_custom_vars_from_components(components: object) -> Dict[str, Any]:
    """从 default_components/additional_components 中提取『自定义变量』组件的默认值快照。"""
    if not isinstance(components, list) or not components:
        return {}

    from engine.configs.components.variable_configs import CustomVariableComponentConfig

    out: Dict[str, Any] = {}
    for item in components:
        if not isinstance(item, dict):
            continue
        comp_type = str(item.get("component_type") or "").strip()
        if comp_type != "自定义变量":
            continue
        settings = _safe_dict(item.get("settings"))
        cfg = CustomVariableComponentConfig.from_dict(settings)
        for var in list(getattr(cfg, "variables", []) or []):
            name = str(getattr(var, "variable_name", "") or "").strip()
            if not name:
                continue
            out[name] = getattr(var, "default_value", None)
    return out


def _extract_custom_vars_from_overrides(overrides: object, *, active_package_id: str | None) -> Dict[str, Any]:
    """从 Instance.override_variables 提取变量覆写（优先使用 variable_name；缺失则用 SchemaView 由 variable_id 反查）。"""
    if not isinstance(overrides, list) or not overrides:
        return {}

    from engine.resources.level_variable_schema_view import get_default_level_variable_schema_view

    schema = get_default_level_variable_schema_view()
    schema.set_active_package_id(active_package_id)
    vars_by_id = schema.get_all_variables()

    out: Dict[str, Any] = {}
    for item in overrides:
        if not isinstance(item, dict):
            continue
        name = str(item.get("variable_name") or "").strip()
        if not name:
            var_id = str(item.get("variable_id") or "").strip()
            if var_id:
                payload = vars_by_id.get(var_id) or {}
                name = str(payload.get("variable_name") or "").strip()
        if not name:
            continue
        if "value" not in item:
            continue
        out[name] = item.get("value")
    return out


def _resolve_graph_code_file(resource_manager: object, graph_id: str) -> Path:
    paths = getattr(resource_manager, "resource_index", {}).get(ResourceType.GRAPH, {})
    if not isinstance(paths, dict):
        raise RuntimeError("ResourceManager.resource_index 不可用")
    path = paths.get(str(graph_id))
    if not isinstance(path, Path):
        raise FileNotFoundError(f"未找到节点图资源文件：{graph_id}")
    return path.resolve()


def _load_graph_meta(resource_manager: object, graph_id: str) -> tuple[str, str]:
    load_meta = getattr(resource_manager, "load_graph_metadata", None)
    if not callable(load_meta):
        return graph_id, "server"
    meta = load_meta(str(graph_id))
    if not isinstance(meta, dict):
        return graph_id, "server"
    name = str(meta.get("name") or graph_id).strip() or graph_id
    gtype = str(meta.get("graph_type") or "server").strip() or "server"
    return name, gtype


def list_mount_resources_for_package(*, workspace_root: Path, package_id: str) -> List[LocalGraphSimMountResourceInfo]:
    """扫描指定项目存档的元件模板/实体摆放，构建本地测试的“可勾选挂载项”列表。"""
    workspace = Path(workspace_root).resolve()
    init_settings_for_workspace(workspace_root=workspace, load_user_settings=False)

    resource_manager, package_index_manager = build_resource_index_context(workspace, init_settings_first=False)
    resource_manager.rebuild_index(active_package_id=str(package_id))
    package_index = package_index_manager.load_package_index(str(package_id))
    if package_index is None:
        raise ValueError(f"未知项目存档: {package_id}")

    resources = getattr(package_index, "resources", None)
    if resources is None:
        return []

    out: List[LocalGraphSimMountResourceInfo] = []

    # --- templates
    for template_id in list(getattr(resources, "templates", []) or []):
        tid = str(template_id or "").strip()
        if not tid:
            continue
        payload = resource_manager.load_resource(ResourceType.TEMPLATE, tid, copy_mode="none")
        if not isinstance(payload, dict):
            continue
        name = str(payload.get("name") or tid).strip() or tid
        graph_ids = list(_iter_graph_ids(payload.get("default_graphs")))
        file_refs = _extract_custom_variable_file_refs(payload)
        custom_vars = _extract_default_values_from_variable_files(
            variable_file_ids=file_refs,
            active_package_id=str(package_id),
        )
        custom_vars.update(_extract_custom_vars_from_components(payload.get("default_components")))
        if not graph_ids and not custom_vars:
            continue

        graphs: List[LocalGraphSimGraphInfo] = []
        for gid in graph_ids:
            gname, gtype = _load_graph_meta(resource_manager, gid)
            gfile = _resolve_graph_code_file(resource_manager, gid)
            graphs.append(
                LocalGraphSimGraphInfo(
                    graph_id=str(gid),
                    graph_name=str(gname),
                    graph_type=str(gtype),
                    graph_code_file=str(gfile),
                )
            )

        spec = LocalGraphSimResourceMountSpec(
            resource_type="template",
            resource_id=tid,
            owner_entity_name=name,
            include_template_graphs=True,
        )
        out.append(
            LocalGraphSimMountResourceInfo(
                spec=spec,
                display_type="元件模板",
                resource_name=name,
                graphs=graphs,
                custom_variable_names=sorted(list(custom_vars.keys()), key=lambda x: str(x)),
            )
        )

    # --- instances
    level_entity_id = str(getattr(package_index, "level_entity_id", "") or "").strip()
    for instance_id in list(getattr(resources, "instances", []) or []):
        iid = str(instance_id or "").strip()
        if not iid:
            continue
        payload = resource_manager.load_resource(ResourceType.INSTANCE, iid, copy_mode="none")
        if not isinstance(payload, dict):
            continue
        name = str(payload.get("name") or iid).strip() or iid

        template_payload: dict | None = None
        template_id = str(payload.get("template_id") or "").strip()
        if template_id:
            t_payload = resource_manager.load_resource(ResourceType.TEMPLATE, template_id, copy_mode="none")
            template_payload = t_payload if isinstance(t_payload, dict) else None

        graph_ids: List[str] = []
        # instance.additional_graphs
        graph_ids.extend(list(_iter_graph_ids(payload.get("additional_graphs"))))
        # template.default_graphs (默认展示出来，便于用户理解“实例继承模板挂图”)
        if template_payload is not None:
            graph_ids.extend(list(_iter_graph_ids(template_payload.get("default_graphs"))))
        # 稳定去重
        seen_graph: set[str] = set()
        graph_ids_unique: List[str] = []
        for gid in graph_ids:
            if gid in seen_graph:
                continue
            seen_graph.add(gid)
            graph_ids_unique.append(gid)

        custom_vars: Dict[str, Any] = {}
        if template_payload is not None:
            template_file_refs = _extract_custom_variable_file_refs(template_payload)
            custom_vars.update(
                _extract_default_values_from_variable_files(
                    variable_file_ids=template_file_refs,
                    active_package_id=str(package_id),
                )
            )
            custom_vars.update(_extract_custom_vars_from_components(template_payload.get("default_components")))
        instance_file_refs = _extract_custom_variable_file_refs(payload)
        custom_vars.update(
            _extract_default_values_from_variable_files(
                variable_file_ids=instance_file_refs,
                active_package_id=str(package_id),
            )
        )
        custom_vars.update(_extract_custom_vars_from_components(payload.get("additional_components")))
        custom_vars.update(
            _extract_custom_vars_from_overrides(
                payload.get("override_variables"),
                active_package_id=str(package_id),
            )
        )
        if not graph_ids_unique and not custom_vars:
            continue

        graphs2: List[LocalGraphSimGraphInfo] = []
        for gid in graph_ids_unique:
            gname, gtype = _load_graph_meta(resource_manager, gid)
            gfile = _resolve_graph_code_file(resource_manager, gid)
            graphs2.append(
                LocalGraphSimGraphInfo(
                    graph_id=str(gid),
                    graph_name=str(gname),
                    graph_type=str(gtype),
                    graph_code_file=str(gfile),
                )
            )

        is_level_entity = bool(level_entity_id) and iid == level_entity_id
        display_type = "关卡实体" if is_level_entity else "实体摆放"
        spec2 = LocalGraphSimResourceMountSpec(
            resource_type="level_entity" if is_level_entity else "instance",
            resource_id=iid,
            owner_entity_name=name,
            include_template_graphs=True,
        )
        out.append(
            LocalGraphSimMountResourceInfo(
                spec=spec2,
                display_type=display_type,
                resource_name=name,
                graphs=graphs2,
                custom_variable_names=sorted(list(custom_vars.keys()), key=lambda x: str(x)),
            )
        )

    # 排序：关卡实体优先，然后按类型+名称
    def _sort_key(x: LocalGraphSimMountResourceInfo) -> tuple[int, str, str]:
        kind_order = 0
        if x.display_type == "关卡实体":
            kind_order = 0
        elif x.display_type == "实体摆放":
            kind_order = 1
        else:
            kind_order = 2
        return (kind_order, str(x.resource_name).casefold(), str(x.spec.resource_id).casefold())

    out.sort(key=_sort_key)
    return out


def resolve_resource_mounts_to_runtime_plan(
    *,
    workspace_root: Path,
    active_package_id: str | None,
    mount_specs: Sequence[LocalGraphSimResourceMountSpec],
) -> tuple[list[tuple[Path, str]], dict[str, dict[str, Any]]]:
    """将勾选的挂载资源解析为（图文件路径+owner实体名）与（实体自定义变量初始值）."""
    workspace = Path(workspace_root).resolve()
    init_settings_for_workspace(workspace_root=workspace, load_user_settings=False)

    pkg = str(active_package_id or "").strip() or ""
    resource_manager, _package_index_manager = build_resource_index_context(workspace, init_settings_first=False)
    resource_manager.rebuild_index(active_package_id=pkg)

    mounts: list[tuple[Path, str]] = []
    custom_vars_by_owner: dict[str, dict[str, Any]] = {}

    for spec in list(mount_specs or ()):
        rtype = str(getattr(spec, "resource_type", "") or "").strip()
        rid = str(getattr(spec, "resource_id", "") or "").strip()
        if not rtype or not rid:
            continue
        owner_override = str(getattr(spec, "owner_entity_name", "") or "").strip()
        include_template = bool(getattr(spec, "include_template_graphs", True))

        if rtype == "template":
            payload = resource_manager.load_resource(ResourceType.TEMPLATE, rid, copy_mode="none")
            if not isinstance(payload, dict):
                continue
            name = str(payload.get("name") or rid).strip() or rid
            owner_name = owner_override or name
            file_refs = _extract_custom_variable_file_refs(payload)
            custom_vars = _extract_default_values_from_variable_files(
                variable_file_ids=file_refs,
                active_package_id=active_package_id,
            )
            custom_vars.update(_extract_custom_vars_from_components(payload.get("default_components")))
            graph_ids = list(_iter_graph_ids(payload.get("default_graphs")))
        elif rtype in {"instance", "level_entity"}:
            payload = resource_manager.load_resource(ResourceType.INSTANCE, rid, copy_mode="none")
            if not isinstance(payload, dict):
                continue
            name = str(payload.get("name") or rid).strip() or rid
            owner_name = owner_override or name

            template_payload: dict | None = None
            template_id = str(payload.get("template_id") or "").strip()
            if template_id:
                tp = resource_manager.load_resource(ResourceType.TEMPLATE, template_id, copy_mode="none")
                template_payload = tp if isinstance(tp, dict) else None

            custom_vars = {}
            graph_ids = []
            if template_payload is not None:
                template_file_refs = _extract_custom_variable_file_refs(template_payload)
                custom_vars.update(
                    _extract_default_values_from_variable_files(
                        variable_file_ids=template_file_refs,
                        active_package_id=active_package_id,
                    )
                )
                custom_vars.update(_extract_custom_vars_from_components(template_payload.get("default_components")))
                if include_template:
                    graph_ids.extend(list(_iter_graph_ids(template_payload.get("default_graphs"))))
            instance_file_refs = _extract_custom_variable_file_refs(payload)
            custom_vars.update(
                _extract_default_values_from_variable_files(
                    variable_file_ids=instance_file_refs,
                    active_package_id=active_package_id,
                )
            )
            custom_vars.update(_extract_custom_vars_from_components(payload.get("additional_components")))
            custom_vars.update(_extract_custom_vars_from_overrides(payload.get("override_variables"), active_package_id=active_package_id))
            graph_ids.extend(list(_iter_graph_ids(payload.get("additional_graphs"))))
        else:
            continue

        # custom vars: 深拷贝，避免运行期修改污染后续重启
        if custom_vars:
            store = custom_vars_by_owner.setdefault(owner_name, {})
            for k, v in custom_vars.items():
                store[str(k)] = copy.deepcopy(v)

        # graphs
        seen_gid: set[str] = set()
        for gid in graph_ids:
            if gid in seen_gid:
                continue
            seen_gid.add(gid)
            gfile = _resolve_graph_code_file(resource_manager, gid)
            mounts.append((gfile, owner_name))

    return mounts, custom_vars_by_owner


__all__ = [
    "LocalGraphSimResourceMountSpec",
    "LocalGraphSimGraphInfo",
    "LocalGraphSimMountResourceInfo",
    "infer_active_package_id_for_resource_file",
    "list_mount_resources_for_package",
    "resolve_resource_mounts_to_runtime_plan",
]

