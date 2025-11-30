"""信号索引与聚合资源写回辅助函数。

本模块集中封装“包级信号 → PackageIndex.signals + 聚合管理资源”的写回规则，
用于避免在 UI 控制器与管理页面中重复维护相同的逻辑。
"""

from __future__ import annotations

from typing import Dict

from engine.resources.package_index import PackageIndex


def sync_package_signals_to_index_and_aggregate(
    resource_manager: "ResourceManager",
    package_index: PackageIndex,
    serialized_signals: Dict[str, Dict],
) -> None:
    """将包级信号配置写回到 PackageIndex.signals（不再生成聚合 JSON）。

    新设计约定：
    - `serialized_signals` 为 `{signal_id: payload_dict}` 结构，但这里只关心 signal_id；
    - PackageIndex.signals 仅作为“当前包引用了哪些信号”的摘要：
      - 键：signal_id（字符串）
      - 值：空字典，占位用，不再存放完整配置；
    - 具体信号定义由 `engine.configs.specialized.signal_definitions_data` 中的
      代码级常量提供，资源库中不再写入 `ResourceType.SIGNAL` 聚合 JSON。
    """
    if not isinstance(serialized_signals, dict):
        serialized_signals = {}

    summary: Dict[str, Dict] = {}
    for signal_id in serialized_signals.keys():
        if not isinstance(signal_id, str) or not signal_id:
            continue
        summary[signal_id] = {}

    package_index.signals = summary

    management_lists = package_index.resources.management
    management_lists.setdefault("signals", [])
    # 仅用于兼容旧版本字段结构：保留字段但不再写入聚合资源 ID。
    management_lists["signals"] = []











