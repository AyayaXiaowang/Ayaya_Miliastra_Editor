from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOTS = ("app/ui",)

# 继承 QDialog 但未使用统一封装（BaseDialog/FormDialog）的类需要人工检查样式。
TARGET_DIALOG_BASES = {"QDialog"}
THEMED_DIALOG_BASES = {"BaseDialog", "FormDialog"}

# 直接调用这些原生对话框构造函数时，通常不会走统一的主题封装。
NATIVE_DIALOG_CTORS = {
    "QDialog",
    "QFileDialog",
    "QInputDialog",
    "QColorDialog",
    "QFontDialog",
    "QProgressDialog",
}

# 可能未套主题样式的基础控件（启发式）：文件若未引用 ThemeManager/StyleMixin 则提示人工检查。
SUSPECT_CONTROL_CLASSES = {
    "QSpinBox",
    "QDoubleSpinBox",
    "QComboBox",
    "QTableWidget",
    "QTreeWidget",
    "QListWidget",
    "QLineEdit",
    "QPlainTextEdit",
    "QTextEdit",
}

# 跳过主题定义、基础封装与本工具自身，避免误报。
SKIP_PATH_PARTS = (
    "ui/foundation/theme/styles",
    "ui/foundation/dialog_utils.py",
    "ui/foundation/style_mixins.py",
    "ui/foundation/base_widgets.py",
    "tools/check_unstyled_qt_windows.py",
)


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        if parent:
            return f"{parent}.{node.attr}"
        return node.attr
    return ""


def matches_target(name: str, candidates: set[str]) -> bool:
    short_name = name.split(".")[-1]
    return name in candidates or short_name in candidates


def should_skip(path: Path) -> bool:
    normalized = str(path).replace("\\", "/")
    for part in SKIP_PATH_PARTS:
        if part in normalized:
            return True
    return False


def iter_source_paths(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        if should_skip(path):
            continue
        yield path


def _has_theme_reference(text: str) -> bool:
    """粗粒度判断文件是否显式引用主题/样式混入。"""
    markers = [
        "ThemeManager",
        "StyleMixin",
        "apply_panel_style",
        "apply_form_dialog_style",
        "apply_card_style",
        "apply_widget_style",
        "apply_management_widget_style",
    ]
    return any(marker in text for marker in markers)


def scan_path(path: Path) -> tuple[list[int], list[int], list[int], bool]:
    text = path.read_text(encoding="utf-8")
    syntax_tree = ast.parse(text, filename=str(path))

    subclass_lines: list[int] = []
    ctor_lines: list[int] = []
    control_lines: list[int] = []

    for node in ast.walk(syntax_tree):
        if isinstance(node, ast.ClassDef):
            base_names = {dotted_name(base) for base in node.bases}
            inherits_qdialog = any(matches_target(name, TARGET_DIALOG_BASES) for name in base_names)
            uses_themed_base = any(matches_target(name, THEMED_DIALOG_BASES) for name in base_names)
            if inherits_qdialog and not uses_themed_base:
                subclass_lines.append(node.lineno)
        elif isinstance(node, ast.Call):
            func_name = dotted_name(node.func)
            if matches_target(func_name, NATIVE_DIALOG_CTORS):
                ctor_lines.append(node.lineno)
            if matches_target(func_name, SUSPECT_CONTROL_CLASSES):
                control_lines.append(node.lineno)

    return subclass_lines, ctor_lines, control_lines, _has_theme_reference(text)


def main(argv: list[str]) -> int:
    roots = argv[1:] if len(argv) > 1 else list(DEFAULT_ROOTS)
    any_issue = False

    for root_str in roots:
        root_path = (PROJECT_ROOT / root_str).resolve()
        if not root_path.exists():
            print(f"[skip] 根目录不存在: {root_path}")
            continue

        print(f"=== 扫描目录: {root_path} ===")
        for source_path in iter_source_paths(root_path):
            subclass_lines, ctor_lines, control_lines, has_theme = scan_path(source_path)
            if not subclass_lines and not ctor_lines and not control_lines:
                continue

            any_issue = True
            relative = source_path.relative_to(PROJECT_ROOT).as_posix()

            if subclass_lines:
                line_numbers = ", ".join(str(number) for number in sorted(subclass_lines))
                print(f"- {relative}: 继承 QDialog 但未使用 BaseDialog/FormDialog，类定义行 {line_numbers}")

            if ctor_lines:
                line_numbers = ", ".join(str(number) for number in sorted(ctor_lines))
                print(f"- {relative}: 直接实例化原生对话框(QDialog/QFileDialog等)，行 {line_numbers}")

            if control_lines and not has_theme:
                line_numbers = ", ".join(str(number) for number in sorted(control_lines))
                print(
                    f"- {relative}: 检测到基础输入/列表控件但文件未引用 ThemeManager/StyleMixin（可能未套主题样式），行 {line_numbers}"
                )

    if not any_issue:
        print("OK: 未发现疑似未走主题封装的对话框。")
    else:
        print("\n提示：请让对话框继承 BaseDialog/FormDialog，或封装文件选择/输入对话框以统一样式。")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

