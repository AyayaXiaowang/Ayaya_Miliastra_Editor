from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Any, Iterable


def _is_level_variable_definition_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = getattr(node, "func", None)
    if isinstance(func, ast.Name) and func.id == "LevelVariableDefinition":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "LevelVariableDefinition":
        return True
    return False


def _extract_constant(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Dict):
        out: dict[Any, Any] = {}
        for k, v in zip(list(node.keys), list(node.values)):
            if k is None or v is None:
                raise ValueError("dict 不支持展开/空 key")
            key = _extract_constant(k)
            out[key] = _extract_constant(v)
        return out
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_extract_constant(x) for x in list(node.elts)]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
        if isinstance(node.operand.value, (int, float)):
            return -node.operand.value
    raise ValueError(f"不支持的常量表达式：{type(node).__name__}")


def _extract_module_string_constant(tree: ast.Module, name: str) -> str | None:
    for stmt in list(getattr(tree, "body", []) or []):
        if not isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            continue
        targets: list[ast.AST] = []
        if isinstance(stmt, ast.Assign):
            targets = list(getattr(stmt, "targets", []) or [])
            value = getattr(stmt, "value", None)
        else:
            targets = [getattr(stmt, "target", None)]
            value = getattr(stmt, "value", None)
        if value is None:
            continue
        for t in targets:
            if isinstance(t, ast.Name) and t.id == name:
                v = _extract_constant(value)
                if not isinstance(v, str) or not v.strip():
                    raise ValueError(f"{name} 必须为非空字符串常量")
                return v.strip()
    return None


def _extract_level_variables_expr(tree: ast.Module) -> ast.AST | None:
    for stmt in list(getattr(tree, "body", []) or []):
        if not isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            continue
        targets: list[ast.AST] = []
        if isinstance(stmt, ast.Assign):
            targets = list(getattr(stmt, "targets", []) or [])
            value = getattr(stmt, "value", None)
        else:
            targets = [getattr(stmt, "target", None)]
            value = getattr(stmt, "value", None)
        if value is None:
            continue
        if any(isinstance(t, ast.Name) and t.id == "LEVEL_VARIABLES" for t in targets):
            return value
    return None


def _build_dict_payload_from_level_variable_definition_call(node: ast.Call) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "variable_id": "",
        "variable_name": "",
        "variable_type": "",
        "default_value": None,
        "is_global": True,
        "description": "",
        "metadata": {},
    }
    for kw in list(getattr(node, "keywords", []) or []):
        key = getattr(kw, "arg", None)
        if key is None:
            raise ValueError("LevelVariableDefinition(...) 不支持 **kwargs（无法迁移 owner）")
        payload[key] = _extract_constant(getattr(kw, "value", None))
    return dict(payload)


def _normalize_one_level_variable_payload(
    payload: dict[str, Any],
    *,
    default_owner: str | None,
    py_path: Path,
) -> dict[str, Any]:
    vid = str(payload.get("variable_id") or "").strip()
    vname = str(payload.get("variable_name") or "").strip()
    vtype = str(payload.get("variable_type") or "").strip()
    if vid == "" or vname == "" or vtype == "":
        raise ValueError(f"无效的关卡变量条目（缺少 id/name/type）：{vid!r}/{vname!r}/{vtype!r}（{py_path}）")

    meta_raw = payload.get("metadata", {})
    if meta_raw is None:
        meta_raw = {}
    if not isinstance(meta_raw, dict):
        raise TypeError(f"metadata 必须为 dict：variable_id={vid!r}（{py_path}）")
    meta: dict[str, Any] = dict(meta_raw)

    owner_raw = str(payload.get("owner") or "").strip().lower()
    auto_owner_raw = str(meta.get("auto_owner") or "").strip().lower()

    if owner_raw == "":
        if auto_owner_raw != "":
            owner_raw = auto_owner_raw
        elif default_owner is not None:
            owner_raw = str(default_owner).strip().lower()
        else:
            raise ValueError(
                "关卡变量缺少 owner（且无 metadata.auto_owner 可迁移）："
                f"variable_id={vid!r}, variable_name={vname!r}（{py_path}）。"
                "请对该文件显式指定 --default-owner level|player|data 后再 --apply。"
            )

    if owner_raw not in {"level", "player", "data"}:
        raise ValueError(
            "关卡变量 owner 值域非法（仅支持 level/player/data）："
            f"variable_id={vid!r}, variable_name={vname!r}, owner={owner_raw!r}（{py_path}）"
        )

    if auto_owner_raw != "" and auto_owner_raw != owner_raw:
        raise ValueError(
            "关卡变量 owner 与 metadata.auto_owner 冲突："
            f"variable_id={vid!r}, variable_name={vname!r}, owner={owner_raw!r}, auto_owner={auto_owner_raw!r}（{py_path}）"
        )

    if "auto_owner" in meta:
        meta.pop("auto_owner", None)

    out: dict[str, Any] = {
        "variable_id": vid,
        "variable_name": vname,
        "variable_type": vtype,
        "owner": owner_raw,
        "default_value": payload.get("default_value", None),
        "is_global": bool(payload.get("is_global", True)),
        "description": str(payload.get("description") or ""),
        "metadata": meta,
    }
    return out


