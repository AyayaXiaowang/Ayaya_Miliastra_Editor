from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from PyQt6 import QtCore, QtWidgets

from app.ui.foundation.base_widgets import BaseDialog
from app.ui.foundation.theme_manager import ThemeManager, Colors


@dataclass(frozen=True, slots=True)
class MergeDecorationsDialogItem:
    instance_id: str
    display_text: str
    search_text: str
    decorations_count: int


class MergeDecorationsDialog(BaseDialog):
    """Merge multiple resources' decorations into one target resource (project-level)."""

    def __init__(
        self,
        *,
        items: Sequence[MergeDecorationsDialogItem],
        package_id: str,
        default_target_instance_id: str | None = None,
        source_kind_label: str = "实体",
        target_kind_label: str | None = None,
        source_origin_hint: str = "",
        default_new_name: str | None = None,
        show_center_policy: bool = True,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(
            title="合并装饰物（项目资源）",
            width=920,
            height=680,
            use_scroll=False,
            parent=parent,
        )
        self._package_id = str(package_id or "").strip()
        self._items = list(items)
        self._default_target_instance_id = str(default_target_instance_id or "").strip()
        self._source_kind = str(source_kind_label or "实体").strip() or "实体"
        self._target_kind = str(target_kind_label or "").strip() or self._source_kind
        self._source_origin_hint = str(source_origin_hint or "").strip()
        self._default_new_name = str(default_new_name or "").strip()
        self._show_center_policy = bool(show_center_policy)

        self._selected_source_ids: list[str] = []
        self._target_instance_id: str = "__new__"
        self._new_instance_name: str = ""
        self._remove_sources: bool = False
        self._do_center: bool = False
        self._center_mode: str = "bbox"
        self._center_axes: str = "xyz"
        self._center_policy: str = "keep_world" if self._show_center_policy else "move_decorations"
        self._items_by_id: dict[str, MergeDecorationsDialogItem] = {
            str(it.instance_id): it for it in self._items if str(it.instance_id)
        }

        self._build_ui()
        self._populate()
        self._apply_filter("")
        self._sync_ok_state()

    # --------------------------------------------------------------------- public getters
    def get_selected_source_instance_ids(self) -> list[str]:
        return list(self._selected_source_ids)

    def get_target_instance_id(self) -> str:
        return str(self._target_instance_id)

    def get_new_instance_name(self) -> str:
        return str(self._new_instance_name)

    def should_remove_sources(self) -> bool:
        return bool(self._remove_sources)

    def should_center(self) -> bool:
        return bool(self._do_center)

    def get_center_mode(self) -> str:
        return str(self._center_mode)

    def get_center_axes(self) -> str:
        return str(self._center_axes)

    def get_center_policy(self) -> str:
        return str(self._center_policy)

    # --------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        if not self._source_origin_hint:
            if self._source_kind == "元件":
                self._source_origin_hint = "来自当前项目存档目录下的“元件库”资源"
            elif self._source_kind == "实体":
                self._source_origin_hint = "来自当前项目存档目录下的“实体摆放”资源"
            else:
                self._source_origin_hint = "来自当前项目存档目录下的资源"

        hint = QtWidgets.QLabel(
            f"将多个{self._source_kind}的 `metadata.common_inspector.model.decorations` 合并到同一个目标{self._target_kind}上。\n"
            f"使用方法：\n"
            f"1) 左侧列表勾选所有要合并的{self._source_kind}（来自：{self._source_origin_hint}；至少 2 个）。\n"
            f"2) 右侧选择目标{self._target_kind}：新建载体（推荐，可命名），或从【左侧已勾选】的{self._source_kind}里选 1 个作为主文件（下拉不会列出未勾选项）。\n"
            f"说明：没有装饰物的{self._source_kind}会被跳过；本工具不会读取/写入 .gia 文件。",
            self,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_HINT};")
        layout.addWidget(hint)

        self._search_edit = QtWidgets.QLineEdit(self)
        self._search_edit.setPlaceholderText(
            f"搜索{self._source_kind}…（按名称/ID/装饰物数量）"
        )
        self._search_edit.setStyleSheet(ThemeManager.input_style())
        self._search_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search_edit)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, self)
        splitter.setHandleWidth(2)
        layout.addWidget(splitter, 1)

        # Left: source list (multi-check) ---------------------------------
        left_root = QtWidgets.QWidget(splitter)
        left_layout = QtWidgets.QVBoxLayout(left_root)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        self._list_widget = QtWidgets.QListWidget(left_root)
        self._list_widget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self._list_widget.itemChanged.connect(self._on_item_changed)
        left_layout.addWidget(self._list_widget, 1)

        left_footer = QtWidgets.QLabel(
            f"提示：勾选 2 个或以上{self._source_kind}后才能确定。", left_root
        )
        left_footer.setStyleSheet(f"color: {Colors.TEXT_HINT};")
        left_layout.addWidget(left_footer)

        # Right: options ---------------------------------------------------
        right_root = QtWidgets.QWidget(splitter)
        right_layout = QtWidgets.QVBoxLayout(right_root)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        options_group = QtWidgets.QGroupBox("合并选项", right_root)
        form = QtWidgets.QFormLayout(options_group)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)

        self._target_combo = QtWidgets.QComboBox(options_group)
        self._target_combo.setStyleSheet(ThemeManager.combo_box_style())
        self._target_combo.currentIndexChanged.connect(self._on_target_changed)
        form.addRow(f"目标{self._target_kind}", self._target_combo)

        self._new_name_edit = QtWidgets.QLineEdit(options_group)
        self._new_name_edit.setStyleSheet(ThemeManager.input_style())
        self._new_name_edit.setPlaceholderText(f"新建目标{self._target_kind}名称")
        self._new_name_edit.textChanged.connect(self._sync_ok_state)
        form.addRow(f"新建{self._target_kind}名称", self._new_name_edit)

        self._remove_sources_checkbox = QtWidgets.QCheckBox(
            f"合并后从当前项目存档移除源{self._source_kind}（移动到默认归档项目，不物理删除）",
            options_group,
        )
        self._remove_sources_checkbox.stateChanged.connect(self._sync_ok_state)
        form.addRow("", self._remove_sources_checkbox)

        self._center_checkbox = QtWidgets.QCheckBox("居中（对装饰物坐标做平移）", options_group)
        self._center_checkbox.stateChanged.connect(self._on_center_toggle_changed)
        form.addRow("", self._center_checkbox)

        center_row = QtWidgets.QWidget(options_group)
        center_row_layout = QtWidgets.QHBoxLayout(center_row)
        center_row_layout.setContentsMargins(0, 0, 0, 0)
        center_row_layout.setSpacing(8)

        self._center_mode_combo = QtWidgets.QComboBox(center_row)
        self._center_mode_combo.setStyleSheet(ThemeManager.combo_box_style())
        self._center_mode_combo.addItem("包围盒中心（bbox）", "bbox")
        self._center_mode_combo.addItem("均值中心（mean）", "mean")
        self._center_mode_combo.currentIndexChanged.connect(self._sync_ok_state)
        center_row_layout.addWidget(self._center_mode_combo)

        self._center_axes_combo = QtWidgets.QComboBox(center_row)
        self._center_axes_combo.setStyleSheet(ThemeManager.combo_box_style())
        for axes in ["xyz", "xz", "xy", "yz", "x", "y", "z"]:
            self._center_axes_combo.addItem(f"轴: {axes}", axes)
        self._center_axes_combo.currentIndexChanged.connect(self._sync_ok_state)
        center_row_layout.addWidget(self._center_axes_combo)

        self._center_policy_combo = QtWidgets.QComboBox(center_row)
        self._center_policy_combo.setStyleSheet(ThemeManager.combo_box_style())
        self._center_policy_combo.addItem("保持世界坐标（keep_world）", "keep_world")
        self._center_policy_combo.addItem("直接移动装饰物（move_decorations）", "move_decorations")
        self._center_policy_combo.currentIndexChanged.connect(self._sync_ok_state)
        center_row_layout.addWidget(self._center_policy_combo)

        form.addRow("居中策略", center_row)

        right_layout.addWidget(options_group)

        if self._show_center_policy:
            warn = QtWidgets.QLabel(
                "注意：当前版本的“保持世界坐标”是平移级别 best-effort。\n"
                "若源/目标实体存在旋转或缩放，可能无法保证装饰物的世界变换完全不变。",
                right_root,
            )
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
            right_layout.addWidget(warn)

        right_layout.addStretch(1)

        splitter.addWidget(left_root)
        splitter.addWidget(right_root)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([560, 360])

        container = QtWidgets.QWidget(self)
        container.setLayout(layout)
        self.add_widget(container)

        self._set_center_controls_enabled(False)

    def _populate(self) -> None:
        # sources list
        self._list_widget.clear()
        for item_data in self._items:
            text = f"{item_data.display_text}  |  装饰物: {item_data.decorations_count}"
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, item_data.instance_id)
            item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, item_data.search_text)
            item.setData(QtCore.Qt.ItemDataRole.UserRole + 2, int(item_data.decorations_count))
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.CheckState.Unchecked)
            item.setToolTip(f"ID: {item_data.instance_id}")
            self._list_widget.addItem(item)

        # target combo: default to "new", and only list targets from checked sources (dynamic updates).
        self._sync_target_combo_options()

        # default new name
        if self._default_new_name:
            self._new_name_edit.setText(self._default_new_name)
        else:
            default_name = "装饰物合并"
            if self._package_id:
                default_name = f"装饰物合并_{self._package_id}"
            self._new_name_edit.setText(default_name)

        # Ensure UI state is synced (enable/disable name edit) and make naming easy when creating a new carrier.
        self._on_target_changed()
        if self._target_combo.currentData() == "__new__":
            self._new_name_edit.selectAll()
            QtCore.QTimer.singleShot(0, self._new_name_edit.setFocus)

    # --------------------------------------------------------------------- filtering / selection
    def _apply_filter(self, text: str) -> None:
        query = str(text or "").strip().casefold()
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            if item is None:
                continue
            hay = str(item.data(QtCore.Qt.ItemDataRole.UserRole + 1) or item.text()).casefold()
            visible = True if not query else (query in hay)
            item.setHidden(not visible)

        # Filtering changes which checked items are considered active (hidden items are ignored).
        self._sync_target_combo_options()
        self._sync_ok_state()

    def _on_item_changed(self, _item: QtWidgets.QListWidgetItem) -> None:
        self._sync_target_combo_options()
        self._sync_ok_state()

    def _on_target_changed(self) -> None:
        is_new = self._target_combo.currentData() == "__new__"
        self._new_name_edit.setEnabled(bool(is_new))
        self._sync_ok_state()

    def _on_center_toggle_changed(self) -> None:
        enabled = bool(self._center_checkbox.isChecked())
        self._set_center_controls_enabled(enabled)
        self._sync_ok_state()

    def _set_center_controls_enabled(self, enabled: bool) -> None:
        self._center_mode_combo.setEnabled(bool(enabled))
        self._center_axes_combo.setEnabled(bool(enabled))
        self._center_policy_combo.setEnabled(bool(enabled and self._show_center_policy))
        self._center_policy_combo.setVisible(bool(self._show_center_policy))

    def _collect_checked_source_ids(self) -> list[str]:
        ids: list[str] = []
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            if item is None or item.isHidden():
                continue
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                raw = item.data(QtCore.Qt.ItemDataRole.UserRole)
                rid = str(raw or "").strip()
                if rid:
                    ids.append(rid)
        return ids

    def _collect_checked_decorations_count(self) -> int:
        total = 0
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            if item is None or item.isHidden():
                continue
            if item.checkState() != QtCore.Qt.CheckState.Checked:
                continue
            raw = item.data(QtCore.Qt.ItemDataRole.UserRole + 2)
            total += int(raw) if isinstance(raw, int) and not isinstance(raw, bool) else 0
        return int(total)

    def _sync_target_combo_options(self) -> None:
        """目标下拉仅允许从“左侧已勾选”的源资源中选择一个，或新建载体。"""
        current = str(self._target_combo.currentData() or "__new__").strip() or "__new__"
        checked_ids = self._collect_checked_source_ids()

        self._target_combo.blockSignals(True)
        self._target_combo.clear()
        self._target_combo.addItem(f"新建载体{self._target_kind}（推荐）", "__new__")

        for rid in checked_ids:
            item_data = self._items_by_id.get(rid)
            if item_data is None:
                continue
            self._target_combo.addItem(item_data.display_text, item_data.instance_id)

        if current != "__new__" and current in checked_ids:
            idx = self._target_combo.findData(current)
            if idx >= 0:
                self._target_combo.setCurrentIndex(idx)
        else:
            self._target_combo.setCurrentIndex(0)

        self._target_combo.blockSignals(False)
        self._on_target_changed()

    def _sync_ok_state(self) -> None:
        ok_btn = self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        if ok_btn is None:
            return
        checked = self._collect_checked_source_ids()
        total_decos = self._collect_checked_decorations_count()
        ok = len(checked) >= 2 and total_decos > 0
        if ok and self._target_combo.currentData() == "__new__":
            ok = bool(self._new_name_edit.text().strip())
        ok_btn.setEnabled(bool(ok))

    # --------------------------------------------------------------------- accept / validate
    def validate(self) -> bool:
        checked = self._collect_checked_source_ids()
        if len(checked) < 2:
            self.show_error(f"请选择至少 2 个要合并的{self._source_kind}。")
            return False
        if self._collect_checked_decorations_count() <= 0:
            self.show_error(
                f"所选{self._source_kind}均不包含装饰物（decorations）。请换一组包含装饰物的{self._source_kind}。"
            )
            return False

        target = str(self._target_combo.currentData() or "").strip() or "__new__"
        if target == "__new__":
            name = str(self._new_name_edit.text() or "").strip()
            if not name:
                self.show_error(f"请输入新建目标{self._target_kind}名称。")
                return False
            self._new_instance_name = name
        else:
            if target not in checked:
                self.show_error(
                    f"目标{self._target_kind}必须从左侧已勾选的{self._source_kind}中选择 1 个作为主文件。"
                )
                return False
            self._new_instance_name = ""

        self._selected_source_ids = checked
        self._target_instance_id = target
        self._remove_sources = bool(self._remove_sources_checkbox.isChecked())
        self._do_center = bool(self._center_checkbox.isChecked())
        self._center_mode = str(self._center_mode_combo.currentData() or "bbox")
        self._center_axes = str(self._center_axes_combo.currentData() or "xyz")
        if self._show_center_policy:
            self._center_policy = str(self._center_policy_combo.currentData() or "keep_world")
        else:
            self._center_policy = "move_decorations"
        return True


__all__ = ["MergeDecorationsDialog", "MergeDecorationsDialogItem"]

