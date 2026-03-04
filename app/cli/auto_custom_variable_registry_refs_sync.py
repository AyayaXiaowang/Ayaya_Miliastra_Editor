from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from engine.resources.auto_custom_variable_registry import (
    OWNER_KEYWORDS,
    AutoCustomVariableDeclaration,
    load_auto_custom_variable_registry_from_code,
    resolve_owner_refs,
    stable_variable_file_id_for,
)
from engine.resources.custom_variable_file_refs import (
    normalize_custom_variable_file_refs,
    serialize_custom_variable_file_refs,
)

_DEFAULT_REGISTRY_FILENAME = "自定义变量注册表.py"


@dataclass(frozen=True, slots=True)
class AutoCustomVarSyncAction:
    file_path: Path
    summary: str


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ensure_metadata_dict(payload: dict) -> dict:
    meta = payload.get("metadata")
    if isinstance(meta, dict):
        return meta
    meta = {}
    payload["metadata"] = meta
    return meta


def _append_file_ref(meta: dict, file_id: str) -> bool:
    old_refs = normalize_custom_variable_file_refs(meta.get("custom_variable_file"))
    if file_id in old_refs:
        return False
    new_refs = list(old_refs) + [file_id]
    meta["custom_variable_file"] = serialize_custom_variable_file_refs(new_refs)
    return True


