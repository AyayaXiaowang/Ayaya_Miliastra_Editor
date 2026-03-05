from __future__ import annotations

from typing import Callable, Mapping, Optional, Sequence, Tuple

from PyQt6 import QtCore, QtWidgets

from engine.resources.resource_manager import ResourceManager, ResourceType
from app.ui.management.section_registry import (
    MANAGEMENT_RESOURCE_DEFAULT_SECTION_KEYS,
    MANAGEMENT_RESOURCE_ORDER,
    MANAGEMENT_RESOURCE_TITLES,
)


SingleConfigKey = str

# 与 PackageView.single_config_fields 语义保持一致：
# 这些字段在 UI 上更适合作为“整块配置”，不逐条罗列聚合资源 ID。
SINGLE_CONFIG_RESOURCE_KEYS: set[SingleConfigKey] = {
    "currency_backpack",
    "peripheral_systems",
    "save_points",
    "level_settings",
}


DisplayNameResolver = Callable[[ResourceType, str], str]
ExtraInfoResolver = Callable[[ResourceType, str], Tuple[str, str]]


def build_management_category_items_for_tree(
    root_item: QtWidgets.QTreeWidgetItem,
    category_resources_map: Mapping[str, Tuple[Sequence[str], Optional[ResourceType]]],
    *,
    resource_manager: ResourceManager,
    mark_management_items: bool = False,
    assume_sorted: bool = False,
    display_name_resolver: Optional[DisplayNameResolver] = None,
    extra_info_resolver: Optional[ExtraInfoResolver] = None,
) -> int:
    """为“管理配置”构建右侧详情树的嵌套分组结构。

    设计目标：
    - 统一处理 signals / 单配置类字段 / 常规聚合字段三类资源；
    - 保持 PackageLibraryWidget 中“管理配置”视图的语义与统计口径不变；
    - 将具体业务遍历逻辑下沉到独立 helper，库页面只关心调用与装配。

    参数：
        root_item:
            作为“管理配置”根节点的 QTreeWidgetItem，函数会在其下追加子分类。
        category_resources_map:
            resource_key → (resource_ids, resource_type) 的映射，
            约定 key 集合与 MANAGEMENT_RESOURCE_ORDER 一致。
        resource_manager:
            用于按 resource_type / resource_id 载入聚合 JSON 与元数据。
        mark_management_items:
            为 True 时，在分类节点与叶子节点上写入“管理配置条目标记”到 UserRole+1。
            该标记同时包含：
            - binding_key（PackageIndex.resources.management 的桶 key，用于右侧摘要与所属存档）
            - jump_section_key（管理页面的 section_key，用于双击跳转）
            - item_id（叶子节点对应的资源 ID）
        assume_sorted:
            为 True 时认为传入的 resource_ids 已经排好序，避免重复排序。
        display_name_resolver / extra_info_resolver:
            可选的显示名与附加信息解析函数；若未提供，则在内部直接
            基于 ResourceManager 读取元数据进行解析。

    返回：
        本次构建的“有效条目”数量：
        - 对 signals：为信号条目总数；
        - 对单配置字段：为非空配置体总数（外围系统则为成就/排行榜/段位条目总和）；
        - 对常规聚合字段：为聚合资源条目数。
    """
    total_count = 0

    for resource_key in MANAGEMENT_RESOURCE_ORDER:
        resource_ids, resource_type = category_resources_map.get(resource_key, ([], None))
        ordered_ids = list(resource_ids)
        if not assume_sorted:
            ordered_ids.sort()
        if not ordered_ids:
            # 该分类在当前视图下完全没有资源，直接跳过。
            continue

        category_label = MANAGEMENT_RESOURCE_TITLES.get(resource_key, resource_key)
        is_single_config_category = resource_key in SINGLE_CONFIG_RESOURCE_KEYS

        if resource_key == "struct_definitions":
            category_items, category_count_for_section = _build_struct_definitions_category_items(
                resource_ids=ordered_ids,
                resource_type=resource_type,
                resource_manager=resource_manager,
                mark_management_items=mark_management_items,
            )
            if not category_items or category_count_for_section <= 0:
                continue
            for category_item in category_items:
                root_item.addChild(category_item)
            total_count += category_count_for_section
            continue

        if resource_key == "signals":
            # 信号管理：不按聚合资源计数，而是枚举聚合 JSON 中的每个信号。
            category_item, category_count_for_section = _build_signals_category_item(
                category_label=category_label,
                resource_ids=ordered_ids,
                resource_type=resource_type,
                resource_key=resource_key,
                resource_manager=resource_manager,
                mark_management_items=mark_management_items,
            )
        elif is_single_config_category and resource_type is not None:
            # 单配置字段（外围系统 / 货币背包 / 局内存档 / 关卡设置）：
            # - 不罗列 pkg_* 聚合资源 ID；
            # - 仅在存在“有效配置体”时展示该分类；
            # - 计数含义依字段类型不同而变化（见下方具体逻辑）。
            category_item, category_count_for_section = _build_single_config_category_item(
                category_label=category_label,
                resource_key=resource_key,
                resource_ids=ordered_ids,
                resource_type=resource_type,
                resource_manager=resource_manager,
            )
        else:
            # 常规管理项：按聚合资源 ID 逐条展示。
            category_item, category_count_for_section = _build_standard_management_category_item(
                category_label=category_label,
                resource_key=resource_key,
                resource_ids=ordered_ids,
                resource_type=resource_type,
                resource_manager=resource_manager,
                mark_management_items=mark_management_items,
                display_name_resolver=display_name_resolver,
                extra_info_resolver=extra_info_resolver,
            )

        if category_item is None or category_count_for_section <= 0:
            # signals / 单配置字段在“完全无有效配置体”时不展示该分类。
            continue

        if mark_management_items:
            # 为分类节点本身写入管理标记：item_id 为空表示“整类配置”。
            category_item.setData(
                0,
                QtCore.Qt.ItemDataRole.UserRole + 1,
                _build_management_item_marker(
                    binding_key=resource_key,
                    item_id="",
                    jump_section_key=_resolve_default_jump_section_key(resource_key),
                ),
            )

        root_item.addChild(category_item)
        total_count += category_count_for_section

    return total_count


