from __future__ import annotations

import tokenize
from pathlib import Path

from tests._helpers.project_paths import get_repo_root


def _iter_python_source_files(project_root: Path) -> list[Path]:
    python_files: list[Path] = []
    for python_file_path in project_root.rglob("*.py"):
        if "__pycache__" in python_file_path.parts:
            continue
        python_files.append(python_file_path)
    return python_files


def test_all_python_files_are_syntax_compilable() -> None:
    """
    目标：确保仓库内所有 .py 文件在 CI 使用的 Python 版本（3.10）下都能被编译通过。

    说明：
    - pytest 的用例只会 import 到少量模块；某些“平时不 import 的文件”若存在 SyntaxError，
      可能绕过测试收集而在真实运行/工具链路径中爆炸。
    - 这里使用内置 compile 做纯语法编译检查，不会执行任何代码，也不会写入 .pyc。
    """

    project_root = get_repo_root()
    python_files = _iter_python_source_files(project_root)

    # 逐文件编译：出现 SyntaxError 会直接让测试失败，并由 pytest 输出具体文件与行号。
    for python_file_path in python_files:
        with tokenize.open(python_file_path) as file_handle:
            source_text = file_handle.read()
        compile(source_text, str(python_file_path), "exec")


