from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

from engine.utils.path_utils import normalize_slash
from engine.utils.source_text import read_source_text
from engine.validate.struct_definition_folder_policy import (
    infer_expected_struct_type_from_source_path,
)

from .graph_validation_quickfixes import QuickFixAction

__all__ = [
    "apply_struct_definition_quickfixes",
]


_STRUCT_ID_LINE_RE = re.compile(
    r"^\s*STRUCT_ID\s*(?::\s*[^=]+)?=\s*(?P<quote>['\"])(?P<value>[^'\"]+)(?P=quote)\s*(?:#.*)?$"
)
_STRUCT_TYPE_LINE_RE = re.compile(
    r"^(?P<prefix>\s*STRUCT_TYPE\s*(?::\s*[^=]+)?=\s*)(?P<quote>['\"])(?P<value>[^'\"]*)(?P=quote)(?P<suffix>\s*(?:#.*)?)$",
    flags=re.MULTILINE,
)
_PAYLOAD_STRUCT_TYPE_RE = re.compile(
    r"(?P<prefix>(?P<key_quote>['\"])(?P<key>struct_ype|struct_type)(?P=key_quote)\s*:\s*)"
    r"(?P<quote>['\"])(?P<value>[^'\"]*)(?P=quote)"
)


def _is_reserved_python_file(py_file: Path) -> bool:
    if py_file.parent.name == "__pycache__":
        return True
    if py_file.name.startswith("_"):
        return True
    if "校验" in py_file.stem:
        return True
    return False


