"""存档加载/保存与存档下拉框相关事件处理。"""

from __future__ import annotations

from app.models.view_modes import ViewMode
from app.ui.foundation import dialog_utils
from app.ui.graph.library_pages.library_scaffold import LibrarySelection


class PackageLoadSaveMixin:
    """处理存档加载/保存、存档下拉框刷新，以及战斗预设延迟选中缓存。"""

    def _set_pending_combat_selection(self, section_key: str, item_id: str) -> None:
        """记录战斗预设待处理的选中项，等进入战斗模式后再加载面板。"""
        if section_key and item_id:
            setattr(self, "_pending_combat_selection", (section_key, item_id))
        else:
            setattr(self, "_pending_combat_selection", None)

        # 同步到 ViewState（单一真源）
        view_state = getattr(self, "view_state", None)
        combat_state = getattr(view_state, "combat", None)
        if combat_state is not None:
            setattr(combat_state, "pending_section_key", str(section_key or ""))
            setattr(combat_state, "pending_item_id", str(item_id or ""))

    def _consume_pending_combat_selection(self) -> tuple[str, str] | None:
        """取出并清空待处理的战斗预设选中项。"""
        pending = getattr(self, "_pending_combat_selection", None)
        setattr(self, "_pending_combat_selection", None)

        # 同步到 ViewState（单一真源）
        view_state = getattr(self, "view_state", None)
        combat_state = getattr(view_state, "combat", None)
        if combat_state is not None:
            setattr(combat_state, "pending_section_key", "")
            setattr(combat_state, "pending_item_id", "")
        return pending

    # === 存档加载/保存 ===

    def _on_package_loaded(self, package_id: str) -> None:
        """存档加载完成"""
        package = self.package_controller.current_package

        # 关键：允许跨项目存档复用相同 graph_id 后，图相关缓存必须随存档切换失效，
        # 避免 GraphDataService 复用上一项目的 GraphConfig/GraphModel/payload。
        from app.runtime.services.graph_data_service import get_shared_graph_data_service

        provider = get_shared_graph_data_service(
            self.app_state.resource_manager,
            self.app_state.package_index_manager,
        )
        provider.invalidate_graph()
        provider.invalidate_package_cache()

        # 文件监控：仅监听“当前项目存档 + 共享”，忽略其它项目的目录事件与自动刷新触发
        file_watcher_manager = getattr(self, "file_watcher_manager", None)
        set_scope = getattr(file_watcher_manager, "set_resource_watch_active_package_id", None)
        if callable(set_scope):
            set_scope(package_id)

        # 关键：复合节点/节点库按“共享根 + 当前存档根”作用域加载。
        # 切包后必须刷新 NodeRegistry 并同步主窗口/图编辑器持有的 node_library，
        # 否则会出现“复合节点仍沿用上一存档/共享视图集合”的串包问题。
        refresh_nodes = getattr(self, "_refresh_node_library_and_sync_composites", None)
        if callable(refresh_nodes):
            refresh_nodes(reload_composite_widget_from_disk=True)

        self.template_widget.set_context(package)
        self.placement_widget.set_context(package)
        self.combat_widget.set_context(package)
        self.management_widget.set_context(package)
        self.graph_library_widget.set_context(package)

        # 复合节点页为懒加载：若已经创建，则同步注入当前存档上下文用于过滤左侧列表。
        composite_widget = getattr(self, "composite_widget", None)
        set_context = getattr(composite_widget, "set_context", None)
        if callable(set_context):
            current_package_index = getattr(self.package_controller, "current_package_index", None)
            set_context(package_id, current_package_index)

        self._refresh_package_list()

        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_view_mode == ViewMode.TODO:
            self._refresh_todo_list()

    def _on_package_saved(self) -> None:
        """存档保存完成"""
        # 存档保存会写入 assets/资源库 下的多类资源（以及 app/runtime 下的运行期状态），可能触发 directoryChanged 风暴；
        # 标记为“内部写盘”以抑制资源库自动刷新误触发。
        file_watcher_manager = getattr(self, "file_watcher_manager", None)
        update_method = getattr(file_watcher_manager, "update_last_resource_write_time", None)
        if callable(update_method):
            update_method()
        self._trigger_validation()
        # 存档落盘后刷新存档库页面，确保 GUID / 挂载节点图等汇总信息与最新落盘状态保持一致。
        if hasattr(self, "package_library_widget"):
            self.package_library_widget.reload()

        # 保存成功：刷新右上角保存状态提示（避免只保存模板/实体摆放等非图内容时状态不更新）
        set_status = getattr(self, "_set_last_save_status", None)
        if callable(set_status):
            set_status("saved")

    # === 存档下拉框 ===

    def _refresh_package_list(self) -> None:
        """刷新存档列表"""
        self.package_combo.blockSignals(True)
        self.package_combo.clear()

        self.package_combo.addItem("<共享资源>", "global_view")

        packages = self.package_controller.get_package_list()
        for pkg_info in packages:
            self.package_combo.addItem(pkg_info["name"], pkg_info["package_id"])

        current_package_id = self.package_controller.current_package_id
        if current_package_id:
            for i in range(self.package_combo.count()):
                if self.package_combo.itemData(i) == current_package_id:
                    self.package_combo.setCurrentIndex(i)
                    break

        self.package_combo.blockSignals(False)

    def _on_package_combo_changed(self, index: int) -> None:
        """存档下拉框改变"""
        if index < 0:
            return

        package_id = self.package_combo.itemData(index)
        if package_id != self.package_controller.current_package_id:
            self._request_load_package(str(package_id))

    def _set_package_combo_to_package_id(self, package_id: str) -> None:
        """将主窗口顶部存档下拉框恢复到指定 package_id（不触发切包回调）。"""
        if not hasattr(self, "package_combo"):
            return
        self.package_combo.blockSignals(True)
        try:
            for i in range(self.package_combo.count()):
                if self.package_combo.itemData(i) == package_id:
                    self.package_combo.setCurrentIndex(i)
                    break
        finally:
            self.package_combo.blockSignals(False)

    def _request_load_package(self, package_id: str) -> None:
        """请求切换当前项目存档（带未保存保护）。"""
        if not package_id:
            return
        if not hasattr(self, "package_controller"):
            return

        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if package_id == current_package_id:
            return

        has_unsaved = False
        has_unsaved_method = getattr(self.package_controller, "has_unsaved_changes", None)
        if callable(has_unsaved_method):
            has_unsaved = bool(has_unsaved_method())
        else:
            dirty_state = getattr(self.package_controller, "dirty_state", None)
            is_empty_method = getattr(dirty_state, "is_empty", None)
            if callable(is_empty_method):
                has_unsaved = not bool(is_empty_method())

        if has_unsaved:
            current_name = ""
            current_package = getattr(self.package_controller, "current_package", None)
            name_value = getattr(current_package, "name", "")
            current_name = str(name_value or "")

            choice = dialog_utils.ask_choice_dialog(
                self,
                "切换项目存档",
                "检测到未保存的修改。\n\n"
                f"- 当前项目存档：{current_name or '<未命名>'}\n"
                f"- 目标项目存档：{package_id}\n\n"
                "请选择要执行的操作：",
                icon="question",
                choices=[
                    ("save", "保存并切换", "accept"),
                    ("discard", "不保存切换", "destructive"),
                    ("cancel", "取消", "reject"),
                ],
                default_choice_key="save",
                escape_choice_key="cancel",
            )
            if choice == "cancel":
                if isinstance(current_package_id, str) and current_package_id:
                    self._set_package_combo_to_package_id(current_package_id)
                    # 若切包入口来自存档库（PACKAGES）页，也需要把左侧存档列表回滚到当前包，
                    # 避免列表停留在“目标包”但实际上下文未切换造成误解。
                    package_library_widget = getattr(self, "package_library_widget", None)
                    set_selection = getattr(package_library_widget, "set_selection", None)
                    if callable(set_selection):
                        set_selection(LibrarySelection(kind="package", id=current_package_id, context=None))
                return
            if choice == "save":
                set_status = getattr(self, "_set_last_save_status", None)
                if callable(set_status):
                    set_status("saving")
                if hasattr(self.package_controller, "save_now"):
                    self.package_controller.save_now()
                else:
                    self.package_controller.save_package()
            elif choice == "discard":
                self.package_controller.reset_dirty_state()
                set_status = getattr(self, "_set_last_save_status", None)
                if callable(set_status):
                    set_status("saved")

            # 若用户已完成“保存/不保存”决策，这里禁止 PackageController 再次自动保存以避免语义重复。
            self.package_controller.load_package(package_id, save_before_switch=False)
            return

        # 无未保存修改：保持旧行为（切包前由 controller 自己决定是否保存）
        self.package_controller.load_package(package_id)


