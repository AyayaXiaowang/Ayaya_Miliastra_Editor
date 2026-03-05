## 目录用途
纯模型层撤销/重做核心：命令接口、命令栈与管理器，用于对 `GraphModel` 等数据结构实现可撤销操作。

## 当前状态
- 核心实现位于 `undo_redo_core.py`。
- 通常通过 `engine.utils` 顶层延迟导出 `UndoRedoManager` / `Command` 供上层使用。

## 注意事项
- 不依赖 UI；命令执行/撤销/重做过程中不进行长耗时 I/O，必要工作由上层编排。
- 对“不影响持久化”的操作应使用显式标记（如 `affects_persistence=False`），由管理器/上层决定是否提示保存。

