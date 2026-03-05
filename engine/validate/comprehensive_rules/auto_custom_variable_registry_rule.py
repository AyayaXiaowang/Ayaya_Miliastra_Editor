from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from engine.resources.auto_custom_variable_registry import (
    OWNER_KEYWORDS,
    AutoCustomVariableDeclaration,
    load_auto_custom_variable_registry_from_code,
    resolve_owner_refs,
    stable_variable_file_id_for,
)
from engine.resources.custom_variable_file_refs import normalize_custom_variable_file_refs

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule


_SPECIAL_VIEW_PACKAGE_IDS = {"global_view", "unclassified_view"}
_REGISTRY_FILENAME = "自定义变量注册表.py"
_CUSTOM_VARIABLE_NAME_MAX_LEN = 20


class AutoCustomVariableRegistryRule(BaseComprehensiveRule):
    """校验『自定义变量注册表』与生成物/引用点的一致性。"""

    rule_id = "package.auto_custom_variable_registry"
    category = "自定义变量注册表"
    default_level = "error"

    def run(self, ctx) -> List[ValidationIssue]:
        return validate_auto_custom_variable_registry(self.validator, ctx)


def _read_json(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _iter_json_files_under(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return []
    return [p for p in root.rglob("*.json") if p.is_file()]


def _build_variables_by_name(level_variables: Mapping[str, object]) -> dict[str, list[dict]]:
    by_name: dict[str, list[dict]] = {}
    for _var_id, payload in (level_variables or {}).items():
        if not isinstance(payload, dict):
            continue
        name = str(payload.get("variable_name") or payload.get("name") or "").strip()
        if not name:
            continue
        by_name.setdefault(name, []).append(payload)
    return by_name


def _find_level_entity_instance_json_paths(package_root: Path) -> list[Path]:
    instances_dir = (package_root / "实体摆放").resolve()
    found: list[Path] = []
    for p in _iter_json_files_under(instances_dir):
        payload = _read_json(p)
        if payload is None:
            continue
        meta = payload.get("metadata")
        if isinstance(meta, dict) and bool(meta.get("is_level_entity")):
            found.append(p)
    found.sort(key=lambda x: x.as_posix().casefold())
    return found


def _extract_custom_variable_file_refs(payload: dict) -> list[str]:
    meta = payload.get("metadata")
    if not isinstance(meta, dict):
        return []
    return normalize_custom_variable_file_refs(meta.get("custom_variable_file"))


def _find_instance_json_by_id(package_root: Path, instance_id: str) -> Path | None:
    target = str(instance_id or "").strip()
    if not target:
        return None
    for p in _iter_json_files_under((package_root / "实体摆放").resolve()):
        payload = _read_json(p)
        if payload is None:
            continue
        if str(payload.get("instance_id") or "").strip() == target:
            return p
    return None


def _find_template_json_by_id(package_root: Path, template_id: str) -> Path | None:
    target = str(template_id or "").strip()
    if not target:
        return None
    for p in _iter_json_files_under((package_root / "元件库").resolve()):
        payload = _read_json(p)
        if payload is None:
            continue
        if str(payload.get("template_id") or "").strip() == target:
            return p
    return None


def validate_auto_custom_variable_registry(validator, ctx) -> List[ValidationIssue]:
    package = getattr(validator, "package", None)
    if package is None:
        return []
    package_id = str(getattr(package, "package_id", "") or "").strip()
    if not package_id or package_id in _SPECIAL_VIEW_PACKAGE_IDS:
        return []
    workspace_root = getattr(ctx, "workspace_path", None)
    workspace = Path(workspace_root or ".").resolve()
    package_root = (workspace / "assets" / "资源库" / "项目存档" / package_id).resolve()
    registry_path = (package_root / "管理配置" / "关卡变量" / _REGISTRY_FILENAME).resolve()
    base_location = f"存档({package_id}) > 管理配置 > 关卡变量 > {_REGISTRY_FILENAME}"
    issues: list[ValidationIssue] = []

    if not registry_path.is_file():
        issues.append(ValidationIssue(
            level="warning", category="自定义变量注册表", location=base_location,
            message="未找到自定义变量注册表文件。",
            suggestion=f"请创建：{registry_path.as_posix()}",
            detail={"type": "auto_custom_var_registry_missing", "package_id": package_id},
        ))
        return issues

    try:
        declarations = load_auto_custom_variable_registry_from_code(registry_path)
    except Exception as e:
        issues.append(ValidationIssue(
            level="error", category="自定义变量注册表", location=base_location,
            message=f"加载注册表失败：{e}",
            suggestion="请检查注册表语法与 CUSTOM_VARIABLE_DECLARATIONS 列表。",
            detail={"type": "auto_custom_var_registry_load_failed", "error": repr(e)},
        ))
        return issues

    issues.extend(_validate_decl_basics(declarations, base_location=base_location))
    if any(i.level == "error" for i in issues):
        return issues

    management = getattr(package, "management", None)
    level_vars = getattr(management, "level_variables", None) if management is not None else None
    level_variables: Dict[str, object] = level_vars if isinstance(level_vars, dict) else {}
    variables_by_name = _build_variables_by_name(level_variables)

    issues.extend(_validate_decl_schema_presence(
        declarations, package_id=package_id, base_location=base_location,
        variables_by_name=variables_by_name,
    ))

    issues.extend(_validate_owner_refs_existence(
        declarations, package_id=package_id, package_root=package_root,
        base_location=base_location,
    ))

    issues.extend(_validate_migration_hints(
        declarations, package=package, package_id=package_id,
        base_location=base_location, variables_by_name=variables_by_name,
    ))

    return issues


def _validate_decl_basics(
    declarations: list[AutoCustomVariableDeclaration], *, base_location: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    seen_names: set[str] = set()
    dup_names: set[str] = set()
    for decl in declarations:
        name = str(getattr(decl, "variable_name", "") or "").strip()
        vtype = str(getattr(decl, "variable_type", "") or "").strip()
        if not name:
            issues.append(ValidationIssue(
                level="error", category="自定义变量注册表", location=base_location,
                message="存在 variable_name 为空的声明。", suggestion="请填写 variable_name。",
                detail={"type": "auto_custom_var_decl_missing_name"},
            ))
            continue
        if len(name) > _CUSTOM_VARIABLE_NAME_MAX_LEN:
            issues.append(ValidationIssue(
                level="error", category="自定义变量注册表", location=base_location,
                message=f"变量名过长：{name!r}（len={len(name)}，上限={_CUSTOM_VARIABLE_NAME_MAX_LEN}）。",
                suggestion="请压缩 variable_name（<=20）。",
                detail={"type": "auto_custom_var_decl_name_too_long", "variable_name": name},
            ))
        if not vtype:
            issues.append(ValidationIssue(
                level="error", category="自定义变量注册表", location=base_location,
                message=f"变量 {name!r} 的 variable_type 为空。", suggestion="请填写 variable_type。",
                detail={"type": "auto_custom_var_decl_missing_type", "variable_name": name},
            ))
        if name in seen_names:
            dup_names.add(name)
        seen_names.add(name)
    if dup_names:
        issues.append(ValidationIssue(
            level="error", category="自定义变量注册表", location=base_location,
            message="重复 variable_name：" + ", ".join(sorted(dup_names)),
            suggestion="请保证 variable_name 全局唯一。",
            detail={"type": "auto_custom_var_decl_duplicate_names", "names": sorted(dup_names)},
        ))
    return issues


def _validate_decl_schema_presence(
    declarations: list[AutoCustomVariableDeclaration], *,
    package_id: str, base_location: str, variables_by_name: dict[str, list[dict]],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for decl in declarations:
        name = str(getattr(decl, "variable_name", "") or "").strip()
        if not name:
            continue
        payloads = variables_by_name.get(name, [])
        if not payloads:
            issues.append(ValidationIssue(
                level="error", category="自定义变量注册表", location=base_location,
                message=f"变量 {name!r} 在 Schema 中不存在（需运行 sync-custom-vars）。",
                suggestion=f"运行：python -X utf8 -m app.cli.graph_tools sync-custom-vars --package-id {package_id}",
                detail={"type": "auto_custom_var_decl_missing_in_schema", "variable_name": name},
            ))
            continue
        if len(payloads) > 1:
            file_ids = sorted({str(p.get("variable_file_id") or "") for p in payloads})
            issues.append(ValidationIssue(
                level="error", category="自定义变量注册表", location=base_location,
                message=f"变量 {name!r} 在 Schema 中出现多份定义：{file_ids}",
                suggestion="请确保全局仅一份定义。",
                detail={"type": "auto_custom_var_decl_ambiguous", "variable_name": name},
            ))
            continue
        payload = payloads[0]
        actual_type = str(payload.get("variable_type") or "").strip()
        expected_type = str(getattr(decl, "variable_type", "") or "").strip()
        if expected_type and actual_type and expected_type != actual_type:
            issues.append(ValidationIssue(
                level="error", category="自定义变量注册表", location=base_location,
                message=f"变量 {name!r} 类型不一致：registry={expected_type!r} / schema={actual_type!r}",
                suggestion="请统一 registry 与变量文件中的 variable_type。",
                detail={"type": "auto_custom_var_type_mismatch", "variable_name": name},
            ))
        owner_refs = resolve_owner_refs(decl)
        expected_file_ids = {
            stable_variable_file_id_for(package_id, owner_ref=r, prefix="auto_custom_vars")
            for r in owner_refs
        }
        actual_file_id = str(payload.get("variable_file_id") or "").strip()
        if actual_file_id and expected_file_ids and actual_file_id not in expected_file_ids:
            issues.append(ValidationIssue(
                level="error", category="自定义变量注册表", location=base_location,
                message=f"变量 {name!r} 落盘文件不符合注册表规则：actual={actual_file_id}",
                suggestion="请运行 sync-custom-vars 重新生成。",
                detail={"type": "auto_custom_var_wrong_file", "variable_name": name},
            ))
    return issues


def _validate_owner_refs_existence(
    declarations: list[AutoCustomVariableDeclaration], *,
    package_id: str, package_root: Path, base_location: str,
) -> list[ValidationIssue]:
    """校验每个 owner_ref 对应的实体/模板是否存在并引用了变量文件。"""
    issues: list[ValidationIssue] = []
    all_refs: set[str] = set()
    for d in declarations:
        all_refs.update(resolve_owner_refs(d))

    if "player" in {r.lower() for r in all_refs}:
        issues.extend(_check_player_refs(package_root, package_id=package_id, base_location=base_location))
    if "level" in {r.lower() for r in all_refs}:
        issues.extend(_check_level_refs(package_root, package_id=package_id, base_location=base_location))
    for ref in sorted(r for r in all_refs if r.lower() not in OWNER_KEYWORDS):
        issues.extend(_check_entity_ref(
            package_root, entity_ref=ref, package_id=package_id, base_location=base_location,
        ))
    return issues


def _check_player_refs(
    package_root: Path, *, package_id: str, base_location: str,
) -> list[ValidationIssue]:
    file_id = stable_variable_file_id_for(package_id, owner_ref="player", prefix="auto_custom_vars")
    player_dir = (package_root / "战斗预设" / "玩家模板").resolve()
    missing: list[str] = []
    for p in sorted([x for x in player_dir.glob("*.json") if x.is_file()], key=lambda x: x.as_posix()):
        payload = _read_json(p)
        if payload is None:
            continue
        refs = _extract_custom_variable_file_refs(payload)
        if file_id not in refs:
            missing.append(p.name)
    if missing:
        return [ValidationIssue(
            level="error", category="自定义变量注册表", location=base_location,
            message=f"玩家变量文件未被所有玩家模板引用：缺失 {len(missing)} 个",
            suggestion="运行 sync-custom-vars 自动补齐引用。",
            detail={"type": "auto_custom_var_player_missing_ref", "missing": missing},
        )]
    return []


def _check_level_refs(
    package_root: Path, *, package_id: str, base_location: str,
) -> list[ValidationIssue]:
    file_id = stable_variable_file_id_for(package_id, owner_ref="level", prefix="auto_custom_vars")
    level_paths = _find_level_entity_instance_json_paths(package_root)
    if not level_paths:
        return [ValidationIssue(
            level="warning", category="自定义变量注册表", location=base_location,
            message="未找到关卡实体实例。", suggestion="请检查实体摆放目录。",
            detail={"type": "auto_custom_var_level_entity_missing"},
        )]
    missing: list[str] = []
    for p in level_paths:
        payload = _read_json(p)
        if payload is None:
            continue
        refs = _extract_custom_variable_file_refs(payload)
        if file_id not in refs:
            missing.append(p.name)
    if missing:
        return [ValidationIssue(
            level="error", category="自定义变量注册表", location=base_location,
            message=f"关卡实体变量文件未被关卡实体引用：缺失 {len(missing)} 个",
            suggestion="运行 sync-custom-vars 自动补齐引用。",
            detail={"type": "auto_custom_var_level_missing_ref", "missing": missing},
        )]
    return []


def _check_entity_ref(
    package_root: Path, *, entity_ref: str, package_id: str, base_location: str,
) -> list[ValidationIssue]:
    file_id = stable_variable_file_id_for(package_id, owner_ref=entity_ref, prefix="auto_custom_vars")

    instance_path = _find_instance_json_by_id(package_root, entity_ref)
    if instance_path is not None:
        instance_payload = _read_json(instance_path) or {}
        template_id = str(instance_payload.get("template_id") or "").strip()
        template_path = _find_template_json_by_id(package_root, template_id)
        if template_path is None:
            return [ValidationIssue(
                level="error", category="自定义变量注册表", location=base_location,
                message=f"实体 {entity_ref!r} 的 template_id={template_id!r} 未找到",
                suggestion="请检查 template_id 是否正确。",
                detail={"type": "auto_custom_var_entity_template_missing", "entity_ref": entity_ref},
            )]
        template_payload = _read_json(template_path) or {}
        refs = _extract_custom_variable_file_refs(template_payload)
        if file_id not in refs:
            return [ValidationIssue(
                level="error", category="自定义变量注册表", location=base_location,
                message=f"实体 {entity_ref!r} 的模板未引用变量文件：{file_id}",
                suggestion="运行 sync-custom-vars 自动补齐引用。",
                detail={"type": "auto_custom_var_entity_missing_ref", "entity_ref": entity_ref},
            )]
        return []

    template_path = _find_template_json_by_id(package_root, entity_ref)
    if template_path is not None:
        template_payload = _read_json(template_path) or {}
        refs = _extract_custom_variable_file_refs(template_payload)
        if file_id not in refs:
            return [ValidationIssue(
                level="error", category="自定义变量注册表", location=base_location,
                message=f"模板 {entity_ref!r} 未引用变量文件：{file_id}",
                suggestion="运行 sync-custom-vars 自动补齐引用。",
                detail={"type": "auto_custom_var_template_missing_ref", "entity_ref": entity_ref},
            )]
        return []

    return [ValidationIssue(
        level="error", category="自定义变量注册表", location=base_location,
        message=f"owner 引用 {entity_ref!r} 在实体摆放和元件库中均未找到",
        suggestion="请检查 owner 值是否为有效的 instance_id 或 template_id。",
        detail={"type": "auto_custom_var_entity_ref_not_found", "entity_ref": entity_ref},
    )]


def _validate_migration_hints(
    declarations: list[AutoCustomVariableDeclaration], *,
    package: Any, package_id: str, base_location: str,
    variables_by_name: dict[str, list[dict]],
) -> list[ValidationIssue]:
    declared_names = {str(d.variable_name or "").strip() for d in declarations if str(d.variable_name or "").strip()}
    package_index = getattr(package, "package_index", None)
    resources_value = getattr(package_index, "resources", None) if package_index is not None else None
    management_value = getattr(resources_value, "management", None) if resources_value is not None else None
    mgmt_mapping: dict[str, object] = management_value if isinstance(management_value, dict) else {}
    package_file_ids_raw = mgmt_mapping.get("level_variables", [])
    package_file_id_set: set[str] = set()
    if isinstance(package_file_ids_raw, list):
        for v in package_file_ids_raw:
            if isinstance(v, str) and v.strip():
                package_file_id_set.add(v.strip())
    missing: list[str] = []
    for payload_list in variables_by_name.values():
        for item in payload_list:
            if not isinstance(item, dict):
                continue
            file_id = str(item.get("variable_file_id") or "").strip()
            if package_file_id_set and file_id and file_id not in package_file_id_set:
                continue
            source_dir = str(item.get("source_directory") or "").strip()
            if not source_dir.startswith("自定义变量"):
                continue
            meta = item.get("metadata")
            category = meta.get("category") if isinstance(meta, dict) else None
            if category in {"UI自动生成", "UI网页默认值"}:
                continue
            var_name = str(item.get("variable_name") or "").strip()
            if not var_name or var_name in declared_names:
                continue
            missing.append(var_name)
    if missing:
        preview = ", ".join(sorted(missing)[:20])
        return [ValidationIssue(
            level="warning", category="自定义变量注册表", location=base_location,
            message=f"发现 {len(missing)} 个自定义变量未迁移到注册表（示例：{preview}）。",
            suggestion="建议逐步将零散变量整理到注册表。",
            detail={"type": "auto_custom_var_missing_in_registry", "count": len(missing)},
        )]
    return []


__all__ = ["AutoCustomVariableRegistryRule", "validate_auto_custom_variable_registry"]