def _iter_json_files_under(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return []
    for p in root.rglob("*.json"):
        if p.is_file():
            yield p
    return []


def _find_level_entity_instance_json_paths(package_root: Path) -> list[Path]:
    instances_dir = (package_root / "实体摆放").resolve()
    found: list[Path] = []
    for p in _iter_json_files_under(instances_dir):
        try:
            payload = _read_json(p)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        meta = payload.get("metadata")
        if isinstance(meta, dict) and bool(meta.get("is_level_entity")):
            found.append(p)
    found.sort(key=lambda x: x.as_posix().casefold())
    return found


def _find_instance_json_by_id(package_root: Path, instance_id: str) -> Path | None:
    target = str(instance_id or "").strip()
    if not target:
        return None
    for p in _iter_json_files_under((package_root / "实体摆放").resolve()):
        try:
            payload = _read_json(p)
        except Exception:
            continue
        if isinstance(payload, dict) and str(payload.get("instance_id") or "").strip() == target:
            return p
    return None


def _find_template_json_by_id(package_root: Path, template_id: str) -> Path | None:
    target = str(template_id or "").strip()
    if not target:
        return None
    for p in _iter_json_files_under((package_root / "元件库").resolve()):
        try:
            payload = _read_json(p)
        except Exception:
            continue
        if isinstance(payload, dict) and str(payload.get("template_id") or "").strip() == target:
            return p
    return None


def _validate_declarations(
    decls: Sequence[AutoCustomVariableDeclaration], *, registry_path: Path,
) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for decl in decls:
        name = str(getattr(decl, "variable_name", "") or "").strip()
        vtype = str(getattr(decl, "variable_type", "") or "").strip()
        if not name:
            raise ValueError(f"{registry_path}: variable_name 不能为空")
        if not vtype:
            raise ValueError(f"{registry_path}: variable_type 不能为空（{name}）")
        if name in seen:
            duplicates.add(name)
        seen.add(name)
    if duplicates:
        raise ValueError(f"{registry_path}: 重复 variable_name：{', '.join(sorted(duplicates))}")


def _collect_owner_refs(declarations: Sequence[AutoCustomVariableDeclaration]) -> set[str]:
    refs: set[str] = set()
    for d in declarations:
        refs.update(resolve_owner_refs(d))
    return refs


def sync_auto_custom_variable_refs_from_registry(
    *,
    workspace_root: Path,
    package_id: str,
    dry_run: bool,
) -> list[AutoCustomVarSyncAction]:
    pkg, package_root, registry_path, declarations = _load_registry_inputs(
        workspace_root=workspace_root, package_id=package_id,
    )
    _validate_declarations(declarations, registry_path=registry_path)
    all_refs = _collect_owner_refs(declarations)
    actions: list[AutoCustomVarSyncAction] = []

    if "player" in {r.lower() for r in all_refs}:
        actions.extend(_sync_player_template_refs(package_root, package_id=pkg, declarations=declarations, dry_run=dry_run))
    if "level" in {r.lower() for r in all_refs}:
        actions.extend(_sync_level_entity_refs(package_root, package_id=pkg, declarations=declarations, dry_run=dry_run))

    entity_refs = {r for r in all_refs if r.lower() not in OWNER_KEYWORDS}
    for ref in sorted(entity_refs, key=lambda x: x.casefold()):
        actions.extend(_sync_entity_ref(package_root, package_id=pkg, entity_ref=ref, dry_run=dry_run))

    return actions


def _load_registry_inputs(
    *, workspace_root: Path, package_id: str,
) -> tuple[str, Path, Path, list[AutoCustomVariableDeclaration]]:
    pkg = str(package_id or "").strip()
    if not pkg:
        raise ValueError("package_id 不能为空")
    workspace = Path(workspace_root).resolve()
    package_root = (workspace / "assets" / "资源库" / "项目存档" / pkg).resolve()
    if not package_root.is_dir():
        raise ValueError(f"未知项目存档目录：{package_root}")
    registry_path = (package_root / "管理配置" / "关卡变量" / _DEFAULT_REGISTRY_FILENAME).resolve()
    if not registry_path.is_file():
        raise FileNotFoundError(f"未找到注册表：{registry_path}")
    declarations = load_auto_custom_variable_registry_from_code(registry_path)
    return pkg, package_root, registry_path, list(declarations or [])


def _sync_player_template_refs(
    package_root: Path, *, package_id: str,
    declarations: Sequence[AutoCustomVariableDeclaration], dry_run: bool,
) -> list[AutoCustomVarSyncAction]:
    file_id = stable_variable_file_id_for(package_id, owner_ref="player", prefix="auto_custom_vars")
    player_dir = (package_root / "战斗预设" / "玩家模板").resolve()
    actions: list[AutoCustomVarSyncAction] = []
    for p in sorted([x for x in player_dir.glob("*.json") if x.is_file()], key=lambda x: x.as_posix()):
        payload = _read_json(p)
        if not isinstance(payload, dict):
            continue
        meta = _ensure_metadata_dict(payload)
        if not _append_file_ref(meta, file_id):
            continue
        summary = f"更新玩家模板 custom_variable_file（追加 {file_id}）"
        if dry_run:
            actions.append(AutoCustomVarSyncAction(file_path=p, summary=f"[DRY-RUN] {summary}"))
            continue
        _write_json(p, payload)
        actions.append(AutoCustomVarSyncAction(file_path=p, summary=summary))
    return actions


def _sync_level_entity_refs(
    package_root: Path, *, package_id: str,
    declarations: Sequence[AutoCustomVariableDeclaration], dry_run: bool,
) -> list[AutoCustomVarSyncAction]:
    file_id = stable_variable_file_id_for(package_id, owner_ref="level", prefix="auto_custom_vars")
    actions: list[AutoCustomVarSyncAction] = []
    for p in _find_level_entity_instance_json_paths(package_root):
        payload = _read_json(p)
        if not isinstance(payload, dict):
            continue
        meta = _ensure_metadata_dict(payload)
        if not _append_file_ref(meta, file_id):
            continue
        summary = f"更新关卡实体 custom_variable_file（追加 {file_id}）"
        if dry_run:
            actions.append(AutoCustomVarSyncAction(file_path=p, summary=f"[DRY-RUN] {summary}"))
            continue
        _write_json(p, payload)
        actions.append(AutoCustomVarSyncAction(file_path=p, summary=summary))
    return actions


def _sync_entity_ref(
    package_root: Path, *, package_id: str, entity_ref: str, dry_run: bool,
) -> list[AutoCustomVarSyncAction]:
    """按 instance_id/template_id 查找实体，把变量文件引用追加到其模板。"""
    file_id = stable_variable_file_id_for(package_id, owner_ref=entity_ref, prefix="auto_custom_vars")
    actions: list[AutoCustomVarSyncAction] = []

    instance_path = _find_instance_json_by_id(package_root, entity_ref)
    if instance_path is not None:
        instance_payload = _read_json(instance_path)
        template_id = str(instance_payload.get("template_id") or "").strip()
        template_path = _find_template_json_by_id(package_root, template_id)
        if template_path is None:
            raise FileNotFoundError(
                f"实体 {entity_ref!r} 的 template_id={template_id!r} 未找到对应模板"
            )
        return _ensure_template_ref(template_path, file_id=file_id, dry_run=dry_run, entity_ref=entity_ref)

    template_path = _find_template_json_by_id(package_root, entity_ref)
    if template_path is not None:
        return _ensure_template_ref(template_path, file_id=file_id, dry_run=dry_run, entity_ref=entity_ref)

    raise FileNotFoundError(
        f"owner 引用 {entity_ref!r} 在实体摆放和元件库中均未找到"
    )


def _ensure_template_ref(
    template_path: Path, *, file_id: str, dry_run: bool, entity_ref: str,
) -> list[AutoCustomVarSyncAction]:
    payload = _read_json(template_path)
    if not isinstance(payload, dict):
        return []
    meta = _ensure_metadata_dict(payload)
    if not _append_file_ref(meta, file_id):
        return []
    summary = f"更新实体({entity_ref}) 模板 custom_variable_file（追加 {file_id}）"
    if dry_run:
        return [AutoCustomVarSyncAction(file_path=template_path, summary=f"[DRY-RUN] {summary}")]
    _write_json(template_path, payload)
    return [AutoCustomVarSyncAction(file_path=template_path, summary=summary)]


__all__ = ["AutoCustomVarSyncAction", "sync_auto_custom_variable_refs_from_registry"]