def _build_management_item_marker(
    *,
    binding_key: str,
    item_id: str,
    jump_section_key: str,
) -> dict:
    """构建写入 QTreeWidgetItem.UserRole+1 的管理条目标记。"""
    return {
        "binding_key": str(binding_key or ""),
        "item_id": str(item_id or ""),
        "jump_section_key": str(jump_section_key or ""),
    }


def _resolve_default_jump_section_key(binding_key: str) -> str:
    normalized = str(binding_key or "").strip()
    if not normalized:
        return ""
    mapped = MANAGEMENT_RESOURCE_DEFAULT_SECTION_KEYS.get(normalized)
    if isinstance(mapped, str) and mapped:
        return mapped
    # 回退：多数情况下 resource_key 与 section_key 相同
    return normalized


def _build_signals_category_item(
    *,
    category_label: str,
    resource_ids: Sequence[str],
    resource_type: Optional[ResourceType],
    resource_key: str,
    resource_manager: ResourceManager,
    mark_management_items: bool,
) -> Tuple[Optional[QtWidgets.QTreeWidgetItem], int]:
    """构建“信号管理”分类节点及其子项。"""
    if resource_type is None:
        return None, 0

    all_signals: list[Tuple[str, str]] = []
    for resource_id in resource_ids:
        payload = resource_manager.load_resource(resource_type, resource_id) or {}
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            if key == "updated_at":
                continue
            if not isinstance(value, dict):
                continue
            signal_id_raw = value.get("signal_id") or key
            signal_id = str(signal_id_raw)
            signal_name_raw = value.get("signal_name") or signal_id
            signal_name = str(signal_name_raw).strip() or signal_id
            all_signals.append((signal_id, signal_name))

    if not all_signals:
        return None, 0

    # 按名称排序，便于浏览。
    all_signals.sort(key=lambda pair: pair[1])
    category_count_for_section = len(all_signals)
    category_display_title = f"{category_label} ({category_count_for_section})"

    category_item = QtWidgets.QTreeWidgetItem([category_display_title, "", "", ""])
    for signal_id, signal_name in all_signals:
        entry_item = QtWidgets.QTreeWidgetItem([category_label, signal_name, "", ""])
        entry_item.setToolTip(1, signal_id)
        if mark_management_items:
            entry_item.setData(
                0,
                QtCore.Qt.ItemDataRole.UserRole + 1,
                _build_management_item_marker(
                    binding_key=resource_key,
                    item_id=signal_id,
                    jump_section_key=_resolve_default_jump_section_key(resource_key),
                ),
            )
        category_item.addChild(entry_item)

    category_item.setExpanded(True)
    return category_item, category_count_for_section


