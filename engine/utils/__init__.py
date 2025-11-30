"""Utilities 工具包

提供通用工具与基础设施能力，按功能拆分为若干子包：
- graph：图结构算法与节点图数据处理工具
- logging：统一日志与控制台输出清洗
- cache：缓存路径与指纹工具
- undo：撤销/重做命令系统（纯模型层）
- text：文本相似度等通用文本工具

为避免导入时的循环依赖，命令系统类采用延迟导入从 `undo` 子包暴露。
"""

__all__ = ["UndoRedoManager", "Command"]


def __getattr__(name: str):
    if name in ("UndoRedoManager", "Command"):
        # 仅导出纯模型版本的命令系统，避免任何 UI 依赖
        from .undo.undo_redo_core import UndoRedoManager, Command  # 延迟导入，避免 graph_model ↔ utilities 循环

        return {"UndoRedoManager": UndoRedoManager, "Command": Command}[name]
    raise AttributeError(name)

