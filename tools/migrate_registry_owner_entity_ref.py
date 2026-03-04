from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_REGISTRY_FILENAME = "自定义变量注册表.py"
_ALLOWED_METADATA_KEYS = {"sources"}


@dataclass(frozen=True, slots=True)
class Change:
    path: Path
    changed: bool
    summary: str


def _iter_registry_paths(workspace_root: Path) -> list[Path]:
    root = Path(workspace_root).resolve()
    base = (root / "assets" / "资源库" / "项目存档").resolve()
    if not base.is_dir():
        raise FileNotFoundError(str(base))
    out: list[Path] = []
    for p in base.rglob(_REGISTRY_FILENAME):
        if p.is_file() and p.parent.name == "关卡变量":
            out.append(p.resolve())
    out.sort(key=lambda x: x.as_posix().casefold())
    return out


def _parse_string_literal(expr: str, *, path: Path, key: str) -> str:
    try:
        value = ast.literal_eval(expr)
    except Exception as e:
        raise ValueError(f"{path}: 无法解析 {key} 字符串字面量：{expr!r}") from e
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: {key} 必须为非空字符串字面量：{expr!r}")
    return value.strip()


def _should_keep_metadata_line(expr: str, *, path: Path) -> bool:
    try:
        value = ast.literal_eval(expr)
    except Exception as e:
        raise ValueError(f"{path}: metadata 必须为可静态解析的 dict 字面量：{expr!r}") from e
    if not isinstance(value, dict):
        raise ValueError(f"{path}: metadata 必须为 dict 字面量：{expr!r}")
    if not value:
        return False
    unknown = sorted([str(k) for k in value.keys() if str(k) not in _ALLOWED_METADATA_KEYS])
    if unknown:
        return False
    sources = value.get("sources", None)
    if sources is None:
        return False
    if not isinstance(sources, list) or any((not isinstance(x, str)) or (not x.strip()) for x in sources):
        raise ValueError(f"{path}: metadata['sources'] 必须为非空字符串列表。")
    return True


def _rewrite_declaration_block(block: list[str], *, path: Path) -> tuple[list[str], list[str]]:
    owner_value: str | None = None
    owner_line_idx: int | None = None
    data_store_key_value: str | None = None
    data_store_key_line_idx: int | None = None

    def _extract_rhs(line: str, key: str) -> str:
        # expects: "    key=<expr>,"
        stripped = line.strip()
        if not stripped.startswith(f"{key}=") or not stripped.endswith(","):
            raise ValueError(f"{path}: 无法解析声明行：{line!r}")
        return stripped[len(f"{key}=") :].rstrip(",").strip()

    for idx, line in enumerate(block):
        stripped = line.strip()
        if stripped.startswith("owner="):
            owner_value = _parse_string_literal(_extract_rhs(line, "owner"), path=path, key="owner")
            owner_line_idx = idx
        if stripped.startswith("data_store_key="):
            data_store_key_value = _parse_string_literal(
                _extract_rhs(line, "data_store_key"),
                path=path,
                key="data_store_key",
            )
            data_store_key_line_idx = idx

    notes: list[str] = []
    out: list[str] = []
    for idx, line in enumerate(block):
        stripped = line.strip()

        if stripped.startswith(("per_player=", "ui_visible=", "frontend_read=")):
            notes.append(f"drop:{stripped.split('=',1)[0]}")
            continue

        if stripped.startswith("data_store_key="):
            notes.append("drop:data_store_key")
            continue

        if stripped.startswith("metadata="):
            rhs = _extract_rhs(line, "metadata")
            if _should_keep_metadata_line(rhs, path=path):
                out.append(line)
                continue
            notes.append("drop:metadata")
            continue

        if stripped.startswith("owner="):
            if owner_value is None:
                raise ValueError(f"{path}: 声明缺少 owner")
            if owner_value.lower() == "data":
                if not data_store_key_value:
                    raise ValueError(f"{path}: owner='data' 但缺少 data_store_key（需迁移为 owner='data:<store_key>'）")
                if data_store_key_value != data_store_key_value.lower():
                    raise ValueError(f"{path}: data_store_key 必须为小写：{data_store_key_value!r}")
                if any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_" for ch in data_store_key_value):
                    raise ValueError(f"{path}: data_store_key 不合法：{data_store_key_value!r}（仅允许 [a-z0-9_]）")
                indent = line[: len(line) - len(line.lstrip(" "))]
                out.append(f'{indent}owner="data:{data_store_key_value}",\n')
                notes.append("owner:data->data:<store_key>")
                continue
            out.append(line)
            continue

        out.append(line)

    if owner_value is not None and owner_value.lower() != "data" and data_store_key_value is not None:
        # 只有 owner=data 才允许出现 data_store_key
        raise ValueError(
            f"{path}: 发现 data_store_key 但 owner != 'data'（owner={owner_value!r}, data_store_key={data_store_key_value!r}）"
        )

    return out, notes


def _rewrite_registry_text(text: str, *, path: Path) -> tuple[str, list[str]]:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    notes: list[str] = []

    in_decl = False
    block_indent = ""
    block: list[str] = []

    for line in lines:
        if not in_decl and "AutoCustomVariableDeclaration(" in line:
            in_decl = True
            block_indent = line[: len(line) - len(line.lstrip(" "))]
            block = [line]
            continue

        if in_decl:
            block.append(line)
            if line.startswith(block_indent) and line.strip() == "),":
                rewritten, n = _rewrite_declaration_block(block, path=path)
                out.extend(rewritten)
                notes.extend(n)
                in_decl = False
                block_indent = ""
                block = []
            continue

        out.append(line)

    if in_decl:
        raise ValueError(f"{path}: AutoCustomVariableDeclaration(...) 块未正常闭合")

    return "".join(out), notes


def migrate_one(*, registry_path: Path, apply: bool) -> Change:
    path = Path(registry_path).resolve()
    before = path.read_text(encoding="utf-8")
    after, notes = _rewrite_registry_text(before, path=path)
    changed = after != before
    summary = "no-op" if not changed else f"updated ({', '.join(sorted(set(notes)))})"
    if apply and changed:
        path.write_text(after, encoding="utf-8")
    return Change(path=path, changed=changed, summary=summary)


def migrate_all(*, workspace_root: Path, apply: bool) -> list[Change]:
    changes: list[Change] = []
    for p in _iter_registry_paths(workspace_root):
        changes.append(migrate_one(registry_path=p, apply=apply))
    return changes


def _format_changes(changes: Iterable[Change]) -> str:
    lines: list[str] = []
    for c in changes:
        flag = "CHANGED" if c.changed else "OK"
        lines.append(f"- [{flag}] {c.path.as_posix()} :: {c.summary}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="migrate registry owner to entity ref (data:<store_key>)")
    parser.add_argument("--workspace-root", default=".", help="repo/workspace root")
    parser.add_argument("--apply", action="store_true", help="write changes to disk")
    args = parser.parse_args(argv)

    workspace_root = Path(str(getattr(args, "workspace_root", ".") or ".")).resolve()
    apply = bool(getattr(args, "apply", False))

    changes = migrate_all(workspace_root=workspace_root, apply=apply)
    changed = [c for c in changes if c.changed]

    print("=" * 80)
    print("migrate_registry_owner_entity_ref")
    print(f"- workspace_root: {workspace_root}")
    print(f"- apply: {apply}")
    print(f"- total: {len(changes)}")
    print(f"- changed: {len(changed)}")
    print("=" * 80)
    print(_format_changes(changes))
    print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

