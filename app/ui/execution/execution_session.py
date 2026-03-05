from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ExecutionSession:
    """一次执行会话的稳定载体（供监控面板/执行桥接/其它协作方复用）。

    约定：
    - `executor` 允许为 None：仅做“上下文注入”（workspace/model/view）时使用；
    - `graph_model`/`graph_view` 的具体类型由调用方决定（面板侧只做存储与委托）。
    """

    workspace_path: Path
    graph_model: object
    executor: object | None
    graph_view: object | None = None


