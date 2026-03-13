"""实体摆放页面的实例操作逻辑。"""

from __future__ import annotations

import copy
import types
from typing import Optional

from PyQt6 import QtCore, QtWidgets

from app.ui.foundation import input_dialogs
from app.ui.foundation.id_generator import generate_prefixed_id
from app.ui.foundation.toast_notification import ToastNotification
from app.ui.forms.schema_dialog import FormDialogBuilder
from app.ui.graph.library_pages.entity_placement.constants import (
    CATEGORY_LEVEL_ENTITY,
    DEFAULT_VECTOR3,
    INSTANCE_ID_ROLE,
    IS_SHARED_INSTANCE_ROLE,
    NEW_INSTANCE_DIALOG_SIZE,
    POSITION_EDITOR_MAX,
    POSITION_EDITOR_MIN,
    ROTATION_EDITOR_MAX,
    ROTATION_EDITOR_MIN,
)
from app.ui.graph.library_pages.library_scaffold import LibraryChangeEvent
from app.ui.graph.library_pages.library_view_scope import describe_resource_view_scope
from engine.configs.resource_types import ResourceType
from engine.graph.models.entity_templates import get_template_library_entity_types
from engine.graph.models.package_model import InstanceConfig, TemplateConfig
from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.package_view import PackageView
from engine.resources.resource_manager import ResourceManager


