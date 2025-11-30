"""
核心执行与编排模块。

- 提供执行器协议与核心实现（EditorExecutor）。
- 收敛编辑器识别、视口映射、缩放控制等“自动化内核”逻辑。
- 对外通常通过 `app.automation.core.editor_executor.EditorExecutor` 以及
  `app.automation.core.executor_protocol.EditorExecutorProtocol` 间接使用。
"""


