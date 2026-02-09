"""UI 样式散落巡检：扫描 setStyleSheet 的内联字符串用法。

目标：
- 找出业务模块中直接拼接/内联 QSS 的位置，便于迁移到 ThemeManager + theme/styles 的集中样式工厂；
- 该脚本只做输出诊断，不改变任何运行时逻辑。

使用方式（推荐模块运行）：
    python -m app.ui._static_checks.check_inline_styles
    python -m app.ui._static_checks.check_inline_styles --fail
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import sys


@dataclass(frozen=True)
class Finding:
    rel_path: str
    lineno: int
    kind: str
    snippet: str


def _ui_root_dir() -> Path:
    # .../app/ui/_static_checks/check_inline_styles.py -> parents[1] == .../app/ui
    return Path(__file__).resolve().parents[1]


def _should_skip(ui_dir: Path, file_path: Path) -> bool:
    rel = file_path.relative_to(ui_dir)
    parts = rel.parts
    if not parts:
        return True
    if parts[0] == "_static_checks":
        return True
    # UI 基础设施层允许做少量样式拼装（属于“统一入口”范围），巡检聚焦业务模块。
    if parts[0] == "foundation":
        return True
    # 样式工厂目录：允许（且鼓励）写纯 QSS 字符串
    if len(parts) >= 3 and parts[0] == "foundation" and parts[1] == "theme" and parts[2] == "styles":
        return True
    return False


def _iter_python_files(ui_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in ui_dir.rglob("*.py"):
        if not path.is_file():
            continue
        if _should_skip(ui_dir, path):
            continue
        files.append(path)
    return sorted(files, key=lambda p: p.as_posix().casefold())


def _is_theme_factory_call(expr: ast.AST) -> bool:
    """允许的“集中样式入口”：ThemeManager.* / TodoStyles.* 等直接调用。"""
    if not isinstance(expr, ast.Call):
        return False
    func = expr.func
    if not isinstance(func, ast.Attribute):
        return False
    owner = func.value
    if isinstance(owner, ast.Name) and owner.id in {"ThemeManager", "TodoStyles"}:
        return True
    return False


def _contains_string_literal(expr: ast.AST) -> bool:
    """是否包含字符串字面量（包含 f-string / 三引号等）。"""
    for node in ast.walk(expr):
        if isinstance(node, ast.JoinedStr):
            return True
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return True
    return False


def _shorten(text: str, limit: int = 140) -> str:
    cleaned = " ".join(str(text or "").strip().split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def _scan_file(ui_dir: Path, file_path: Path) -> list[Finding]:
    source = file_path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source, filename=str(file_path))
    findings: list[Finding] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr != "setStyleSheet":
            continue
        if not node.args:
            continue

        arg0 = node.args[0]
        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str) and arg0.value.strip() == "":
            # 常见用途：setStyleSheet("") 用于清理样式，不属于“内联 QSS 散落”
            continue
        rel = file_path.relative_to(ui_dir).as_posix()
        lineno = int(getattr(node, "lineno", 0) or 0)
        snippet = _shorten(ast.get_source_segment(source, node) or "")

        # 1) 直接调用集中样式工厂（推荐）
        if _is_theme_factory_call(arg0) and not _contains_string_literal(arg0):
            continue

        # 2) 其余情况：若包含字符串字面量，基本可以判定为“内联/拼接 QSS”
        if _contains_string_literal(arg0):
            findings.append(Finding(rel, lineno, "INLINE_QSS", snippet))
            continue

        # 3) 兜底：未知来源（例如变量、函数返回值），先标注为需要人工确认
        findings.append(Finding(rel, lineno, "UNKNOWN_SOURCE", snippet))

    return findings


def main(argv: list[str]) -> None:
    ui_dir = _ui_root_dir()
    files = _iter_python_files(ui_dir)

    all_findings: list[Finding] = []
    for file_path in files:
        all_findings.extend(_scan_file(ui_dir, file_path))

    inline = [f for f in all_findings if f.kind == "INLINE_QSS"]
    unknown = [f for f in all_findings if f.kind == "UNKNOWN_SOURCE"]

    print(f"[UI][StyleCheck] scanned_files={len(files)} inline_qss={len(inline)} unknown={len(unknown)}")

    if inline:
        print("\n[INLINE_QSS] 建议迁移到 ThemeManager + theme/styles：")
        for f in inline:
            print(f"- {f.rel_path}:{f.lineno}  {f.snippet}")

    if unknown and ("--verbose" in argv or "--show-unknown" in argv):
        print("\n[UNKNOWN_SOURCE] 需人工确认（可能是集中样式，也可能是间接拼接）：")
        for f in unknown:
            print(f"- {f.rel_path}:{f.lineno}  {f.snippet}")

    if "--fail" in argv and inline:
        raise SystemExit(1)


if __name__ == "__main__":
    main(sys.argv[1:])

