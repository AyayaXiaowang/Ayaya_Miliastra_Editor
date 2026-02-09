from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SOURCE_ENCODING: str = "utf-8-sig"


@dataclass(frozen=True, slots=True)
class SourceText:
    """文件源码快照（bytes + 解码文本 + md5）。

    约定：
    - 默认解码使用 `utf-8-sig`，兼容 Windows 常见 UTF-8 BOM，避免 `ast.parse` 看到 U+FEFF。
    - 不做任何 try/except；读不到/解码失败应直接抛错，由上层处理。
    """

    raw_bytes: bytes
    text: str
    md5: str


def read_text(path: Path, *, encoding: str = DEFAULT_SOURCE_ENCODING) -> str:
    """读取文本（默认 `utf-8-sig`）。"""

    return path.read_text(encoding=encoding)


def read_source_text(path: Path, *, encoding: str = DEFAULT_SOURCE_ENCODING) -> SourceText:
    """读取 bytes 并按 encoding 解码，同时计算 md5。"""

    raw_bytes = path.read_bytes()
    text = raw_bytes.decode(encoding)
    md5 = hashlib.md5(raw_bytes).hexdigest()
    return SourceText(raw_bytes=raw_bytes, text=text, md5=md5)



