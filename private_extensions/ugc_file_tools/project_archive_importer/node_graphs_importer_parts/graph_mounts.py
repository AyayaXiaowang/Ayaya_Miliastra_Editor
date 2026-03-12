from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

from .constants import MOUNT_LINE_RE, SCAN_HEAD_CHARS

_GRAPH_CATEGORY_ENTITY = 20000
_GRAPH_CATEGORY_STATUS = 20003
_GRAPH_CATEGORY_CLASS = 20004
_GRAPH_CATEGORY_ITEM = 20005

_GRAPH_CATEGORY_BY_DIR_NAME: dict[str, int] = {
    "实体节点图": _GRAPH_CATEGORY_ENTITY,
    "状态节点图": _GRAPH_CATEGORY_STATUS,
    "职业节点图": _GRAPH_CATEGORY_CLASS,
    "道具节点图": _GRAPH_CATEGORY_ITEM,
}

_MOUNT_ENTITY_PREFIXES = ("entity_key:", "entity:")
_MOUNT_COMPONENT_PREFIXES = ("component_key:", "component:")

_ENTITY_PLACEMENT_SECTION_KEY = "5"
_ENTITY_PLACEMENT_ENTRY_LIST_KEY = "1"

_ENTITY_ENTRY_INSTANCE_ID_KEY = "1"
_ENTITY_ENTRY_COMPONENT_LIST_KEY = "6"

_COMPONENT_ITEM_SLOT_ID_KEY = "1"
_NODE_GRAPH_MOUNT_COMPONENT_SLOT_ID = 3

_NODE_GRAPH_MOUNT_FIELD_KEY = "13"
_NODE_GRAPH_MOUNT_CONTAINER_KEY_L1 = "1"
_NODE_GRAPH_MOUNT_CONTAINER_KEY_L2 = "1"

_MOUNT_LOCATOR_FIELD_ENABLED = "1"
_MOUNT_LOCATOR_FIELD_GRAPH_ID_INT = "2"
_MOUNT_LOCATOR_FIELD_GRAPH_CATEGORY_INT = "501"
_MOUNT_LOCATOR_ENABLED_VALUE = 1


@dataclass(frozen=True, slots=True)
class GraphMountUsage:
    entity_names: tuple[str, ...]
    component_names: tuple[str, ...]

    @property
    def is_used(self) -> bool:
        return bool(self.entity_names or self.component_names)


@dataclass(frozen=True, slots=True)
class ResolvedGraphMountTarget:
    kind: str  # "entity" | "component"
    name: str
    instance_id_int: int


@dataclass(frozen=True, slots=True)
class UnresolvedGraphMountTarget:
    kind: str  # "entity" | "component"
    name: str
    reason: str


_UNRESOLVED_REASON_MAPPING_TABLE_MISSING = "mapping table missing"
_UNRESOLVED_REASON_NAME_NOT_FOUND = "name not found in mapping table"


def _dedupe_text_keep_order(values: Sequence[str]) -> tuple[str, ...]:
    """对文本序列做稳定去重并保留顺序。"""
    seen: set[str] = set()
    out: list[str] = []
    for v0 in list(values or []):
        v = str(v0 or "").strip()
        if v == "":
            continue
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return tuple(out)


def scan_graph_mount_usage_from_graph_code_file(*, graph_code_file: Path) -> GraphMountUsage:
    """从 Graph Code 文件头部 metadata 扫描 mount 声明。"""
    p = Path(graph_code_file).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))

    head = p.read_text(encoding="utf-8")[: int(SCAN_HEAD_CHARS)]
    mount_values = [str(x or "").strip() for x in MOUNT_LINE_RE.findall(head)]

    entity_names: list[str] = []
    component_names: list[str] = []

    for raw0 in mount_values:
        raw = str(raw0 or "").strip()
        if raw == "":
            raise ValueError(f"mount metadata 为空：{str(p)!r}")

        lowered = raw.lower()
        if lowered.startswith(_MOUNT_ENTITY_PREFIXES):
            prefix = next(pfx for pfx in _MOUNT_ENTITY_PREFIXES if lowered.startswith(pfx))
            name = raw[len(prefix) :].strip()
            if name == "":
                raise ValueError(f"mount 实体声明缺少名称：{raw0!r} in {str(p)!r}")
            entity_names.append(str(name))
            continue

        if lowered.startswith(_MOUNT_COMPONENT_PREFIXES):
            prefix = next(pfx for pfx in _MOUNT_COMPONENT_PREFIXES if lowered.startswith(pfx))
            name = raw[len(prefix) :].strip()
            if name == "":
                raise ValueError(f"mount 元件声明缺少名称：{raw0!r} in {str(p)!r}")
            component_names.append(str(name))
            continue

        raise ValueError(
            "mount 声明必须以 entity_key:/entity:/component_key:/component: 开头："
            f"value={raw0!r} file={str(p)!r}"
        )

    return GraphMountUsage(
        entity_names=_dedupe_text_keep_order(entity_names),
        component_names=_dedupe_text_keep_order(component_names),
    )


