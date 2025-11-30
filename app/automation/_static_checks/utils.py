from __future__ import annotations

from pathlib import Path
from typing import Iterator


def iter_python_files(root_directory: str) -> Iterator[str]:
    """
    遍历给定目录下的所有 Python 文件，返回绝对路径字符串。

    Args:
        root_directory: 需要扫描的目录路径。

    Yields:
        每个 Python 文件的绝对路径。
    """
    root_path = Path(root_directory).resolve()
    for file_path in root_path.rglob("*.py"):
        if file_path.is_file():
            yield str(file_path)


__all__ = ["iter_python_files"]

