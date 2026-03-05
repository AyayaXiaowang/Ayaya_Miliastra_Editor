from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional, Sequence

from PyQt6 import QtCore, QtWidgets

from engine.resources.resource_manager import ResourceType
from engine.utils.resource_library_layout import get_packages_root_dir, get_shared_root_dir

from app.ui.management.section_registry import (
    MANAGEMENT_RESOURCE_BINDINGS,
    MANAGEMENT_RESOURCE_DEFAULT_SECTION_KEYS,
    MANAGEMENT_RESOURCE_ORDER,
    MANAGEMENT_RESOURCE_TITLES,
)


class PackageLibraryPreviewMixin:
    """右侧详情树的“预览（磁盘扫描）”渲染与根节点构建。"""

    def _render_empty_detail(self) -> None:
        self.header_label.setText("未选择项目存档")
        self.detail_tree.clear()

    def _render_package_detail(self, package_id: str) -> None:
        self.detail_tree.setUpdatesEnabled(False)
        self.detail_tree.clear()

        # 预览视图：默认仅展示“分类 + 计数”（保持折叠），展开时懒加载前 N 条并提供“加载更多”入口。
        if package_id == "global_view":
            self._render_global_view_overview()
        else:
            self._render_package_index_overview(package_id)
        self.detail_tree.setUpdatesEnabled(True)

    def _clear_preview_scan_cache(self) -> None:
        self._preview_scan_service.invalidate()

    def _get_preview_root_dir(self, package_id: str) -> Path | None:
        """返回该 package_id 在“预览”语义下应扫描的资源根目录（共享根 or 项目存档根）。"""
        resource_library_dir = getattr(self.rm, "resource_library_dir", None)
        if not isinstance(resource_library_dir, Path):
            return None

        normalized = str(package_id or "").strip()
        if not normalized:
            return None

        if normalized == "global_view":
            return get_shared_root_dir(resource_library_dir)
        return get_packages_root_dir(resource_library_dir) / normalized

    def _resolve_management_category_label(self, resource_key: str) -> str:
        override = self._MANAGEMENT_CATEGORY_LABEL_OVERRIDES.get(resource_key)
        if override:
            return override
        return MANAGEMENT_RESOURCE_TITLES.get(resource_key, resource_key)

    @staticmethod
    def _resolve_management_jump_section_key(binding_key: str) -> str:
        normalized = str(binding_key or "").strip()
        if not normalized:
            return ""
        mapped = MANAGEMENT_RESOURCE_DEFAULT_SECTION_KEYS.get(normalized)
        if isinstance(mapped, str) and mapped:
            return mapped
        return normalized

    @staticmethod
    def _build_management_item_marker(
        *,
        binding_key: str,
        item_id: str,
        jump_section_key: str,
    ) -> dict:
        return {
            "binding_key": str(binding_key or ""),
            "item_id": str(item_id or ""),
            "jump_section_key": str(jump_section_key or ""),
        }

    def _build_preview_management_category_map(
        self,
        *,
        package_root_dir: Path,
        shared_root_dir: Path | None,
        package_root_key: str,
        include_shared: bool,
    ) -> dict[str, tuple[Sequence[str], Optional[ResourceType]]]:
        """为“预览（磁盘扫描）”构建管理配置分类映射。

        关键点：
        - 对“具体项目存档”视图：管理配置按“共享根 + 项目存档根”合并展示，避免出现
          “项目本身没放结构体/信号文件，但实际上可用的共享定义在 UI 中看不到”的错觉；
        """
        mapping: dict[str, tuple[Sequence[str], Optional[ResourceType]]] = {}

        for resource_key in MANAGEMENT_RESOURCE_ORDER:
            resource_type = MANAGEMENT_RESOURCE_BINDINGS.get(resource_key)

            if resource_type is None:
                mapping[resource_key] = ([], None)
                continue

            if resource_key == "struct_definitions" and resource_type == ResourceType.STRUCT_DEFINITION:
                basic_ids, ingame_ids = self._preview_scan_service.get_struct_definition_ids_by_kind(
                    root_key=package_root_key,
                    root_dir=package_root_dir,
                )
                package_ids = sorted(
                    set(basic_ids).union(ingame_ids),
                    key=lambda text: text.casefold(),
                )
            else:
                package_ids = self._preview_scan_service.get_resource_ids(
                    root_key=package_root_key,
                    root_dir=package_root_dir,
                    resource_type=resource_type,
                )

            shared_ids: list[str] = []
            if (
                include_shared
                and shared_root_dir is not None
                and shared_root_dir.exists()
                and shared_root_dir.is_dir()
            ):
                if resource_key == "struct_definitions" and resource_type == ResourceType.STRUCT_DEFINITION:
                    shared_basic_ids, shared_ingame_ids = (
                        self._preview_scan_service.get_struct_definition_ids_by_kind(
                            root_key="shared",
                            root_dir=shared_root_dir,
                        )
                    )
                    shared_ids = sorted(
                        set(shared_basic_ids).union(shared_ingame_ids),
                        key=lambda text: text.casefold(),
                    )
                else:
                    shared_ids = self._preview_scan_service.get_resource_ids(
                        root_key="shared",
                        root_dir=shared_root_dir,
                        resource_type=resource_type,
                    )

            if package_ids and shared_ids:
                merged = sorted(
                    set(package_ids).union(shared_ids),
                    key=lambda text: text.casefold(),
                )
            elif package_ids:
                merged = list(package_ids)
            else:
                merged = list(shared_ids)

            mapping[resource_key] = (merged, resource_type)

        return mapping

    def _render_global_view_overview(self) -> None:
        """渲染共享资源视图的预览（分类 + 计数；展开时懒加载）。"""
        root_dir = self._get_preview_root_dir("global_view")
        if root_dir is None or not root_dir.exists() or not root_dir.is_dir():
            self.header_label.setText("共享资源目录不存在")
            return

        root_key = "shared"
        total_count = 0

        templates = self._preview_scan_service.get_resource_ids(
            root_key=root_key,
            root_dir=root_dir,
            resource_type=ResourceType.TEMPLATE,
        )
        instances = self._preview_scan_service.get_resource_ids(
            root_key=root_key,
            root_dir=root_dir,
            resource_type=ResourceType.INSTANCE,
        )
        graphs = self._preview_scan_service.get_resource_ids(
            root_key=root_key,
            root_dir=root_dir,
            resource_type=ResourceType.GRAPH,
        )

        total_count += self._add_lazy_resource_section_root("元件", ResourceType.TEMPLATE, templates)
        total_count += self._add_lazy_resource_section_root("实体摆放", ResourceType.INSTANCE, instances)
        total_count += self._add_lazy_resource_section_root("节点图", ResourceType.GRAPH, graphs)

        total_count += self._add_lazy_nested_combat_section_root(
            "战斗预设",
            {
                sub_key: (
                    self._preview_scan_service.get_resource_ids(
                        root_key=root_key,
                        root_dir=root_dir,
                        resource_type=resource_type,
                    ),
                    resource_type,
                )
                for sub_key, resource_type in self.COMBAT_RESOURCE_TYPES.items()
            },
        )

        total_count += self._add_lazy_nested_management_section_root(
            "管理配置",
            self._build_preview_management_category_map(
                package_root_dir=root_dir,
                shared_root_dir=root_dir,
                package_root_key=root_key,
                include_shared=False,
            ),
            package_root_dir=root_dir,
            shared_root_dir=root_dir,
            package_root_key=root_key,
            include_shared=False,
        )

        self.header_label.setText(f"共享资源（共 {total_count} 项）")

    def _render_package_index_overview(self, package_id: str) -> None:
        """渲染具体项目存档的预览（分类 + 计数；展开时懒加载）。"""
        root_dir = self._get_preview_root_dir(package_id)
        if root_dir is None or not root_dir.exists() or not root_dir.is_dir():
            self.header_label.setText("项目存档不存在")
            return

        pkg_info = None
        if hasattr(self.pim, "get_package_info"):
            pkg_info = self.pim.get_package_info(package_id)  # type: ignore[attr-defined]
        title = str(pkg_info.get("name") if isinstance(pkg_info, dict) else "") or str(package_id)

        root_key = str(package_id)
        total_count = 0

        templates = self._preview_scan_service.get_resource_ids(
            root_key=root_key,
            root_dir=root_dir,
            resource_type=ResourceType.TEMPLATE,
        )
        instances = self._preview_scan_service.get_resource_ids(
            root_key=root_key,
            root_dir=root_dir,
            resource_type=ResourceType.INSTANCE,
        )
        graphs = self._preview_scan_service.get_resource_ids(
            root_key=root_key,
            root_dir=root_dir,
            resource_type=ResourceType.GRAPH,
        )

        # 关卡实体：约定 ID 为 level_<package_id>；存在则单独展示并从“实体摆放”中剔除，避免重复计数。
        level_entity_id = f"level_{package_id}"
        if level_entity_id in instances:
            total_count += self._add_level_entity_row_by_id(level_entity_id)
            instances = [rid for rid in instances if rid != level_entity_id]
        else:
            self._add_simple_section("关卡实体", "(未设置)", item_count=0)

        total_count += self._add_lazy_resource_section_root("元件", ResourceType.TEMPLATE, templates)
        total_count += self._add_lazy_resource_section_root("实体摆放", ResourceType.INSTANCE, instances)
        total_count += self._add_lazy_resource_section_root("节点图", ResourceType.GRAPH, graphs)

        total_count += self._add_lazy_nested_combat_section_root(
            "战斗预设",
            {
                sub_key: (
                    self._preview_scan_service.get_resource_ids(
                        root_key=root_key,
                        root_dir=root_dir,
                        resource_type=resource_type,
                    ),
                    resource_type,
                )
                for sub_key, resource_type in self.COMBAT_RESOURCE_TYPES.items()
            },
        )

        total_count += self._add_lazy_nested_management_section_root(
            "管理配置",
            self._build_preview_management_category_map(
                package_root_dir=root_dir,
                shared_root_dir=self._get_preview_root_dir("global_view"),
                package_root_key=root_key,
                include_shared=True,
            ),
            package_root_dir=root_dir,
            shared_root_dir=self._get_preview_root_dir("global_view"),
            package_root_key=root_key,
            include_shared=True,
        )

        self.header_label.setText(f"{title}（共 {total_count} 项）")

    def _add_lazy_resource_section_root(
        self,
        section_title: str,
        resource_type: ResourceType,
        resource_ids: Sequence[str],
    ) -> int:
        """添加一个“资源分类根节点”，并在展开/默认展开时按需加载叶子条目。"""
        ordered_ids = list(resource_ids)
        item_count = len(ordered_ids)

        root_title = section_title if item_count <= 0 else f"{section_title} ({item_count})"
        root_item = QtWidgets.QTreeWidgetItem([root_title, "", "", ""])

        if item_count > 0:
            root_item.setChildIndicatorPolicy(
                QtWidgets.QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
            )
            root_item.setData(
                0,
                self._ROLE_LAZY_PAYLOAD,
                {
                    "kind": self._LAZY_KIND_RESOURCE_SECTION,
                    "section_title": section_title,
                    "resource_type": resource_type,
                    "ids": ordered_ids,
                    "next_index": 0,
                },
            )

        self.detail_tree.addTopLevelItem(root_item)
        return item_count

    def _add_lazy_nested_combat_section_root(
        self,
        root_title: str,
        category_resources_map: Mapping[str, tuple[Sequence[str], Optional[ResourceType]]],
    ) -> int:
        """添加“战斗预设”根节点，子分类在展开/默认展开时按需加载条目。"""
        root_item = QtWidgets.QTreeWidgetItem([root_title, "", "", ""])

        total_count = 0
        for resource_key in sorted(category_resources_map.keys()):
            resource_ids, resource_type = category_resources_map[resource_key]
            ordered_ids = list(resource_ids)
            if not ordered_ids:
                continue
            total_count += len(ordered_ids)

            category_label = self.COMBAT_CATEGORY_TITLES.get(resource_key, resource_key)
            category_display_title = f"{category_label} ({len(ordered_ids)})"
            category_item = QtWidgets.QTreeWidgetItem([category_display_title, "", "", ""])
            category_item.setChildIndicatorPolicy(
                QtWidgets.QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
            )

            combat_kind: Optional[str]
            if resource_key == "player_templates":
                combat_kind = "combat_player_template"
            elif resource_key == "player_classes":
                combat_kind = "combat_player_class"
            elif resource_key == "skills":
                combat_kind = "combat_skill"
            elif resource_key == "items":
                combat_kind = "combat_item"
            else:
                combat_kind = None

            category_item.setData(
                0,
                self._ROLE_LAZY_PAYLOAD,
                {
                    "kind": self._LAZY_KIND_COMBAT_CATEGORY,
                    "category_label": category_label,
                    "combat_kind": combat_kind,
                    "resource_type": resource_type,
                    "ids": ordered_ids,
                    "next_index": 0,
                },
            )
            root_item.addChild(category_item)

        if total_count > 0:
            root_item.setText(0, f"{root_title} ({total_count})")
        self.detail_tree.addTopLevelItem(root_item)
        return total_count

    def _add_lazy_nested_management_section_root(
        self,
        root_title: str,
        category_resources_map: Mapping[str, tuple[Sequence[str], Optional[ResourceType]]],
        *,
        package_root_dir: Path,
        shared_root_dir: Path | None,
        package_root_key: str,
        include_shared: bool,
    ) -> int:
        """添加“管理配置”根节点，子分类在展开时按需加载条目。"""
        root_item = QtWidgets.QTreeWidgetItem([root_title, "", "", ""])

        total_count = 0
        for resource_key in MANAGEMENT_RESOURCE_ORDER:
            resource_ids, resource_type = category_resources_map.get(resource_key, ([], None))
            ordered_ids = list(resource_ids)
            if not ordered_ids:
                continue
            # 结构体定义：按 payload 类型拆成“基础/局内存档”两个分类（与管理页一致）。
            if resource_key == "struct_definitions":
                allowed_ids = {str(sid or "").strip() for sid in ordered_ids if isinstance(sid, str) and sid}

                pkg_basic_ids, pkg_ingame_ids = self._preview_scan_service.get_struct_definition_ids_by_kind(
                    root_key=package_root_key,
                    root_dir=package_root_dir,
                )
                basic_set = set(pkg_basic_ids)
                ingame_set = set(pkg_ingame_ids)

                if (
                    include_shared
                    and shared_root_dir is not None
                    and shared_root_dir.exists()
                    and shared_root_dir.is_dir()
                ):
                    shared_basic_ids, shared_ingame_ids = (
                        self._preview_scan_service.get_struct_definition_ids_by_kind(
                            root_key="shared",
                            root_dir=shared_root_dir,
                        )
                    )
                    basic_set.update(shared_basic_ids)
                    ingame_set.update(shared_ingame_ids)

                # 以预览映射为准：仅纳入当前聚合视图的条目
                basic_set.intersection_update(allowed_ids)
                ingame_set.intersection_update(allowed_ids)
                # ingame_save 优先（更严格）
                basic_set.difference_update(ingame_set)

                basic_ids = sorted(basic_set, key=lambda text: text.casefold())
                ingame_ids = sorted(ingame_set, key=lambda text: text.casefold())

                def _append_struct_category(*, label: str, ids: list[str], jump_section_key: str) -> None:
                    nonlocal total_count
                    if not ids:
                        return
                    total_count += len(ids)
                    category_display_title = f"{label} ({len(ids)})"
                    category_item = QtWidgets.QTreeWidgetItem([category_display_title, "", "", ""])
                    category_item.setData(
                        0,
                        QtCore.Qt.ItemDataRole.UserRole + 1,
                        self._build_management_item_marker(
                            binding_key="struct_definitions",
                            item_id="",
                            jump_section_key=jump_section_key,
                        ),
                    )
                    category_item.setChildIndicatorPolicy(
                        QtWidgets.QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
                    )
                    category_item.setData(
                        0,
                        self._ROLE_LAZY_PAYLOAD,
                        {
                            "kind": self._LAZY_KIND_MANAGEMENT_CATEGORY,
                            "resource_key": "struct_definitions",
                            "category_label": label,
                            "resource_type": resource_type,
                            "ids": ids,
                            "next_index": 0,
                            "jump_section_key": jump_section_key,
                        },
                    )
                    root_item.addChild(category_item)

                _append_struct_category(
                    label="🧬 基础结构体定义",
                    ids=basic_ids,
                    jump_section_key="struct_definitions",
                )
                _append_struct_category(
                    label="💾 局内存档结构体定义",
                    ids=ingame_ids,
                    jump_section_key="ingame_struct_definitions",
                )
                continue

            total_count += len(ordered_ids)

            category_label = self._resolve_management_category_label(resource_key)
            category_display_title = f"{category_label} ({len(ordered_ids)})"
            category_item = QtWidgets.QTreeWidgetItem([category_display_title, "", "", ""])

            jump_section_key = self._resolve_management_jump_section_key(resource_key)
            category_item.setData(
                0,
                QtCore.Qt.ItemDataRole.UserRole + 1,
                self._build_management_item_marker(
                    binding_key=resource_key,
                    item_id="",
                    jump_section_key=jump_section_key,
                ),
            )
            category_item.setChildIndicatorPolicy(
                QtWidgets.QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
            )
            category_item.setData(
                0,
                self._ROLE_LAZY_PAYLOAD,
                {
                    "kind": self._LAZY_KIND_MANAGEMENT_CATEGORY,
                    "resource_key": resource_key,
                    "category_label": category_label,
                    "resource_type": resource_type,
                    "ids": ordered_ids,
                    "next_index": 0,
                    "jump_section_key": jump_section_key,
                },
            )
            root_item.addChild(category_item)

        if total_count > 0:
            root_item.setText(0, f"{root_title} ({total_count})")
        self.detail_tree.addTopLevelItem(root_item)
        return total_count

    def _add_simple_section(self, title: str, value: str, *, item_count: int = 0) -> int:
        display_title = title
        if item_count > 0:
            display_title = f"{title} ({item_count})"
        item = QtWidgets.QTreeWidgetItem([display_title, value, "", ""])
        self.detail_tree.addTopLevelItem(item)
        return item_count

    def _add_level_entity_row_by_id(self, level_entity_id: str) -> int:
        if not isinstance(level_entity_id, str) or not level_entity_id:
            self._add_simple_section("关卡实体", "(未设置)", item_count=0)
            return 0

        guid_text, graphs_text = self._get_resource_extra_info(
            ResourceType.INSTANCE,
            level_entity_id,
        )
        item = QtWidgets.QTreeWidgetItem(
            ["关卡实体", level_entity_id, guid_text, graphs_text]
        )
        item.setToolTip(1, level_entity_id)
        self._set_item_resource_kind(item, "关卡实体", level_entity_id, is_level_entity=True)
        self.detail_tree.addTopLevelItem(item)
        return 1