def _detect_newline(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    return "\n"


def _relative_path_for_action(file_path: Path, workspace_root: Path) -> str:
    resolved_file = file_path.resolve()
    resolved_workspace = workspace_root.resolve()
    rel = normalize_slash(str(resolved_file))
    ws_prefix = normalize_slash(str(resolved_workspace)) + "/"
    if rel.startswith(ws_prefix):
        return rel[len(ws_prefix) :]
    return normalize_slash(str(file_path))


def _insert_struct_type_constant(original_text: str, *, expected_type: str) -> Tuple[str, bool]:
    newline = _detect_newline(original_text)
    lines = original_text.splitlines(keepends=True)

    struct_id_idx: int | None = None
    for idx, line in enumerate(lines):
        if _STRUCT_ID_LINE_RE.match(line.strip("\r\n")):
            struct_id_idx = idx
            break

    if struct_id_idx is None:
        return original_text, False

    insertion = f'STRUCT_TYPE = "{expected_type}"{newline}'
    lines.insert(struct_id_idx + 1, insertion)
    return "".join(lines), True


def _insert_payload_struct_type(original_text: str, *, expected_type: str) -> Tuple[str, bool]:
    newline = _detect_newline(original_text)
    lines = original_text.splitlines(keepends=True)

    payload_start_idx: int | None = None
    for idx, line in enumerate(lines):
        if "STRUCT_PAYLOAD" in line and "{" in line:
            payload_start_idx = idx
            break
    if payload_start_idx is None:
        return original_text, False

    # 优先插在 type: "Struct" 行之后，保持字段排序稳定
    insert_after_idx: int | None = None
    entry_indent = " " * 4
    quote = '"'
    scan_end = min(payload_start_idx + 80, len(lines))
    for idx in range(payload_start_idx, scan_end):
        raw = lines[idx]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.search(r"['\"]type['\"]\s*:\s*['\"]Struct['\"]", raw):
            insert_after_idx = idx
            indent_match = re.match(r"^(\s*)", raw)
            if indent_match:
                entry_indent = indent_match.group(1)
            # 保持 key/value 的引号风格与现有行一致
            quote_match = re.search(r"(?P<q>['\"])type(?P=q)", raw)
            if quote_match:
                quote = quote_match.group("q")
            break
        # 遇到结构体名字段也可作为 fallback 锚点
        if re.search(r"['\"]struct_name['\"]\s*:", raw):
            insert_after_idx = idx
            indent_match = re.match(r"^(\s*)", raw)
            if indent_match:
                entry_indent = indent_match.group(1)
            quote_match = re.search(r"(?P<q>['\"])struct_name(?P=q)", raw)
            if quote_match:
                quote = quote_match.group("q")
            break

    if insert_after_idx is None:
        return original_text, False

    insertion = f"{entry_indent}{quote}struct_ype{quote}: {quote}{expected_type}{quote},{newline}"
    lines.insert(insert_after_idx + 1, insertion)
    return "".join(lines), True


def _patch_struct_definition_text(
    original_text: str,
    *,
    expected_type: str,
) -> Tuple[str, bool, Dict[str, object]]:
    """将结构体定义文件中的 STRUCT_TYPE 与 STRUCT_PAYLOAD.struct_type 对齐为 expected_type。"""
    detail: Dict[str, object] = {"expected_struct_type": str(expected_type)}
    changed = False
    text = original_text

    # 兼容 Windows 文本写入的换行转换：若历史写盘产生了 `\r\r\n`，先归一化回 `\r\n`
    #（否则会在编辑器中表现为“每行之间多一空行”）。
    if "\r\r\n" in text:
        text = text.replace("\r\r\n", "\r\n")
        detail["newline_normalized"] = True
        changed = True

    # 1) STRUCT_TYPE 常量（可选但推荐，保持与 payload 一致）
    match = _STRUCT_TYPE_LINE_RE.search(text)
    if match:
        old_value = str(match.group("value") or "").strip()
        if old_value != expected_type:
            detail["struct_type_constant_old"] = old_value
            detail["struct_type_constant_new"] = expected_type

            def _replace(m: re.Match[str]) -> str:
                prefix = m.group("prefix")
                q = m.group("quote")
                suffix = m.group("suffix")
                return f"{prefix}{q}{expected_type}{q}{suffix}"

            text, count = _STRUCT_TYPE_LINE_RE.subn(_replace, text, count=1)
            if count:
                changed = True
    else:
        # 常量缺失：补齐（保持与示例模板一致）
        inserted, did = _insert_struct_type_constant(text, expected_type=expected_type)
        if did:
            detail["struct_type_constant_old"] = "<missing>"
            detail["struct_type_constant_new"] = expected_type
            text = inserted
            changed = True

    # 2) STRUCT_PAYLOAD 中的 struct_ype/struct_type（必须）
    payload_old: List[str] = []

    def _payload_replace(m: re.Match[str]) -> str:
        nonlocal changed
        key = str(m.group("key") or "")
        old_value = str(m.group("value") or "").strip()
        if old_value != expected_type:
            payload_old.append(f"{key}={old_value or '<empty>'}")
            changed = True
        prefix = m.group("prefix")
        q = m.group("quote")
        return f"{prefix}{q}{expected_type}{q}"

    text2, count2 = _PAYLOAD_STRUCT_TYPE_RE.subn(_payload_replace, text)
    if count2:
        if payload_old:
            detail["payload_struct_type_old"] = payload_old
            detail["payload_struct_type_new"] = expected_type
        text = text2
    else:
        inserted, did = _insert_payload_struct_type(text, expected_type=expected_type)
        if did:
            detail["payload_struct_type_old"] = "<missing>"
            detail["payload_struct_type_new"] = expected_type
            text = inserted
            changed = True

    return text, changed, detail


def apply_struct_definition_quickfixes(
    *,
    workspace_root: Path,
    package_id: str,
    dry_run: bool,
) -> List[QuickFixAction]:
    """按“目录即分类”规则自动修正结构体定义的 struct_type 声明。

    约定：
    - `结构体定义/基础结构体/**.py` 必须为 `basic`
    - `结构体定义/局内存档结构体/**.py` 必须为 `ingame_save`

    注意：
    - 仅修正结构体定义文件的声明字段，不重排字段、不改业务字段名。
    - 默认只读，只有 dry_run=False 时才会写盘。
    """
    package_id_text = str(package_id or "").strip()
    if not package_id_text:
        return []

    base_dir = (
        workspace_root
        / "assets"
        / "资源库"
        / "项目存档"
        / package_id_text
        / "管理配置"
        / "结构体定义"
    )
    if not base_dir.exists() or not base_dir.is_dir():
        return []

    py_files = sorted(
        [p for p in base_dir.rglob("*.py") if p.is_file()],
        key=lambda p: p.as_posix().casefold(),
    )

    actions: List[QuickFixAction] = []
    for py_file in py_files:
        if _is_reserved_python_file(py_file):
            continue
        expected_type = infer_expected_struct_type_from_source_path(py_file)
        if not expected_type:
            continue

        source = read_source_text(py_file)
        new_text, changed, detail = _patch_struct_definition_text(
            source.text,
            expected_type=expected_type,
        )
        if not changed:
            continue

        if not dry_run:
            has_bom = source.raw_bytes.startswith(b"\xef\xbb\xbf")
            encoding = "utf-8-sig" if has_bom else "utf-8"
            py_file.write_bytes(new_text.encode(encoding))

        rel = _relative_path_for_action(py_file, workspace_root)
        mode_text = "DRY-RUN" if dry_run else "APPLY"
        actions.append(
            QuickFixAction(
                file_path=rel,
                kind="fix_struct_definition_type_by_folder",
                summary=f"[{mode_text}] 修正结构体类型声明为 '{expected_type}'（目录即分类）",
                detail=detail,
            )
        )

    return actions