def _build_struct_definitions_category_items(
    *,
    resource_ids: Sequence[str],
    resource_type: Optional[ResourceType],
    resource_manager: ResourceManager,
    mark_management_items: bool,
) -> Tuple[list[QtWidgets.QTreeWidgetItem], int]:
    """将结构体定义按类型拆成两个分类：基础结构体 / 局内存档结构体。"""
    if resource_type is None:
        return [], 0

    basic_ids: list[str] = []
    ingame_ids: list[str] = []
    for struct_id in resource_ids:
        payload = resource_manager.load_resource(resource_type, struct_id) or {}
        if not isinstance(payload, dict):
            continue
        struct_type = _infer_struct_type_from_payload(payload)
        if struct_type == "ingame_save":
            ingame_ids.append(struct_id)
        else:
            basic_ids.append(struct_id)

    items: list[QtWidgets.QTreeWidgetItem] = []
    total_count = 0

    if basic_ids:
        category_label = "🧬 基础结构体定义"
        category_item = QtWidgets.QTreeWidgetItem([f"{category_label} ({len(basic_ids)})", "", "", ""])
        if mark_management_items:
            category_item.setData(
                0,
                QtCore.Qt.ItemDataRole.UserRole + 1,
                _build_management_item_marker(
                    binding_key="struct_definitions",
                    item_id="",
                    jump_section_key="struct_definitions",
                ),
            )
        for struct_id in basic_ids:
            payload = resource_manager.load_resource(resource_type, struct_id) or {}
            display_name = _get_struct_display_name(struct_id, payload)
            entry_item = QtWidgets.QTreeWidgetItem([category_label, display_name, "", ""])
            entry_item.setToolTip(1, struct_id)
            if mark_management_items:
                entry_item.setData(
                    0,
                    QtCore.Qt.ItemDataRole.UserRole + 1,
                    _build_management_item_marker(
                        binding_key="struct_definitions",
                        item_id=struct_id,
                        jump_section_key="struct_definitions",
                    ),
                )
            category_item.addChild(entry_item)
        items.append(category_item)
        total_count += len(basic_ids)

    if ingame_ids:
        category_label = "💾 局内存档结构体定义"
        category_item = QtWidgets.QTreeWidgetItem([f"{category_label} ({len(ingame_ids)})", "", "", ""])
        if mark_management_items:
            category_item.setData(
                0,
                QtCore.Qt.ItemDataRole.UserRole + 1,
                _build_management_item_marker(
                    binding_key="struct_definitions",
                    item_id="",
                    jump_section_key="ingame_struct_definitions",
                ),
            )
        for struct_id in ingame_ids:
            payload = resource_manager.load_resource(resource_type, struct_id) or {}
            display_name = _get_struct_display_name(struct_id, payload)
            entry_item = QtWidgets.QTreeWidgetItem([category_label, display_name, "", ""])
            entry_item.setToolTip(1, struct_id)
            if mark_management_items:
                entry_item.setData(
                    0,
                    QtCore.Qt.ItemDataRole.UserRole + 1,
                    _build_management_item_marker(
                        binding_key="struct_definitions",
                        item_id=struct_id,
                        jump_section_key="ingame_struct_definitions",
                    ),
                )
            category_item.addChild(entry_item)
        items.append(category_item)
        total_count += len(ingame_ids)

    return items, total_count


