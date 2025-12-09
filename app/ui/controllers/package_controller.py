"""存档控制器 - 管理存档的生命周期"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Iterable
from datetime import datetime

from PyQt6 import QtCore, QtWidgets

from engine.resources.resource_manager import ResourceManager, ResourceType
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.package_index import PackageIndex
from engine.resources.package_view import PackageView
from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.signal_index_helpers import (
    sync_package_signals_to_index_and_aggregate,
)
from engine.resources.unclassified_resource_view import UnclassifiedResourceView
from engine.resources.ingame_save_template_schema_view import (
    get_default_ingame_save_template_schema_view,
    update_default_template_id,
)
from ui.foundation import dialog_utils, input_dialogs
from ui.foundation.id_generator import generate_prefixed_id
from ui.management.section_registry import MANAGEMENT_RESOURCE_BINDINGS


@dataclass
class PackageDirtyState:
    """记录当前存档待落盘的脏块信息。"""

    graph_dirty: bool = False
    template_ids: set[str] = field(default_factory=set)
    instance_ids: set[str] = field(default_factory=set)
    level_entity_dirty: bool = False
    combat_dirty: bool = False
    management_keys: set[str] = field(default_factory=set)
    signals_dirty: bool = False
    index_dirty: bool = False
    full_management_sync: bool = False

    def is_empty(self) -> bool:
        return not (
            self.graph_dirty
            or self.template_ids
            or self.instance_ids
            or self.level_entity_dirty
            or self.combat_dirty
            or self.management_keys
            or self.signals_dirty
            or self.index_dirty
            or self.full_management_sync
        )

    def should_flush_property_panel(self) -> bool:
        return bool(
            self.graph_dirty
            or self.template_ids
            or self.instance_ids
            or self.level_entity_dirty
        )

    def snapshot(self) -> "PackageDirtyState":
        """生成当前脏状态的浅拷贝，便于保存时使用。"""
        return PackageDirtyState(
            graph_dirty=self.graph_dirty,
            template_ids=set(self.template_ids),
            instance_ids=set(self.instance_ids),
            level_entity_dirty=self.level_entity_dirty,
            combat_dirty=self.combat_dirty,
            management_keys=set(self.management_keys),
            signals_dirty=self.signals_dirty,
            index_dirty=self.index_dirty,
            full_management_sync=self.full_management_sync,
        )

    def clear(self) -> None:
        self.graph_dirty = False
        self.template_ids.clear()
        self.instance_ids.clear()
        self.level_entity_dirty = False
        self.combat_dirty = False
        self.management_keys.clear()
        self.signals_dirty = False
        self.index_dirty = False
        self.full_management_sync = False


class PackageController(QtCore.QObject):
    """存档生命周期管理控制器"""
    
    # 信号定义
    package_loaded = QtCore.pyqtSignal(str)  # package_id
    package_saved = QtCore.pyqtSignal()
    package_list_changed = QtCore.pyqtSignal()
    title_update_requested = QtCore.pyqtSignal(str)  # new_title
    request_save_current_graph = QtCore.pyqtSignal()  # 请求保存当前图
    
    def __init__(
        self, 
        workspace: Path,
        resource_manager: ResourceManager,
        package_index_manager: PackageIndexManager,
        parent: Optional[QtCore.QObject] = None
    ):
        super().__init__(parent)
        
        self.workspace_path = workspace
        self.resource_manager = resource_manager
        self.package_index_manager = package_index_manager
        
        # 当前存档状态
        self.current_package_index: Optional[PackageIndex] = None
        self.current_package: Optional[PackageView] = None
        self.current_package_id: Optional[str] = None
        self.dirty_state = PackageDirtyState()
        
        # 用于获取当前编辑对象（由主窗口设置）
        self.get_current_graph_container = None
        self.get_property_panel_object_type = None
        # 用于在保存前刷新右侧属性面板中使用去抖写回的基础信息编辑内容
        self.flush_current_resource_panel: Optional[Callable[[], None]] = None
        # 在检测到外部资源库变更时由主窗口注入的刷新回调
        self.on_external_resource_change: Optional[Callable[[], None]] = None

    def reset_dirty_state(self) -> None:
        """清空当前存档的脏标记。"""
        self.dirty_state.clear()

    def mark_graph_dirty(self) -> None:
        self.dirty_state.graph_dirty = True

    def clear_graph_dirty(self) -> None:
        self.dirty_state.graph_dirty = False

    def mark_template_dirty(self, template_id: Optional[str]) -> None:
        if isinstance(template_id, str) and template_id:
            self.dirty_state.template_ids.add(template_id)

    def mark_instance_dirty(self, instance_id: Optional[str]) -> None:
        if isinstance(instance_id, str) and instance_id:
            self.dirty_state.instance_ids.add(instance_id)

    def mark_level_entity_dirty(self, instance_id: Optional[str]) -> None:
        if isinstance(instance_id, str) and instance_id:
            self.dirty_state.level_entity_dirty = True
            self.dirty_state.instance_ids.add(instance_id)

    def mark_management_dirty(self, keys: Iterable[str]) -> None:
        for key in keys:
            if isinstance(key, str) and key:
                self.dirty_state.management_keys.add(key)

    def mark_combat_dirty(self) -> None:
        self.dirty_state.combat_dirty = True

    def mark_signals_dirty(self) -> None:
        self.dirty_state.signals_dirty = True

    def mark_index_dirty(self) -> None:
        self.dirty_state.index_dirty = True

    def mark_resource_dirty(self, object_type: Optional[str], object_id: Optional[str]) -> None:
        if object_type == "template":
            self.mark_template_dirty(object_id)
        elif object_type in ("instance", "level_entity"):
            self.mark_instance_dirty(object_id)
            if object_type == "level_entity":
                self.dirty_state.level_entity_dirty = True

    def _build_full_dirty_snapshot(self) -> PackageDirtyState:
        snapshot = PackageDirtyState(
            graph_dirty=True,
            combat_dirty=True,
            signals_dirty=True,
            index_dirty=True,
            full_management_sync=True,
        )

        if self.get_current_graph_container and self.get_property_panel_object_type:
            container = self.get_current_graph_container()
            object_type = self.get_property_panel_object_type()
            if object_type == "template" and hasattr(container, "template_id"):
                snapshot.template_ids.add(container.template_id)
            elif object_type in ("instance", "level_entity") and hasattr(container, "instance_id"):
                snapshot.instance_ids.add(container.instance_id)
                if object_type == "level_entity":
                    snapshot.level_entity_dirty = True
        return snapshot

    def _sync_fingerprint_before_save(self) -> None:
        """在保存前同步资源库指纹基线。

        设计说明：
        - 当代码修改资源后，FileWatcherManager 已检测到变化并刷新了 UI；
        - 此时 UI 显示的内容已经是最新的，保存操作不会覆盖任何有效数据；
        - 因此在保存前先将指纹基线更新为当前磁盘状态，避免误判为"外部修改"。
        """
        if self.resource_manager.has_resource_library_changed():
            print(
                "[PACKAGE-SAVE] 检测到资源库指纹变化，同步基线后继续保存"
            )
            self.resource_manager.refresh_resource_library_fingerprint()
    
    def load_initial_package(self) -> None:
        """加载初始存档"""
        packages = self.package_index_manager.list_packages()
        
        if not packages:
            # 不创建默认存档，保持空白
            self.package_list_changed.emit()
            return
        
        # 加载最近的或第一个（支持全局视图 global_view 的恢复）
        last_id = self.package_index_manager.get_last_opened_package()
        if last_id == "global_view":
            self.load_package("global_view")
        elif last_id == "unclassified_view":
            self.load_package("unclassified_view")
        elif last_id and any(p["package_id"] == last_id for p in packages):
            self.load_package(last_id)
        else:
            self.load_package(packages[0]["package_id"])
        
        self.package_list_changed.emit()
    
    def load_package(self, package_id: str) -> None:
        """加载存档或全局视图"""
        # 保存当前存档
        if self.current_package and self.current_package_id and self.current_package_id != "global_view":
            self.save_package()
        self.reset_dirty_state()
        
        # 检查是否是特殊浏览模式
        if package_id == "global_view":
            self.current_package_index = None
            self.current_package = GlobalResourceView(self.resource_manager)
            self.current_package_id = package_id
            
            # 更新标题
            self.title_update_requested.emit("<全部资源>")
            # 记录最近打开为全局视图
            self.package_index_manager.set_last_opened_package("global_view")
        elif package_id == "unclassified_view":
            self.current_package_index = None
            self.current_package = UnclassifiedResourceView(self.resource_manager, self.package_index_manager)
            self.current_package_id = package_id

            # 更新标题
            self.title_update_requested.emit("<未分类资源>")
            # 记录最近打开
            self.package_index_manager.set_last_opened_package("unclassified_view")
        else:
            # 加载存档索引
            package_index = self.package_index_manager.load_package_index(package_id)
            if not package_index:
                # 创建新的空存档索引
                package_index = PackageIndex(
                    package_id=package_id,
                    name="未命名存档"
                )
                self.package_index_manager.save_package_index(package_index)
            
            self.current_package_index = package_index
            self.current_package = PackageView(package_index, self.resource_manager)
            self.current_package_id = package_id
            
            # 更新标题
            self.title_update_requested.emit(self.current_package.name)
            
            # 记录最近打开
            self.package_index_manager.set_last_opened_package(package_id)
        
        # 发送加载完成信号
        self.package_loaded.emit(package_id)
    
    def create_package(self, parent_widget: QtWidgets.QWidget) -> None:
        """创建新存档"""
        name = input_dialogs.prompt_text(parent_widget, "新建存档", "请输入存档名称:")
        if not name:
            return
        package_id = self.package_index_manager.create_package(name)
        self.package_list_changed.emit()
        self.load_package(package_id)
    
    def save_package(self) -> None:
        """保存存档（全量）。"""
        self._save_internal(force_full=True)

    def save_dirty_blocks(self) -> None:
        """仅保存已标记的脏块。"""
        self._save_internal(force_full=False)

    def _save_internal(self, *, force_full: bool) -> None:
        """按需保存当前存档或视图。"""
        # 保存前同步指纹基线，确保不会因为之前的代码修改而误判为"外部修改"
        self._sync_fingerprint_before_save()

        is_special_view = self.current_package_id in ("global_view", "unclassified_view")
        dirty_snapshot = (
            self._build_full_dirty_snapshot() if force_full else self.dirty_state.snapshot()
        )

        if not force_full and dirty_snapshot.is_empty():
            return

        if self.flush_current_resource_panel is not None:
            if force_full or dirty_snapshot.should_flush_property_panel():
                self.flush_current_resource_panel()

        print(
            "[PACKAGE-SAVE] 开始保存存档: "
            f"package_id={self.current_package_id!r}, force_full={force_full}"
        )

        # 特殊视图模式下保存当前编辑的资源
        if is_special_view:
            did_write = self._save_special_view(dirty_snapshot, force_full)
            if did_write:
                self.dirty_state.clear()
                self.package_saved.emit()
            return
        
        if not self.current_package_index or not self.current_package_id:
            print(
                "[PACKAGE-SAVE] 跳过保存：current_package_index 或 current_package_id 为空"
            )
            return
        
        did_write = self._save_package_view(dirty_snapshot, force_full)
        if did_write:
            self.dirty_state.clear()
            self.package_saved.emit()
    
    def _save_resource_container(self, container, object_type: str, verbose: bool = False) -> None:
        """统一保存资源容器（模板、实例或关卡实体）
        
        Args:
            container: 资源容器对象
            object_type: 对象类型（"template"、"instance"或"level_entity"）
            verbose: 是否打印详细日志
        """
        if not container:
            return
        
        # 根据对象类型保存到 ResourceManager
        if object_type == "template":
            # 保存模板（包括节点图）
            if hasattr(container, "template_id"):
                payload = container.serialize()
                metadata = payload.get("metadata", {}) or {}
                guid_value = None
                if isinstance(metadata, dict):
                    guid_value = metadata.get("guid")
                self.resource_manager.save_resource(
                    ResourceType.TEMPLATE,
                    container.template_id,
                    payload,
                )
                print(
                    "[RESOURCE-SAVE] 模板已保存："
                    f"name={getattr(container, 'name', '')!r}, "
                    f"id={container.template_id!r}, guid={guid_value!r}"
                )
                if verbose:
                    print(f"已保存模板：{container.name} ({container.template_id})")
        
        elif object_type in ("instance", "level_entity"):
            # 保存实例（包括节点图，关卡实体也是实例）
            if hasattr(container, "instance_id"):
                payload = container.serialize()
                metadata = payload.get("metadata", {}) or {}
                guid_value = None
                if isinstance(metadata, dict):
                    guid_value = metadata.get("guid")
                self.resource_manager.save_resource(
                    ResourceType.INSTANCE,
                    container.instance_id,
                    payload,
                )
                print(
                    "[RESOURCE-SAVE] 实例已保存："
                    f"name={getattr(container, 'name', '')!r}, "
                    f"id={container.instance_id!r}, guid={guid_value!r}, "
                    f"is_level_entity={object_type == 'level_entity'}"
                )
                if verbose:
                    print(f"已保存实例：{container.name} ({container.instance_id})")
    
    def _save_global_view_resources(self, *, allowed_template_ids: set[str] | None = None, allowed_instance_ids: set[str] | None = None) -> bool:
        """保存全局视图模式下修改的资源"""
        package = getattr(self, "current_package", None)
        if package is None:
            return False

        saved_any = False

        # 优先按传入的 ID 集合保存；若未提供，则回退到当前属性上下文
        if allowed_template_ids or allowed_instance_ids:
            saved_any = self._save_resources_for_ids(
                package,
                allowed_template_ids or set(),
                allowed_instance_ids or set(),
                save_level_entity=False,
                verbose=True,
            )
        elif self.get_current_graph_container and self.get_property_panel_object_type:
            current_graph_container = self.get_current_graph_container()
            object_type = self.get_property_panel_object_type()
            if current_graph_container is not None and object_type:
                self._save_resource_container(current_graph_container, object_type, verbose=True)
                saved_any = True

        return saved_any

    def _save_combat_presets_for_special_view(self) -> None:
        """在全局视图/未分类视图下，将战斗预设视图模型写回资源库。

        设计约定：
        - 仅负责把当前视图中的 CombatPresets 映射序列化回对应的资源文件；
        - 不改动任何 PackageIndex，战斗预设的归属仍由各功能包索引维护；
        - bucket 定义与 `_sync_combat_presets_to_index` 保持一致，避免两套写回规则分叉。
        """
        package = getattr(self, "current_package", None)
        if package is None:
            return

        # 仅在特殊视图下生效，具体存档的战斗预设写回仍由 _sync_combat_presets_to_index 负责。
        if not isinstance(package, (GlobalResourceView, UnclassifiedResourceView)):
            return

        combat_presets_view = getattr(package, "combat_presets", None)
        if combat_presets_view is None:
            return

        bucket_definitions = [
            ("player_templates", ResourceType.PLAYER_TEMPLATE, "template_id"),
            ("player_classes", ResourceType.PLAYER_CLASS, "class_id"),
            ("unit_statuses", ResourceType.UNIT_STATUS, "status_id"),
            ("skills", ResourceType.SKILL, "skill_id"),
            ("projectiles", ResourceType.PROJECTILE, "projectile_id"),
            ("items", ResourceType.ITEM, "item_id"),
        ]

        for bucket_key, resource_type, id_field in bucket_definitions:
            bucket_mapping_any = getattr(combat_presets_view, bucket_key, None)
            if not isinstance(bucket_mapping_any, dict):
                continue

            bucket_mapping = bucket_mapping_any
            print(
                "[COMBAT-PRESETS] special-view bucket 写回：",
                f"mode={self.current_package_id!r}, bucket_key={bucket_key!r}, "
                f"preset_count={len(bucket_mapping)}",
            )

            for preset_id, payload_any in bucket_mapping.items():
                if not isinstance(preset_id, str) or not preset_id:
                    continue
                if not isinstance(payload_any, dict):
                    continue

                payload = payload_any

                # 规范化通用 ID 字段与类型专用 ID 字段，保持与资源模型一致。
                if "id" not in payload:
                    payload["id"] = preset_id
                specific_id_value = payload.get(id_field)
                if not isinstance(specific_id_value, str) or not specific_id_value:
                    payload[id_field] = preset_id

                self.resource_manager.save_resource(resource_type, preset_id, payload)

    def _save_management_for_special_view(self, allowed_keys: set[str] | None = None) -> None:
        """在全局视图/未分类视图下，将管理页面编辑的配置直接写回管理配置资源。

        设计约定：
        - 仅负责将 current_package.management.* 写回 `assets/资源库/管理配置/*/*.json`，
          不改动任何 PackageIndex（包仍仅作为“引用这些资源的索引”存在）；
        - 多记录管理项（timers/level_variables/...）按 {resource_id: payload} 逐条保存；
        - 单配置管理项（currency_backpack/peripheral_systems/save_points/level_settings）
          使用固定的全局资源 ID：`global_view_<field>`，供 GlobalResourceView 与
          UnclassifiedResourceView 以“单一配置体”语义访问。
        """
        package = getattr(self, "current_package", None)
        if package is None:
            return

        management = getattr(package, "management", None)
        if management is None:
            return

        single_config_fields = {
            "currency_backpack",
            "peripheral_systems",
            "level_settings",
        }

        for resource_key, resource_type in MANAGEMENT_RESOURCE_BINDINGS.items():
            if allowed_keys is not None and resource_key not in allowed_keys:
                continue
            # 信号与结构体定义采用专用写回路径，这里保持只处理管理配置本体。
            if resource_key in {"signals", "struct_definitions"}:
                continue
            if resource_key == "level_variables":
                continue

            value = getattr(management, resource_key, None)

            # 局内存档管理（save_points）：拆分为“全局元配置 + 每模板一份 JSON”。
            if resource_key == "save_points":
                self._save_single_config_save_points(value)
                continue

            # 单配置字段：直接保存为 global_view_<field> 资源
            if resource_key in single_config_fields:
                if not isinstance(value, dict) or not value:
                    continue
                resource_id = f"global_view_{resource_key}"
                self.resource_manager.save_resource(
                    resource_type,
                    resource_id,
                    dict(value),
                )
                continue

            # 多配置字段：期望为 {resource_id: payload}
            if not isinstance(value, dict):
                continue

            for resource_id, payload in value.items():
                if not isinstance(resource_id, str) or not resource_id:
                    continue
                if not isinstance(payload, dict):
                    continue
                self.resource_manager.save_resource(
                    resource_type,
                    resource_id,
                    payload,
                )

    def _save_single_config_save_points(self, raw_value) -> None:
        """在全局/未分类视图下，将 management.save_points 的“当前模板状态”写回模板。

        设计约定：
        - 当前启用模板由各模板 payload 中的 `is_default_template` 字段表达，
          本方法负责根据 enabled/active_template_id 更新所有模板的该字段；
        - 旧版的全局元配置仍通过 ID 为 'global_view_save_points' 的 SAVE_POINT 资源
          记录 enabled/active_template_id/updated_at，仅作为兼容视图的数据来源；
        - 当 active_template_id 不再对应任何代码级模板时，在视图层自动关闭启用状态，
          并清空所有模板的 `is_default_template` 状态。
        """
        from datetime import datetime

        if not isinstance(raw_value, dict):
            return

        value = raw_value

        enabled_flag = bool(value.get("enabled", False))
        active_template_id = str(value.get("active_template_id", "")).strip()

        schema_view = get_default_ingame_save_template_schema_view()
        all_templates = schema_view.get_all_templates()

        if enabled_flag and active_template_id:
            if active_template_id not in all_templates:
                enabled_flag = False
                active_template_id = ""
                value["enabled"] = False
                value["active_template_id"] = ""

        # 1. 将当前启用模板状态写回代码级模板（is_default_template 字段）。
        if enabled_flag and active_template_id:
            update_default_template_id(active_template_id)
        else:
            update_default_template_id(None)

        # 2. 维护旧版全局元配置资源（仅作为兼容视图的数据来源）。
        updated_at_value = value.get("updated_at")
        if isinstance(updated_at_value, str) and updated_at_value.strip():
            updated_at_text = updated_at_value.strip()
        else:
            updated_at_text = datetime.now().isoformat(timespec="seconds")
            value["updated_at"] = updated_at_text

        meta_payload = {
            "enabled": enabled_flag,
            "active_template_id": active_template_id,
            "updated_at": updated_at_text,
        }

        resource_manager = self.resource_manager
        aggregator_id = "global_view_save_points"
        resource_manager.save_resource(
            ResourceType.SAVE_POINT,
            aggregator_id,
            meta_payload,
        )
    
    def _save_package_resources(self) -> bool:
        """保存当前属性上下文对应的资源到 ResourceManager"""
        if not self.current_package:
            return False

        if not self.get_current_graph_container or not self.get_property_panel_object_type:
            return False

        current_graph_container = self.get_current_graph_container()
        object_type = self.get_property_panel_object_type()

        if current_graph_container is None or not object_type:
            return False

        self._save_resource_container(current_graph_container, object_type, verbose=False)
        return True

    def _sync_combat_presets_to_index(
        self,
        package: PackageView,
        package_index: PackageIndex,
        allowed_buckets: set[str] | None = None,
    ) -> None:
        """将 PackageView 中的战斗预设写回资源库与 PackageIndex.resources.combat_presets。

        设计约定：
        - 视图模型 `package.combat_presets` 视为当前包下战斗预设的“单一真实来源”；
        - 每次保存时，将该视图中的各类战斗预设序列化为独立资源文件（PLAYER_TEMPLATE / PLAYER_CLASS / ...），
          并用其 ID 列表覆盖 `PackageIndex.resources.combat_presets[...]` 中对应的引用；
        - 对于在旧索引中存在但当前视图中已不存在的 ID，仅从索引中移除引用，不物理删除资源文件，
          由未分类视图负责聚合这些“游离战斗预设”。
        """
        print(
            "[COMBAT-PRESETS] 开始写回战斗预设到索引：",
            f"package_id={package_index.package_id!r}",
        )
        combat_presets_view = getattr(package, "combat_presets", None)
        if combat_presets_view is None:
            # 若当前视图中未提供战斗预设视图模型，则保持索引结构但清空引用列表。
            print(
                "[COMBAT-PRESETS] 当前 PackageView 未提供 combat_presets 视图模型，"
                "将清空索引中的战斗预设引用列表。",
                f"package_id={package_index.package_id!r}",
            )
            package_index.resources.combat_presets = {
                "player_templates": [],
                "player_classes": [],
                "unit_statuses": [],
                "skills": [],
                "projectiles": [],
                "items": [],
            }
            return

        bucket_definitions = [
            ("player_templates", ResourceType.PLAYER_TEMPLATE, "template_id"),
            ("player_classes", ResourceType.PLAYER_CLASS, "class_id"),
            ("unit_statuses", ResourceType.UNIT_STATUS, "status_id"),
            ("skills", ResourceType.SKILL, "skill_id"),
            ("projectiles", ResourceType.PROJECTILE, "projectile_id"),
            ("items", ResourceType.ITEM, "item_id"),
        ]

        combat_index_lists = package_index.resources.combat_presets

        for bucket_key, resource_type, id_field in bucket_definitions:
            if allowed_buckets is not None and bucket_key not in allowed_buckets:
                continue
            bucket_mapping_any = getattr(combat_presets_view, bucket_key, None)
            if not isinstance(bucket_mapping_any, dict):
                print(
                    "[COMBAT-PRESETS] bucket 映射不是字典或为空，将写回空列表：",
                    f"package_id={package_index.package_id!r}, bucket_key={bucket_key!r}, "
                    f"actual_type={type(bucket_mapping_any).__name__}",
                )
                combat_index_lists[bucket_key] = []
                continue

            bucket_mapping = bucket_mapping_any
            print(
                "[COMBAT-PRESETS] bucket 写回前视图统计：",
                f"package_id={package_index.package_id!r}, bucket_key={bucket_key!r}, "
                f"preset_count={len(bucket_mapping)}",
            )
            new_ids: list[str] = []

            for preset_id, payload_any in bucket_mapping.items():
                if not isinstance(preset_id, str) or not preset_id:
                    continue
                if not isinstance(payload_any, dict):
                    continue

                payload = payload_any

                # 规范化通用 ID 字段与类型专用 ID 字段，保持与资源模型一致
                if "id" not in payload:
                    payload["id"] = preset_id
                specific_id_value = payload.get(id_field)
                if not isinstance(specific_id_value, str) or not specific_id_value:
                    payload[id_field] = preset_id

                self.resource_manager.save_resource(resource_type, preset_id, payload)
                new_ids.append(preset_id)

            new_ids.sort()
            combat_index_lists[bucket_key] = new_ids
            print(
                "[COMBAT-PRESETS] bucket 写回完成：",
                f"package_id={package_index.package_id!r}, bucket_key={bucket_key!r}, "
                f"saved_count={len(new_ids)}, index_ids={combat_index_lists[bucket_key]!r}",
            )

    def _sync_signals_to_index(self, package: PackageView, package_index: PackageIndex) -> None:
        """将 PackageView 中的信号配置写回到 PackageIndex.signals 摘要。"""
        signals_dict = getattr(package, "signals", None)
        if not isinstance(signals_dict, dict):
            sync_package_signals_to_index_and_aggregate(
                self.resource_manager,
                package_index,
                {},
            )
            return

        serialized_signals: dict[str, dict] = {}
        for signal_id in signals_dict.keys():
            if not isinstance(signal_id, str) or not signal_id:
                continue
            # 仅关心 ID，本字典的值在 helpers 中会被规约为占位空字典。
            serialized_signals[signal_id] = {}

        sync_package_signals_to_index_and_aggregate(
            self.resource_manager,
            package_index,
            serialized_signals,
        )

    def _sync_management_resources_to_index(
        self,
        package: PackageView,
        package_index: PackageIndex,
        allowed_keys: set[str] | None = None,
    ) -> None:
        """将管理页面编辑的配置写回资源库与 PackageIndex.resources.management。

        约定：
        - 对于 timers/level_variables 等“多条记录”的管理项：使用 {resource_id: payload} 形式；
          保存时为每条记录创建/更新一个资源文件，并将 ID 列表写回索引。
        - 对于 currency_backpack / peripheral_systems / save_points / level_settings 等“整包级单配置”：
          使用单个资源文件承载所有配置字段，索引中仅维护一个 ID。
        """
        management = getattr(package, "management", None)
        if management is None:
            return

        for resource_key, resource_type in MANAGEMENT_RESOURCE_BINDINGS.items():
            if allowed_keys is not None and resource_key not in allowed_keys:
                continue
            # 信号配置采用专用聚合资源写回逻辑（见 _sync_signals_to_index），
            # 这里跳过，避免与包级信号语义重复或被覆盖。
            # 结构体定义的归属由结构体管理页通过 PackageIndexManager 维护到
            # resources.management["struct_definitions"]，不通过 ManagementData 写回。
            if resource_key in {"signals", "struct_definitions"}:
                continue
            value = getattr(management, resource_key, None)

            # 局内存档模板（save_points）、外围系统（peripheral_systems）、货币与背包
            # （currency_backpack）以及关卡设置（level_settings）的配置体本体统一在
            # 全局视图/未分类视图下通过 `_save_management_for_special_view()` 写回到
            # `global_view_<field>` 资源中；在具体存档视图中这里不再重写索引中的
            # `resources.management[...]`，使“所属存档”多选行仅通过 PackageIndexManager
            # 维护模板或配置体 ID 列表。
            if resource_key in {
                "save_points",
                "peripheral_systems",
                "currency_backpack",
                "level_settings",
            }:
                continue

            management_lists = package_index.resources.management

            # 多配置字段：期望为 {resource_id: payload} 字典
            if not isinstance(value, dict):
                management_lists[resource_key] = []
                continue

            new_ids: list[str] = []
            for resource_id, payload in value.items():
                if not isinstance(resource_id, str) or not resource_id:
                    continue
                if not isinstance(payload, dict):
                    continue
                self.resource_manager.save_resource(resource_type, resource_id, payload)
                new_ids.append(resource_id)

            new_ids.sort()
            management_lists[resource_key] = new_ids

    def _save_resources_for_ids(
        self,
        package: object,
        template_ids: set[str],
        instance_ids: set[str],
        save_level_entity: bool,
        *,
        verbose: bool,
    ) -> bool:
        """按 ID 集合保存模板/实例/关卡实体。"""
        saved_any = False

        if template_ids:
            for template_id in template_ids:
                template_obj = getattr(package, "get_template", lambda _x: None)(template_id)
                if template_obj is None:
                    continue
                self._save_resource_container(template_obj, "template", verbose=verbose)
                saved_any = True

        if instance_ids:
            for instance_id in instance_ids:
                instance_obj = getattr(package, "get_instance", lambda _x: None)(instance_id)
                if instance_obj is None:
                    continue
                self._save_resource_container(
                    instance_obj,
                    "instance",
                    verbose=verbose,
                )
                saved_any = True

        if save_level_entity:
            level_entity_obj = getattr(package, "level_entity", None)
            if level_entity_obj is not None:
                self._save_resource_container(
                    level_entity_obj,
                    "level_entity",
                    verbose=verbose,
                )
                saved_any = True

        return saved_any

    def _save_special_view(self, dirty_snapshot: PackageDirtyState, force_full: bool) -> bool:
        """在全局/未分类视图下按需保存。"""
        did_write = False

        if force_full or dirty_snapshot.graph_dirty:
            self.request_save_current_graph.emit()
            did_write = True

        package = getattr(self, "current_package", None)
        if package is None:
            return did_write

        if force_full or dirty_snapshot.template_ids or dirty_snapshot.instance_ids or dirty_snapshot.level_entity_dirty:
            resource_saved = self._save_global_view_resources(
                allowed_template_ids=None if force_full else dirty_snapshot.template_ids,
                allowed_instance_ids=None if force_full else dirty_snapshot.instance_ids,
            )
            did_write = did_write or resource_saved

        if force_full or dirty_snapshot.combat_dirty:
            self._save_combat_presets_for_special_view()
            did_write = True

        if force_full or dirty_snapshot.full_management_sync or dirty_snapshot.management_keys:
            allowed_keys = None if force_full or dirty_snapshot.full_management_sync else set(dirty_snapshot.management_keys)
            self._save_management_for_special_view(allowed_keys=allowed_keys)
            did_write = True

        if did_write:
            self.resource_manager.refresh_resource_library_fingerprint()
            print(
                "[PACKAGE-SAVE] 已保存全局/未分类视图下的资源，"
                f"mode={self.current_package_id!r}"
            )

        return did_write

    def _save_package_view(self, dirty_snapshot: PackageDirtyState, force_full: bool) -> bool:
        """在具体存档视图下保存按需落盘的脏块。"""
        package = self.current_package
        package_index = self.current_package_index
        if not isinstance(package, PackageView) or not isinstance(package_index, PackageIndex):
            return False

        did_write = False
        need_save_index = False

        if force_full or dirty_snapshot.graph_dirty:
            self.request_save_current_graph.emit()
            did_write = True

        if force_full:
            saved_resources = self._save_package_resources()
        else:
            saved_resources = self._save_resources_for_ids(
                package,
                dirty_snapshot.template_ids,
                dirty_snapshot.instance_ids,
                dirty_snapshot.level_entity_dirty,
                verbose=False,
            )
        did_write = did_write or saved_resources

        # 战斗预设：视图模型写回索引与资源
        if force_full or dirty_snapshot.combat_dirty:
            self._sync_combat_presets_to_index(package, package_index)
            need_save_index = True
            did_write = True

        # 信号摘要：索引聚合
        if force_full or dirty_snapshot.signals_dirty:
            self._sync_signals_to_index(package, package_index)
            need_save_index = True

        # 管理配置：可按键增量
        if force_full or dirty_snapshot.full_management_sync or dirty_snapshot.management_keys:
            allowed_keys = None if force_full or dirty_snapshot.full_management_sync else set(dirty_snapshot.management_keys)
            self._sync_management_resources_to_index(package, package_index, allowed_keys=allowed_keys)
            need_save_index = True
            did_write = True

        if dirty_snapshot.index_dirty:
            need_save_index = True

        if need_save_index:
            self.package_index_manager.save_package_index(package_index)
            self.resource_manager.refresh_resource_library_fingerprint()
            print(f"[PACKAGE-SAVE] 存档索引已写入：package_id={self.current_package_id!r}")
            did_write = True
        elif did_write:
            # 资源写入已由 ResourceManager 刷新指纹
            self.resource_manager.refresh_resource_library_fingerprint()

        return did_write
    
    def export_package(self, parent_widget: QtWidgets.QWidget) -> None:
        """导出存档"""
        if not self.current_package:
            return
        
        # 特殊视图模式不支持导出
        if self.current_package_id in ("global_view", "unclassified_view"):
            dialog_utils.show_warning_dialog(
                parent_widget,
                "提示",
                "当前视图不支持导出。\n请选择具体的存档后再导出。",
            )
            return
        
        self.save_package()
        
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            parent_widget, "导出存档",
            f"{self.current_package.name}.json",
            filter="JSON (*.json)"
        )
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.current_package.serialize(), f, ensure_ascii=False, indent=2)
            dialog_utils.show_info_dialog(
                parent_widget,
                "成功",
                f"存档已导出到: {path}",
            )
    
    def import_package(self, parent_widget: QtWidgets.QWidget) -> None:
        """导入存档（支持新旧格式）"""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            parent_widget, "导入存档", filter="JSON (*.json)"
        )
        if not path:
            return
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 检测格式
        if "resources" in data and isinstance(data.get("resources"), dict):
            # 新格式：存档索引
            self._import_package_index(data)
        elif "templates" in data or "instances" in data:
            # 旧格式：单体JSON
            self._import_monolithic_package(data, Path(path))
        else:
            dialog_utils.show_warning_dialog(
                parent_widget,
                "错误",
                "无法识别的存档格式",
            )
            return
        
        # 刷新存档列表
        self.package_list_changed.emit()
        dialog_utils.show_info_dialog(
            parent_widget,
            "成功",
            "存档导入成功！",
        )
    
    def _import_package_index(self, data: dict) -> None:
        """导入新格式存档索引"""
        package_index = PackageIndex.deserialize(data)
        
        # 生成新的package_id（避免冲突）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        old_id = package_index.package_id
        new_id = f"pkg_imported_{timestamp}"
        package_index.package_id = new_id
        
        # 保存存档索引
        self.package_index_manager.save_package_index(package_index)
        
        print(f"已导入存档索引：{package_index.name} (ID: {old_id} -> {new_id})")
    
    def _import_monolithic_package(self, data: dict, source_path: Path) -> None:
        """导入旧格式单体JSON并转换为离散资源"""
        from tests.migrate_to_discrete_resources import ResourceMigrator
        
        # 临时保存到存档数据目录
        temp_file = self.workspace_path / "存档数据" / source_path.name
        temp_file.parent.mkdir(exist_ok=True)
        
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # 使用迁移工具转换
        migrator = ResourceMigrator(self.workspace_path)
        migrator._migrate_package(temp_file)
        
        print(f"已导入并转换单体JSON存档：{data.get('name', '未命名')}")
    
    def get_package_list(self) -> list:
        """获取存档列表"""
        return self.package_index_manager.list_packages()

