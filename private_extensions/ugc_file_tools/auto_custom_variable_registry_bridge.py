from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from engine.resources.auto_custom_variable_registry import (
    OWNER_KEYWORDS,
    load_auto_custom_variable_registry_from_code,
    normalize_owner_refs,
)


OWNER_LEVEL = "level"
OWNER_PLAYER = "player"


@dataclass(frozen=True, slots=True)
class AutoCustomVariableRegistryIndex:
    registry_path: Path
    # owner(lower) -> variable_name(casefold) -> payload
    payloads_by_owner_and_name: dict[str, dict[str, dict[str, Any]]]
    # variable_id(casefold) -> payload
    payloads_by_id: dict[str, dict[str, Any]]


def _build_level_variable_payload_from_registry_decl(
    decl: Mapping[str, Any],
    *,
    owner: str,
    registry_path: Path,
) -> dict[str, Any]:
    vid = str(decl.get("variable_id") or "").strip()
    vname = str(decl.get("variable_name") or "").strip()
    vtype = str(decl.get("variable_type") or "").strip()
    if vid == "" or vname == "" or vtype == "":
        raise ValueError(f"{registry_path}: 注册表声明缺少必要字段：variable_id/variable_name/variable_type")
    payload: dict[str, Any] = {
        "variable_id": vid,
        "variable_name": vname,
        "variable_type": vtype,
        "default_value": decl.get("default_value"),
        "description": str(decl.get("description") or ""),
        "owner": str(owner),
        "category": str(decl.get("category") or ""),
        "metadata": (dict(decl.get("metadata")) if isinstance(decl.get("metadata"), dict) else {}),
        "_source_registry": str(Path(registry_path).resolve()),
    }
    return payload


def try_load_auto_custom_variable_registry_index_from_project_root(
    *, project_root: Path
) -> AutoCustomVariableRegistryIndex | None:
    """
    若项目存档存在 `管理配置/关卡变量/自定义变量注册表.py`，则静态加载其声明并构建索引。

    约定：
    - 仅收录 owner 为广播关键字（player/level）的声明；第三方 owner（instance_id/template_id）不进入该索引。
    - 同一条声明若同时包含 player 与 level 两个广播 owner：直接 fail-fast（避免一条变量声明被两个系统入口复用导致语义不清）。
    """
    project_root = Path(project_root).resolve()
    registry_path = (project_root / "管理配置" / "关卡变量" / "自定义变量注册表.py").resolve()
    if not registry_path.is_file():
        return None

    decls = load_auto_custom_variable_registry_from_code(registry_path)

    payloads_by_owner_and_name: dict[str, dict[str, dict[str, Any]]] = {OWNER_LEVEL: {}, OWNER_PLAYER: {}}
    payloads_by_id: dict[str, dict[str, Any]] = {}

    for d in decls:
        dct = {
            "variable_id": str(d.variable_id or ""),
            "variable_name": str(d.variable_name or ""),
            "variable_type": str(d.variable_type or ""),
            "default_value": d.default_value,
            "description": str(d.description or ""),
            "owner": d.owner,
            "category": str(d.category or ""),
            "metadata": (dict(d.metadata) if isinstance(d.metadata, dict) else {}),
        }
        owner_refs = [str(x).strip().lower() for x in normalize_owner_refs(dct.get("owner"))]
        broadcast = sorted({x for x in owner_refs if x in OWNER_KEYWORDS})
        if not broadcast:
            continue
        if len(broadcast) >= 2:
            raise ValueError(
                f"{registry_path}: 注册表声明同时包含多个广播 owner（不支持）："
                f"variable_id={dct.get('variable_id')!r} variable_name={dct.get('variable_name')!r} owners={broadcast}"
            )
        owner = str(broadcast[0])
        payload = _build_level_variable_payload_from_registry_decl(dct, owner=owner, registry_path=registry_path)

        vid_cf = str(payload["variable_id"]).casefold()
        if vid_cf in payloads_by_id:
            raise ValueError(f"{registry_path}: 重复的 variable_id：{payload['variable_id']!r}")
        payloads_by_id[vid_cf] = dict(payload)

        name_cf = str(payload["variable_name"]).casefold()
        existing = payloads_by_owner_and_name.get(owner, {}).get(name_cf)
        if existing is not None:
            raise ValueError(
                f"{registry_path}: 同一 owner 下 variable_name 重复：{payload['variable_name']!r}"
                f"（existing_id={existing.get('variable_id')!r} new_id={payload.get('variable_id')!r}）"
            )
        payloads_by_owner_and_name.setdefault(owner, {})[name_cf] = dict(payload)

    return AutoCustomVariableRegistryIndex(
        registry_path=Path(registry_path),
        payloads_by_owner_and_name={k: dict(v) for k, v in payloads_by_owner_and_name.items()},
        payloads_by_id=dict(payloads_by_id),
    )


__all__ = [
    "OWNER_LEVEL",
    "OWNER_PLAYER",
    "AutoCustomVariableRegistryIndex",
    "try_load_auto_custom_variable_registry_index_from_project_root",
]

