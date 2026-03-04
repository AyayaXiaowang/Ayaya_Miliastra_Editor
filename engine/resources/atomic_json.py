from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any


_LOCK_GUARD = threading.Lock()
_LOCK_BY_TARGET: dict[str, threading.Lock] = {}


def _get_lock_for_target(target_file: Path) -> threading.Lock:
    # Windows 下路径大小写不敏感：统一 casefold 作为 key，避免同一文件拿到两把锁。
    normalized = target_file if target_file.is_absolute() else target_file.absolute()
    key = str(normalized).casefold()
    with _LOCK_GUARD:
        lock = _LOCK_BY_TARGET.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCK_BY_TARGET[key] = lock
        return lock


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
    # 重要：使用“唯一临时文件名”，避免并发写入时多个写者争用同一个 *.tmp 文件。
    # 同时对同一目标文件加互斥锁，避免 Windows 上 replace 在并发场景下出现 WinError 5。
    lock = _get_lock_for_target(target_file)
    with lock:
        tmp_name = f".{target_file.name}.{os.getpid()}.{threading.get_ident()}.{time.monotonic_ns()}.tmp"
        tmp_file = target_file.with_name(tmp_name)
        with open(tmp_file, "w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=ensure_ascii, indent=int(indent))
            file_obj.flush()
            os.fsync(file_obj.fileno())
        tmp_file.replace(target_file)


