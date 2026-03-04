from __future__ import annotations

"""Python 源文件模块加载工具（替代 deprecated 的 `SourceFileLoader.load_module()`）。

用途：
- 从任意 .py 文件加载为模块对象（不要求其在 sys.path 上）；
- 统一通过 `spec_from_file_location + exec_module` 执行；
- 默认在执行前把模块注册到 `sys.modules`，以兼容：
  - dataclasses + `from __future__ import annotations` 在处理字符串注解时查询 sys.modules 的行为。

注意：
- 本模块仅提供“加载工具”，不做 try/except 吞错；加载失败应直接抛异常暴露问题。
"""

import re
import sys
import zlib
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType


def sanitize_module_part(text: str) -> str:
    """清洗为可用于 module_name 的片段（允许中文与下划线）。"""
    cleaned = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", "_", str(text or ""))
    cleaned = cleaned.strip("_") or "module"
    if cleaned[0].isdigit():
        cleaned = "_" + cleaned
    return cleaned


def build_stable_module_name(*, prefix: str, file_path: Path, tag: str = "") -> str:
    """构造稳定的 module_name（避免 `hash()` 随机化导致调试困难）。"""
    p = Path(file_path).resolve()
    path_text = p.as_posix()
    checksum = zlib.adler32(path_text.encode("utf-8")) & 0xFFFFFFFF

    prefix_part = sanitize_module_part(prefix)
    stem_part = sanitize_module_part(p.stem)

    if tag:
        tag_part = sanitize_module_part(tag)
        return f"{prefix_part}_{stem_part}_{checksum:08x}_{tag_part}"
    return f"{prefix_part}_{stem_part}_{checksum:08x}"


def load_module_from_file(*, module_name: str, file_path: Path, register_in_sys_modules: bool = True) -> ModuleType:
    """从 file_path 加载模块并返回 module 对象。"""
    p = Path(file_path).resolve()
    spec = spec_from_file_location(str(module_name), str(p))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法为 Python 文件创建模块说明：{p}")

    module = module_from_spec(spec)
    if register_in_sys_modules:
        sys.modules[str(spec.name)] = module
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


__all__ = [
    "build_stable_module_name",
    "load_module_from_file",
    "sanitize_module_part",
]

