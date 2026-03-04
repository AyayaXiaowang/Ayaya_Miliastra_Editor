from __future__ import annotations

from pathlib import Path


def _dump_gil_to_json_with_dll(*, input_gil_file_path: Path, dll_dump_path: Path) -> None:
    # 延迟导入：保持 `--help` 纯参数路径轻量。
    # 备注：这里的 dump 已改为纯 Python 实现（函数名保留为兼容历史命名）。
    from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json

    dump_gil_to_json(str(input_gil_file_path), str(dll_dump_path))


