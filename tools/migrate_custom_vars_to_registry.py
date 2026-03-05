from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from engine.resources.level_variable_source_extractor import try_extract_variable_file_header_and_entries_from_code


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _is_player_oriented_variable_file(*, file_id: str, file_name: str, py_path: Path) -> bool:
    hay = " ".join([file_id, file_name, py_path.name, py_path.stem]).casefold()
    keywords = [
        "player_template",
        "ui_player",
        "玩家模板",
        "玩家变量",
        "玩家",
    ]
    return any(k.casefold() in hay for k in keywords)


def _infer_owner_for_variable_file(*, file_id: str, file_name: str, py_path: Path) -> str:
    return "player" if _is_player_oriented_variable_file(file_id=file_id, file_name=file_name, py_path=py_path) else "level"


def _infer_ui_visible(*, variable_name: str, metadata: dict[str, Any]) -> bool:
    if str(variable_name).strip().startswith("UI"):
        return True
    if any(k in metadata for k in ["ui_defaults_managed_keys", "ui_defaults", "ui_key", "ui_category"]):
        return True
    return False


def _stable_file_id_for(*, package_id: str, owner: str) -> str:
    pkg = str(package_id).strip()
    scope = str(owner).strip().lower()
    return f"auto_custom_vars__{scope}__{pkg}"


def _replace_strings_in_json(value: Any, *, mapping: dict[str, str]) -> Any:
    if isinstance(value, str):
        return mapping.get(value, value)
    if isinstance(value, list):
        return [_replace_strings_in_json(x, mapping=mapping) for x in value]
    if isinstance(value, dict):
        return {k: _replace_strings_in_json(v, mapping=mapping) for k, v in value.items()}
    return value


def _render_py_literal(value: Any) -> str:
    if isinstance(value, str):
        return repr(value)
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_render_py_literal(x) for x in value) + "]"
    if isinstance(value, tuple):
        inner = ", ".join(_render_py_literal(x) for x in value)
        return f"({inner},)" if len(value) == 1 else f"({inner})"
    if isinstance(value, dict):
        items = ", ".join(f"{_render_py_literal(k)}: {_render_py_literal(v)}" for k, v in value.items())
        return "{" + items + "}"
    raise TypeError(f"无法渲染为 Python 字面量：{type(value).__name__}")


def _render_declaration(*, decl: dict[str, Any]) -> str:
    keys = [
        "variable_id",
        "variable_name",
        "variable_type",
        "default_value",
        "description",
        "owner",
        "category",
    ]
    parts: list[str] = []
    for k in keys:
        if k not in decl:
            continue
        v = decl[k]
        if k in {"category"} and _normalize_text(v) == "":
            continue
        parts.append(f"        {k}={_render_py_literal(v)},")
    body = "\n".join(parts)
    return "    AutoCustomVariableDeclaration(\n" + body + "\n    ),"


def _write_registry_file(*, registry_path: Path, package_id: str, declarations: list[dict[str, Any]]) -> None:
    lines: list[str] = [
        "from __future__ import annotations",
        "",
        "from engine.resources.auto_custom_variable_registry import (",
        "    AutoCustomVariableDeclaration,",
        ")",
        "",
        f'# 本文件：自定义变量“统一声明入口”（{package_id}）。',
        "# - 不执行运行期逻辑；仅做静态声明。",
        "# - owner：直接填实体/元件 ID 或 player/level（支持列表形式的多 owner）。",
        "",
        "CUSTOM_VARIABLE_DECLARATIONS: list[AutoCustomVariableDeclaration] = [",
    ]
    for decl in declarations:
        lines.append(_render_declaration(decl=decl))
    lines.append("]")
    lines.append("")
    registry_path.write_text("\n".join(lines), encoding="utf-8")


