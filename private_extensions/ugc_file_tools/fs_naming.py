from __future__ import annotations

import re
from pathlib import Path

_INVALID_WINDOWS_FILENAME_CHARS_PATTERN = re.compile(r'[<>:"/\\\\|?*]')


def sanitize_file_stem(name: str, *, max_length: int = 80) -> str:
    """
    将任意字符串清洗为“适合作为文件名 stem”的文本（不含扩展名）。

    约定（对齐 ugc_file_tools 内既有行为）：
    - 去掉首尾空白；空则返回 "untitled"
    - 替换 Windows 非法字符为 "_"
    - 归一化空白为单空格
    - 超长截断（默认 80），并去掉截断后的尾部空白
    """
    text = str(name or "").strip()
    if text == "":
        return "untitled"
    text = _INVALID_WINDOWS_FILENAME_CHARS_PATTERN.sub("_", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > int(max_length):
        text = text[: int(max_length)].rstrip()
    if text == "":
        return "untitled"
    return text


def is_relative_to(child: Path, parent: Path) -> bool:
    """
    Path.is_relative_to 的兼容实现（兼容旧 Python）。
    """
    child_resolved = Path(child).resolve()
    parent_resolved = Path(parent).resolve()
    if hasattr(child_resolved, "is_relative_to"):
        return bool(child_resolved.is_relative_to(parent_resolved))
    parent_parts = parent_resolved.parts
    child_parts = child_resolved.parts
    return len(child_parts) >= len(parent_parts) and child_parts[: len(parent_parts)] == parent_parts


def format_path_for_display(*, path: Path, workspace_root: Path) -> str:
    """
    用于 UI 展示的路径格式化：
    - 若 path 位于 workspace_root 下：显示为相对路径（posix 风格）
    - 否则：显示绝对路径
    """
    p = Path(path).resolve()
    root = Path(workspace_root).resolve()
    if is_relative_to(p, root):
        return p.relative_to(root).as_posix()
    return str(p)

