"""库页面通用的资源视图 scope 识别。

目的：
- 多个“库页面”需要在 LibraryChangeEvent / LibrarySelection 的 context 中携带 scope，
  用于上层区分“具体存档 / 全局资源”等视图范围。
- 将重复逻辑集中到单一实现，避免页面间漂移（修了 A 忘了 B）。
"""

from __future__ import annotations

from typing import Any

from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_view import PackageView


def describe_resource_view_scope(view: Any) -> str:
    """返回资源视图的 scope 标识：package/global/unknown。"""
    if isinstance(view, PackageView):
        return "package"
    if isinstance(view, GlobalResourceView):
        return "global"
    return "unknown"


