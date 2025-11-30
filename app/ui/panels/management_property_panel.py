from __future__ import annotations

"""管理配置通用属性面板 - 作为主窗口右侧“属性”标签在管理模式下的承载面板。

设计目标：
- 只负责展示当前选中管理记录的只读摘要（按列标题 + 单元格文本渲染为表单）。
- 不参与任何保存逻辑，也不直接依赖具体管理页面类型。
- 由主窗口在管理模式下根据页面回调填充内容，并按“有选中 → 显示标签 / 无选中 → 收起标签”
  的规则控制右侧整体可见性，使其行为与模板/实体属性面板保持一致。
"""

from PyQt6 import QtWidgets, QtCore
from typing import Callable, Optional

from ui.foundation.theme_manager import Sizes
from ui.panels.panel_scaffold import PanelScaffold
from ui.panels.package_membership_selector import (
    PackageMembershipSelector,
    build_package_membership_row,
)


class ManagementPropertyPanel(PanelScaffold):
    """管理配置通用属性面板。

    使用 `set_rows()` 接收一组 (label, value) 对并以只读表单形式展示；
    使用 `build_edit_form()` 在同一表单布局中构建可编辑字段；
    面板顶部通过“所属存档”多选行统一管理当前管理记录与各存档之间的归属关系。
    """

    # 资源归属变更 (resource_key, resource_id, package_id, is_checked)
    management_package_membership_changed = QtCore.pyqtSignal(str, str, str, bool)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(
            parent,
            title="管理配置详情",
            description="在左侧选择一条管理配置记录查看详情。",
        )

        self._package_row_widget: Optional[QtWidgets.QWidget] = None
        self._package_label: Optional[QtWidgets.QLabel] = None
        self._package_selector: Optional[PackageMembershipSelector] = None
        self._current_section_key: Optional[str] = None
        self._current_resource_key: Optional[str] = None
        self._current_resource_id: Optional[str] = None

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
        # “所属存档”行在管理模式下经常是唯一一行可编辑内容，此处显式限制其高度，
        # 避免在右侧高面板中被拉伸成一整块大区域，保持与其它属性面板一致的紧凑行高。
        if self._package_row_widget is not None:
            # 行高由内部控件的 sizeHint 自然决定，但不参与纵向拉伸，避免随右侧面板高度一起被拔高。
            self._package_row_widget.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Preferred,
                QtWidgets.QSizePolicy.Policy.Maximum,
            )
        if self._package_selector is not None:
            self._package_selector.setEnabled(False)

        self._form_container = QtWidgets.QWidget(self)
        self._form_layout = QtWidgets.QFormLayout(self._form_container)
        self._form_layout.setContentsMargins(0, 0, 0, 0)
        # 管理属性/编辑表单整体采用更紧凑的行间距，避免在右侧宽面板中出现“行与行之间过于疏松”的观感。
        self._form_layout.setHorizontalSpacing(Sizes.SPACING_SMALL)
        self._form_layout.setVerticalSpacing(Sizes.SPACING_TINY)
        # 关键：表单容器自身高度不再“拉伸填满”整个右侧面板，
        # 而是以内容自然高度为主，避免在记录较少时 QFormLayout 将多余高度
        # 平均分摊到每一行，造成看起来像“填充式”的大块行间空白。
        self._form_container.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Maximum,
        )
        # 显式将表单容器对齐到内容区域顶部，避免在行数较少时整体垂直居中。
        self.body_layout.addWidget(
            self._form_container,
            0,
            QtCore.Qt.AlignmentFlag.AlignTop,
        )
        # 将多余的垂直空间交给末尾的伸缩项，而不是平均摊到“所属存档”行与表单行上，
        # 这样在仅展示少量字段时，面板顶部区域仍然保持紧凑，不会出现单行控件占据整块空间的观感。
        self.body_layout.addStretch(1)
        self.setEnabled(False)

    def _clear_rows(self) -> None:
        """清空当前所有展示行。"""
        while self._form_layout.rowCount():
            self._form_layout.removeRow(0)

    def _clear_membership_context(self) -> None:
        """清空当前的所属存档上下文并禁用选择器。"""
        self._current_section_key = None
        self._current_resource_key = None
        self._current_resource_id = None
        if self._package_selector is not None:
            self._package_selector.clear_membership()
            self._package_selector.setEnabled(False)

    def _on_package_membership_changed(self, package_id: str, is_checked: bool) -> None:
        """用户在“所属存档”多选行中勾选/取消某个存档时回调。"""
        if not package_id:
            return
        if not self._current_resource_key or not self._current_resource_id:
            return
        self.management_package_membership_changed.emit(
            self._current_resource_key,
            self._current_resource_id,
            package_id,
            is_checked,
        )

    def set_membership_context(
        self,
        section_key: str,
        resource_key: str,
        resource_id: str,
        packages: list[dict],
        membership: set[str],
    ) -> None:
        """为当前管理记录更新“所属存档”多选行。

        section_key 仅用于标识当前管理类型，真正写回索引时由上层处理；
        resource_key/resource_id 对应 PackageIndex.resources.management 中的键与资源 ID。
        """
        self._current_section_key = section_key
        self._current_resource_key = resource_key
        self._current_resource_id = resource_id

        selector = self._package_selector
        if selector is None:
            return
        if not packages or not resource_id or not resource_key:
            self._clear_membership_context()
            return

        selector.set_packages(packages)
        selector.set_membership(membership)
        selector.setEnabled(True)

    def set_header(self, title: str, description: str) -> None:
        """更新面板标题与说明。"""
        if title:
            self.set_title(title)
        if description:
            self.set_description(description)

    def set_rows(self, rows: list[tuple[str, str]]) -> None:
        """以 (label, value) 对的形式更新展示内容。"""
        self._clear_rows()
        for label, value in rows:
            label_widget = QtWidgets.QLabel(label)
            value_widget = QtWidgets.QLabel(value)
            value_widget.setWordWrap(True)
            self._form_layout.addRow(label_widget, value_widget)
        self.setEnabled(bool(rows))

    def build_edit_form(
        self,
        title: str,
        description: str,
        build_form: Callable[[QtWidgets.QFormLayout], None],
    ) -> None:
        """使用给定构建函数在面板中搭建可编辑表单。

        本方法只负责清空现有行、更新标题与说明，并在回调中构建具体输入控件，
        不直接参与数据校验与持久化逻辑。
        """
        self.set_header(title, description)
        self._clear_rows()
        build_form(self._form_layout)
        self.setEnabled(True)

    def clear(self) -> None:
        """清空并禁用面板，用于“无有效选中对象”的场景。"""
        self._clear_rows()
        self._clear_membership_context()
        self.setEnabled(False)