def infer_graph_category_int_from_graph_code_file(*, graph_code_file: Path) -> int:
    """从节点图源码路径推断 GraphCategory(type_int)。"""
    p = Path(graph_code_file).resolve()
    for part in p.parts:
        cat = _GRAPH_CATEGORY_BY_DIR_NAME.get(str(part))
        if isinstance(cat, int):
            return int(cat)
    expected = ", ".join(sorted(_GRAPH_CATEGORY_BY_DIR_NAME.keys(), key=lambda t: t.casefold()))
    raise ValueError(f"无法从节点图路径推断 GraphCategory（期望目录名之一：{expected}）：{str(p)!r}")


def resolve_graph_mount_targets(
    *,
    usage: GraphMountUsage,
    entity_name_to_guid: Mapping[str, int] | None,
    component_name_to_id: Mapping[str, int] | None,
) -> tuple[ResolvedGraphMountTarget, ...]:
    """将 mount 声明按参考映射表解析为具体 instance_id_int。"""
    resolved: list[ResolvedGraphMountTarget] = []

    if usage.entity_names:
        if entity_name_to_guid is None:
            raise RuntimeError("Graph Code 使用了 entity_key/entity mount，但未提供 entity_name_to_guid 映射表")
        for name in list(usage.entity_names):
            eid = entity_name_to_guid.get(str(name))
            if not isinstance(eid, int) or int(eid) <= 0:
                raise KeyError(f"未在实体映射表中找到实体名：{str(name)!r}")
            resolved.append(ResolvedGraphMountTarget(kind="entity", name=str(name), instance_id_int=int(eid)))

    if usage.component_names:
        if component_name_to_id is None:
            raise RuntimeError("Graph Code 使用了 component_key/component mount，但未提供 component_name_to_id 映射表")
        for name in list(usage.component_names):
            cid = component_name_to_id.get(str(name))
            if not isinstance(cid, int) or int(cid) <= 0:
                raise KeyError(f"未在元件映射表中找到元件名：{str(name)!r}")
            resolved.append(ResolvedGraphMountTarget(kind="component", name=str(name), instance_id_int=int(cid)))

    return tuple(resolved)


def resolve_graph_mount_targets_best_effort(
    *,
    usage: GraphMountUsage,
    entity_name_to_guid: Mapping[str, int] | None,
    component_name_to_id: Mapping[str, int] | None,
) -> tuple[tuple[ResolvedGraphMountTarget, ...], tuple[UnresolvedGraphMountTarget, ...]]:
    """尽力解析 mount 声明并返回未解析项（不抛 KeyError）。"""
    resolved: list[ResolvedGraphMountTarget] = []
    unresolved: list[UnresolvedGraphMountTarget] = []

    if usage.entity_names:
        if entity_name_to_guid is None:
            for name in list(usage.entity_names):
                unresolved.append(
                    UnresolvedGraphMountTarget(
                        kind="entity",
                        name=str(name),
                        reason=str(_UNRESOLVED_REASON_MAPPING_TABLE_MISSING),
                    )
                )
        else:
            for name in list(usage.entity_names):
                eid = entity_name_to_guid.get(str(name))
                if not isinstance(eid, int) or int(eid) <= 0:
                    unresolved.append(
                        UnresolvedGraphMountTarget(
                            kind="entity",
                            name=str(name),
                            reason=str(_UNRESOLVED_REASON_NAME_NOT_FOUND),
                        )
                    )
                    continue
                resolved.append(ResolvedGraphMountTarget(kind="entity", name=str(name), instance_id_int=int(eid)))

    if usage.component_names:
        if component_name_to_id is None:
            for name in list(usage.component_names):
                unresolved.append(
                    UnresolvedGraphMountTarget(
                        kind="component",
                        name=str(name),
                        reason=str(_UNRESOLVED_REASON_MAPPING_TABLE_MISSING),
                    )
                )
        else:
            for name in list(usage.component_names):
                cid = component_name_to_id.get(str(name))
                if not isinstance(cid, int) or int(cid) <= 0:
                    unresolved.append(
                        UnresolvedGraphMountTarget(
                            kind="component",
                            name=str(name),
                            reason=str(_UNRESOLVED_REASON_NAME_NOT_FOUND),
                        )
                    )
                    continue
                resolved.append(ResolvedGraphMountTarget(kind="component", name=str(name), instance_id_int=int(cid)))

    return tuple(resolved), tuple(unresolved)


