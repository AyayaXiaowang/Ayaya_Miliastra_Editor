from __future__ import annotations

from typing import Callable

from PyQt6 import QtCore, QtWidgets

from app.ui.foundation.theme_manager import Sizes
from app.ui.foundation.toolbar_utils import apply_standard_toolbar


class PackageLibraryUiMixin:
    """UI 装配相关逻辑（不含数据构建与预览树填充）。"""

    def _setup_ui(self) -> None:
        # 顶部：标题右侧放搜索框，快速过滤项目存档列表
        self.search_edit = QtWidgets.QLineEdit(self)
        self.search_edit.setPlaceholderText("搜索项目存档...")
        self.search_edit.setMinimumHeight(Sizes.INPUT_HEIGHT)
        self.add_action_widget(self.search_edit)
        self.connect_search(self.search_edit, self._filter_packages, placeholder="搜索项目存档...")

        # 标题下方：项目存档操作按钮行（重命名/删除/刷新）
        toolbar_widget = QtWidgets.QWidget()
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(Sizes.SPACING_MEDIUM)
        apply_standard_toolbar(toolbar_layout)

        # 插件扩展区：允许私有扩展在不触碰内部 layout 的情况下追加按钮
        extension_toolbar_widget = QtWidgets.QWidget(toolbar_widget)
        extension_toolbar_layout = QtWidgets.QHBoxLayout(extension_toolbar_widget)
        extension_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        extension_toolbar_layout.setSpacing(Sizes.SPACING_MEDIUM)
        self._extension_toolbar_layout = extension_toolbar_layout
        self._extension_toolbar_widget_host = extension_toolbar_widget
        toolbar_layout.addWidget(extension_toolbar_widget)

        self.rename_btn = QtWidgets.QPushButton("重命名")
        self.rename_btn.setToolTip("已禁用：项目显示名以目录名为真源，目录重命名风险较高。")
        self.open_btn = QtWidgets.QPushButton("切换为当前")
        self.clone_btn = QtWidgets.QPushButton("复制")
        self.delete_btn = QtWidgets.QPushButton("删除")
        self.refresh_btn = QtWidgets.QPushButton("刷新")

        self.rename_btn.clicked.connect(self._on_rename)
        self.open_btn.clicked.connect(self._on_open_clicked)
        self.clone_btn.clicked.connect(self._on_clone)
        self.delete_btn.clicked.connect(self._on_delete)
        self.refresh_btn.clicked.connect(self.refresh)

        toolbar_layout.addWidget(self.rename_btn)
        toolbar_layout.addWidget(self.open_btn)
        toolbar_layout.addWidget(self.clone_btn)
        toolbar_layout.addWidget(self.delete_btn)
        toolbar_layout.addWidget(self.refresh_btn)
        toolbar_layout.addStretch(1)
        self.set_status_widget(toolbar_widget)

        self.package_list = QtWidgets.QListWidget()
        self.package_list.setObjectName("leftPanel")
        # 不要锁死宽度：该页面使用 QSplitter，左侧列表需要允许用户拖拽分隔线改变宽度。
        # 默认宽度仍以主题 token 为基准，初始分配由 splitter.setSizes(...) 负责。
        self.package_list.setMinimumWidth(Sizes.LEFT_PANEL_WIDTH)
        self.package_list.itemSelectionChanged.connect(self._on_package_selected)
        self.package_list.itemDoubleClicked.connect(self._on_package_item_double_clicked)
        self.package_list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )

        # 右侧：包详情（标题 + 树）
        right_container = QtWidgets.QWidget(self)
        right_layout = QtWidgets.QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self.header_label = QtWidgets.QLabel("")
        header_font = self.header_label.font()
        header_font.setPointSize(Sizes.FONT_LARGE)
        header_font.setBold(True)
        self.header_label.setFont(header_font)
        right_layout.addWidget(self.header_label)

        self.detail_tree = QtWidgets.QTreeWidget()
        self.detail_tree.setHeaderLabels(["类别", "标识/名称", "GUID", "挂载节点图"])
        # 调整列宽：类别列略宽一些，保证中文类别标题与计数完整可见
        self.detail_tree.setColumnWidth(0, 220)
        self.detail_tree.setColumnWidth(1, 220)
        self.detail_tree.setColumnWidth(2, 200)
        self.detail_tree.setColumnWidth(3, 260)
        # 单击明细行时，将对应资源类型与 ID 交给主窗口，由主窗口决定如何在右侧属性面板中展示。
        self.detail_tree.itemClicked.connect(self._on_detail_item_activated)
        # 双击明细行时，尝试跳转到对应的编辑页面（元件库 / 实体摆放 / 节点图编辑器）。
        self.detail_tree.itemDoubleClicked.connect(self._on_detail_item_double_clicked)
        # 展开节点时按需构建子项，避免在切换存档预览时批量创建大量 TreeWidgetItem 造成卡顿。
        self.detail_tree.itemExpanded.connect(self._on_detail_tree_item_expanded)
        right_layout.addWidget(self.detail_tree, 1)

        self.build_dual_pane(
            self.package_list,
            right_container,
            left_title="项目存档列表",
            left_description="选择项目存档或特殊视图",
            right_title="项目存档内容详情",
            right_description="查看元件、实体、管理配置等资源",
        )
        # 左侧默认收窄，但允许用户拖到更宽
        self._splitter.setSizes([Sizes.LEFT_PANEL_WIDTH, 1000])

    def _on_open_clicked(self) -> None:
        """显式切换为当前存档：发射 package_load_requested，由主窗口走切包保护入口处理。"""
        package_id = str(self._current_package_id or "").strip()
        if not package_id:
            return
        self.package_load_requested.emit(package_id)

    def _on_package_item_double_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        """双击左侧存档条目：视为显式切换为当前存档。"""
        if item is None:
            return
        package_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(package_id, str) or not package_id:
            return
        self.package_load_requested.emit(package_id)

    # === 插件扩展：工具栏按钮 ===
    def ensure_extension_toolbar_button(
        self,
        key: str,
        text: str,
        *,
        tooltip: str = "",
        on_clicked: Callable[[], None] | None = None,
        enabled: bool = True,
    ) -> QtWidgets.QPushButton:
        """确保“扩展工具栏”存在一个按钮（幂等）。

        约定：
        - key 必须唯一且非空；同 key 多次调用会复用同一个按钮实例；
        - 为避免插件重复 install 导致多次 connect，这里不会自动替换既有 clicked 连接。
        """
        normalized_key = str(key or "").strip()
        if not normalized_key:
            raise ValueError("extension toolbar button key 不能为空")

        existing = self._extension_toolbar_buttons.get(normalized_key)
        if existing is not None:
            if not isinstance(existing, QtWidgets.QPushButton):
                raise TypeError(
                    f"extension toolbar key 已存在但不是 QPushButton: key={normalized_key!r}, type={type(existing).__name__}"
                )
            existing.setText(str(text))
            if tooltip:
                existing.setToolTip(str(tooltip))
            existing.setEnabled(bool(enabled))
            return existing

        if self._extension_toolbar_layout is None:
            raise RuntimeError("extension toolbar layout 未初始化（_setup_ui 尚未完成）")

        button = QtWidgets.QPushButton(str(text))
        if tooltip:
            button.setToolTip(str(tooltip))
        button.setEnabled(bool(enabled))
        if on_clicked is not None:
            button.clicked.connect(on_clicked)
        self._extension_toolbar_layout.addWidget(button)
        self._extension_toolbar_buttons[normalized_key] = button
        return button

    def ensure_extension_toolbar_widget(
        self,
        key: str,
        create_widget: Callable[[QtWidgets.QWidget], QtWidgets.QWidget],
        *,
        visible: bool = True,
    ) -> QtWidgets.QWidget:
        """确保“扩展工具栏”存在一个自定义 widget（幂等）。

        设计目的：允许插件在项目存档页工具栏注入非按钮控件（例如进度条/状态指示器），
        同时避免插件直接访问内部 layout 私有字段。

        约定：
        - key 必须唯一且非空；
        - 同 key 多次调用会复用同一个 widget 实例；
        - key 不可与 ensure_extension_toolbar_button 的 key 冲突。
        """
        normalized_key = str(key or "").strip()
        if not normalized_key:
            raise ValueError("extension toolbar widget key 不能为空")
        if normalized_key in self._extension_toolbar_buttons:
            raise RuntimeError(f"extension toolbar key 已被按钮占用：{normalized_key!r}")

        existing = self._extension_toolbar_widgets.get(normalized_key)
        if existing is not None:
            existing.setVisible(bool(visible))
            return existing

        if self._extension_toolbar_layout is None:
            raise RuntimeError("extension toolbar layout 未初始化（_setup_ui 尚未完成）")
        if self._extension_toolbar_widget_host is None:
            raise RuntimeError("extension toolbar host 未初始化（_setup_ui 尚未完成）")

        widget = create_widget(self._extension_toolbar_widget_host)
        if not isinstance(widget, QtWidgets.QWidget):
            raise TypeError(
                f"create_widget 必须返回 QWidget（key={normalized_key!r}, got={type(widget).__name__}）"
            )
        widget.setVisible(bool(visible))
        self._extension_toolbar_layout.addWidget(widget)
        self._extension_toolbar_widgets[normalized_key] = widget
        return widget