def _infer_struct_type_from_payload(payload: Mapping[str, object]) -> str:
    raw_value = payload.get("struct_ype")
    if isinstance(raw_value, str) and raw_value.strip():
        return raw_value.strip()
    raw_struct_type = payload.get("struct_type")
    if isinstance(raw_struct_type, str) and raw_struct_type.strip():
        return raw_struct_type.strip()
    return "basic"


def _get_struct_display_name(struct_id: str, payload: object) -> str:
    if isinstance(payload, dict):
        name_value = payload.get("name")
        if isinstance(name_value, str) and name_value.strip():
            return name_value.strip()
        struct_name_value = payload.get("struct_name")
        if isinstance(struct_name_value, str) and struct_name_value.strip():
            return struct_name_value.strip()
    return str(struct_id or "")


def _build_single_config_category_item(
    *,
    category_label: str,
    resource_key: str,
    resource_ids: Sequence[str],
    resource_type: ResourceType,
    resource_manager: ResourceManager,
) -> Tuple[Optional[QtWidgets.QTreeWidgetItem], int]:
    """构建单配置类管理字段（外围系统 / 货币背包 / 局内存档 / 关卡设置）的分类节点。

    统计口径：
        - 外围系统（peripheral_systems）：
            成就 / 排行榜 / 段位三者条目数之和；
        - 其他字段：
            非空配置体的数量（通常等于“已配置此项的存档数”）。

    若所有聚合资源均为空或仅包含元数据，则返回 (None, 0)，外层调用方据此跳过该分类。
    """
    non_empty_resource_ids: list[str] = []
    total_items_in_category = 0

    for resource_id in resource_ids:
        payload = resource_manager.load_resource(resource_type, resource_id) or {}
        if not isinstance(payload, dict):
            continue

        if resource_key == "peripheral_systems":
            # 支持两种结构：
            # - 聚合结构：{"achievements": [...], "leaderboards": [...], "ranks": [...]}
            # - 模板字典结构：{system_id: {leaderboard_settings/competitive_rank_settings/achievement_settings}, ...}
            if any(key in payload for key in ("achievements", "leaderboards", "ranks")):
                achievements = payload.get("achievements", [])
                leaderboards = payload.get("leaderboards", [])
                ranks = payload.get("ranks", [])

                achievements_count = len(achievements) if isinstance(achievements, list) else 0
                leaderboards_count = len(leaderboards) if isinstance(leaderboards, list) else 0
                ranks_count = len(ranks) if isinstance(ranks, list) else 0

                record_count = achievements_count + leaderboards_count + ranks_count
            else:
                # 模板字典结构：逐模板汇总三个子配置中的条目数量。
                record_count = 0
                for system_payload in payload.values():
                    if not isinstance(system_payload, dict):
                        continue
                    achievement_cfg = system_payload.get("achievement_settings", {})
                    leaderboard_cfg = system_payload.get("leaderboard_settings", {})
                    rank_cfg = system_payload.get("competitive_rank_settings", {})

                    achievements_items = (
                        achievement_cfg.get("items", []) if isinstance(achievement_cfg, dict) else []
                    )
                    leaderboard_items = (
                        leaderboard_cfg.get("records", []) if isinstance(leaderboard_cfg, dict) else []
                    )
                    score_groups = (
                        rank_cfg.get("score_groups", []) if isinstance(rank_cfg, dict) else []
                    )

                    if isinstance(achievements_items, list):
                        record_count += len(achievements_items)
                    if isinstance(leaderboard_items, list):
                        record_count += len(leaderboard_items)
                    if isinstance(score_groups, list):
                        record_count += len(score_groups)

            if record_count <= 0:
                # 该聚合资源中完全没有外围系统条目，视为“空配置”。
                continue

            total_items_in_category += record_count
        else:
            # 对于货币背包 / 局内存档 / 关卡设置等字段，只要配置体字典非空即视为“已配置”。
            if not payload:
                continue
            total_items_in_category += 1

        non_empty_resource_ids.append(resource_id)

    if total_items_in_category <= 0:
        # 所有聚合资源均为空（或仅包含元数据），该管理分类在当前视图下视为“未使用”，不展示。
        return None, 0

    category_display_title = f"{category_label} ({total_items_in_category})"
    category_item = QtWidgets.QTreeWidgetItem([category_display_title, "", "", ""])

    # 将底层聚合资源 ID 折叠到 tooltip 中，仅在需要排查实现细节时可见。
    if non_empty_resource_ids:
        category_item.setToolTip(1, ", ".join(non_empty_resource_ids))

    return category_item, total_items_in_category


