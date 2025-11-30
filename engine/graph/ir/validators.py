from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class Validators:
    """仅收集解析过程中的提醒/警告，不进行输出。"""
    warnings: List[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        self.warnings.append(message)



