"""资源库刷新服务（缓存失效 + 资源索引重建）。

设计原则：
- 服务只负责“失效与重建”，不直接操作 UI 组件；
- UI（主窗口/控制器）只订阅刷新结果，并决定如何刷新页面与恢复上下文。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.common.in_memory_graph_payload_cache import clear_all_graph_data
from engine.layout import invalidate_layout_caches
from engine.resources.definition_schema_view import (
    invalidate_default_signal_cache,
    invalidate_default_struct_cache,
)
from app.runtime.services.graph_data_service import get_shared_graph_data_service

from .app_state import MainWindowAppState


@dataclass(frozen=True, slots=True)
class ResourceRefreshOutcome:
    """一次资源库刷新后的结果摘要（供 UI 决策后续刷新动作）。"""

    current_package_id: str | None
    did_clear_current_package_cache: bool
    did_clear_global_resource_view_cache: bool


class ResourceRefreshService:
    """集中处理“资源库刷新”的失效与重建步骤。"""

    def refresh(
        self,
        *,
        app_state: MainWindowAppState,
        package_controller: Any,
        global_resource_view: Any | None,
    ) -> ResourceRefreshOutcome:
        """执行缓存失效与资源索引重建，并返回结果摘要。"""
        # 0) 代码级 Schema 缓存失效
        invalidate_default_struct_cache()
        invalidate_default_signal_cache()

        # 同步失效管理页面内基于 ResourceManager 的结构体记录快照
        #（避免“基础结构体定义/局内存档结构体定义”仍展示旧记录）
        from app.ui.graph.library_pages.management_section_struct_definitions import (
            StructDefinitionSection,
        )

        StructDefinitionSection._invalidate_struct_records_cache(app_state.resource_manager)

        # 1) 统一清理运行期缓存（内存 + 磁盘），缩短“刷新需要手动清一串缓存”的链路
        app_state.resource_manager.clear_all_caches()
        clear_all_graph_data()
        invalidate_layout_caches(app_state.graph_model)

        # 2) 重建资源索引并刷新指纹基线
        app_state.resource_manager.rebuild_index()

        # 3) 失效图属性面板/引用查询等共享数据提供器缓存（避免仍展示旧图数据/旧引用列表）
        provider = get_shared_graph_data_service(
            app_state.resource_manager,
            app_state.package_index_manager,
        )
        provider.invalidate_graph()
        provider.invalidate_package_cache()

        # 4) 清理当前 PackageView 的懒加载缓存（若存在）
        did_clear_current_package_cache = False
        current_package = getattr(package_controller, "current_package", None)
        clear_package_cache = getattr(current_package, "clear_cache", None)
        if callable(clear_package_cache):
            clear_package_cache()
            did_clear_current_package_cache = True

        # 5) 清理全局资源视图（只读预览）懒加载缓存（若存在）
        did_clear_global_resource_view_cache = False
        clear_global_cache = getattr(global_resource_view, "clear_cache", None)
        if callable(clear_global_cache):
            clear_global_cache()
            did_clear_global_resource_view_cache = True

        current_package_id = getattr(package_controller, "current_package_id", None)
        if not isinstance(current_package_id, str) or not current_package_id:
            current_package_id = None

        return ResourceRefreshOutcome(
            current_package_id=current_package_id,
            did_clear_current_package_cache=did_clear_current_package_cache,
            did_clear_global_resource_view_cache=did_clear_global_resource_view_cache,
        )


