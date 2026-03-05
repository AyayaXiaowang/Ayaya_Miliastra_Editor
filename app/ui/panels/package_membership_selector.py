from __future__ import annotations

from typing import Callable, Iterable, List, Optional, Sequence, Tuple

from PyQt6 import QtCore, QtWidgets

from app.ui.foundation.dialog_utils import ask_yes_no_dialog
from app.ui.foundation.theme_manager import Sizes


class PackageMembershipSelector(QtWidgets.QComboBox):
    """单选的“归属位置/所属存档”选择器。

    新语义（目录即存档）：
    - 一个资源只归属一个“资源根目录”（共享 / 某个项目存档目录）；
    - UI 选择行为等价于“将资源文件移动到目标根目录”。

    兼容：对外仍沿用 `membership_changed(package_id, is_checked)` 信号形态，
    其中 is_checked 在单选模式下恒为 True（表示“切换到该目标”）。

    约定的特殊项：
    - package_id == "shared"：表示移动到 `assets/资源库/共享/`
    """

    membership_changed = QtCore.pyqtSignal(str, bool)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        line_edit = self.lineEdit()
        if line_edit:
            line_edit.setReadOnly(True)
            line_edit.setPlaceholderText("<未设置>")
            if hasattr(line_edit, "setTextInteractionFlags"):
                line_edit.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.NoTextInteraction)
            line_edit.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self._packages: List[dict] = []
        self._is_refreshing: bool = False
        self._include_shared: bool = True
        self._current_owner_id: str = ""
        # items 重建缓存：避免在“单击预览/快速切换选中”时重复 clear()+addItem(...) 导致 UI 卡顿
        self._items_token: str = ""
        self._items_built: bool = False
        self.currentIndexChanged.connect(self._on_current_index_changed)
        self.setEnabled(False)

    def set_packages(self, packages: Sequence[dict], *, include_shared: bool = True) -> None:
        self._packages = list(packages)
        self._include_shared = bool(include_shared)

        # packages 变化会影响下拉内容：仅在内容确实变化时才标记为需要重建，
        # 避免“单击切换选中 → membership 回调每次都 set_packages(...)”导致重复 clear()+addItem(...) 卡顿。
        new_token = self._build_items_token()
        if self._items_built and new_token == self._items_token:
            return
        self._items_token = new_token
        self._items_built = False

    def set_membership(self, membership: Iterable[str]) -> None:
        """设置当前归属（单选）。

        兼容旧调用：参数仍是 iterable，但只取其中一个值作为“当前归属”。
        """
        selected_owner_id = ""
        for entry in membership:
            if isinstance(entry, str) and entry.strip():
                selected_owner_id = entry.strip()
                break

        self._is_refreshing = True
        try:
            self._ensure_items_up_to_date()
            self._select_owner_id(selected_owner_id)
        finally:
            self._is_refreshing = False

        self._current_owner_id = selected_owner_id
        self.setEnabled(bool(self._packages) or self._include_shared)
        self._sync_line_edit_text()

    def clear_membership(self) -> None:
        self._packages = []
        self._current_owner_id = ""
        self._items_token = ""
        self._items_built = False
        self._is_refreshing = True
        try:
            self.clear()
        finally:
            self._is_refreshing = False

        if self.lineEdit():
            self.lineEdit().setText("-")
        self.setEnabled(False)

    def _build_items_token(self) -> str:
        """构建下拉内容的稳定 token，用于避免重复重建 items。"""
        parts: list[str] = []
        parts.append("shared=1" if self._include_shared else "shared=0")
        for package in self._packages:
            package_id_value = package.get("package_id", "")
            if not isinstance(package_id_value, str) or not package_id_value.strip():
                continue
            package_id = package_id_value.strip()
            package_name_value = package.get("name", package_id)
            package_name = (
                str(package_name_value).strip() if package_name_value is not None else ""
            ) or package_id
            parts.append(f"{package_id}:{package_name}")
        return "|".join(parts)

    def _ensure_items_up_to_date(self) -> None:
        """仅在 packages/include_shared 变化时重建 items。"""
        token = self._build_items_token()
        if self._items_built and token == self._items_token:
            return
        self._items_token = token
        self._items_built = True

        self.clear()

        def _add_item(display_text: str, owner_id: str) -> None:
            self.addItem(display_text, owner_id)

        if self._include_shared:
            # “共享”需要足够醒目：当前项目视图下会混入共享资源，必须让用户一眼区分。
            _add_item("🌐 共享", "shared")

        for package in self._packages:
            package_id_value = package.get("package_id", "")
            if not isinstance(package_id_value, str) or not package_id_value.strip():
                continue
            package_id = package_id_value.strip()
            package_name_value = package.get("name", package_id)
            package_name = (
                str(package_name_value).strip() if package_name_value is not None else ""
            ) or package_id
            _add_item(package_name, package_id)

    def _select_owner_id(self, selected_owner_id: str) -> None:
        if not selected_owner_id:
            self.setCurrentIndex(-1)
            return

        # 选中匹配项；若不存在则保持不选中
        for index in range(self.count()):
            owner_id = self.itemData(index)
            if owner_id == selected_owner_id:
                self.setCurrentIndex(index)
                return
        self.setCurrentIndex(-1)

    def _sync_line_edit_text(self) -> None:
        line_edit = self.lineEdit()
        if line_edit is None:
            return
        if not self._current_owner_id:
            line_edit.setText("<未设置>")
            return
        current_text = self.currentText()
        line_edit.setText(current_text if current_text else "<未设置>")

    def _find_index_for_owner_id(self, owner_id: str) -> int:
        owner_id_text = str(owner_id or "").strip()
        if not owner_id_text:
            return -1
        for index in range(self.count()):
            candidate = self.itemData(index)
            candidate_text = str(candidate).strip() if candidate is not None else ""
            if candidate_text == owner_id_text:
                return index
        return -1

    def _format_owner_label(self, owner_id: str) -> str:
        owner_id_text = str(owner_id or "").strip()
        if not owner_id_text:
            return "<未设置>"
        index = self._find_index_for_owner_id(owner_id_text)
        if index >= 0:
            return self.itemText(index) or owner_id_text
        return owner_id_text

    def _on_current_index_changed(self, index: int) -> None:
        if self._is_refreshing:
            return
        if index < 0:
            self._current_owner_id = ""
            self._sync_line_edit_text()
            return
        owner_id = self.itemData(index)
        owner_id_text = str(owner_id).strip() if owner_id is not None else ""
        if not owner_id_text:
            return
        if owner_id_text == self._current_owner_id:
            self._sync_line_edit_text()
            return

        previous_owner_id = self._current_owner_id
        previous_label = self._format_owner_label(previous_owner_id)
        next_label = self.itemText(index) or owner_id_text

        hint_lines: list[str] = []
        if owner_id_text == "shared":
            hint_lines.append("切换到「共享」后：所有存档都能看到并直接使用该资源。")
        else:
            hint_lines.append("切换到某个存档后：该资源将归属该存档（其它存档将不再显示）。")

        confirmed = ask_yes_no_dialog(
            self,
            "确认切换所属存档",
            (
                f"即将把该资源的归属从「{previous_label}」切换到「{next_label}」。\n\n"
                + "\n".join(hint_lines)
                + "\n\n该操作会移动资源文件位置。\n是否继续？"
            ),
            default_yes=False,
        )
        if not confirmed:
            # 用户取消：回滚 UI 选择，保持与磁盘归属一致。
            restore_index = self._find_index_for_owner_id(previous_owner_id)
            self._is_refreshing = True
            try:
                self.setCurrentIndex(restore_index)
            finally:
                self._is_refreshing = False
            self._sync_line_edit_text()
            return

        self._current_owner_id = owner_id_text
        self._sync_line_edit_text()
        # 单选：恒为 True（表示切换目标）
        self.membership_changed.emit(owner_id_text, True)