def _build_standard_management_category_item(
    *,
    category_label: str,
    resource_key: str,
    resource_ids: Sequence[str],
    resource_type: Optional[ResourceType],
    resource_manager: ResourceManager,
    mark_management_items: bool,
    display_name_resolver: Optional[DisplayNameResolver],
    extra_info_resolver: Optional[ExtraInfoResolver],
) -> Tuple[Optional[QtWidgets.QTreeWidgetItem], int]:
    """构建常规管理配置分类：按聚合资源 ID 逐条展示。"""
    category_count_for_section = len(resource_ids)
    if category_count_for_section <= 0:
        return None, 0

    category_display_title = f"{category_label} ({category_count_for_section})"
    category_item = QtWidgets.QTreeWidgetItem([category_display_title, "", "", ""])

    for resource_id in resource_ids:
        if resource_type is not None and display_name_resolver is not None:
            display_name = display_name_resolver(resource_type, resource_id)
        elif resource_type is not None:
            metadata = resource_manager.get_resource_metadata(resource_type, resource_id)
            if metadata and metadata.get("name"):
                display_name = str(metadata["name"])
            else:
                display_name = resource_id
        else:
            display_name = resource_id

        guid_text = ""
        graphs_text = ""
        if resource_type is not None and resource_type is not ResourceType.GRAPH:
            if extra_info_resolver is not None:
                guid_text, graphs_text = extra_info_resolver(resource_type, resource_id)
            else:
                guid_text, graphs_text = _resolve_default_extra_info(
                    resource_manager,
                    resource_type,
                    resource_id,
                )

        entry_item = QtWidgets.QTreeWidgetItem(
            [category_label, display_name, guid_text, graphs_text]
        )
        entry_item.setToolTip(1, resource_id)
        if mark_management_items:
            entry_item.setData(
                0,
                QtCore.Qt.ItemDataRole.UserRole + 1,
                (resource_key, resource_id),
            )
        category_item.addChild(entry_item)

    return category_item, category_count_for_section


def _resolve_default_extra_info(
    resource_manager: ResourceManager,
    resource_type: ResourceType,
    resource_id: str,
) -> Tuple[str, str]:
    """在未提供 extra_info_resolver 的情况下，根据元数据生成 GUID 与挂载节点图信息。"""
    guid_text = ""
    graphs_text = ""

    metadata = resource_manager.get_resource_metadata(resource_type, resource_id)
    if not metadata:
        return guid_text, graphs_text

    raw_guid = metadata.get("guid")
    if raw_guid:
        guid_text = str(raw_guid)

    raw_graph_ids = metadata.get("graph_ids") or []
    if isinstance(raw_graph_ids, list) and raw_graph_ids:
        graph_id_strings: list[str] = []
        for graph_id in raw_graph_ids:
            if isinstance(graph_id, str):
                graph_id_strings.append(graph_id)
        graphs_text = ", ".join(graph_id_strings)

    return guid_text, graphs_text