def _extract_instance_id_int_from_entity_entry(entry: Mapping[str, Any]) -> int | None:
    """从实体摆放 entry 中提取 instance_id_int。"""
    value = entry.get(_ENTITY_ENTRY_INSTANCE_ID_KEY)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, list) and value and isinstance(value[0], int):
        return int(value[0])
    return None


def _extract_component_slot_id_int(component_item: Mapping[str, Any]) -> int | None:
    """从实体组件条目中提取 slot_id。"""
    value = component_item.get(_COMPONENT_ITEM_SLOT_ID_KEY)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, list) and value and isinstance(value[0], int):
        return int(value[0])
    return None


def _try_extract_mounted_graph_id_int(component_item: Mapping[str, Any]) -> int | None:
    """从组件条目的现有挂载字段中尽力提取已挂载的 graph_id_int。"""
    v13 = component_item.get(_NODE_GRAPH_MOUNT_FIELD_KEY)
    if not isinstance(v13, dict):
        return None
    l1 = v13.get(_NODE_GRAPH_MOUNT_CONTAINER_KEY_L1)
    if not isinstance(l1, dict):
        return None
    l2 = l1.get(_NODE_GRAPH_MOUNT_CONTAINER_KEY_L2)
    if not isinstance(l2, dict):
        return None
    gid = l2.get(_MOUNT_LOCATOR_FIELD_GRAPH_ID_INT)
    if isinstance(gid, int):
        return int(gid)
    return None


def _apply_graph_mount_to_instance_id(
    *,
    payload_root: Dict[str, Any],
    target: ResolvedGraphMountTarget,
    graph_id_int: int,
    graph_category_int: int,
) -> Dict[str, Any]:
    """对单个 instance_id_int 写入或覆盖节点图挂载字段。"""
    section5 = payload_root.get(_ENTITY_PLACEMENT_SECTION_KEY)
    if not isinstance(section5, dict):
        raise ValueError("payload_root['5'] must be dict for graph mounts")
    entries_value = section5.get(_ENTITY_PLACEMENT_ENTRY_LIST_KEY)
    if isinstance(entries_value, list):
        entries = [e for e in entries_value if isinstance(e, dict)]
    elif isinstance(entries_value, dict):
        entries = [entries_value]
    else:
        raise ValueError("payload_root['5']['1'] must be list/dict for graph mounts")

    want_instance_id = int(target.instance_id_int)
    found_entry: Dict[str, Any] | None = None
    for e in entries:
        eid = _extract_instance_id_int_from_entity_entry(e)
        if isinstance(eid, int) and int(eid) == int(want_instance_id):
            found_entry = e
            break
    if found_entry is None:
        raise ValueError(
            "目标实体实例未在输出 gil 的实体摆放段中找到，无法挂载节点图："
            f"kind={target.kind!r} name={target.name!r} instance_id_int={want_instance_id}"
        )

    components_value = found_entry.get(_ENTITY_ENTRY_COMPONENT_LIST_KEY)
    if isinstance(components_value, list):
        components = [c for c in components_value if isinstance(c, dict)]
    elif isinstance(components_value, dict):
        components = [components_value]
    else:
        raise ValueError(f"目标实体 entry 缺少组件列表 entry['6']：instance_id_int={want_instance_id}")

    graph_slot_item: Dict[str, Any] | None = None
    for c in components:
        slot_id = _extract_component_slot_id_int(c)
        if isinstance(slot_id, int) and int(slot_id) == int(_NODE_GRAPH_MOUNT_COMPONENT_SLOT_ID):
            graph_slot_item = c
            break
    if graph_slot_item is None:
        raise ValueError(
            "目标实体 entry 缺少可写回的节点图挂载组件槽（slot_id=3），无法挂载节点图："
            f"instance_id_int={want_instance_id}"
        )

    old_graph_id_int = _try_extract_mounted_graph_id_int(graph_slot_item)
    graph_slot_item[_NODE_GRAPH_MOUNT_FIELD_KEY] = {
        _NODE_GRAPH_MOUNT_CONTAINER_KEY_L1: {
            _NODE_GRAPH_MOUNT_CONTAINER_KEY_L2: {
                _MOUNT_LOCATOR_FIELD_ENABLED: int(_MOUNT_LOCATOR_ENABLED_VALUE),
                _MOUNT_LOCATOR_FIELD_GRAPH_ID_INT: int(graph_id_int),
                _MOUNT_LOCATOR_FIELD_GRAPH_CATEGORY_INT: int(graph_category_int),
            }
        }
    }

    return {
        "kind": str(target.kind),
        "name": str(target.name),
        "target_instance_id_int": int(want_instance_id),
        "old_graph_id_int": (int(old_graph_id_int) if isinstance(old_graph_id_int, int) else None),
        "new_graph_id_int": int(graph_id_int),
        "graph_category_int": int(graph_category_int),
    }


