import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class TraceEvent:
    source: str
    kind: str
    message: str
    timestamp: float
    stack: List[str]
    details: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "kind": self.kind,
            "message": self.message,
            "timestamp": self.timestamp,
            "stack": list(self.stack),
            "details": dict(self.details),
        }


class TraceRecorder:
    """轻量级事件追踪记录器，用于捕获运行期的节点执行与信号事件。"""

    def __init__(self, sink: Optional[Callable[[TraceEvent], None]] = None) -> None:
        self.events: List[TraceEvent] = []
        self.sink = sink

    def record(
        self,
        source: str,
        kind: str,
        message: str,
        *,
        stack: Optional[List[str]] = None,
        **details: Any,
    ) -> TraceEvent:
        event_stack = list(stack) if stack else []
        event = TraceEvent(
            source=source,
            kind=kind,
            message=message,
            timestamp=time.time(),
            stack=event_stack,
            details=dict(details),
        )
        self.events.append(event)
        if self.sink is not None:
            self.sink(event)
        return event

    def set_sink(self, sink: Optional[Callable[[TraceEvent], None]]) -> None:
        self.sink = sink

    def clear(self) -> None:
        self.events.clear()

    def as_list(self) -> List[TraceEvent]:
        return list(self.events)

