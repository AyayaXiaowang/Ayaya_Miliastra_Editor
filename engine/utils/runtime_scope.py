from __future__ import annotations

"""运行期作用域（进程内全局）。

用途：
- 在不引入 app/UI 依赖的前提下，为引擎层提供“当前项目存档（active_package_id）”这一运行期上下文；
- 供节点库/复合节点扫描、指纹计算与代码级 Schema 等模块读取，避免跨项目存档全量聚合导致重复 ID 或串包。

注意：
- 本模块仅保存运行期状态，不落盘；
- 不吞异常；上层应保证传入的 package_id 合法且与 ResourceManager 的作用域一致。
"""

from engine.utils.resource_library_layout import normalize_active_package_id

_ACTIVE_PACKAGE_ID: str | None = None


def set_active_package_id(package_id: str | None) -> None:
    """设置当前作用域的 active_package_id（None 表示仅共享根）。"""
    global _ACTIVE_PACKAGE_ID
    _ACTIVE_PACKAGE_ID = normalize_active_package_id(package_id)


def get_active_package_id() -> str | None:
    """获取当前作用域的 active_package_id（None 表示仅共享根）。"""
    return _ACTIVE_PACKAGE_ID


