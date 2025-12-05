from __future__ import annotations

from typing import List

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt

from app.models import TodoItem
from ui.todo.todo_config import TodoStyles, LayoutConstants
from ui.todo.todo_detail_model import DetailDocument
from ui.todo.todo_detail_renderer import TodoDetailBuilder
from ui.todo.todo_detail_adapter import TodoDetailAdapter
from ui.todo.todo_widgets import create_execute_button


class TodoDetailView(QtWidgets.QWidget):
    """基于 DetailDocument 的只读详情视图。

    不依赖 TodoItem，仅负责将结构化文档渲染为若干 QLabel/QTableWidget 等控件。
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._layout = layout

    def clear(self) -> None:
        """清空当前内容控件。"""
        while self._layout.count() > 0:
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def render(self, document: DetailDocument) -> None:
        """根据给定的 DetailDocument 重建视图内容。"""
        self.clear()
        if document.is_empty():
            return

        for section in document.sections:
            if section.title:
                title_label = QtWidgets.QLabel(section.title)
                font = title_label.font()
                # level 越小视为层级越高，这里简单用字号表达
                if section.level <= 3:
                    font.setPointSize(font.pointSize() + 2)
                    font.setBold(True)
                elif section.level == 4:
                    font.setBold(True)
                title_label.setFont(font)
                title_label.setWordWrap(True)
                self._layout.addWidget(title_label)

            for block in section.blocks:
                from ui.todo.todo_detail_model import ParagraphBlock, ParagraphStyle, TableBlock, BulletListBlock

                if isinstance(block, ParagraphBlock):
                    label = QtWidgets.QLabel(block.text)
                    label.setWordWrap(True)
                    font = label.font()
                    if block.style == ParagraphStyle.EMPHASIS:
                        font.setBold(True)
                    elif block.style == ParagraphStyle.HINT:
                        font.setPointSize(max(font.pointSize() - 1, 8))
                    label.setFont(font)
                    self._layout.addWidget(label)
                elif isinstance(block, BulletListBlock):
                    for item_text in block.items:
                        bullet_label = QtWidgets.QLabel(f"• {item_text}")
                        bullet_label.setWordWrap(True)
                        self._layout.addWidget(bullet_label)
                elif isinstance(block, TableBlock):
                    headers = list(block.headers)
                    rows = list(block.rows)
                    if not rows:
                        continue
                    row_count = len(rows)
                    column_count = len(rows[0]) if rows[0] else 0
                    if column_count == 0:
                        continue
                    table = QtWidgets.QTableWidget(row_count, column_count, self)
                    table.setEditTriggers(
                        QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
                    )
                    table.setSelectionMode(
                        QtWidgets.QAbstractItemView.SelectionMode.NoSelection
                    )
                    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                    if headers and len(headers) == column_count:
                        table.setHorizontalHeaderLabels(headers)
                    else:
                        table.horizontalHeader().hide()
                    for row_index, row in enumerate(rows):
                        for column_index, cell_text in enumerate(row):
                            item = QtWidgets.QTableWidgetItem(str(cell_text))
                            table.setItem(row_index, column_index, item)
                    table.resizeRowsToContents()
                    header = table.horizontalHeader()
                    header.setStretchLastSection(True)
                    header.setSectionResizeMode(
                        QtWidgets.QHeaderView.ResizeMode.ResizeToContents
                    )
                    table.verticalHeader().hide()
                    table.setSizePolicy(
                        QtWidgets.QSizePolicy.Policy.Expanding,
                        QtWidgets.QSizePolicy.Policy.Fixed,
                    )
                    table.setHorizontalScrollBarPolicy(
                        Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                    )
                    table.setVerticalScrollBarPolicy(
                        Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                    )
                    table.setMinimumHeight(table.sizeHint().height())
                    self._layout.addWidget(table)

        # 在末尾增加少量伸缩空间，令滚动体验更自然
        self._layout.addStretch(1)


class TodoDetailPanel(QtWidgets.QWidget):
    """右侧详情页：标题/描述/HTML 详情 + 执行按钮。

    依赖适配器与渲染器完成统计与 HTML 生成。
    """

    execute_clicked = QtCore.pyqtSignal()
    execute_remaining_clicked = QtCore.pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setObjectName("detailCard")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        title_label = QtWidgets.QLabel("任务详情")
        title_font = title_label.font()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        scroll = QtWidgets.QScrollArea()
        scroll.setObjectName("detailScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        self.detail_widget = QtWidgets.QWidget()
        self.detail_layout = QtWidgets.QVBoxLayout(self.detail_widget)
        self.detail_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.detail_layout.setSpacing(10)

        self.detail_title = QtWidgets.QLabel("请选择一个任务")
        self.detail_title.setObjectName("detailContentTitle")
        self.detail_title.setWordWrap(True)
        font = self.detail_title.font()
        font.setPointSize(14)
        font.setBold(True)
        self.detail_title.setFont(font)
        self.detail_layout.addWidget(self.detail_title)

        self.detail_desc = QtWidgets.QLabel("")
        self.detail_desc.setObjectName("detailContentDesc")
        self.detail_desc.setWordWrap(True)
        self.detail_layout.addWidget(self.detail_desc)

        self.execute_button = create_execute_button(
            self,
            self.execute_clicked.emit,
            minimum_height=40,
        )
        self.detail_layout.addWidget(self.execute_button)

        # 执行剩余步骤按钮（与当前步骤同级从本步到末尾）
        self.execute_remaining_button = QtWidgets.QPushButton("执行剩余步骤")
        self.execute_remaining_button.setMinimumHeight(36)
        self.execute_remaining_button.setStyleSheet(TodoStyles.execute_button_qss())
        self.execute_remaining_button.setVisible(False)
        self.execute_remaining_button.clicked.connect(self.execute_remaining_clicked.emit)
        self.detail_layout.addWidget(self.execute_remaining_button)

        self.detail_view = TodoDetailView(self.detail_widget)
        self.detail_view.setObjectName("detailContentText")
        self.detail_view.setMinimumHeight(LayoutConstants.DETAIL_TEXT_MIN_HEIGHT)
        self.detail_layout.addWidget(self.detail_view)

        scroll.setWidget(self.detail_widget)
        layout.addWidget(scroll)

        # 渲染器与适配器
        self.detail_adapter = TodoDetailAdapter(self)
        self.detail_builder = TodoDetailBuilder(
            self.detail_adapter.collect_categories_info,
            self.detail_adapter.collect_category_items,
            self.detail_adapter.collect_template_summary,
            self.detail_adapter.collect_instance_summary,
        )
        self.current_detail_info: dict | None = None
        # 宿主列表组件（用于访问 todo_map 等运行态数据源）
        self.host_list_widget = None

    @property
    def todo_map(self):
        """为适配器提供统一的 todo_map 访问入口。
        优先从宿主的 TreeManager 读取（权威来源），回退到宿主自身的 todo_map，最后回退为空映射。
        """
        host = self.host_list_widget
        if host is not None:
            if hasattr(host, "tree_manager") and hasattr(host.tree_manager, "todo_map"):
                return host.tree_manager.todo_map
            if hasattr(host, "todo_map"):
                return host.todo_map
        return {}

    @property
    def resource_manager(self):
        """为适配器提供统一的 ResourceManager 访问入口。

        优先从宿主 TodoListWidget 注入的 `resource_manager` 读取，避免在适配器中直接依赖 MainWindow。
        """
        host = self.host_list_widget
        if host is not None and hasattr(host, "resource_manager"):
            return host.resource_manager
        return None

    def set_detail(self, todo: TodoItem) -> None:
        self.current_detail_info = todo.detail_info
        self.detail_title.setText(todo.title)
        self.detail_desc.setText(todo.description)
        document = self.detail_builder.build_document(todo)
        self.detail_view.render(document)

    def set_execute_visible(self, visible: bool) -> None:
        self.execute_button.setVisible(visible)

    def set_execute_remaining_visible(self, visible: bool) -> None:
        self.execute_remaining_button.setVisible(visible)

    def set_execute_text(self, text: str) -> None:
        self.execute_button.setText(text)

    def set_execute_remaining_text(self, text: str) -> None:
        self.execute_remaining_button.setText(text)


