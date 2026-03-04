from __future__ import annotations

from pathlib import Path
from typing import Optional


def resolve_out_dir() -> Path:
    """返回 `ugc_file_tools/out` 的绝对路径，并确保目录存在。"""
    out_dir = Path(__file__).resolve().parent / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def resolve_output_file_path_in_out_dir(
    output_file_path: Path,
    *,
    default_file_name: Optional[str] = None,
) -> Path:
    """
    强制将“输出文件”落盘到 `ugc_file_tools/out/` 下（允许 out 内子目录）。

    规则：
    - 若传入绝对路径且已在 out 目录内：按原路径输出（仍在 out 内）。
    - 若传入绝对路径但不在 out 目录内：仅取文件名，输出到 out 根目录。
    - 若传入相对路径：
      - 支持 `out/xxx` 与 `ugc_file_tools/out/xxx` 两种写法（会去掉前缀）。
      - 其余相对路径将被视为 out 内的相对路径（允许子目录）。
    - 禁止出现 `..` 以避免逃逸 out 目录。
    """
    out_dir = resolve_out_dir().resolve()

    p = Path(output_file_path)
    if p.is_absolute():
        resolved = p.resolve()
        if resolved == out_dir or out_dir in resolved.parents:
            return resolved
        file_name = p.name
        if file_name == "":
            if not default_file_name:
                raise ValueError("output file path is empty and default_file_name is not provided")
            file_name = str(default_file_name)
        return (out_dir / file_name).resolve()

    rel = p
    parts_lower = [str(x).lower() for x in rel.parts]
    if len(parts_lower) >= 2 and parts_lower[0] == "ugc_file_tools" and parts_lower[1] == "out":
        rel = Path(*rel.parts[2:])
    elif len(parts_lower) >= 1 and parts_lower[0] == "out":
        rel = Path(*rel.parts[1:])

    rel_text = str(rel).strip()
    if rel_text == "" or rel_text == ".":
        if not default_file_name:
            raise ValueError("output file path is empty and default_file_name is not provided")
        rel = Path(str(default_file_name))

    if any(str(part) == ".." for part in rel.parts):
        raise ValueError("output file path must not contain '..'")

    resolved = (out_dir / rel).resolve()
    if not (resolved == out_dir or out_dir in resolved.parents):
        raise ValueError(f"resolved output path escaped out dir: {str(resolved)}")
    return resolved


def resolve_output_dir_path_in_out_dir(
    output_dir_path: Path,
    *,
    default_dir_name: Optional[str] = None,
) -> Path:
    """
    强制将“输出目录”落盘到 `ugc_file_tools/out/` 下（允许 out 内子目录）。

    规则同 `resolve_output_file_path_in_out_dir`，但语义为目录路径。
    """
    out_dir = resolve_out_dir().resolve()

    p = Path(output_dir_path)
    if p.is_absolute():
        resolved = p.resolve()
        if resolved == out_dir or out_dir in resolved.parents:
            return resolved
        dir_name = p.name
        if dir_name == "":
            if not default_dir_name:
                raise ValueError("output dir path is empty and default_dir_name is not provided")
            dir_name = str(default_dir_name)
        return (out_dir / dir_name).resolve()

    rel = p
    parts_lower = [str(x).lower() for x in rel.parts]
    if len(parts_lower) >= 2 and parts_lower[0] == "ugc_file_tools" and parts_lower[1] == "out":
        rel = Path(*rel.parts[2:])
    elif len(parts_lower) >= 1 and parts_lower[0] == "out":
        rel = Path(*rel.parts[1:])

    rel_text = str(rel).strip()
    if rel_text == "" or rel_text == ".":
        if not default_dir_name:
            raise ValueError("output dir path is empty and default_dir_name is not provided")
        rel = Path(str(default_dir_name))

    if any(str(part) == ".." for part in rel.parts):
        raise ValueError("output dir path must not contain '..'")

    resolved = (out_dir / rel).resolve()
    if not (resolved == out_dir or out_dir in resolved.parents):
        raise ValueError(f"resolved output dir escaped out dir: {str(resolved)}")
    return resolved