def apply_graph_mounts_to_payload_root(
    *,
    payload_root: Dict[str, Any],
    targets: Sequence[ResolvedGraphMountTarget],
    graph_id_int: int,
    graph_category_int: int,
) -> list[Dict[str, Any]]:
    """将节点图挂载写入 payload_root 的实体摆放段。"""
    out: list[Dict[str, Any]] = []
    for t in list(targets or []):
        out.append(
            _apply_graph_mount_to_instance_id(
                payload_root=payload_root,
                target=t,
                graph_id_int=int(graph_id_int),
                graph_category_int=int(graph_category_int),
            )
        )
    return out


def apply_graph_mounts_to_payload_root_best_effort(
    *,
    payload_root: Dict[str, Any],
    targets: Sequence[ResolvedGraphMountTarget],
    graph_id_int: int,
    graph_category_int: int,
) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    """尽力写入节点图挂载并返回成功/失败报告（不抛异常）。"""
    applied: list[Dict[str, Any]] = []
    failed: list[Dict[str, Any]] = []
    for t in list(targets or []):
        try:
            applied.append(
                _apply_graph_mount_to_instance_id(
                    payload_root=payload_root,
                    target=t,
                    graph_id_int=int(graph_id_int),
                    graph_category_int=int(graph_category_int),
                )
            )
        except Exception as e:
            failed.append(
                {
                    "kind": str(t.kind),
                    "name": str(t.name),
                    "target_instance_id_int": int(t.instance_id_int),
                    "error": f"{type(e).__name__}: {str(e)}",
                }
            )
    return applied, failed


def preflight_graph_mount_targets_for_graph_code_files(
    *,
    graph_code_files: Sequence[Path],
    entity_name_to_guid: Mapping[str, int] | None,
    component_name_to_id: Mapping[str, int] | None,
) -> list[Dict[str, Any]]:
    """预检 Graph Code 的 mount 声明并返回解析结果（用于尽早提示缺失映射）。"""
    out: list[Dict[str, Any]] = []
    for p0 in list(graph_code_files or []):
        p = Path(p0).resolve()
        try:
            usage = scan_graph_mount_usage_from_graph_code_file(graph_code_file=Path(p))
        except Exception as e:
            out.append(
                {
                    "graph_code_file": str(p),
                    "scan_error": f"{type(e).__name__}: {str(e)}",
                }
            )
            continue

        if not usage.is_used:
            continue

        resolved, unresolved = resolve_graph_mount_targets_best_effort(
            usage=usage,
            entity_name_to_guid=entity_name_to_guid,
            component_name_to_id=component_name_to_id,
        )
        out.append(
            {
                "graph_code_file": str(p),
                "resolved_targets": [
                    {"kind": str(t.kind), "name": str(t.name), "instance_id_int": int(t.instance_id_int)} for t in resolved
                ],
                "unresolved_targets": [{"kind": str(t.kind), "name": str(t.name), "reason": str(t.reason)} for t in unresolved],
            }
        )

    return out


__all__ = [
    "GraphMountUsage",
    "ResolvedGraphMountTarget",
    "UnresolvedGraphMountTarget",
    "apply_graph_mounts_to_payload_root",
    "apply_graph_mounts_to_payload_root_best_effort",
    "infer_graph_category_int_from_graph_code_file",
    "resolve_graph_mount_targets",
    "resolve_graph_mount_targets_best_effort",
    "scan_graph_mount_usage_from_graph_code_file",
    "preflight_graph_mount_targets_for_graph_code_files",
]

