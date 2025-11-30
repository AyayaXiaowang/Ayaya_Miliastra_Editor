from __future__ import annotations

from typing import List

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt

from app.models import TodoItem
from ui.todo.todo_config import TodoStyles, LayoutConstants
from ui.todo.todo_detail_renderer import TodoDetailRenderer
from ui.todo.todo_detail_adapter import TodoDetailAdapter
from ui.todo.todo_widgets import create_execute_button


class TodoDetailPanel(QtWidgets.QWidget):
    """右侧详情页：标题/描述/HTML 详情 + 执行按钮。

    依赖适配器与渲染器完成统计与 HTML 生成。
    """

    execute_clicked = QtCore.pyqtSignal()
    execute_remaining_clicked = QtCore.pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

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
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        self.detail_widget = QtWidgets.QWidget()
        self.detail_layout = QtWidgets.QVBoxLayout(self.detail_widget)
        self.detail_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.detail_layout.setSpacing(10)

        self.detail_title = QtWidgets.QLabel("请选择一个任务")
        self.detail_title.setWordWrap(True)
        font = self.detail_title.font()
        font.setPointSize(14)
        font.setBold(True)
        self.detail_title.setFont(font)
        self.detail_layout.addWidget(self.detail_title)

        self.detail_desc = QtWidgets.QLabel("")
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
        self.execute_remaining_button.setStyleSheet(TodoStyles.EXECUTE_BUTTON_QSS)
        self.execute_remaining_button.setVisible(False)
        self.execute_remaining_button.clicked.connect(self.execute_remaining_clicked.emit)
        self.detail_layout.addWidget(self.execute_remaining_button)

        self.detail_text = QtWidgets.QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMinimumHeight(LayoutConstants.DETAIL_TEXT_MIN_HEIGHT)
        self.detail_layout.addWidget(self.detail_text)

        scroll.setWidget(self.detail_widget)
        layout.addWidget(scroll)

        # 渲染器与适配器
        self.detail_adapter = TodoDetailAdapter(self)
        self.detail_renderer = TodoDetailRenderer(
            self._build_table,
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

    def _build_table(self, headers: List[str], rows: List[List[str]]) -> str:
        parts = ["<table>"]
        if headers:
            parts.append("<tr>" + "".join(f"<th>{h}</th>" for h in headers) + "</tr>")
        for row in rows:
            parts.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>")
        parts.append("</table>")
        return "".join(parts)

    def format_detail_html(self, todo: TodoItem) -> str:
        return self.detail_renderer.format_detail_html(todo)

    def set_detail(self, todo: TodoItem) -> None:
        self.current_detail_info = todo.detail_info
        self.detail_title.setText(todo.title)
        self.detail_desc.setText(todo.description)
        html = self.format_detail_html(todo)
        self.detail_text.setHtml(html)

    def set_execute_visible(self, visible: bool) -> None:
        self.execute_button.setVisible(visible)

    def set_execute_remaining_visible(self, visible: bool) -> None:
        self.execute_remaining_button.setVisible(visible)

    def set_execute_text(self, text: str) -> None:
        self.execute_button.setText(text)


