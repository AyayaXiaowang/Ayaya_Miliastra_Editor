"""节点图卡片部件 - 用于在节点图库中展示节点图详细信息"""

from PyQt6 import QtCore, QtWidgets, QtGui
from typing import Optional
from datetime import datetime
from pathlib import Path
from app.ui.foundation import fonts as ui_fonts
from app.ui.foundation.theme_manager import ThemeManager, Colors, Sizes
from app.ui.controllers.graph_error_tracker import get_instance as get_error_tracker


class GraphCardWidget(QtWidgets.QWidget):
    """节点图卡片部件 - 显示节点图的详细信息"""
    
    # 信号
    clicked = QtCore.pyqtSignal(str)  # graph_id
    double_clicked = QtCore.pyqtSignal(str)  # graph_id
    reference_clicked = QtCore.pyqtSignal(str)  # graph_id - 点击引用次数时触发
    edit_clicked = QtCore.pyqtSignal(str)  # graph_id - 点击编辑按钮时触发
    variables_clicked = QtCore.pyqtSignal(str)  # graph_id - 点击节点图变量按钮时触发
    
    def __init__(self, graph_id: str, graph_data: dict, reference_count: int = 0, 
                 resource_manager=None, parent=None, has_error: bool = False):
        super().__init__(parent)
        self.graph_id = graph_id
        self.graph_data = graph_data
        self.reference_count = reference_count
        self.resource_manager = resource_manager
        self.is_selected = False
        self.has_error = has_error  # 是否有错误
        
        # 错误跟踪器（单例）
        self.error_tracker = get_error_tracker()
        
        # 连接错误状态变化信号
        self.error_tracker.error_status_changed.connect(self._on_error_status_changed)
        
        self._setup_ui()
        # 节点图库列表不再在卡片内展示“节点数/连线数”，避免信息噪音；
        # 计数信息只在右侧属性面板的“基本信息”中展示。
        self.setMinimumHeight(86)
        self.setMaximumHeight(120)
        
        # 鼠标悬停效果
        self.setMouseTracking(True)
        self._hover = False
        
        # 拖拽相关
        self._drag_start_pos = None
    
    def _setup_ui(self) -> None:
        """设置UI"""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # 第一行：名称和类型
        header_layout = QtWidgets.QHBoxLayout()

        # 类型图标
        self.type_label = QtWidgets.QLabel()
        self.type_label.setFont(ui_fonts.emoji_font(14))
        header_layout.addWidget(self.type_label)

        # 名称
        self.name_label = QtWidgets.QLabel()
        self.name_label.setObjectName("graphCardName")
        self.name_label.setFont(ui_fonts.ui_font(11, bold=True))
        header_layout.addWidget(self.name_label, 1)

        # 共享徽章：当前项目视图下会混入共享资源，需要在卡片层级显式标记归属。
        self.shared_badge = QtWidgets.QLabel("共享")
        self.shared_badge.setObjectName("graphCardSharedBadge")
        self.shared_badge.setFont(ui_fonts.ui_font(8, bold=True))
        self.shared_badge.setToolTip("共享资源：所有存档可见并可直接使用。")
        self.shared_badge.setVisible(False)
        header_layout.addWidget(self.shared_badge)
        
        # 节点图变量按钮
        self.variables_button = QtWidgets.QPushButton("📊 变量")
        self.variables_button.setObjectName("graphCardVariablesButton")
        self.variables_button.setFont(ui_fonts.ui_font(9))
        self.variables_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.variables_button.clicked.connect(lambda: self.variables_clicked.emit(self.graph_id))
        header_layout.addWidget(self.variables_button)
        
        # 编辑按钮
        self.edit_button = QtWidgets.QPushButton("✏️ 编辑")
        self.edit_button.setObjectName("graphCardEditButton")
        self.edit_button.setFont(ui_fonts.ui_font(9))
        self.edit_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.edit_button.clicked.connect(lambda: self.edit_clicked.emit(self.graph_id))
        header_layout.addWidget(self.edit_button)
        
        # 引用次数（可点击）
        self.ref_button = QtWidgets.QPushButton()
        self.ref_button.setObjectName("graphCardRefButton")
        self.ref_button.setFont(ui_fonts.ui_font(9))
        self.ref_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.ref_button.clicked.connect(lambda: self.reference_clicked.emit(self.graph_id))
        header_layout.addWidget(self.ref_button)
        
        layout.addLayout(header_layout)
        
        # 第三行：修改时间
        self.time_label = QtWidgets.QLabel()
        self.time_label.setObjectName("graphCardTime")
        self.time_label.setFont(ui_fonts.ui_font(8))
        layout.addWidget(self.time_label)

        # 描述（如果有）
        self.description_label = QtWidgets.QLabel()
        self.description_label.setObjectName("graphCardDescription")
        self.description_label.setFont(ui_fonts.ui_font(8))
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)

        # 初始使用未选中样式
        self._apply_unselected_styles()

        self._apply_graph_data_to_widgets()

    def _apply_graph_data_to_widgets(self) -> None:
        """根据当前 graph_data 刷新 UI 文本。"""
        graph_type = self.graph_data.get("graph_type", "server")
        self.type_label.setText("🔷" if graph_type == "server" else "🔶")

        graph_name = self.graph_data.get("name") or self.graph_id
        self.name_label.setText(graph_name)

        is_shared = bool(self.graph_data.get("is_shared", False))
        if hasattr(self, "shared_badge"):
            self.shared_badge.setVisible(is_shared)

        self._update_reference_button()

        modification_time = self._get_modification_time()
        self.time_label.setText(f"🕒 修改: {modification_time}")

        description = self.graph_data.get("description", "")
        if description:
            trimmed = description[:50] + ("..." if len(description) > 50 else "")
            self.description_label.setText(trimmed)
            self.description_label.show()
        else:
            self.description_label.clear()
            self.description_label.hide()

    def _update_reference_button(self) -> None:
        """根据引用次数更新引用按钮。"""
        if self.reference_count > 0:
            self.ref_button.setText(f"🔗 {self.reference_count}")
            self.ref_button.show()
        else:
            self.ref_button.hide()

    def set_variables_button_enabled(self, enabled: bool) -> None:
        """控制变量按钮是否可用/可见，用于只读场景下隐藏变量编辑入口。"""
        self.variables_button.setVisible(enabled)

    def _apply_unselected_styles(self) -> None:
        """应用卡片未选中时的文字样式（由全局 QSS 驱动）。"""
        self._apply_text_selected_property(False)

    def _apply_selected_styles(self) -> None:
        """应用卡片选中时的文字样式（由全局 QSS 驱动）。"""
        self._apply_text_selected_property(True)

    def _apply_text_selected_property(self, selected: bool) -> None:
        """通过动态属性让 QSS 切换文字配色，避免在业务代码内拼接样式字符串。"""
        for label in (self.name_label, self.time_label, self.description_label):
            label.setProperty("selected", bool(selected))
            style = label.style()
            style.unpolish(label)
            style.polish(label)
            label.update()

    def update_graph_info(self, graph_data: dict, reference_count: int, has_error: bool) -> None:
        """复用现有卡片更新内容，避免重复创建 QWidget。"""
        self.graph_data = graph_data
        self.reference_count = reference_count
        self.set_error_status(has_error)
        self._apply_graph_data_to_widgets()
    
    def _get_modification_time(self) -> str:
        """获取节点图的修改时间。

        优先级：
        1) 列表轻量元数据提供的 `last_modified_ts`（file mtime）
        2) 兼容旧字段 `last_modified/created_at`（ISO 字符串或展示字符串）
        3) 无法解析时回退为“未知”
        """
        timestamp_value = self.graph_data.get("last_modified_ts")
        if isinstance(timestamp_value, (int, float)) and timestamp_value:
            dt = datetime.fromtimestamp(float(timestamp_value))
            return dt.strftime("%Y-%m-%d %H:%M")

        fallback_value = self.graph_data.get("last_modified", self.graph_data.get("created_at", ""))
        if isinstance(fallback_value, str) and fallback_value:
            try:
                dt = datetime.fromisoformat(fallback_value)
            except ValueError:
                # 已经是可读字符串（例如 "2025-12-15 10:20:30"）时，直接展示
                return fallback_value
            return dt.strftime("%Y-%m-%d %H:%M")

        return "未知"
    
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """绘制卡片背景和边框"""
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()

        # 背景（使用主题的渐变/配色方案）
        if self.is_selected:
            # PyQt6 下 QLinearGradient(start, finalStop) 需要 QPointF 或浮点坐标，
            # 直接传递 QRect.topLeft()/bottomLeft() 返回的 QPoint 会导致类型不匹配。
            # 这里改为使用坐标重载，保证在 Qt6 下类型安全。
            gradient = QtGui.QLinearGradient(
                rect.left(),
                rect.top(),
                rect.left(),
                rect.bottom(),
            )
            gradient.setColorAt(0.0, QtGui.QColor(Colors.PRIMARY))
            gradient.setColorAt(1.0, QtGui.QColor(Colors.PRIMARY_LIGHT))
            bg_brush = QtGui.QBrush(gradient)
            border_color = QtGui.QColor(Colors.PRIMARY_DARK)
            border_width = 2
        elif self._hover:
            bg_brush = QtGui.QBrush(QtGui.QColor(Colors.BG_CARD_HOVER))
            border_color = QtGui.QColor(Colors.BORDER_NORMAL)
            border_width = 1
        else:
            bg_brush = QtGui.QBrush(QtGui.QColor(Colors.BG_CARD))
            border_color = QtGui.QColor(Colors.BORDER_LIGHT)
            border_width = 1
        
        # 绘制背景
        painter.setBrush(bg_brush)
        painter.setPen(QtGui.QPen(border_color, border_width))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), Sizes.RADIUS_MEDIUM, Sizes.RADIUS_MEDIUM)
        
        # 如果有错误，在右上角绘制黄色感叹号
        if self.has_error:
            self._draw_error_indicator(painter, rect)
    
    def enterEvent(self, event: QtCore.QEvent) -> None:
        """鼠标进入"""
        self._hover = True
        self.update()
        super().enterEvent(event)
    
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        """鼠标离开"""
        self._hover = False
        self.update()
        super().leaveEvent(event)
    
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """鼠标按下"""
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            # 错误指示器区域点击 → 显示错误信息，不改变选中状态
            if self.has_error:
                indicator_size = 24
                margin = 8
                indicator_rect = QtCore.QRect(
                    self.width() - margin - indicator_size,
                    margin,
                    indicator_size,
                    indicator_size
                )
                if indicator_rect.contains(event.pos()):
                    error_info = self.error_tracker.get_error_info(self.graph_id)
                    if error_info:
                        QtWidgets.QToolTip.showText(
                            event.globalPosition().toPoint(),
                            f"保存失败: {error_info.error_message}\n\n"
                            f"时间: {error_info.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                            f"请检查控制台输出获取详细信息。",
                            self
                        )
                    event.accept()
                    return
            # 普通左键点击 → 选中并发出点击信号，支持拖拽
            self._drag_start_pos = event.pos()
            self.clicked.emit(self.graph_id)
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        """鼠标移动 - 检测拖拽"""
        if self._drag_start_pos is not None:
            # 检查是否超过拖拽阈值
            if (event.pos() - self._drag_start_pos).manhattanLength() >= QtWidgets.QApplication.startDragDistance():
                self._start_drag()
                self._drag_start_pos = None
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        """鼠标释放"""
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)
    
    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        """鼠标双击"""
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.graph_id)
        super().mouseDoubleClickEvent(event)
    
    def _start_drag(self) -> None:
        """发起拖拽操作"""
        drag = QtGui.QDrag(self)
        mime_data = QtCore.QMimeData()
        mime_data.setText(self.graph_id)
        mime_data.setData("application/x-graph-id", self.graph_id.encode('utf-8'))
        drag.setMimeData(mime_data)
        
        # 设置拖拽游标（可选：创建缩略图）
        drag.exec(QtCore.Qt.DropAction.MoveAction)
    
    def set_selected(self, selected: bool) -> None:
        """设置选中状态"""
        self.is_selected = selected
        if selected:
            self._apply_selected_styles()
        else:
            self._apply_unselected_styles()
        self.update()
    
    def set_error_status(self, has_error: bool) -> None:
        """设置错误状态
        
        Args:
            has_error: 是否有错误
        """
        if self.has_error != has_error:
            self.has_error = has_error
            self.update()  # 触发重绘
    
    def _on_error_status_changed(self, graph_id: str, has_error: bool) -> None:
        """错误状态变化回调
        
        Args:
            graph_id: 节点图ID
            has_error: 是否有错误
        """
        if graph_id == self.graph_id:
            self.set_error_status(has_error)
    
    def _draw_error_indicator(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        """绘制错误指示器（黄色感叹号）
        
        Args:
            painter: 画笔
            rect: 卡片区域
        """
        # 在右上角绘制圆形背景
        indicator_size = 24
        margin = 8
        center_x = rect.right() - margin - indicator_size / 2
        center_y = rect.top() + margin + indicator_size / 2
        
        # 绘制强调色圆形背景
        painter.setBrush(QtGui.QColor(Colors.WARNING))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawEllipse(
            QtCore.QPointF(center_x, center_y),
            indicator_size / 2,
            indicator_size / 2
        )
        
        # 绘制感叹号
        painter.setPen(QtGui.QPen(QtGui.QColor(Colors.TEXT_ON_PRIMARY), 2))
        font = QtGui.QFont("Arial", 14, QtGui.QFont.Weight.Bold)
        painter.setFont(font)
        
        # 绘制 "!" 字符
        text_rect = QtCore.QRectF(
            center_x - indicator_size / 2,
            center_y - indicator_size / 2,
            indicator_size,
            indicator_size
        )
        painter.drawText(text_rect, QtCore.Qt.AlignmentFlag.AlignCenter, "!")
    
    

