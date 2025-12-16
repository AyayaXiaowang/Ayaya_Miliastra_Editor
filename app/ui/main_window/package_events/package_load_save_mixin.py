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

        self.template_widget.set_package(package)
        self.placement_widget.set_package(package)
        self.combat_widget.set_package(package)
        self.management_widget.set_package(package)
        self.graph_library_widget.set_package(package)

        # 管理编辑页（按 section 拆分的旧管理页面）同样绑定到当前视图，
        # 确保右侧编辑内容与管理库列表的数据来源一致。
        management_edit_pages = getattr(self, "management_edit_pages", None)
        if isinstance(management_edit_pages, dict):
            for editor in management_edit_pages.values():
                set_package = getattr(editor, "set_package", None)
                if callable(set_package) and package is not None:
                    set_package(package)

        self._refresh_package_list()

        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_view_mode == ViewMode.TODO:
            self._refresh_todo_list()

    def _on_package_saved(self) -> None:
        """存档保存完成"""
        self._trigger_validation()
        # 存档落盘后刷新存档库页面，确保 GUID / 挂载节点图等汇总信息与最新落盘状态保持一致。
        if hasattr(self, "package_library_widget"):
            self.package_library_widget.refresh()

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


