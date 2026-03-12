"""实体摆放页面的装饰物合并逻辑。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6 import QtWidgets

from app.common.decorations_merge import MergeDecorationsOutcome, merge_instance_decorations
from app.ui.foundation.id_generator import generate_prefixed_id
from app.ui.foundation.toast_notification import ToastNotification
from app.ui.graph.library_pages.entity_placement.constants import (
    CATEGORY_LEVEL_ENTITY,
    DEFAULT_VECTOR3,
    MERGE_CARRIER_TEMPLATE_ID_PREFIX,
    MERGE_TARGET_NEW_INSTANCE_ID,
)
from app.ui.graph.library_pages.library_scaffold import LibraryChangeEvent
from app.ui.graph.library_pages.library_view_scope import describe_resource_view_scope
from app.ui.graph.library_pages.merge_decorations_dialog import (
    MergeDecorationsDialog,
    MergeDecorationsDialogItem,
)
from engine.configs.resource_types import ResourceType
from engine.graph.models.entity_templates import get_entity_type_info
from engine.graph.models.package_model import InstanceConfig, TemplateConfig
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.package_view import PackageView
from engine.resources.resource_manager import ResourceManager
from engine.utils.resource_library_layout import get_packages_root_dir


class EntityPlacementMergeDecorationsMixin:
    """实体摆放页面装饰物合并 mixin。"""

    def _ensure_merge_carrier_template(self) -> str:
        """确保当前项目存档存在用于承载装饰物的空载体元件。"""
        if not isinstance(self.current_package, PackageView):
            raise TypeError("合并装饰物仅支持在具体项目存档（PackageView）中使用")

        package_id = str(getattr(self.current_package, "package_id", "") or "").strip()
        if not package_id:
            raise ValueError("无法解析当前项目存档 package_id")

        template_id = f"{MERGE_CARRIER_TEMPLATE_ID_PREFIX}{package_id}"
        existing = self.current_package.get_template(template_id)
        if existing is not None:
            return template_id

        template = TemplateConfig(
            template_id=template_id,
            name="空载体（装饰物合并）",
            entity_type="物件",
            description="由“合并装饰物”工具自动创建：用于承载 common_inspector.model.decorations。",
            default_graphs=[],
            default_components=[],
            entity_config={
                "render": {"model_name": "空模型", "visible": True},
            },
            metadata={
                "object_model_name": "空模型",
                "shape_editor": {"kind": "canvas_carrier"},
            },
            graph_variable_overrides={},
        )
        self.current_package.add_template(template)

        self.data_changed.emit(
            LibraryChangeEvent(
                kind="template",
                id=template_id,
                operation="create",
                context={
                    "scope": describe_resource_view_scope(self.current_package),
                    "source": "merge_decorations",
                },
            )
        )
        return template_id

    def _merge_decorations_into_one_instance(self) -> None:
        """将多个实体的 decorations 合并到同一个目标实体。"""
        package = self._get_package_view_for_merge_decorations()
        if package is None:
            return

        resource_manager = getattr(package, "resource_manager", None)
        if not isinstance(resource_manager, ResourceManager):
            self.show_warning("警告", "ResourceManager 不可用，无法执行合并。")
            return

        resource_library_dir = getattr(resource_manager, "resource_library_dir", None)
        if not isinstance(resource_library_dir, Path):
            self.show_warning("警告", "无法解析资源库根目录（resource_library_dir）。")
            return

        package_id = str(getattr(package, "package_id", "") or "").strip()
        items = self._collect_merge_decorations_dialog_items(
            package=package,
            package_id=package_id,
            resource_manager=resource_manager,
            resource_library_dir=resource_library_dir,
        )
        if not items:
            self.show_warning("提示", "当前项目存档下没有可用的实体摆放资源。")
            return

        items.sort(key=lambda it: it.display_text.casefold())
        dialog = MergeDecorationsDialog(
            items=items,
            package_id=package_id,
            default_new_name=f"装饰物合并实体_{package_id}" if package_id else "装饰物合并实体",
            parent=self,
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        target_spec = self._resolve_merge_target_from_dialog(package=package, dialog=dialog)
        if target_spec is None:
            return
        target_instance, op, include_target_existing = target_spec

        source_ids = dialog.get_selected_source_instance_ids()
        source_instances = self._collect_source_instances_for_merge(
            package=package,
            source_ids=source_ids,
            target_instance_id=target_instance.instance_id,
        )

        outcome = merge_instance_decorations(
            source_instances=source_instances,
            target_instance=target_instance,
            include_target_existing=include_target_existing,
            center=dialog.should_center(),
            center_mode=dialog.get_center_mode(),
            center_axes=dialog.get_center_axes(),
            center_policy=dialog.get_center_policy(),
        )

        updated_target = outcome.target_instance
        package.add_instance(updated_target)
        self.data_changed.emit(
            LibraryChangeEvent(
                kind="instance",
                id=updated_target.instance_id,
                operation=op,
                context={
                    "scope": describe_resource_view_scope(package),
                    "action": "merge_decorations",
                },
            )
        )

        removed_ids: list[str] = []
        if dialog.should_remove_sources():
            removed_ids = self._remove_sources_after_merge(
                package=package,
                source_ids=source_ids,
                updated_target_id=updated_target.instance_id,
            )

        self._rebuild_instances()
        self.select_instance(updated_target.instance_id)
        self._show_merge_decorations_result(outcome=outcome, updated_target=updated_target, removed_ids=removed_ids)

    def _get_package_view_for_merge_decorations(self) -> Optional[PackageView]:
        """校验并返回用于合并装饰物的 PackageView。"""
        if not isinstance(self.current_package, PackageView):
            self.show_warning("提示", "请先切换到具体项目存档视图（非 <全部资源>）再使用“合并装饰物”。")
            return None
        if self.current_category == CATEGORY_LEVEL_ENTITY:
            self.show_warning("提示", "关卡实体分类下不支持“合并装饰物”。请切换到“全部实体”或其它分类。")
            return None
        return self.current_package

    def _collect_merge_decorations_dialog_items(
        self,
        *,
        package: PackageView,
        package_id: str,
        resource_manager: ResourceManager,
        resource_library_dir: Path,
    ) -> list[MergeDecorationsDialogItem]:
        """收集合并装饰物对话框需要展示的实例条目。"""
        package_root_dir = get_packages_root_dir(resource_library_dir) / package_id
        package_root_abs = package_root_dir if package_root_dir.is_absolute() else package_root_dir.absolute()
        pkg_parts = tuple(part.casefold() for part in package_root_abs.parts)
        instance_paths = resource_manager.list_resource_file_paths(ResourceType.INSTANCE)

        items: list[MergeDecorationsDialogItem] = []
        for instance_id, instance in package.instances.items():
            if not isinstance(instance_id, str) or not instance_id:
                continue
            file_path = instance_paths.get(instance_id)
            if not isinstance(file_path, Path):
                continue
            file_abs = file_path if file_path.is_absolute() else file_path.absolute()
            if not self._is_path_under_root(file_abs=file_abs, root_abs=package_root_abs, root_parts=pkg_parts):
                continue

            deco_count = self._count_instance_decorations(instance)
            template = package.get_template(instance.template_id)
            resolved_entity_type, template_name = self._resolve_template_info_for_merge(
                template=template,
                instance=instance,
            )
            icon = get_entity_type_info(resolved_entity_type).get("icon", "📦")

            name_text = str(instance.name or "").strip() or instance_id
            template_suffix = f"（{template_name}）" if template_name else ""
            display_text = f"{icon} {name_text}{template_suffix}".strip()
            search_text = " ".join(
                token
                for token in [
                    name_text,
                    instance_id,
                    str(instance.template_id or "").strip(),
                    template_name,
                    str(deco_count),
                ]
                if token
            )

            items.append(
                MergeDecorationsDialogItem(
                    instance_id=instance_id,
                    display_text=display_text,
                    search_text=search_text,
                    decorations_count=int(deco_count),
                )
            )

        return items

    def _is_path_under_root(self, *, file_abs: Path, root_abs: Path, root_parts: tuple[str, ...]) -> bool:
        """判断文件绝对路径是否位于指定根目录下。"""
        if hasattr(file_abs, "is_relative_to"):
            return bool(file_abs.is_relative_to(root_abs))  # type: ignore[attr-defined]
        file_parts = tuple(part.casefold() for part in file_abs.parts)
        return len(file_parts) >= len(root_parts) and file_parts[: len(root_parts)] == root_parts

    def _count_instance_decorations(self, instance: InstanceConfig) -> int:
        """从实例 metadata 统计 decorations 条目数量。"""
        meta = getattr(instance, "metadata", {}) or {}
        if not isinstance(meta, dict):
            return 0
        inspector = meta.get("common_inspector") if isinstance(meta.get("common_inspector"), dict) else {}
        model = inspector.get("model") if isinstance(inspector.get("model"), dict) else {}
        decos = model.get("decorations")
        return int(len(decos)) if isinstance(decos, list) else 0

    def _resolve_template_info_for_merge(
        self,
        *,
        template: TemplateConfig | None,
        instance: InstanceConfig,
    ) -> tuple[str, str]:
        """解析用于合并对话框显示的 entity_type 与元件名称。"""
        resolved_entity_type = ""
        template_name = ""
        if template is not None:
            resolved_entity_type = str(template.entity_type or "").strip()
            template_name = str(template.name or "").strip()
            return resolved_entity_type, template_name

        meta = getattr(instance, "metadata", {}) or {}
        if isinstance(meta, dict):
            et = meta.get("entity_type")
            if isinstance(et, str):
                resolved_entity_type = et.strip()
        return resolved_entity_type, template_name

    def _resolve_merge_target_from_dialog(
        self,
        *,
        package: PackageView,
        dialog: MergeDecorationsDialog,
    ) -> Optional[tuple[InstanceConfig, str, bool]]:
        """根据对话框选择解析目标实例与操作类型。"""
        target_choice_id = dialog.get_target_instance_id()
        if target_choice_id == MERGE_TARGET_NEW_INSTANCE_ID:
            carrier_template_id = self._ensure_merge_carrier_template()
            new_instance_id = generate_prefixed_id("instance")
            target_instance = InstanceConfig(
                instance_id=new_instance_id,
                name=dialog.get_new_instance_name(),
                template_id=carrier_template_id,
                position=list(DEFAULT_VECTOR3),
                rotation=list(DEFAULT_VECTOR3),
            )
            return target_instance, "create", False

        target_instance = package.get_instance(target_choice_id)
        if target_instance is None:
            self._rebuild_instances()
            self.show_warning("提示", "目标实体不存在或已被移除，请刷新后重试。")
            return None
        return target_instance, "update", True

    def _collect_source_instances_for_merge(
        self,
        *,
        package: PackageView,
        source_ids: list[str],
        target_instance_id: str,
    ) -> list[InstanceConfig]:
        """根据源 ID 列表收集合并所需的源实例对象。"""
        source_instances: list[InstanceConfig] = []
        for sid in source_ids:
            if sid == target_instance_id:
                continue
            inst = package.get_instance(sid)
            if inst is None:
                continue
            source_instances.append(inst)
        return source_instances

    def _remove_sources_after_merge(
        self,
        *,
        package: PackageView,
        source_ids: list[str],
        updated_target_id: str,
    ) -> list[str]:
        """在合并完成后将源实例从当前包中移除并返回移除列表。"""
        window = self.window()
        app_state = getattr(window, "app_state", None) if window is not None else None
        package_index_manager = (
            getattr(app_state, "package_index_manager", None) if app_state is not None else None
        )
        if not isinstance(package_index_manager, PackageIndexManager):
            self.show_warning("警告", "无法移除源实体：PackageIndexManager 不可用。")
            return []

        removed_ids: list[str] = []
        for sid in source_ids:
            if sid == updated_target_id:
                continue
            moved_ok = package_index_manager.remove_resource_from_package(
                package.package_id,
                "instance",
                sid,
            )
            if not moved_ok:
                continue
            removed_ids.append(sid)
            package.remove_instance(sid)

        if removed_ids and hasattr(package, "clear_cache"):
            package.clear_cache()

        for rid in removed_ids:
            self.data_changed.emit(
                LibraryChangeEvent(
                    kind="instance",
                    id=rid,
                    operation="delete",
                    context={
                        "scope": describe_resource_view_scope(package),
                        "action": "merge_decorations_remove_sources",
                    },
                )
            )
        return removed_ids

    def _show_merge_decorations_result(
        self,
        *,
        outcome: MergeDecorationsOutcome,
        updated_target: InstanceConfig,
        removed_ids: list[str],
    ) -> None:
        """展示合并完成后的提示信息与可能的警告。"""
        skipped = len(outcome.skipped_instance_ids)
        removed = len(removed_ids)
        merged = len(outcome.merged_decorations)
        msg = f"已合并装饰物：{merged} 个 → {updated_target.name}"
        if skipped:
            msg += f"（跳过 {skipped} 个无装饰物实体）"
        if removed:
            msg += f"（已移除 {removed} 个源实体）"
        ToastNotification.show_message(self, msg, "success")

        if outcome.warnings:
            self.show_warning("提示", "\n".join(outcome.warnings))