def _format_python_literal(value: Any, *, indent: int) -> str:
    pad = " " * indent
    if isinstance(value, str):
        return repr(value)
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        if not value:
            return "[]"
        inner = ",\n".join(f"{pad}    {_format_python_literal(v, indent=indent + 4)}" for v in value)
        return "[\n" + inner + f",\n{pad}]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = []
        for k, v in value.items():
            key_text = _format_python_literal(k, indent=indent + 4)
            val_text = _format_python_literal(v, indent=indent + 4)
            items.append(f"{pad}    {key_text}: {val_text}")
        return "{\n" + ",\n".join(items) + f",\n{pad}}}"
    raise TypeError(f"不支持的字面量类型：{type(value).__name__}")


def _render_variable_file(*, file_id: str, file_name: str, variables: list[dict[str, Any]]) -> str:
    lines: list[str] = [
        "from __future__ import annotations",
        "",
        f"VARIABLE_FILE_ID = {_format_python_literal(file_id, indent=0)}",
        f"VARIABLE_FILE_NAME = {_format_python_literal(file_name, indent=0)}",
        "",
        "LEVEL_VARIABLES: list[dict] = [",
    ]
    for payload in variables:
        lines.append(f"    {_format_python_literal(payload, indent=4)},")
    lines.append("]")
    lines.append("")
    return "\n".join(lines)


def _iter_target_py_files(*, base_dir: Path) -> Iterable[Path]:
    for p in sorted(base_dir.rglob("*.py"), key=lambda x: x.as_posix().casefold()):
        if p.is_file():
            yield p


def _process_one_py_file(*, py_path: Path, default_owner: str | None, apply: bool) -> bool:
    source = py_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(py_path))

    file_id = _extract_module_string_constant(tree, "VARIABLE_FILE_ID")
    file_name = _extract_module_string_constant(tree, "VARIABLE_FILE_NAME") or py_path.stem
    if not file_id:
        return False

    lv_expr = _extract_level_variables_expr(tree)
    if lv_expr is None:
        return False

    if not isinstance(lv_expr, (ast.List, ast.Tuple)):
        raise ValueError(f"LEVEL_VARIABLES 必须为 list literal（{py_path}）")

    normalized: list[dict[str, Any]] = []
    for elt in list(lv_expr.elts):
        if isinstance(elt, ast.Dict):
            raw = _extract_constant(elt)
            if not isinstance(raw, dict):
                raise ValueError(f"LEVEL_VARIABLES 条目必须为 dict（{py_path}）")
            payload = dict(raw)
        elif _is_level_variable_definition_call(elt):
            payload = _build_dict_payload_from_level_variable_definition_call(elt)  # type: ignore[arg-type]
        else:
            raise ValueError(f"LEVEL_VARIABLES 条目不支持（仅支持 dict / LevelVariableDefinition(...)）：{py_path}")

        normalized.append(_normalize_one_level_variable_payload(payload, default_owner=default_owner, py_path=py_path))

    if not apply:
        return True

    new_text = _render_variable_file(file_id=str(file_id), file_name=str(file_name), variables=normalized)
    py_path.write_text(new_text, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="一次性迁移关卡变量文件：补齐 payload.owner，并移除 metadata.auto_owner。")
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        help="仅处理指定文件（可重复传入；相对路径以仓库根目录解析）。",
    )
    parser.add_argument("--package-id", default="", help="仅处理指定项目存档（assets/资源库/项目存档/<package_id>/...）。")
    parser.add_argument(
        "--default-owner",
        default="",
        help="当条目缺失 owner 且无 metadata.auto_owner 时，使用该 owner（level|player|data）。",
    )
    parser.add_argument("--apply", action="store_true", help="写回修改（默认只校验并输出问题）。")
    args = parser.parse_args(list(argv) if argv is not None else None)

    repo_root = Path(__file__).resolve().parents[1]
    explicit_files = [str(x).strip() for x in list(args.file or []) if str(x).strip() != ""]
    if explicit_files:
        target_files = [Path(repo_root / x).resolve() for x in explicit_files]
        base_dir = repo_root
    elif str(args.package_id or "").strip():
        base_dir = (
            repo_root
            / "assets"
            / "资源库"
            / "项目存档"
            / str(args.package_id).strip()
            / "管理配置"
            / "关卡变量"
        ).resolve()
        target_files = list(_iter_target_py_files(base_dir=base_dir))
    else:
        base_dir = (repo_root / "assets" / "资源库" / "项目存档").resolve()
        target_files = list(_iter_target_py_files(base_dir=base_dir))

    default_owner = str(args.default_owner or "").strip().lower() or None
    if default_owner is not None and default_owner not in {"level", "player", "data"}:
        raise ValueError("--default-owner 仅支持 level|player|data")

    processed = 0
    changed_or_validated = 0
    failed = 0
    for py_path in target_files:
        processed += 1
        try:
            ok = _process_one_py_file(py_path=py_path, default_owner=default_owner, apply=bool(args.apply))
            if ok:
                changed_or_validated += 1
        except Exception as e:
            failed += 1
            print(f"[FAIL] {py_path}: {e}", file=sys.stderr)

    if failed:
        return 1
    if changed_or_validated == 0:
        print(f"[WARN] 未发现可处理的关卡变量文件：base_dir={base_dir}")
    else:
        mode = "apply" if bool(args.apply) else "check"
        print(f"[OK] mode={mode} processed={processed} migrated_or_checked={changed_or_validated} base_dir={base_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

