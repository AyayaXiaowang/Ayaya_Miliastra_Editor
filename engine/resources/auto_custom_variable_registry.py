from __future__ import annotations

import ast
import tokenize
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from engine.graph.utils.ast_utils import (
    NOT_EXTRACTABLE,
    clear_module_constants_context,
    collect_module_constants,
    extract_constant_value,
    set_module_constants_context,
)

OWNER_KEYWORDS: frozenset[str] = frozenset({"player", "level"})

_REGISTRY_DECL_FIELDS_ORDERED: list[str] = [
    "variable_id",
    "variable_name",
    "variable_type",
    "default_value",
    "description",
    "owner",
    "category",
    "metadata",
]

_REGISTRY_DECL_FIELDS_ALLOWED: set[str] = set(_REGISTRY_DECL_FIELDS_ORDERED)

_REGISTRY_DECL_METADATA_ALLOWED_KEYS: set[str] = {
    "sources",
}


def normalize_owner_refs(owner: object) -> list[str]:
    """将 owner 字段值归一化为 list[str]。支持 str 或 list[str]。"""
    if isinstance(owner, str):
        s = owner.strip()
        if not s:
            raise ValueError("owner 不能为空")
        return [s]
    if isinstance(owner, list):
        out: list[str] = []
        for item in owner:
            s = str(item).strip()
            if not s:
                raise ValueError("owner 列表中存在空值")
            out.append(s)
        if not out:
            raise ValueError("owner 列表不能为空")
        return out
    raise TypeError(f"owner 类型不支持：{type(owner).__name__}（允许 str 或 list[str]）")


def validate_owner_ref(ref: str, *, registry_path: Path) -> None:
    """校验单个 owner 引用值（关键字或实体/元件 ID）。"""
    lower = ref.lower().strip()
    if lower == "auto":
        raise ValueError(
            f"{registry_path}: owner='auto' 已禁止；请显式填写实体/元件 ID 或 player/level。"
        )
    if lower == "data" or lower.startswith("data:"):
        raise ValueError(
            f"{registry_path}: owner='{ref}' 已禁止（data: 间接引用已废弃）；"
            "请直接填写实体 instance_id 或元件 template_id。"
        )


def _validate_registry_decl_metadata(
    meta: dict[str, Any], *, registry_path: Path, variable_name: str,
) -> None:
    unknown = sorted(k for k in meta if str(k) not in _REGISTRY_DECL_METADATA_ALLOWED_KEYS)
    if unknown:
        raise ValueError(
            f"{registry_path}: 变量 {variable_name!r} 的 metadata 存在未允许的 keys：{unknown}；"
            f"允许 keys：{sorted(_REGISTRY_DECL_METADATA_ALLOWED_KEYS)}"
        )
    sources = meta.get("sources")
    if sources is None:
        return
    if not isinstance(sources, list) or any((not isinstance(x, str)) or (not x.strip()) for x in sources):
        raise ValueError(
            f"{registry_path}: 变量 {variable_name!r} 的 metadata['sources'] 必须为非空字符串列表。"
        )


@dataclass(frozen=True, slots=True)
class AutoCustomVariableDeclaration:
    """自定义变量注册表单条声明。

    owner: str | list[str]
      - "player" / "level" — 广播关键字
      - instance_id / template_id — 直接引用实体/元件
      - 列表形式表示多 owner
    """

    variable_name: str
    variable_type: str
    default_value: Any = None
    description: str = ""
    variable_id: str = ""
    owner: str | list[str] = ""
    category: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def _find_module_assignment_value(tree: ast.Module, name: str) -> ast.expr | None:
    want = str(name or "").strip()
    if not want:
        return None
    for stmt in list(getattr(tree, "body", []) or []):
        if isinstance(stmt, ast.Assign):
            for target in list(getattr(stmt, "targets", []) or []):
                if isinstance(target, ast.Name) and target.id == want:
                    return stmt.value
        elif isinstance(stmt, ast.AnnAssign):
            target = getattr(stmt, "target", None)
            if isinstance(target, ast.Name) and target.id == want:
                return getattr(stmt, "value", None)
    return None


