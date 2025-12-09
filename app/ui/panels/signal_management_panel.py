from __future__ import annotations

"""信号管理右侧编辑面板。

作为主窗口右侧标签页中的一个面板，承载信号的编辑器与“使用情况”摘要：
- 上方标题与说明由 `PanelScaffold` 提供；
- 中部通过 `QTabWidget` 区分“基本信息”和“使用情况”；
- “基本信息”页内嵌 `SignalEditorWidget`，用于编辑信号名、描述与参数列表；
- “使用情况”页展示当前信号在服务器节点图中的引用统计文本。

本面板只关心 UI 组织与展示，具体的数据加载与保存逻辑由 `SignalsPage`
通过公开属性 `editor/usage_label/tab_widget` 间接驱动。
"""

from PyQt6 import QtCore, QtWidgets

from ui.dialogs.signal_edit_dialog import SignalEditorWidget
from ui.foundation.theme_manager import ThemeManager, Sizes
from ui.panels.package_membership_selector import (
    PackageMembershipSelector,
    build_package_membership_row,
)
from ui.panels.panel_scaffold import PanelScaffold, build_scrollable_column


class SignalManagementPanel(PanelScaffold):
    """信号管理右侧编辑面板。

    左侧列表负责选择信号，本面板负责：
    - 展示与编辑信号的基础信息与参数；
    - 通过统一的“所属存档”多选行维护信号与功能包之间的多对多归属关系。
    """

    # 信号所属存档变更 (signal_id, package_id, is_checked)
    signal_package_membership_changed = QtCore.pyqtSignal(str, str, bool)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(
            parent,
            title="信号详情",
            description=(
                "信号定义已迁移为代码级常量：左侧选择信号以查看名称与参数，"
                "实际增删改请在对应的 Python 模块中完成。"
            ),
        )
        self._package_row_widget: QtWidgets.QWidget
        self._package_label: QtWidgets.QLabel
        self._package_selector: PackageMembershipSelector
        self._current_signal_id: str | None = None

        (
            self._package_row_widget,
            self._package_label,
            self._package_selector,
        ) = build_package_membership_row(
            self.body_layout,
            self,
            self._on_package_membership_changed,
            label_text="所属存档:",
        )
        # 初始阶段尚未选中具体信号，仅禁用下拉，多选行本身保持可见以统一布局
        self._package_selector.setEnabled(False)

        self.tab_widget = QtWidgets.QTabWidget(self)
        self.body_layout.addWidget(self.tab_widget, 1)

        basic_tab = QtWidgets.QWidget(self.tab_widget)
        basic_layout = QtWidgets.QVBoxLayout(basic_tab)
        basic_layout.setContentsMargins(0, 0, 0, 0)
        basic_layout.setSpacing(Sizes.SPACING_SMALL)

        (
            scroll_area,
            editor_container,
            editor_layout,
        ) = build_scrollable_column(
            basic_tab,
            spacing=Sizes.SPACING_SMALL,
            margins=(0, 0, 0, 0),
            alignment=QtCore.Qt.AlignmentFlag.AlignTop,
            add_trailing_stretch=True,
        )

        self.editor = SignalEditorWidget(editor_container)
        stretch_index = max(editor_layout.count() - 1, 0)
        editor_layout.insertWidget(stretch_index, self.editor)
        basic_layout.addWidget(scroll_area, 1)
        self.tab_widget.addTab(basic_tab, "基本信息")

        usage_tab = QtWidgets.QWidget(self.tab_widget)
        usage_layout = QtWidgets.QVBoxLayout(usage_tab)
        usage_layout.setContentsMargins(0, 0, 0, 0)
        usage_layout.setSpacing(Sizes.SPACING_SMALL)

        self.usage_label = QtWidgets.QLabel("未选择信号", usage_tab)
        self.usage_label.setStyleSheet(ThemeManager.info_label_style())
        self.usage_label.setWordWrap(True)
        usage_layout.addWidget(self.usage_label)
        usage_layout.addStretch(1)

        self.tab_widget.addTab(usage_tab, "使用情况")

        # 管理模式下信号详情面板当前仅作为只读视图使用，实际定义在代码中维护。
        # 对话框等其它入口若需要可编辑能力，可直接使用 `SignalEditorWidget` 并保持默认状态。
        self.editor.set_read_only(True)

    def set_package_display(self, text: str) -> None:
        """更新“所属存档”行标题。

        当前实现保持标签文本为统一的“所属存档:”，具体视图上下文（如“<全部资源>”、
        “<未分类资源>”或具体存档名称）由外层页面通过标题、描述等位置展示，不再在
        本行标签后追加括号说明，避免与其它复用该行布局的面板样式不一致。
        """
        _ = text  # 视图上下文目前仅用于外层展示，这里保持统一文案
        self._package_label.setText("所属存档:")

    def set_signal_membership(self, packages: list[dict], membership: set[str]) -> None:
        """根据给定包列表与归属集合更新多选下拉状态。

        `packages` 期望包含至少 `package_id` 与 `name` 字段。
        """
        if not packages:
            self._package_selector.clear_membership()
            self._package_selector.setEnabled(False)
            return

        self._package_selector.set_packages(packages)
        self._package_selector.set_membership(membership)
        # 仅在存在当前选中信号时允许编辑归属；无选中信号时保持禁用，但仍展示全部存档列表
        self._package_selector.setEnabled(self._current_signal_id is not None)

    def set_current_signal_id(self, signal_id: str | None) -> None:
        """更新当前正在编辑的信号 ID，用于在归属变更时发射完整上下文。"""
        self._current_signal_id = signal_id
        if signal_id is None:
            self._package_selector.clear_membership()
            self._package_selector.setEnabled(False)

    def set_usage_text(self, text: str) -> None:
        """更新“使用情况”页中的摘要文本。"""
        self.usage_label.setText(text)

    def reset(self) -> None:
        """清空右侧编辑器显示，但保留控件结构。"""
        self.editor.clear()
        self.usage_label.setText("未选择信号")
        self.tab_widget.setCurrentIndex(0)
        self.set_current_signal_id(None)

    def _on_package_membership_changed(self, package_id: str, is_checked: bool) -> None:
        """用户在“所属存档”多选下拉中勾选/取消某个存档时触发。"""
        if not package_id:
            return
        if not self._current_signal_id:
            return
        self.signal_package_membership_changed.emit(
            self._current_signal_id,
            package_id,
            is_checked,
        )


