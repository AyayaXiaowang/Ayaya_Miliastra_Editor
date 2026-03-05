from __future__ import annotations

from pathlib import Path


def get_beyond_local_export_dir() -> Path:
    """
    真源可识别的固定导出目录（Windows）。

    约定：
    - 本项目所有 `.gia` 的“最终导出位置”应为该目录；
    - `ugc_file_tools/out/` 仍可用于中间产物与可追溯输出，但用户侧不应手动搬运。
    """

    home = Path.home().resolve()
    return (home / "AppData" / "LocalLow" / "miHoYo" / "原神" / "BeyondLocal" / "Beyond_Local_Export").resolve()


def copy_file_to_beyond_local_export(src_file: Path) -> Path:
    import shutil

    src = Path(src_file).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"src_file not found: {str(src)!r}")

    dst_dir = get_beyond_local_export_dir()
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst_path = (dst_dir / src.name).resolve()
    shutil.copy2(src, dst_path)
    return dst_path