def _build_declarations_from_variable_file_entries(
    *,
    package_id: str,
    file_owner: str,
    entries: list[dict],
    py_path: Path,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in list(entries or []):
        if not isinstance(entry, dict):
            raise TypeError(f"无效 LEVEL_VARIABLES 条目类型：{type(entry).__name__}（{py_path}）")

        variable_id = _normalize_text(entry.get("variable_id"))
        variable_name = _normalize_text(entry.get("variable_name"))
        variable_type = _normalize_text(entry.get("variable_type"))
        if variable_id == "" or variable_name == "" or variable_type == "":
            raise ValueError(f"关卡变量条目缺少必要字段：variable_id/name/type（{py_path}）")

        meta_raw = entry.get("metadata", {})
        if meta_raw is None:
            meta_raw = {}
        if not isinstance(meta_raw, dict):
            raise TypeError(f"metadata 必须为 dict：variable_id={variable_id!r}（{py_path}）")
        meta: dict[str, Any] = dict(meta_raw)

        category = _normalize_text(meta.pop("category", ""))
        decl_owner = str(file_owner).strip().lower()
        if decl_owner not in {"player", "level"}:
            raise ValueError(f"不支持的 file_owner：{decl_owner!r}（{py_path}）")

        out.append(
            {
                "variable_id": variable_id,
                "variable_name": variable_name,
                "variable_type": variable_type,
                "default_value": entry.get("default_value", None),
                "description": _normalize_text(entry.get("description", "")),
                "owner": decl_owner,
                "category": category,
                # 说明：旧变量文件的 is_global 概念未纳入 registry 声明；如未来需要可升级为一等字段。
            }
        )
    return out


def _update_json_references(*, package_root: Path, mapping: dict[str, str]) -> list[Path]:
    changed: list[Path] = []
    for json_path in sorted(package_root.rglob("*.json"), key=lambda p: p.as_posix().casefold()):
        if not json_path.is_file():
            continue
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        new_payload = _replace_strings_in_json(payload, mapping=mapping)
        if new_payload == payload:
            continue
        json_path.write_text(json.dumps(new_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changed.append(json_path)
    return changed


def _ensure_claude_md(*, base_dir: Path) -> None:
    claude = (base_dir / "claude.md").resolve()
    if claude.is_file():
        return
    claude.write_text(
        "\n".join(
            [
                "## 目录用途",
                "关卡变量（Level Variables）代码资源根：以 `自定义变量注册表.py` 为单文件真源，Schema 从注册表派生虚拟变量文件。",
                "",
                "## 当前状态",
                "- 当项目存档存在 `自定义变量注册表.py` 时：禁止在 `自定义变量/` 下维护散落变量文件（校验会 fail-fast）。",
                "- 局内存档变量仍位于 `自定义变量-局内存档变量/`（不在本次收敛范围内）。",
                "",
                "## 注意事项",
                "- 只修改 `自定义变量注册表.py` 来新增/调整自定义变量声明；不要新增 `自定义变量/*.py`。",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _overwrite_custom_dir_claude_md(*, custom_dir: Path, package_id: str) -> None:
    claude = (custom_dir / "claude.md").resolve()
    if not claude.parent.is_dir():
        return
    claude.write_text(
        "\n".join(
            [
                "## 目录用途",
                "历史目录：曾存放项目自定义变量的散落变量文件。",
                "当前仓库已统一收敛为 `自定义变量注册表.py` 单文件真源，本目录应保持为空。",
                "",
                "## 当前状态",
                f"- `{package_id}`：自定义变量全部在 `../自定义变量注册表.py` 声明。",
                "- 本目录下若存在任意 `.py`，`validate-project/validate-file` 将 fail-fast（禁止多处真源）。",
                "",
                "## 注意事项",
                "- 禁止在本目录新增/修改变量文件；请只修改 `自定义变量注册表.py`。",
                "",
            ]
        ),
        encoding="utf-8",
    )


def migrate_one_package(*, repo_root: Path, package_id: str, apply: bool) -> None:
    pkg = str(package_id).strip()
    if pkg == "":
        raise ValueError("package_id 不能为空")

    package_root = (repo_root / "assets" / "资源库" / "项目存档" / pkg).resolve()
    base_dir = (package_root / "管理配置" / "关卡变量").resolve()
    if not base_dir.is_dir():
        raise FileNotFoundError(str(base_dir))

    custom_dir = (base_dir / "自定义变量").resolve()
    if not custom_dir.is_dir():
        custom_dir.mkdir(parents=True, exist_ok=True)

    registry_path = (base_dir / "自定义变量注册表.py").resolve()
    if registry_path.is_file():
        raise ValueError(f"注册表已存在（为避免覆盖请先手工处理）：{registry_path}")

    py_paths_all = sorted((p for p in custom_dir.rglob("*.py") if p.is_file()), key=lambda p: p.as_posix().casefold())
    # 派生/自动生成变量文件不是“真源”，不迁入注册表；但仍会在 apply 模式下删除，以保持目录为空。
    py_paths: list[Path] = []
    skipped_py_paths: list[Path] = []
    for p in py_paths_all:
        stem = str(p.stem or "").strip()
        if stem.startswith("自动分配_") or ("自动生成" in stem):
            skipped_py_paths.append(p)
            continue
        py_paths.append(p)
    old_file_ids: list[str] = []
    mapping: dict[str, str] = {}
    decls: list[dict[str, Any]] = []
    seen_vid: set[str] = set()

    for py_path in py_paths:
        file_id, file_name, entries = try_extract_variable_file_header_and_entries_from_code(py_path)
        if not isinstance(file_id, str) or file_id.strip() == "":
            continue
        if entries is None:
            raise ValueError(f"变量文件无法静态提取 LEVEL_VARIABLES（请改为常量写法）：{py_path}")
        file_id_text = str(file_id).strip()
        file_name_text = _normalize_text(file_name) or py_path.stem

        owner = _infer_owner_for_variable_file(file_id=file_id_text, file_name=file_name_text, py_path=py_path)
        new_file_id = _stable_file_id_for(package_id=pkg, owner=owner)
        old_file_ids.append(file_id_text)
        mapping[file_id_text] = new_file_id

        items = _build_declarations_from_variable_file_entries(
            package_id=pkg,
            file_owner=owner,
            entries=list(entries),
            py_path=py_path,
        )
        for d in items:
            vid = str(d.get("variable_id") or "").strip()
            if vid in seen_vid:
                raise ValueError(f"重复的 variable_id（跨文件冲突）：{vid!r}（file={py_path}）")
            seen_vid.add(vid)
            decls.append(d)

    if not decls:
        # 允许空 registry：用于“先落规则，再逐步补齐变量声明”的迁移过程
        decls = []

    if not apply:
        _write_registry_file(registry_path=registry_path, package_id=pkg, declarations=decls)
        return

    _ensure_claude_md(base_dir=base_dir)
    _write_registry_file(registry_path=registry_path, package_id=pkg, declarations=decls)
    _overwrite_custom_dir_claude_md(custom_dir=custom_dir, package_id=pkg)

    _update_json_references(package_root=package_root, mapping=mapping)

    for py_path in (py_paths + skipped_py_paths):
        py_path.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="将项目存档的 `管理配置/关卡变量/自定义变量/*.py` 迁移到 `自定义变量注册表.py`（单文件真源），并删除散落变量文件。",
    )
    parser.add_argument("--package-id", required=True, help="项目存档包名（assets/资源库/项目存档/<package_id>）。")
    parser.add_argument("--apply", action="store_true", help="写盘并删除散落变量文件（默认不写盘）。")
    args = parser.parse_args(list(argv) if argv is not None else None)

    repo_root = Path(__file__).resolve().parents[1]
    migrate_one_package(repo_root=repo_root, package_id=str(args.package_id), apply=bool(args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

