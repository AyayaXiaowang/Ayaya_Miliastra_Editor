"""UI 单文件体积护栏：扫描 app/ui 下的 Python 文件行数。

目标：
- 防止 UI 业务逻辑继续回流到单体文件（1500+ 行）导致难以维护与频繁冲突；
- 该脚本只做输出诊断与可选 fail，不改变任何运行时逻辑。

使用方式（推荐模块运行）：
    python -m app.ui._static_checks.check_large_files
    python -m app.ui._static_checks.check_large_files --fail
    python -m app.ui._static_checks.check_large_files --fail --max-lines 1500
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


@dataclass(frozen=True)
class Finding:
    rel_path: str
    line_count: int


def _ui_root_dir() -> Path:
    # .../app/ui/_static_checks/check_large_files.py -> parents[1] == .../app/ui
    return Path(__file__).resolve().parents[1]


def _parse_max_lines(argv: list[str]) -> int:
    if "--max-lines" not in argv:
        return 1500
    idx = argv.index("--max-lines")
    if idx + 1 >= len(argv):
        raise ValueError("--max-lines requires an integer")
    raw = str(argv[idx + 1]).strip()
    if not raw.isdigit():
        raise ValueError(f"--max-lines must be a positive integer, got: {raw!r}")
    value = int(raw)
    if value <= 0:
        raise ValueError(f"--max-lines must be > 0, got: {value}")
    return int(value)


def _should_skip(ui_dir: Path, file_path: Path) -> bool:
    rel = file_path.relative_to(ui_dir)
    parts = rel.parts
    if not parts:
        return True
    if "__pycache__" in parts:
        return True
    if parts[0] == "_static_checks":
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


def _count_lines(file_path: Path) -> int:
    # 以 text 方式读取：对 UI 代码而言可接受；若文件包含异常编码，按默认策略直接抛出便于定位修复。
    text = file_path.read_text(encoding="utf-8")
    # splitlines() 不包含末尾空行的额外计数；符合“肉眼看到的行数”直觉
    return int(len(text.splitlines()))


def main(argv: list[str]) -> None:
    ui_dir = _ui_root_dir()
    max_lines = _parse_max_lines(argv)
    files = _iter_python_files(ui_dir)

    findings: list[Finding] = []
    for file_path in files:
        n = _count_lines(file_path)
        if n > int(max_lines):
            findings.append(
                Finding(
                    rel_path=file_path.relative_to(ui_dir).as_posix(),
                    line_count=int(n),
                )
            )

    print(f"[UI][LargeFiles] scanned_files={len(files)} max_lines={max_lines} violations={len(findings)}")
    if findings:
        print("\n[VIOLATIONS] 建议拆分为子模块/ mixin / service（保持稳定导入门面）：")
        for f in findings:
            print(f"- {f.rel_path}\tlines={f.line_count}")

    if "--fail" in argv and findings:
        raise SystemExit(1)


if __name__ == "__main__":
    main(sys.argv[1:])

