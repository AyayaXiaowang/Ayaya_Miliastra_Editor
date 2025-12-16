from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def atomic_write_json(
    target_file: Path,
    payload: Any,
    *,
    ensure_ascii: bool = False,
    indent: int = 2,
) -> None:
    """原子写 JSON：先写临时文件，再 replace 到目标文件，避免中断导致空文件/半写入。

    约束：
    - 临时文件与目标文件在同一目录，确保 replace 行为在同一文件系统内完成；
    - 不吞异常：写入失败应直接抛出，交由上层处理。
    """
    target_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = target_file.with_name(f"{target_file.name}.tmp")
    with open(tmp_file, "w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, ensure_ascii=ensure_ascii, indent=int(indent))
    tmp_file.replace(target_file)


