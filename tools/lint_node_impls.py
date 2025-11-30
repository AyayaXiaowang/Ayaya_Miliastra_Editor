from __future__ import annotations

import argparse
import ast
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
IMPL = ROOT / "node_implementations"
import ast as _ast


def _find_node_spec_funcs(source: str) -> List[ast.FunctionDef]:
    tree = ast.parse(source)
    results: List[ast.FunctionDef] = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef):
            for d in n.decorator_list:
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "node_spec":
                    results.append(n)
                    break
    return results


def _get_spec_str(call: ast.Call, key: str) -> str | None:
    for kw in call.keywords:
        if kw.arg == key and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def lint_file(path: Path) -> List[str]:
    errors: List[str] = []
    text = path.read_text(encoding="utf-8")
    if text.count("@node_spec") != 1:
        errors.append(f"{path}: 必须且仅含一个 @node_spec")
    if len(text.splitlines()) >= 300:
        errors.append(f"{path}: 文件行数应 < 300")
    if "print(" in text:
        errors.append(f"{path}: 不允许使用 print()，请改用 core.utilities.logger")

    # 目录类别校验
    tree = ast.parse(text)
    for n in tree.body:
        if isinstance(n, ast.FunctionDef):
            for d in n.decorator_list:
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "node_spec":
                    category = _get_spec_str(d, "category")
                    if category:
                        # 计算相对实现根目录的层级：期望为 <scope>/<category>/<file>.py
                        rel = path.relative_to(IMPL)
                        parts = rel.parts
                        if len(parts) < 3:
                            errors.append(f"{path}: 文件层级不完整，应位于 '{IMPL}/<scope>/{category}/' 下")
                        else:
                            actual_category = parts[1]
                            if actual_category != category:
                                errors.append(f"{path}: 目录名 '{actual_category}' 与 @node_spec(category='{category}') 不一致")
                    break

    return errors


def collect_target_files() -> List[Path]:
    files: List[Path] = []
    for sub in [IMPL / "server", IMPL / "client"]:
        if not sub.exists():
            continue
        for category_dir in sub.iterdir():
            if not category_dir.is_dir():
                continue
            # 递归收集类别目录下的所有实现文件
            for f in category_dir.rglob("*.py"):
                files.append(f)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint node implementation files")
    parser.add_argument("--strict", action="store_true", help="严格模式（全部启用）")
    args = parser.parse_args()

    errors: List[str] = []
    for f in collect_target_files():
        errors.extend(lint_file(f))

    if errors:
        for e in errors:
            print(e)
        return 1
    print("OK: 所有节点实现文件通过校验")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


