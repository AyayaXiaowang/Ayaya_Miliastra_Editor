"""本地测试对话框的纯业务逻辑（无 PyQt6 依赖）。

目标：
- 把 owner 推断索引、graph_id 解析、key=value 参数解析等可测试逻辑从 UI 中抽离；
- UI 层仅负责控件绑定与生命周期（start/stop/open browser）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from engine.configs.resource_types import ResourceType
from engine.resources.graph_reference_service import iter_references_from_package_index


def parse_graph_id_from_source_file(graph_code_file: Path, *, max_lines: int = 220) -> str:
    """从 Graph Code 源码头部解析 `graph_id:` 字段。

    说明：
    - 仅扫描前 max_lines 行，避免大型图文件反复全量读取；
    - 不做异常吞并：文件不存在/读取失败等直接抛出，交由上层统一处理。
    """
    path = Path(graph_code_file).resolve()
    if not path.is_file():
        return ""

    lines: list[str] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for _ in range(int(max_lines)):
            line = f.readline()
            if not line:
                break
            lines.append(line)
    head = "".join(lines)
    match = re.search(r"^graph_id:\s*(.+?)\s*$", head, flags=re.MULTILINE)
    return str(match.group(1)).strip() if match else ""


def parse_kv_lines(raw_text: str) -> tuple[dict[str, Any], str]:
    """解析每行 `key=value` 的参数文本。

    返回：(params, error_message)。error_message 非空表示解析失败。
    """
    params: dict[str, Any] = {}
    for line_no, raw_line in enumerate(str(raw_text or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if "=" not in line:
            return {}, f"第 {line_no} 行不是 key=value：{raw_line!r}"
        key, value = line.split("=", 1)
        k = key.strip()
        v = value.strip()
        if not k:
            return {}, f"第 {line_no} 行 key 为空：{raw_line!r}"
        if v.lower() in {"true", "false"}:
            params[k] = v.lower() == "true"
            continue
        if v.isdigit() or (v.startswith("-") and v[1:].isdigit()):
            params[k] = int(v)
            continue
        params[k] = v
    return params, ""


@dataclass(frozen=True, slots=True)
class OwnerCandidate:
    entity_type: str
    entity_id: str
    entity_name: str
    owner_name: str
    display_type: str
    priority: int

    def to_combo_payload(self) -> dict[str, str]:
        return {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "owner_name": self.owner_name,
            "display_type": self.display_type,
            "priority": str(self.priority),
        }


@dataclass(frozen=True, slots=True)
class _OwnerReferenceIndex:
    package_id: str
    fingerprint: str
    graph_to_refs: dict[str, list[tuple[str, str, str, str]]]
    level_entity_id: str
    level_entity_name: str


class LocalGraphSimOwnerInferenceService:
    """根据主图（入口挂载图）graph_id 推断 owner 候选（仅当前项目存档范围）。"""

    def __init__(self, *, resource_manager: Any | None, package_index_manager: Any | None) -> None:
        self._resource_manager = resource_manager
        self._package_index_manager = package_index_manager
        self._index: _OwnerReferenceIndex | None = None

    def is_available(self) -> bool:
        return self._resource_manager is not None and self._package_index_manager is not None

    def _build_index(self, *, package_id: str) -> _OwnerReferenceIndex:
        rm = self._resource_manager
        pim = self._package_index_manager
        if rm is None or pim is None:
            raise RuntimeError("OwnerInferenceService 未注入 resource_manager / package_index_manager")

        fingerprint = str(rm.get_resource_library_fingerprint() or "").strip()
        package_index = pim.load_package_index(package_id, refresh_resource_names=False)
        if package_index is None:
            return _OwnerReferenceIndex(
                package_id=package_id,
                fingerprint=fingerprint,
                graph_to_refs={},
                level_entity_id="",
                level_entity_name="关卡实体",
            )

        level_entity_id = str(getattr(package_index, "level_entity_id", "") or "").strip()
        level_entity_name = "关卡实体"
        if level_entity_id:
            payload = rm.load_resource(ResourceType.INSTANCE, level_entity_id, copy_mode="none")
            if isinstance(payload, dict):
                name = str(payload.get("name") or "").strip()
                if name:
                    level_entity_name = name

        graph_to_refs: dict[str, list[tuple[str, str, str, str]]] = {}
        for ref in iter_references_from_package_index(
            package_id=package_id,
            package_index=package_index,
            resource_manager=rm,
            include_combat_presets=False,
            include_skill_ugc_indirect=False,
        ):
            graph_to_refs.setdefault(ref.graph_id, []).append(
                (ref.reference_type, ref.reference_id, ref.reference_name, ref.package_id)
            )

        return _OwnerReferenceIndex(
            package_id=package_id,
            fingerprint=fingerprint,
            graph_to_refs=graph_to_refs,
            level_entity_id=level_entity_id,
            level_entity_name=level_entity_name,
        )

    def ensure_index(self, *, package_id: str, force_rebuild: bool) -> None:
        pkg = str(package_id or "").strip()
        if not pkg or not self.is_available():
            self._index = None
            return

        rm = self._resource_manager
        fingerprint = str(rm.get_resource_library_fingerprint() or "").strip() if rm is not None else ""
        idx = self._index
        if (
            (not force_rebuild)
            and idx is not None
            and idx.package_id == pkg
            and idx.fingerprint == fingerprint
        ):
            return

        self._index = self._build_index(package_id=pkg)

    def list_candidates(self, *, package_id: str, graph_id: str) -> list[OwnerCandidate]:
        pkg = str(package_id or "").strip()
        gid = str(graph_id or "").strip()
        if not pkg or not gid:
            return []

        idx = self._index
        if idx is None or idx.package_id != pkg:
            return []

        refs = list(idx.graph_to_refs.get(gid, []) or [])
        out: list[OwnerCandidate] = []
        seen: set[tuple[str, str]] = set()

        level_entity_id = str(idx.level_entity_id or "").strip()
        level_entity_name = str(idx.level_entity_name or "关卡实体").strip() or "关卡实体"

        for rtype, rid, rname, rpackage in refs:
            if str(rpackage or "").strip() != pkg:
                continue
            kind = str(rtype or "").strip()
            if kind == "level_entity":
                if not level_entity_id:
                    continue
                key = ("level_entity", level_entity_id)
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    OwnerCandidate(
                        entity_type="level_entity",
                        entity_id=level_entity_id,
                        entity_name=level_entity_name,
                        owner_name=level_entity_name,
                        display_type="关卡实体",
                        priority=0,
                    )
                )
                continue
            if kind == "instance":
                entity_id = str(rid or "").strip()
                if not entity_id:
                    continue
                key = ("instance", entity_id)
                if key in seen:
                    continue
                seen.add(key)
                name = str(rname or entity_id).strip() or entity_id
                out.append(
                    OwnerCandidate(
                        entity_type="instance",
                        entity_id=entity_id,
                        entity_name=name,
                        owner_name=name,
                        display_type="实体摆放",
                        priority=1,
                    )
                )
                continue
            if kind == "template":
                entity_id = str(rid or "").strip()
                if not entity_id:
                    continue
                key = ("template", entity_id)
                if key in seen:
                    continue
                seen.add(key)
                name = str(rname or entity_id).strip() or entity_id
                out.append(
                    OwnerCandidate(
                        entity_type="template",
                        entity_id=entity_id,
                        entity_name=name,
                        owner_name=name,
                        display_type="元件模板",
                        priority=2,
                    )
                )
                continue

        out.sort(key=lambda x: (int(x.priority), str(x.entity_name).casefold()))
        return out


def pick_preferred_candidate_index(candidates: Iterable[OwnerCandidate]) -> int:
    """返回 candidates 中优先级最小的候选索引（默认 0）。"""
    best_i = 0
    best_priority = 999
    for i, c in enumerate(list(candidates or [])):
        pr = int(getattr(c, "priority", 999))
        if pr < best_priority:
            best_priority = pr
            best_i = i
    return int(best_i)

