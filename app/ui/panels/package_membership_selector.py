from __future__ import annotations

from typing import Callable, Iterable, List, Optional, Sequence, Set, Tuple

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.foundation.theme_manager import Sizes


class PackageMembershipSelector(QtWidgets.QComboBox):
    """带复选的存档选择器，封装检查逻辑和展示文案。"""

    membership_changed = QtCore.pyqtSignal(str, bool)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self._is_popup_visible: bool = False
        line_edit = self.lineEdit()
        if line_edit:
            line_edit.setReadOnly(True)
            line_edit.setPlaceholderText("<未设置>")
            # 禁止文本选择，点击整块区域仅用于展开/收起下拉，不触发文本选中
            if hasattr(line_edit, "setTextInteractionFlags"):
                line_edit.setTextInteractionFlags(
                    QtCore.Qt.TextInteractionFlag.NoTextInteraction
                )
            line_edit.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self._model = QtGui.QStandardItemModel(self)
        self.setModel(self._model)
        self._packages: List[dict] = []
        self._current_membership: Set[str] = set()
        self._is_refreshing = False
        self._model.itemChanged.connect(self._on_item_changed)
        self.installEventFilter(self)
        if line_edit:
            line_edit.installEventFilter(self)
        if self.view():
            self.view().setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
            self.view().pressed.connect(self._on_view_pressed)
        self.setEnabled(False)

    def showPopup(self) -> None:  # type: ignore[override]
        """显式记录下拉框展开状态，便于实现点击组件区域的展开/收起切换。"""
        super().showPopup()
        self._is_popup_visible = True

    def hidePopup(self) -> None:  # type: ignore[override]
        """隐藏下拉框时同步更新内部状态标记。"""
        super().hidePopup()
        self._is_popup_visible = False

    def set_packages(self, packages: Sequence[dict]) -> None:
        self._packages = list(packages)

    def set_membership(self, membership: Iterable[str]) -> None:
        self._current_membership = set(membership)
        self._refresh_items()
        self.setEnabled(bool(self._packages))

    def clear_membership(self) -> None:
        self._current_membership.clear()
        self._model.clear()
        if self.lineEdit():
            self.lineEdit().setText("-")
        self.setEnabled(False)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if watched in (self, self.lineEdit()):
            event_type = event.type()
            if event_type in (
                QtCore.QEvent.Type.MouseButtonPress,
                QtCore.QEvent.Type.MouseButtonDblClick,
            ):
                # 统一行为：点击组件区域仅在“展开/收起”之间切换；不穿透到内部编辑逻辑。
                if self._is_popup_visible:
                    self.hidePopup()
                else:
                    self.showPopup()
                return True
            # 避免鼠标释放再次触发 QComboBox 默认的展开逻辑，导致“先收起又立刻重新展开”
            if event_type == QtCore.QEvent.Type.MouseButtonRelease:
                return True
            # 阻止拖动过程中对文本的选择
            if (
                event_type == QtCore.QEvent.Type.MouseMove
                and isinstance(event, QtGui.QMouseEvent)
                and event.buttons() & QtCore.Qt.MouseButton.LeftButton
            ):
                return True
        return super().eventFilter(watched, event)

    def _refresh_items(self) -> None:
        self._is_refreshing = True
        self._model.clear()
        for package in self._packages:
            pkg_id = package.get("package_id", "")
            pkg_name = package.get("name", pkg_id)
            item = QtGui.QStandardItem(pkg_name or pkg_id)
            item.setFlags(
                QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsUserCheckable
            )
            state = (
                QtCore.Qt.CheckState.Checked
                if pkg_id in self._current_membership
                else QtCore.Qt.CheckState.Unchecked
            )
            item.setCheckState(state)
            item.setData(pkg_id, QtCore.Qt.ItemDataRole.UserRole)
            self._model.appendRow(item)
        self._is_refreshing = False
        self._update_display_text()

    def _on_view_pressed(self, index: QtCore.QModelIndex) -> None:
        if not index.isValid():
            return
        item = self._model.itemFromIndex(index)
        if not item:
            return
        new_state = (
            QtCore.Qt.CheckState.Unchecked
            if item.checkState() == QtCore.Qt.CheckState.Checked
            else QtCore.Qt.CheckState.Checked
        )
        item.setCheckState(new_state)

    def _on_item_changed(self, item: QtGui.QStandardItem) -> None:
        if self._is_refreshing:
            return
        pkg_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not pkg_id:
            return
        is_checked = item.checkState() == QtCore.Qt.CheckState.Checked
        if is_checked:
            self._current_membership.add(pkg_id)
        else:
            self._current_membership.discard(pkg_id)
        self._update_display_text()
        self.membership_changed.emit(pkg_id, is_checked)

    def _update_display_text(self) -> None:
        if not self.lineEdit():
            return
        if not self._current_membership:
            self.lineEdit().setText("<未设置>")
            return
        names: List[str] = []
        for pkg in self._packages:
            package_id_value = pkg.get("package_id", "")
            if package_id_value in self._current_membership:
                names.append(pkg.get("name", package_id_value))
        self.lineEdit().setText("、".join(names))


def build_package_membership_row(
    parent_layout: QtWidgets.QBoxLayout,
    selector_parent: QtWidgets.QWidget,
    on_membership_changed: Callable[[str, bool], None],
    label_text: str = "所属存档:",
) -> Tuple[QtWidgets.QWidget, QtWidgets.QLabel, PackageMembershipSelector]:
    """
    构建一行标准的“所属存档”行并挂载到给定布局上。

    设计约定：
    - 左侧固定为文本标签（默认“所属存档:”），右侧为 `PackageMembershipSelector`；
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

    row_layout.addWidget(label_widget)
    row_layout.addWidget(package_selector, 1)

    parent_layout.addWidget(container_widget)
    return container_widget, label_widget, package_selector

