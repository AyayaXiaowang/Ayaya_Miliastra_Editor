from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from engine.resources.auto_custom_variable_registry import (
    OWNER_KEYWORDS,
    AutoCustomVariableDeclaration,
    load_auto_custom_variable_registry_from_code,
    resolve_owner_refs,
    stable_variable_file_id_for,
    stable_variable_id_for,
)

REGISTRY_FILENAME = "自定义变量注册表.py"
_VARIABLE_ID_PREFIX = "var_auto"
_VARIABLE_FILE_ID_PREFIX = "auto_custom_vars"


@dataclass(frozen=True, slots=True)
class VirtualVariableFile:
    file_id: str
    file_name: str
    variables: tuple[dict[str, Any], ...]


def _ensure_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _build_variable_payloads(
    decls: Iterable[AutoCustomVariableDeclaration],
    *,
    package_id: str,
    owner_ref: str,
) -> tuple[dict[str, Any], ...]:
    payloads: list[dict[str, Any]] = []
    for decl in list(decls or []):
        var_name = str(getattr(decl, "variable_name", "") or "").strip()
        vtype = str(getattr(decl, "variable_type", "") or "").strip()
        var_id = str(getattr(decl, "variable_id", "") or "").strip()
        if not var_id:
            var_id = stable_variable_id_for(package_id, variable_name=var_name, prefix=_VARIABLE_ID_PREFIX)
        meta: dict[str, Any] = {}
        meta.update(_ensure_dict(getattr(decl, "metadata", None)))
        category = str(getattr(decl, "category", "") or "").strip()
        if category and "category" not in meta:
            meta["category"] = category
        owner_lower = owner_ref.lower()
        owner_val = owner_lower if owner_lower in OWNER_KEYWORDS else "data"
        payloads.append({
            "variable_id": var_id,
            "variable_name": var_name,
            "variable_type": vtype,
            "owner": owner_val,
            "default_value": getattr(decl, "default_value", None),
            "is_global": False,
            "description": str(getattr(decl, "description", "") or "").strip(),
            "metadata": meta,
        })
    return tuple(payloads)


def _friendly_name_for_owner(owner_ref: str, package_id: str) -> str:
    lower = owner_ref.lower()
    if lower == "player":
        return f"注册表派生_玩家变量__{package_id}"
    if lower == "level":
        return f"注册表派生_关卡实体变量__{package_id}"
    short = owner_ref[:40] if len(owner_ref) > 40 else owner_ref
    return f"注册表派生_实体变量__{short}__{package_id}"


def load_virtual_variable_files_from_registry(
    *,
    registry_path: Path,
    package_id: str,
) -> tuple[VirtualVariableFile, ...]:
    declarations = load_auto_custom_variable_registry_from_code(registry_path)

    by_owner: dict[str, list[AutoCustomVariableDeclaration]] = {}
    for decl in list(declarations or []):
        for ref in resolve_owner_refs(decl):
            by_owner.setdefault(ref, []).append(decl)

    out: list[VirtualVariableFile] = []
    for owner_ref in sorted(by_owner, key=lambda x: (x.lower() not in OWNER_KEYWORDS, x.casefold())):
        decls = by_owner[owner_ref]
        file_id = stable_variable_file_id_for(package_id, owner_ref=owner_ref, prefix=_VARIABLE_FILE_ID_PREFIX)
        out.append(VirtualVariableFile(
            file_id=file_id,
            file_name=_friendly_name_for_owner(owner_ref, package_id),
            variables=_build_variable_payloads(decls, package_id=package_id, owner_ref=owner_ref),
        ))

    return tuple(out)


__all__ = [
    "REGISTRY_FILENAME",
    "VirtualVariableFile",
    "load_virtual_variable_files_from_registry",
]