def _resolve_name_alias(tree: ast.Module, expr: ast.expr, *, max_depth: int = 6) -> ast.expr:
    current = expr
    seen: set[str] = set()
    for _ in range(int(max_depth)):
        if not isinstance(current, ast.Name):
            return current
        name = str(getattr(current, "id", "") or "").strip()
        if not name or name in seen:
            return current
        seen.add(name)
        next_expr = _find_module_assignment_value(tree, name)
        if next_expr is None:
            return current
        current = next_expr
    return current


def _try_extract_declaration_from_ast(node: ast.expr) -> dict | None:
    if isinstance(node, ast.Dict):
        raise ValueError("注册表声明禁止使用 dict 写法；请使用 AutoCustomVariableDeclaration(...)。")
    if not isinstance(node, ast.Call):
        return None
    func = getattr(node, "func", None)
    is_call = (
        (isinstance(func, ast.Name) and func.id == "AutoCustomVariableDeclaration")
        or (isinstance(func, ast.Attribute) and func.attr == "AutoCustomVariableDeclaration")
    )
    if not is_call:
        return None
    payload: dict[str, object] = {
        "variable_id": "", "variable_name": "", "variable_type": "",
        "default_value": None, "description": "", "owner": "",
        "category": "", "metadata": {},
    }
    for idx, arg_node in enumerate(list(getattr(node, "args", []) or [])):
        if idx >= len(_REGISTRY_DECL_FIELDS_ORDERED):
            raise ValueError("位置参数数量超出允许范围；请改用关键字参数。")
        extracted = extract_constant_value(arg_node)
        if extracted is NOT_EXTRACTABLE:
            raise ValueError(f"字段 {_REGISTRY_DECL_FIELDS_ORDERED[idx]!r} 必须为可静态解析的常量。")
        payload[_REGISTRY_DECL_FIELDS_ORDERED[idx]] = extracted
    for kw in list(getattr(node, "keywords", []) or []):
        key = getattr(kw, "arg", None)
        if key is None:
            raise ValueError("禁止使用 **kwargs。")
        name = str(key).strip()
        if name not in _REGISTRY_DECL_FIELDS_ALLOWED:
            raise ValueError(f"未知字段 {name!r}；允许：{sorted(_REGISTRY_DECL_FIELDS_ALLOWED)}")
        extracted = extract_constant_value(getattr(kw, "value", None))
        if extracted is NOT_EXTRACTABLE:
            raise ValueError(f"字段 {name!r} 必须为可静态解析的常量。")
        payload[name] = extracted
    meta = payload.get("metadata")
    if not isinstance(meta, dict):
        payload["metadata"] = {}
    return dict(payload)


