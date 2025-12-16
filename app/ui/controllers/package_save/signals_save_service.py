"""信号保存服务：将 PackageView.signals 摘要聚合写回 PackageIndex.signals 与信号聚合资源。"""

from __future__ import annotations

from engine.resources.package_index import PackageIndex
from engine.resources.package_view import PackageView
from engine.resources.resource_manager import ResourceManager
from engine.resources.signal_index_helpers import sync_package_signals_to_index_and_aggregate


class SignalsSaveService:
    def __init__(self, resource_manager: ResourceManager):
        self._resource_manager = resource_manager

    def sync_to_index(self, *, package: PackageView, package_index: PackageIndex) -> None:
        """将 PackageView 中的信号配置写回到 PackageIndex.signals 摘要并落盘聚合资源。"""
        signals_dict = getattr(package, "signals", None)
        if not isinstance(signals_dict, dict):
            sync_package_signals_to_index_and_aggregate(
                self._resource_manager,
                package_index,
                {},
            )
            return

        serialized_signals: dict[str, dict] = {}
        for signal_id in signals_dict.keys():
            if not isinstance(signal_id, str) or not signal_id:
                continue
            serialized_signals[signal_id] = {}

        sync_package_signals_to_index_and_aggregate(
            self._resource_manager,
            package_index,
            serialized_signals,
        )


