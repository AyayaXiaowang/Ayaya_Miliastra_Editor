"""资源库刷新服务（缓存失效 + 资源索引重建）。

设计原则：
- 服务只负责“失效与重建”，不直接操作 UI 组件；
- UI（主窗口/控制器）只订阅刷新结果，并决定如何刷新页面与恢复上下文。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from engine.layout import invalidate_layout_caches
from engine.resources.definition_schema_view import (
    invalidate_default_signal_cache,
    invalidate_default_struct_cache,
)
from engine.resources.ingame_save_template_schema_view import (
    invalidate_default_ingame_save_template_cache,
)
from engine.resources.level_variable_schema_view import (
    invalidate_default_level_variable_cache,
)
from engine.signal import invalidate_default_signal_repository_cache
from engine.utils.logging.logger import log_warn
from engine.resources.resource_index_builder import ResourceIndexData
from app.runtime.services.graph_data_service import get_shared_graph_data_service

from .app_state import MainWindowAppState


@dataclass(frozen=True, slots=True)
class ResourceRefreshOutcome:
    """一次资源库刷新后的结果摘要（供 UI 决策后续刷新动作）。"""

    current_package_id: str | None
    did_clear_current_package_cache: bool
    did_clear_global_resource_view_cache: bool
    did_composite_library_change: bool


class ResourceRefreshService:
    """集中处理“资源库刷新”的失效与重建步骤。"""

    @staticmethod
    def _extract_composite_library_segment(resource_library_fingerprint: str) -> str:
        fingerprint_text = str(resource_library_fingerprint or "")
        if not fingerprint_text:
            return ""
        for part in fingerprint_text.split("|"):
            if part.startswith("复合节点库:"):
                return part
        return ""

    def refresh(
        self,
        *,
        app_state: MainWindowAppState,
        package_controller: Any,
        graph_controller: Any,
        global_resource_view: Any | None,
        prebuilt_index_data: ResourceIndexData | None = None,
        prebuilt_resource_library_fingerprint: str | None = None,
    ) -> ResourceRefreshOutcome:
        """执行缓存失效与资源索引重建，并返回结果摘要。"""
        started_monotonic = float(time.monotonic())
        fingerprint_before_refresh = str(app_state.resource_manager.get_resource_library_fingerprint() or "")
        composite_segment_before_refresh = self._extract_composite_library_segment(fingerprint_before_refresh)

        # 当前视图作用域：允许跨项目存档重复资源 ID 后，必须按“共享 + 当前项目存档”构建索引。
        current_package_id_value = getattr(package_controller, "current_package_id", None)
        current_package_id_text = str(current_package_id_value or "").strip()
        active_package_id: str | None = None
        if current_package_id_text and current_package_id_text != "global_view":
            active_package_id = current_package_id_text

        log_warn(
            "[REFRESH][service] 开始：current_package_id={}, active_package_id={}, fp_before={}",
            str(current_package_id_text),
            str(active_package_id or ""),
            str(composite_segment_before_refresh or "<no-composite-segment>"),
        )

        provider = get_shared_graph_data_service(
            app_state.resource_manager,
            app_state.package_index_manager,
        )

        # 0) 代码级 Schema / Repository 缓存失效（避免刷新后仍读到旧代码资源）
        schema_invalidate_started = float(time.monotonic())
        invalidate_default_struct_cache()
        invalidate_default_signal_cache()
        invalidate_default_level_variable_cache()
        invalidate_default_ingame_save_template_cache()
        invalidate_default_signal_repository_cache()
        log_warn(
            "[REFRESH][service] step0 schema invalidate 完成：elapsed={:.2f}s",
            float(time.monotonic()) - schema_invalidate_started,
        )

        # 同步失效管理页面内基于 ResourceManager 的结构体记录快照
        #（避免“基础结构体定义/局内存档结构体定义”仍展示旧记录）
        from app.ui.graph.library_pages.management_section_struct_definitions import (
            StructDefinitionSection,
        )

        StructDefinitionSection._invalidate_struct_records_cache(app_state.resource_manager)

        # 1) 统一清理运行期缓存（内存 + 磁盘），缩短“刷新需要手动清一串缓存”的链路
        clear_cache_started = float(time.monotonic())
        removed_cache_summary = app_state.resource_manager.clear_all_caches()
        cleared_payload_count = provider.clear_all_payload_graph_data()
        current_model = graph_controller.get_current_model()
        invalidate_layout_caches(current_model)
        log_warn(
            "[REFRESH][service] step1 clear caches 完成：elapsed={:.2f}s, removed_cache_summary={}, cleared_payload_count={}",
            float(time.monotonic()) - clear_cache_started,
            str(removed_cache_summary),
            int(cleared_payload_count),
        )

        # 2) 重建资源索引并刷新指纹基线
        rebuild_index_started = float(time.monotonic())
        if prebuilt_index_data is None:
            app_state.resource_manager.rebuild_index(active_package_id=active_package_id)
        else:
            app_state.resource_manager.apply_index_snapshot(
                index_data=prebuilt_index_data,
                resource_library_fingerprint=str(prebuilt_resource_library_fingerprint or ""),
                active_package_id=active_package_id,
            )
        log_warn(
            "[REFRESH][service] step2 rebuild_index/apply_snapshot 完成：elapsed={:.2f}s",
            float(time.monotonic()) - rebuild_index_started,
        )

        fingerprint_after_refresh = str(app_state.resource_manager.get_resource_library_fingerprint() or "")
        composite_segment_after_refresh = self._extract_composite_library_segment(fingerprint_after_refresh)
        did_composite_library_change = bool(
            composite_segment_after_refresh and composite_segment_after_refresh != composite_segment_before_refresh
        )

        # 3) 失效图属性面板/引用查询等共享数据提供器缓存（避免仍展示旧图数据/旧引用列表）
        invalidate_provider_started = float(time.monotonic())
        provider.invalidate_graph()
        provider.invalidate_package_cache()
        log_warn(
            "[REFRESH][service] step3 invalidate provider 完成：elapsed={:.2f}s",
            float(time.monotonic()) - invalidate_provider_started,
        )

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

        current_package_id = current_package_id_text or None

        elapsed_total = float(time.monotonic()) - started_monotonic
        log_warn(
            "[REFRESH][service] 完成：elapsed_total={:.2f}s, fp_after={}, composite_changed={}, clear_pkg_cache={}, clear_global_cache={}",
            float(elapsed_total),
            str(composite_segment_after_refresh or "<no-composite-segment>"),
            bool(did_composite_library_change),
            bool(did_clear_current_package_cache),
            bool(did_clear_global_resource_view_cache),
        )
        return ResourceRefreshOutcome(
            current_package_id=current_package_id,
            did_clear_current_package_cache=did_clear_current_package_cache,
            did_clear_global_resource_view_cache=did_clear_global_resource_view_cache,
            did_composite_library_change=did_composite_library_change,
        )


