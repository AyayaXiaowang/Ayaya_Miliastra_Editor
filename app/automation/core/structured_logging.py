from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class LogEvent:
    category: str
    message: str
    details: Optional[Dict[str, Any]] = None

    def format(self, prefix: str = "") -> str:
        base = f"[{self.category}] {self.message}"
        if self.details:
            detail_text = ", ".join(f"{key}={self._stringify(value)}" for key, value in self.details.items())
            base = f"{base} ({detail_text})"
        return f"{prefix}{base}" if prefix else base

    @staticmethod
    def _stringify(value: Any) -> str:
        if isinstance(value, float):
            return f"{value:.4f}"
        if isinstance(value, (list, tuple)):
            return "[" + ", ".join(LogEvent._stringify(v) for v in value) + "]"
        return str(value)


class StructuredLogger:
    def __init__(
        self,
        executor,
        log_callback,
        *,
        prefix: str = "",
    ) -> None:
        self._executor = executor
        self._log_callback = log_callback
        self._prefix = prefix

    def log(self, category: str, message: str, **details: Any) -> None:
        event = LogEvent(category, message, details or None)
        self._executor._log(event.format(self._prefix), self._log_callback)

    def child(self, prefix: str) -> "StructuredLogger":
        next_prefix = f"{self._prefix}{prefix}"
        return StructuredLogger(self._executor, self._log_callback, prefix=next_prefix)


