"""存档加载/保存与存档下拉框相关事件处理。"""

from __future__ import annotations

from app.models.view_modes import ViewMode


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
        # 存档保存会写入 assets/资源库 下的多类资源与功能包索引，可能触发 directoryChanged 风暴；
        # 标记为“内部写盘”以抑制资源库自动刷新误触发。
        file_watcher_manager = getattr(self, "file_watcher_manager", None)
        update_method = getattr(file_watcher_manager, "update_last_resource_write_time", None)
        if callable(update_method):
            update_method()
        self._trigger_validation()
        # 存档落盘后刷新存档库页面，确保 GUID / 挂载节点图等汇总信息与最新落盘状态保持一致。
        if hasattr(self, "package_library_widget"):
            self.package_library_widget.reload()

    # === 存档下拉框 ===

    def _refresh_package_list(self) -> None:
        """刷新存档列表"""
        self.package_combo.blockSignals(True)
        self.package_combo.clear()

        self.package_combo.addItem("<全部资源>", "global_view")
        self.package_combo.addItem("<未分类资源>", "unclassified_view")

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
            self.package_controller.load_package(package_id)


