"""标准双栏“左树右列表”库页骨架。

目的：
- 元件库/实体摆放等页面高度同构：标题行右侧搜索框 + 标题下工具栏按钮行 + 左侧分类树 + 右侧列表。
- 将 UI 骨架集中实现，页面只保留“业务差异”（分类树内容、列表构建、选中信号与增删逻辑），避免修一页忘一页。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PyQt6 import QtCore, QtWidgets

from app.ui.foundation.theme_manager import Sizes
from app.ui.graph.library_pages.library_scaffold import DualPaneLibraryScaffold


@dataclass(frozen=True)
class StandardDualPaneListWidgets:
    """标准双栏库页骨架创建后对外暴露的核心控件集合。"""

    search_edit: QtWidgets.QLineEdit
    toolbar_widget: QtWidgets.QWidget
    category_tree: QtWidgets.QTreeWidget
    list_widget: QtWidgets.QListWidget
    right_container: QtWidgets.QWidget


class StandardDualPaneListPage(DualPaneLibraryScaffold):
    """提供“搜索 + 工具栏 + 左树右列表”的通用 UI 构建方法。"""

    def build_standard_dual_pane_list_ui(
        self,
        *,
        search_placeholder: str,
        toolbar_buttons: list[QtWidgets.QAbstractButton],
        left_header_label: str,
        left_title: str,
        left_description: str,
        right_title: str,
        right_description: str,
        list_object_name: Optional[str] = None,
        tree_indentation: Optional[int] = None,
        wrap_right_list: bool = True,
    ) -> StandardDualPaneListWidgets:
        """构建标准库页骨架并返回关键控件引用。

        注意：本方法只负责 UI 骨架，不连接任何业务信号；业务连接由子类完成。
        """
        # 顶部：标题右侧搜索框（actions 区）
        search_edit = QtWidgets.QLineEdit(self)
        search_edit.setPlaceholderText(search_placeholder)
        search_edit.setMinimumHeight(Sizes.INPUT_HEIGHT)
        self.add_action_widget(search_edit)

        # 标题下方：工具栏按钮行（仅放主操作按钮）
        toolbar_widget = QtWidgets.QWidget(self)
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        self.init_toolbar(toolbar_layout)
        for button in toolbar_buttons:
            button.setMinimumHeight(Sizes.BUTTON_HEIGHT)
        self.setup_toolbar_with_search(toolbar_layout, toolbar_buttons, None)
        self.set_status_widget(toolbar_widget)

        # 左侧分类树
        category_tree = QtWidgets.QTreeWidget(self)
        category_tree.setHeaderLabel(left_header_label)
        category_tree.setObjectName("leftPanel")
        category_tree.setFixedWidth(Sizes.LEFT_PANEL_WIDTH)
        if tree_indentation is not None:
            category_tree.setIndentation(tree_indentation)

        # 右侧列表
        list_widget = QtWidgets.QListWidget(self)
        list_widget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        if list_object_name:
            list_widget.setObjectName(list_object_name)

        if wrap_right_list:
            right_container = QtWidgets.QWidget(self)
            right_layout = QtWidgets.QVBoxLayout(right_container)
            right_layout.setContentsMargins(0, 0, 0, 0)
            right_layout.setSpacing(0)
            right_layout.addWidget(list_widget)
            right_widget: QtWidgets.QWidget = right_container
        else:
            right_container = list_widget
            right_widget = list_widget

        self.build_dual_pane(
            category_tree,
            right_widget,
            left_title=left_title,
            left_description=left_description,
            right_title=right_title,
            right_description=right_description,
        )

        return StandardDualPaneListWidgets(
            search_edit=search_edit,
            toolbar_widget=toolbar_widget,
            category_tree=category_tree,
            list_widget=list_widget,
            right_container=right_container,
        )








