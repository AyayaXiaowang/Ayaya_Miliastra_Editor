"""存档控制器 - 管理存档的生命周期"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional, Iterable
from datetime import datetime

from PyQt6 import QtCore, QtWidgets

from engine.resources.resource_manager import ResourceManager
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.package_index import PackageIndex
from engine.resources.package_view import PackageView
from engine.resources.global_resource_view import GlobalResourceView
from app.ui.foundation import dialog_utils, input_dialogs
from app.ui.controllers.package_dirty_state import PackageDirtyState
from app.ui.controllers.package_save import PackageSaveOrchestrator


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
        self.current_package: PackageView | GlobalResourceView | None = None
        self.current_package_id: Optional[str] = None
        self.dirty_state = PackageDirtyState()
        
        # 用于获取当前编辑对象（由主窗口设置）
        self.get_current_graph_container = None
        self.get_property_panel_object_type = None
        # 用于在保存前刷新右侧属性面板中使用去抖写回的基础信息编辑内容
        self.flush_current_resource_panel: Optional[Callable[[], None]] = None
        # 在检测到外部资源库变更时由主窗口注入的刷新回调
        self.on_external_resource_change: Optional[Callable[[], None]] = None

        # 保存事务编排：把保存阶段顺序从 PackageController 中抽离
        self._save_orchestrator = PackageSaveOrchestrator(
            resource_manager=self.resource_manager,
            package_index_manager=self.package_index_manager,
            get_current_graph_container=self._get_current_graph_container_for_save,
            get_property_panel_object_type=self._get_property_panel_object_type_for_save,
        )

    def _get_current_graph_container_for_save(self) -> object | None:
        getter = getattr(self, "get_current_graph_container", None)
        if callable(getter):
            return getter()
        return None

    def _get_property_panel_object_type_for_save(self) -> str | None:
        getter = getattr(self, "get_property_panel_object_type", None)
        if callable(getter):
            object_type = getter()
            return str(object_type) if object_type else None
        return None

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

    def mark_combat_preset_dirty(self, section_key: Optional[str], item_id: Optional[str]) -> None:
        """标记某个战斗预设资源为脏（用于按条目增量写回资源文件）。"""
        if not isinstance(section_key, str) or not section_key:
            return
        if not isinstance(item_id, str) or not item_id:
            return
        self.dirty_state.combat_preset_keys.add((section_key, item_id))

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
        snapshot = self.dirty_state.snapshot()
        snapshot.graph_dirty = True
        snapshot.combat_dirty = True
        snapshot.signals_dirty = True
        snapshot.index_dirty = True
        snapshot.full_management_sync = True

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
        elif last_id and any(p["package_id"] == last_id for p in packages):
            self.load_package(last_id)
        else:
            self.load_package(packages[0]["package_id"])
        
        self.package_list_changed.emit()
    
    def load_package(self, package_id: str, *, save_before_switch: bool = True) -> None:
        """加载存档或全局视图。

        Args:
            save_before_switch:
                - True：切换前执行 `save_now()`（默认，兼容旧行为）
                - False：切换前不保存（用于上层已完成“保存/不保存/取消”的确认流程）
        """
        # 兼容旧状态：历史版本可能保存过 unclassified_view，这里将其回退为“第一个存档”或全局视图。
        if package_id == "unclassified_view":
            packages = self.package_index_manager.list_packages()
            if packages:
                package_id = str(packages[0].get("package_id") or "")
            package_id = package_id or "global_view"

        # 切换存档前：优先 flush 右侧属性面板中的去抖缓冲，再按脏块增量落盘。
        # 约定：若无任何本地改动则不写盘，避免无意义覆盖与 I/O 卡顿。
        if save_before_switch and self.current_package and self.current_package_id:
            self.save_now()
        self.reset_dirty_state()

        # 关键：允许“不同项目存档内存在重复资源 ID”后，资源索引必须按当前视图作用域构建。
        # - global_view：仅共享根
        # - 具体项目存档：共享根 + 当前项目存档根
        if package_id == "global_view":
            self.resource_manager.rebuild_index(active_package_id=None)
        else:
            self.resource_manager.rebuild_index(active_package_id=package_id)
            # 重要：PackageIndexManager 的派生缓存仅以“目录 mtime”为一致性基线，
            # 若该包曾在“共享视图（仅扫描共享根）”作用域下被派生并缓存，会导致 resources.graphs 等资源列表为空，
            # 进而使节点图库/存档库等页面错误地只显示共享资源。切包时强制失效该包缓存，确保使用当前作用域重新派生。
            self.package_index_manager.invalidate_package_index_cache(package_id)
        
        # 检查是否是特殊浏览模式
        if package_id == "global_view":
            self.current_package_index = None
            self.current_package = GlobalResourceView(self.resource_manager)
            self.current_package_id = package_id
            
            # 更新标题
            self.title_update_requested.emit("<共享资源>")
            # 记录最近打开为全局视图
            self.package_index_manager.set_last_opened_package("global_view")
        else:
            # 加载存档索引
            package_index = self.package_index_manager.load_package_index(package_id)
            if not package_index:
                # 创建新的空存档索引
                package_index = PackageIndex(
                    package_id=package_id,
                    name="未命名项目存档"
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
        """创建新项目存档"""
        name = input_dialogs.prompt_text(parent_widget, "新建项目存档", "请输入项目存档名称:")
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

    def save_now(self) -> None:
        """保存当前脏块（用户显式保存/切换项目存档等入口使用）。

        约定：
        - 先 flush 右侧属性面板中使用去抖写回的编辑缓冲（名称/描述/GUID 等）；
        - 再按脏块增量保存（无脏块则不写盘）。
        """
        flush_callback = getattr(self, "flush_current_resource_panel", None)
        if callable(flush_callback):
            flush_callback()
        self.save_dirty_blocks()

    def has_unsaved_changes(self) -> bool:
        """当前项目存档是否存在未落盘的本地修改（按脏块）。"""
        return not self.dirty_state.is_empty()

    def _save_internal(self, *, force_full: bool) -> None:
        """按需保存当前项目存档或视图。"""
        dirty_snapshot = (
            self._build_full_dirty_snapshot() if force_full else self.dirty_state.snapshot()
        )

        did_write = self._save_orchestrator.save(
            current_package_id=self.current_package_id,
            current_package=self.current_package,
            current_package_index=self.current_package_index,
            dirty_snapshot=dirty_snapshot,
            force_full=force_full,
            flush_current_resource_panel=self.flush_current_resource_panel,
            request_save_current_graph=lambda: self.request_save_current_graph.emit(),
        )
        if did_write:
            self.dirty_state.clear()
            self.package_saved.emit()
        # 保存实现已迁移到 `app/ui/controllers/package_save/` 下的 service。
    
    def export_package(self, parent_widget: QtWidgets.QWidget) -> None:
        """导出项目存档（JSON）"""
        if not self.current_package:
            return
        
        # 特殊视图模式不支持导出
        if self.current_package_id in ("global_view", "unclassified_view"):
            dialog_utils.show_warning_dialog(
                parent_widget,
                "提示",
                "当前视图不支持导出。\n请选择具体的项目存档后再导出。",
            )
            return
        
        self.save_now()
        
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            parent_widget, "导出项目存档（JSON）",
            f"{self.current_package.name}.json",
            filter="JSON (*.json)"
        )
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.current_package.serialize(), f, ensure_ascii=False, indent=2)
            dialog_utils.show_info_dialog(
                parent_widget,
                "成功",
                f"项目存档已导出到: {path}",
            )
    
    def import_package(self, parent_widget: QtWidgets.QWidget) -> None:
        """导入项目存档（索引格式，JSON）"""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            parent_widget, "导入项目存档（JSON）", filter="JSON (*.json)"
        )
        if not path:
            return
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 检测格式
        if "resources" in data and isinstance(data.get("resources"), dict):
            # 新格式：存档索引
            self._import_package_index(data)
        else:
            dialog_utils.show_warning_dialog(
                parent_widget,
                "错误",
                "无法识别的项目存档格式（仅支持 PackageIndex 索引格式导入）",
            )
            return
        
        # 刷新存档列表
        self.package_list_changed.emit()
        dialog_utils.show_info_dialog(
            parent_widget,
            "成功",
            "项目存档导入成功！",
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
    
    def get_package_list(self) -> list:
        """获取存档列表"""
        return self.package_index_manager.list_packages()