class EntityPlacementInstanceOpsMixin:
    """实体摆放页面实例操作 mixin。"""

    def _current_instance_id(self) -> Optional[str]:
        """返回当前列表选中的实例 ID。"""
        current_item = self.entity_list.currentItem()
        if current_item is None:
            return None
        instance_id = current_item.data(INSTANCE_ID_ROLE)
        return instance_id if isinstance(instance_id, str) else None

    def select_instance(self, instance_id: str) -> None:
        """在列表中选中并滚动到指定实例。"""
        for row in range(self.entity_list.count()):
            item = self.entity_list.item(row)
            if item and item.data(INSTANCE_ID_ROLE) == instance_id:
                self.entity_list.setCurrentRow(row)
                self.entity_list.scrollToItem(
                    item,
                    QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter,
                )
                self._emit_current_selection_or_clear()
                break

    def _prompt_new_instance(self) -> Optional[InstanceConfig]:
        """弹出对话框收集新实体信息并返回实例配置。"""
        if not self.current_package:
            return None

        builder = FormDialogBuilder(self, "新建实体", fixed_size=NEW_INSTANCE_DIALOG_SIZE)
        allowed_types = set(get_template_library_entity_types())
        templates = [
            template
            for template in self.current_package.templates.values()
            if template.entity_type in allowed_types
        ]

        template_combo = builder.add_combo_box(
            "选择元件:",
            [f"{template.name} ({template.entity_type})" for template in templates] or [],
        )
        for index, template in enumerate(templates):
            template_combo.setItemData(index, template.template_id)

        name_edit = builder.add_line_edit("实体名称:", "")
        pos_editors = builder.add_vector3_editor(
            "位置",
            list(DEFAULT_VECTOR3),
            minimum=POSITION_EDITOR_MIN,
            maximum=POSITION_EDITOR_MAX,
        )
        rot_editors = builder.add_vector3_editor(
            "旋转",
            list(DEFAULT_VECTOR3),
            minimum=ROTATION_EDITOR_MIN,
            maximum=ROTATION_EDITOR_MAX,
        )

        selected_template: Optional[TemplateConfig] = None

        def on_template_changed(index: int) -> None:
            """根据元件选择更新默认实体名称。"""
            nonlocal selected_template
            if index < 0:
                selected_template = None
                return
            template_id = template_combo.itemData(index)
            selected_template = self.current_package.get_template(template_id)
            if not selected_template:
                return
            instance_count = len(self.current_package.instances) + 1
            name_edit.setText(f"{selected_template.name}_{instance_count}")

        template_combo.currentIndexChanged.connect(on_template_changed)
        if template_combo.count() > 0:
            on_template_changed(template_combo.currentIndex())

        def _validate(dialog_self):
            """校验对话框输入合法性。"""
            template_id = template_combo.itemData(template_combo.currentIndex())
            if not template_id:
                dialog_self.show_error("请选择元件")
                return False
            if not name_edit.text().strip():
                dialog_self.show_error("请输入实体名称")
                return False
            return True

        builder.dialog.validate = types.MethodType(_validate, builder.dialog)
        if not builder.exec():
            return None

        template_id = template_combo.itemData(template_combo.currentIndex())
        if not template_id:
            return None
        template = self.current_package.get_template(template_id)
        if not template:
            return None

        return InstanceConfig(
            instance_id=generate_prefixed_id("instance"),
            name=name_edit.text().strip(),
            template_id=template.template_id,
            position=[editor.value() for editor in pos_editors],
            rotation=[editor.value() for editor in rot_editors],
        )

    def _add_from_template(self) -> None:
        """从元件添加实体或在关卡实体分类下创建关卡实体。"""
        if not self.current_package:
            self.show_warning("警告", "请先选择或创建存档")
            return

        if self.current_category == CATEGORY_LEVEL_ENTITY:
            self._ensure_level_entity_exists()
            self._rebuild_instances()
            self._emit_current_selection_or_clear()
            self.data_changed.emit(
                LibraryChangeEvent(
                    kind="level_entity",
                    id="",
                    operation="update",
                    context={
                        "scope": describe_resource_view_scope(self.current_package),
                        "action": "ensure_level_entity",
                    },
                )
            )
            return

        allowed_types = set(get_template_library_entity_types())
        available_templates = [
            t for t in self.current_package.templates.values() if t.entity_type in allowed_types
        ]
        if not available_templates:
            self.show_warning("警告", "请先在元件库中创建元件")
            return

        instance = self._prompt_new_instance()
        if not instance:
            return

        self.current_package.add_instance(instance)
        self._rebuild_instances()
        self.show_info("成功", f"已添加实体: {instance.name}")
        self.data_changed.emit(
            LibraryChangeEvent(
                kind="instance",
                id=instance.instance_id,
                operation="create",
                context={"scope": describe_resource_view_scope(self.current_package)},
            )
        )

    def _duplicate_instance(self) -> None:
        """复制当前选中的实体并生成新的实例 ID。"""
        if not self.current_package:
            self.show_warning("警告", "请先选择或创建存档")
            return

        instance_id = self._current_instance_id()
        if not instance_id:
            self.show_warning("提示", "请先选择要复制的实体")
            return

        instance = self.current_package.get_instance(instance_id)
        if instance is None:
            self._rebuild_instances()
            return

        metadata = getattr(instance, "metadata", {}) or {}
        if isinstance(metadata, dict) and metadata.get("is_level_entity"):
            self.show_warning("提示", "关卡实体不支持复制（每个存档仅允许一个）。")
            return

        new_instance_id = generate_prefixed_id("instance")
        new_name = f"{instance.name} - 副本"

        new_metadata = copy.deepcopy(metadata) if isinstance(metadata, dict) else {}
        if isinstance(new_metadata, dict):
            new_metadata.pop("guid", None)
            new_metadata.pop("is_level_entity", None)

        new_instance = InstanceConfig(
            instance_id=new_instance_id,
            name=new_name,
            template_id=str(getattr(instance, "template_id", "") or ""),
            position=list(getattr(instance, "position", list(DEFAULT_VECTOR3)) or list(DEFAULT_VECTOR3)),
            rotation=list(getattr(instance, "rotation", list(DEFAULT_VECTOR3)) or list(DEFAULT_VECTOR3)),
            override_variables=copy.deepcopy(getattr(instance, "override_variables", []) or []),
            additional_graphs=list(getattr(instance, "additional_graphs", []) or []),
            additional_components=copy.deepcopy(getattr(instance, "additional_components", []) or []),
            metadata=new_metadata if isinstance(new_metadata, dict) else {},
            graph_variable_overrides=copy.deepcopy(getattr(instance, "graph_variable_overrides", {}) or {}),
        )

        self.current_package.add_instance(new_instance)
        self._rebuild_instances()
        self.select_instance(new_instance_id)
        self.data_changed.emit(
            LibraryChangeEvent(
                kind="instance",
                id=new_instance_id,
                operation="create",
                context={
                    "scope": describe_resource_view_scope(self.current_package),
                    "source": "duplicate",
                },
            )
        )
        ToastNotification.show_message(self, f"已复制实体：{new_name}", "success")

    def _rename_instance(self) -> None:
        """重命名当前选中的实体并写回 name 字段。"""
        if not self.current_package:
            self.show_warning("警告", "请先选择或创建存档")
            return

        instance_id = self._current_instance_id()
        if not instance_id:
            self.show_warning("提示", "请先选择要重命名的实体")
            return

        instance = self.current_package.get_instance(instance_id)
        if instance is None:
            self._rebuild_instances()
            return

        old_name = str(getattr(instance, "name", "") or "").strip() or instance_id
        new_name = input_dialogs.prompt_text(
            self,
            "重命名实体",
            "请输入新的实体名称:",
            text=old_name,
        )
        if not new_name:
            return
        new_name = str(new_name).strip()
        if not new_name or new_name == old_name:
            return

        instance.name = new_name
        self._rebuild_instances()
        self.select_instance(instance_id)
        self.data_changed.emit(
            LibraryChangeEvent(
                kind="instance",
                id=instance_id,
                operation="update",
                context={
                    "scope": describe_resource_view_scope(self.current_package),
                    "action": "rename",
                },
            )
        )
        ToastNotification.show_message(self, f"已重命名实体：{new_name}", "info")

    def _change_selected_instance_owner(self) -> None:
        """修改当前选中实体的归属位置并触发资源移动。"""
        if not self.current_package:
            self.show_warning("警告", "请先选择或创建存档")
            return

        instance_id = self._current_instance_id()
        if not instance_id:
            self.show_warning("提示", "请先选择要移动的实体")
            return

        if self._is_level_entity_instance_id(instance_id):
            self.show_warning("提示", "关卡实体请在右侧属性面板中修改“所属存档/归属位置”。")
            return

        window = self.window()
        app_state = getattr(window, "app_state", None) if window is not None else None
        package_index_manager = (
            getattr(app_state, "package_index_manager", None) if app_state is not None else None
        )
        if not isinstance(package_index_manager, PackageIndexManager):
            self.show_warning("警告", "无法移动：PackageIndexManager 不可用。")
            return

        previous_owner = package_index_manager.get_resource_owner_root_id(
            resource_type="instance",
            resource_id=instance_id,
        )

        packages = package_index_manager.list_packages()
        choice_labels: list[str] = ["🌐 共享（shared）"]
        label_to_root_id: dict[str, str] = {"🌐 共享（shared）": "shared"}
        for pkg in packages:
            package_id = pkg.get("package_id")
            if not isinstance(package_id, str) or not package_id:
                continue
            display_name = str(pkg.get("name") or package_id).strip() or package_id
            label = f"{display_name}（{package_id}）"
            choice_labels.append(label)
            label_to_root_id[label] = package_id

        current_index = 0
        if previous_owner == "shared":
            current_index = 0
        elif isinstance(previous_owner, str) and previous_owner:
            for idx, label in enumerate(choice_labels):
                if label_to_root_id.get(label) == previous_owner:
                    current_index = idx
                    break

        selected_label = input_dialogs.prompt_item(
            self,
            "移动实体（所属存档）",
            "请选择目标归属位置:",
            choice_labels,
            current_index=current_index,
            editable=False,
        )
        if not selected_label:
            return

        target_root_id = label_to_root_id.get(selected_label, "")
        if not target_root_id:
            return
        if target_root_id == previous_owner:
            return

        previous_label = "🌐 共享" if previous_owner == "shared" else (previous_owner or "(未知)")
        next_label = "🌐 共享" if target_root_id == "shared" else target_root_id
        if not self.confirm(
            "确认切换所属存档",
            f"即将把实体 '{instance_id}' 的归属从「{previous_label}」切换到「{next_label}」。\n\n确定要继续吗？",
        ):
            return

        handler = getattr(window, "_on_instance_package_membership_changed", None) if window is not None else None
        if callable(handler):
            handler(instance_id, target_root_id, True)
        else:
            moved = package_index_manager.move_resource_to_root(target_root_id, "instance", instance_id)
            if not moved:
                self.show_warning("警告", "移动失败：未找到资源文件或目标目录不可用。")
                return
            if hasattr(self.current_package, "clear_cache"):
                self.current_package.clear_cache()
            self._rebuild_instances()

        ToastNotification.show_message(self, "归属已更新。", "info")

    def _locate_issues_for_selected_instance(self) -> None:
        """打开验证面板并定位到当前实体相关的问题。"""
        instance_id = self._current_instance_id()
        if not instance_id:
            self.show_warning("提示", "请先选择要定位问题的实体")
            return
        window = self.window()
        locate = getattr(window, "_locate_issues_for_resource_id", None) if window is not None else None
        if callable(locate):
            locate(instance_id)

    def _delete_instance(self) -> None:
        """删除当前选中实体并按视图语义执行移除或物理删除。"""
        instance_id = self._current_instance_id()
        if not instance_id:
            self.show_warning("警告", "请先选择要删除的实体")
            return

        current_item = self.entity_list.currentItem()
        is_shared_instance = bool(current_item.data(IS_SHARED_INSTANCE_ROLE)) if current_item is not None else False
        if isinstance(self.current_package, PackageView) and is_shared_instance:
            self.show_warning(
                "提示",
                "该实体属于【共享】资源，无法在“具体存档”视图下删除。\n\n"
                "如需删除共享实体，请切换到 <全部资源> 视图执行全局删除；\n"
                "如需让实体仅属于当前存档，请在右侧属性面板中修改其“所属存档/归属位置”。",
            )
            return

        instance = self.current_package.get_instance(instance_id)
        if not instance:
            return

        metadata = getattr(instance, "metadata", {}) or {}
        if isinstance(metadata, dict) and metadata.get("is_level_entity"):
            self.show_warning("警告", "关卡实体不允许在此处删除，请通过存档管理与索引工具维护。")
            return

        if not self.confirm("确认删除", f"确定要删除实体 '{instance.name}' 吗？"):
            return

        if isinstance(self.current_package, PackageView):
            window = self.window()
            package_index_manager_candidate = (
                getattr(window, "package_index_manager", None) if window is not None else None
            )
            if not isinstance(package_index_manager_candidate, PackageIndexManager):
                self.show_warning(
                    "警告",
                    "无法从当前存档移除实体：未找到 PackageIndexManager（无法执行文件移动）。",
                )
                return

            moved_ok = package_index_manager_candidate.remove_resource_from_package(
                self.current_package.package_id,
                "instance",
                instance_id,
            )
            if not moved_ok:
                self.show_warning(
                    "警告",
                    "无法从当前存档移除实体：资源文件未找到或移动失败。",
                )
                return

            self.current_package.remove_instance(instance_id)
            if hasattr(self.current_package, "clear_cache"):
                self.current_package.clear_cache()

        elif isinstance(self.current_package, GlobalResourceView):
            resource_manager_candidate = getattr(self.current_package, "resource_manager", None)
            if not isinstance(resource_manager_candidate, ResourceManager):
                self.show_warning("警告", "当前视图不支持删除实体：resource_manager 不可用。")
                return

            resource_manager_candidate.delete_resource(ResourceType.INSTANCE, instance_id)
            self.current_package.remove_instance(instance_id)
            if hasattr(self.current_package, "clear_cache"):
                self.current_package.clear_cache()

        self._rebuild_instances()
        self.data_changed.emit(
            LibraryChangeEvent(
                kind="instance",
                id=instance_id,
                operation="delete",
                context={"scope": describe_resource_view_scope(self.current_package)},
            )
        )
        ToastNotification.show_message(self, f"已删除实体 '{instance.name}'。", "success")