class _ClickToShowPopupFilter(QtCore.QObject):
    """将任意区域的鼠标点击转发为 QComboBox.showPopup()。

    背景：PackageMembershipSelector 为了展示 placeholder 使用了 editable + 只读 lineEdit，
    Qt 默认行为下点击 lineEdit 区域不会弹出下拉框，只有点右侧小箭头才会展开。
    """

    def __init__(
        self,
        selector: PackageMembershipSelector,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._selector = selector

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.Type.MouseButtonPress:
            mouse_event = event
            if (
                hasattr(mouse_event, "button")
                and mouse_event.button() == QtCore.Qt.MouseButton.LeftButton
                and self._selector.isEnabled()
            ):
                self._selector.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
                self._selector.showPopup()
                return True
        return super().eventFilter(watched, event)


def build_package_membership_row(
    parent_layout: QtWidgets.QBoxLayout,
    selector_parent: QtWidgets.QWidget,
    on_membership_changed: Callable[[str, bool], None],
    label_text: str = "所属项目存档:",
) -> Tuple[QtWidgets.QWidget, QtWidgets.QLabel, PackageMembershipSelector]:
    """
    构建一行标准的“所属项目存档”行并挂载到给定布局上。

    设计约定：
    - 左侧固定为文本标签（默认“所属项目存档:”），右侧为 `PackageMembershipSelector`；
    - 行内边距为 0，横向间距使用 `Sizes.SPACING_MEDIUM`；
    - 返回 (container_widget, label_widget, selector) 便于调用方保存引用和控制显隐。
    """
    container_widget = QtWidgets.QWidget(selector_parent)
    row_layout = QtWidgets.QHBoxLayout(container_widget)
    row_layout.setContentsMargins(0, 0, 0, 0)
    row_layout.setSpacing(Sizes.SPACING_MEDIUM)

    label_widget = QtWidgets.QLabel(label_text, container_widget)
    package_selector = PackageMembershipSelector(selector_parent)
    package_selector.membership_changed.connect(on_membership_changed)

    # 交互改进：整行可点击展开（包含标签、文字区域，不仅是右侧小箭头）
    click_filter = _ClickToShowPopupFilter(package_selector, parent=container_widget)
    container_widget.installEventFilter(click_filter)
    label_widget.installEventFilter(click_filter)
    package_selector.installEventFilter(click_filter)
    line_edit = package_selector.lineEdit()
    if line_edit is not None:
        line_edit.installEventFilter(click_filter)
    # 显式持有引用，避免潜在 GC 造成过滤器失效（即使 parent 绑定也保留一份更直观）。
    setattr(container_widget, "_package_membership_click_filter", click_filter)

    row_layout.addWidget(label_widget)
    row_layout.addWidget(package_selector, 1)

    parent_layout.addWidget(container_widget)
    return container_widget, label_widget, package_selector

