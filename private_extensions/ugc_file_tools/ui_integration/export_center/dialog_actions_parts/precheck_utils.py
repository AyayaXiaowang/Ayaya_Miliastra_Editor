from __future__ import annotations

from pathlib import Path


def record_precheck_skip(*, precheck_skipped_inputs: list[dict[str, str]], category: str, file_path: Path, reason: str) -> None:
    """记录预检阶段自动跳过的输入文件条目。"""

    precheck_skipped_inputs.append(
        {
            "category": str(category),
            "file": str(Path(file_path).resolve()),
            "reason": str(reason),
        }
    )


__all__ = [
    "record_precheck_skip",
]