def extract_auto_custom_variable_declarations_from_code(py_path: Path) -> list[dict]:
    """从注册表文件静态提取声明列表（不执行代码）。"""
    path = Path(py_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    with tokenize.open(str(path)) as f:
        source_text = f.read()
    tree = ast.parse(source_text, filename=str(path))
    constants = collect_module_constants(tree)
    set_module_constants_context(constants)
    candidates = [
        "CUSTOM_VARIABLE_DECLARATIONS", "AUTO_CUSTOM_VARIABLE_DECLARATIONS",
        "AUTO_CUSTOM_VARIABLES", "DECLARATIONS",
    ]
    decl_expr: ast.expr | None = None
    decl_name = ""
    for name in candidates:
        expr = _find_module_assignment_value(tree, name)
        if expr is None:
            continue
        decl_expr = _resolve_name_alias(tree, expr)
        decl_name = name
        break
    if decl_expr is None:
        clear_module_constants_context()
        raise ValueError(f"{path}: 未导出声明列表（请定义 {candidates[0]}: list[...]）。")
    if not isinstance(decl_expr, (ast.List, ast.Tuple)):
        clear_module_constants_context()
        raise ValueError(f"{path}: {decl_name} 必须为 list[...]。")
    items: list[dict] = []
    for elt in list(getattr(decl_expr, "elts", []) or []):
        try:
            item = _try_extract_declaration_from_ast(elt)
        except Exception as e:
            clear_module_constants_context()
            raise ValueError(f"{path}: {decl_name} 声明不合法：{e}") from e
        if not isinstance(item, dict):
            clear_module_constants_context()
            raise ValueError(f"{path}: 声明必须为 AutoCustomVariableDeclaration(...) 常量写法。")
        items.append(item)
    clear_module_constants_context()
    return items


def load_auto_custom_variable_registry_from_code(
    py_path: Path,
) -> list[AutoCustomVariableDeclaration]:
    """静态加载并校验注册表声明列表（不执行顶层代码）。"""
    items = extract_auto_custom_variable_declarations_from_code(py_path)
    decls = normalize_declarations(items)
    registry_path = Path(py_path).resolve()
    for d in decls:
        name = str(d.variable_name or "").strip()
        vid = str(d.variable_id or "").strip()
        if not vid:
            raise ValueError(f"{registry_path}: 变量 {name!r} 缺少 variable_id。")
        refs = normalize_owner_refs(d.owner)
        for ref in refs:
            validate_owner_ref(ref, registry_path=registry_path)
        meta = d.metadata if isinstance(d.metadata, dict) else {}
        _validate_registry_decl_metadata(meta, registry_path=registry_path, variable_name=name)
    return decls


def crc32_hex(text: str) -> str:
    value = zlib.crc32(str(text).encode("utf-8")) & 0xFFFFFFFF
    return f"{value:08x}"


def stable_variable_id_for(
    package_id: str, *, variable_name: str, prefix: str = "auto",
) -> str:
    pkg = str(package_id or "").strip()
    name = str(variable_name or "").strip()
    digest = crc32_hex(f"{pkg}:{name}")
    return f"{prefix}_{digest}__{pkg}" if pkg else f"{prefix}_{digest}"


def stable_variable_file_id_for(
    package_id: str, *, owner_ref: str, prefix: str = "auto_custom_vars",
) -> str:
    """为 owner 引用生成稳定的虚拟变量文件 ID。"""
    pkg = str(package_id or "").strip()
    ref = str(owner_ref or "").strip()
    ref_lower = ref.lower()
    if ref_lower == "player":
        return f"{prefix}__player__{pkg}" if pkg else f"{prefix}__player"
    if ref_lower == "level":
        return f"{prefix}__level__{pkg}" if pkg else f"{prefix}__level"
    ref_digest = crc32_hex(ref)
    return f"{prefix}__ref__{ref_digest}__{pkg}" if pkg else f"{prefix}__ref__{ref_digest}"


def resolve_owner_refs(decl: AutoCustomVariableDeclaration) -> list[str]:
    """返回声明的全部 owner 引用列表。"""
    return normalize_owner_refs(decl.owner)


def resolve_owner(decl: AutoCustomVariableDeclaration) -> str:
    """向后兼容：返回第一个 owner 引用。多 owner 场景应改用 resolve_owner_refs。"""
    refs = resolve_owner_refs(decl)
    return refs[0] if refs else ""


def normalize_declarations(items: Iterable[object]) -> list[AutoCustomVariableDeclaration]:
    out: list[AutoCustomVariableDeclaration] = []
    for item in list(items or []):
        if isinstance(item, AutoCustomVariableDeclaration):
            out.append(item)
            continue
        if isinstance(item, dict):
            owner_raw = item.get("owner", "")
            if isinstance(owner_raw, list):
                owner_list = [str(x).strip() for x in owner_raw if str(x).strip()]
                owner_val: str | list[str] = owner_list if len(owner_list) != 1 else owner_list[0]
            else:
                owner_val = str(owner_raw or "").strip()
            out.append(AutoCustomVariableDeclaration(
                variable_id=str(item.get("variable_id") or "").strip(),
                variable_name=str(item.get("variable_name") or item.get("name") or "").strip(),
                variable_type=str(item.get("variable_type") or item.get("type") or "").strip(),
                default_value=item.get("default_value", item.get("default")),
                description=str(item.get("description") or "").strip(),
                owner=owner_val,
                category=str(item.get("category") or "").strip(),
                metadata=dict(item.get("metadata") or {}) if isinstance(item.get("metadata"), dict) else {},
            ))
            continue
        raise TypeError(f"无效条目类型：{type(item).__name__}")
    return out


__all__ = [
    "AutoCustomVariableDeclaration",
    "OWNER_KEYWORDS",
    "crc32_hex",
    "extract_auto_custom_variable_declarations_from_code",
    "load_auto_custom_variable_registry_from_code",
    "normalize_declarations",
    "normalize_owner_refs",
    "resolve_owner",
    "resolve_owner_refs",
    "stable_variable_file_id_for",
    "stable_variable_id_for",
    "validate_owner_ref",
]
