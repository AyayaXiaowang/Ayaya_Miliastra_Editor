"""存档索引管理器 - 对外兼容入口。

该模块保持 import 路径稳定：`from engine.resources.package_index_manager import PackageIndexManager`。
具体实现已拆分到 `engine.resources.package_index_manager_parts`，避免单文件过长难以维护。
"""

from engine.resources.package_index_manager_parts.manager import PackageIndexManager

__all__ = ["PackageIndexManager"]
