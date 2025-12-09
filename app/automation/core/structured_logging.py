from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass(frozen=True)
class LogEvent:
    category: str
    message: str
    details: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "category": self.category,
            "message": self.message,
            "timestamp": self.timestamp,
        }
        if self.context:
            data["context"] = dict(self.context)
        if self.details:
            data["details"] = dict(self.details)
        return data

    def format(self, prefix: str = "") -> str:
        base = f"[{self.category}] {self.message}"
        merged_details = self._merge_details()
        if merged_details:
            detail_items = []
            for key in sorted(merged_details.keys()):
                detail_items.append(f"{key}={self._stringify(merged_details[key])}")
            detail_text = ", ".join(detail_items)
            base = f"{base} ({detail_text})"
        return f"{prefix}{base}" if prefix else base

    def _merge_details(self) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        if self.context:
            merged.update(self.context)
        if self.details:
            merged.update(self.details)
        return merged

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
        context: Optional[Dict[str, Any]] = None,
        event_sink: Optional[Callable[[LogEvent], None]] = None,
    ) -> None:
        self._executor = executor
        self._log_callback = log_callback
        self._prefix = prefix
        self._context = dict(context) if context else {}
        self._event_sink = event_sink

    def log(self, category: str, message: str, **details: Any) -> None:
        merged_context = self._context or None
        event = LogEvent(category, message, details or None, merged_context)
        self._emit(event)

    def child(self, prefix: str) -> "StructuredLogger":
        next_prefix = f"{self._prefix}{prefix}"
        return StructuredLogger(
            self._executor,
            self._log_callback,
            prefix=next_prefix,
            context=self._context,
            event_sink=self._event_sink,
        )

    def with_context(self, **context: Any) -> "StructuredLogger":
        merged_context = dict(self._context)
        merged_context.update(context)
        return StructuredLogger(
            self._executor,
            self._log_callback,
            prefix=self._prefix,
            context=merged_context,
            event_sink=self._event_sink,
        )

    def _emit(self, event: LogEvent) -> None:
        self._executor.log(event.format(self._prefix), self._log_callback)
        sink: Optional[Callable[[LogEvent], None]] = self._event_sink
        if sink is None:
            sink = getattr(self._executor, "record_structured_event", None)
        if sink is not None:
            sink(event)


