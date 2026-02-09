from __future__ import annotations

from pathlib import Path

from app.automation.editor.editor_executor import EditorExecutor


class EditorExecutorProvider:
    """提供/复用 EditorExecutor 的统一入口（集中共享策略，避免 UI 各处自行创建）。"""

    def get_or_create_executor(
        self,
        *,
        workspace_path: Path,
        monitor_port: object | None,
    ) -> EditorExecutor:
        shared_executor: object | None = None
        if monitor_port is not None:
            get_shared_executor = getattr(monitor_port, "get_shared_executor", None)
            if callable(get_shared_executor):
                shared_executor = get_shared_executor()

        if shared_executor is not None:
            shared_workspace_path = getattr(shared_executor, "workspace_path", None)
            if str(shared_workspace_path or "") == str(workspace_path):
                return shared_executor  # type: ignore[return-value]

        executor = EditorExecutor(workspace_path)

        if monitor_port is not None:
            set_shared_executor = getattr(monitor_port, "set_shared_executor", None)
            if callable(set_shared_executor):
                set_shared_executor(executor)

        return executor


