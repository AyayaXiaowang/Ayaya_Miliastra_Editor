"""Toast通知组件 - 非模态的角落提示框"""

from PyQt6 import QtCore, QtGui, QtWidgets
from ui.foundation.theme_manager import Colors, Sizes, ThemeManager


_TOAST_POPUP_ENABLED: bool = False


class ToastNotification(QtWidgets.QWidget):
    """Toast通知组件 - 在窗口右上角显示提示信息（自上而下堆叠）"""
    
    # 全局单例实例列表（支持多个Toast堆叠）
    _active_toasts: list["ToastNotification"] = []
    
    def __init__(self, parent: QtWidgets.QWidget, message: str, toast_type: str = "info"):
        """初始化Toast通知
        
        Args:
            parent: 父窗口
            message: 提示消息
            toast_type: 类型 ("info" | "warning" | "error" | "success")
        """
        super().__init__(parent)
        
        self.message = message
        self.toast_type = toast_type
        self.auto_close_duration = 3000  # 3秒后自动关闭
        
        # 设置窗口属性
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint |
            QtCore.Qt.WindowType.Tool |
            QtCore.Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        # 设置UI
        self._setup_ui()
        
        # 设置动画
        self._setup_animations()
        
        # 自动关闭定时器
        self.close_timer = QtCore.QTimer()
        self.close_timer.setSingleShot(True)
        self.close_timer.timeout.connect(self.fade_out)
    
    def _setup_ui(self) -> None:
        """设置UI"""
        # 主布局
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # 内容容器
        content_widget = QtWidgets.QWidget()
        content_widget.setObjectName("toastContent")
        content_layout = QtWidgets.QHBoxLayout(content_widget)
        content_layout.setContentsMargins(15, 10, 15, 10)
        content_layout.setSpacing(10)
        
        # 彩色左边框
        border_widget = QtWidgets.QWidget()
        border_widget.setFixedWidth(4)
        border_widget.setStyleSheet(f"background: {self._get_accent_color()}; border-radius: 2px;")
        content_layout.addWidget(border_widget)
        
        # 图标
        icon_label = QtWidgets.QLabel()
        icon_map = {
            "info": "ℹ",
            "warning": "⚠",
            "error": "✖",
            "success": "✓"
        }
        icon_label.setText(icon_map.get(self.toast_type, "ℹ"))
        icon_label.setStyleSheet(f"font-size: {Sizes.FONT_LARGE}px; color: {self._get_accent_color()};")
        content_layout.addWidget(icon_label)
        
        # 消息文本
        message_label = QtWidgets.QLabel(self.message)
        message_label.setWordWrap(True)
        message_label.setStyleSheet(f"font-size: {Sizes.FONT_NORMAL}px; color: {Colors.TEXT_PRIMARY};")
        content_layout.addWidget(message_label, 1)
        
        main_layout.addWidget(content_widget)
        
        # 使用主题管理器的样式
        content_widget.setStyleSheet(ThemeManager.toast_style())
        
        # 设置阴影效果
        shadow = QtWidgets.QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QtGui.QColor(0, 0, 0, 80))
        shadow.setOffset(0, 4)
        content_widget.setGraphicsEffect(shadow)
        
        # 自动调整大小
        self.adjustSize()
        self.setFixedSize(self.sizeHint())
    
    def _get_accent_color(self) -> str:
        """获取强调色（用于左边框和图标）"""
        color_map = {
            "info": Colors.INFO,
            "warning": Colors.WARNING,
            "error": Colors.ERROR,
            "success": Colors.SUCCESS
        }
        return color_map.get(self.toast_type, Colors.INFO)
    
    def _setup_animations(self) -> None:
        """设置动画"""
        # 淡入动画
        self.fade_in_animation = QtCore.QPropertyAnimation(self, b"windowOpacity")
        self.fade_in_animation.setDuration(300)
        self.fade_in_animation.setStartValue(0.0)
        self.fade_in_animation.setEndValue(1.0)
        self.fade_in_animation.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        
        # 淡出动画
        self.fade_out_animation = QtCore.QPropertyAnimation(self, b"windowOpacity")
        self.fade_out_animation.setDuration(300)
        self.fade_out_animation.setStartValue(1.0)
        self.fade_out_animation.setEndValue(0.0)
        self.fade_out_animation.setEasingCurve(QtCore.QEasingCurve.Type.InCubic)
        self.fade_out_animation.finished.connect(self._on_fade_out_finished)
    
    def show_toast(self) -> None:
        """显示Toast（相对于父窗口右上角，自上而下堆叠）"""
        if not _TOAST_POPUP_ENABLED:
            return
        
        parent_widget = self.parent()
        # 计算Y偏移（按已有 Toast 自上而下堆叠）
        y_offset = 20
        for toast in ToastNotification._active_toasts:
            if toast.isVisible():
                y_offset += toast.height() + 10
        
        margin_right = 20
        if parent_widget is None:
            # 无父窗口：退化为相对于主屏右上角
            screen_geo = QtGui.QGuiApplication.primaryScreen().availableGeometry()
            x = screen_geo.x() + screen_geo.width() - self.width() - margin_right
            y = screen_geo.y() + y_offset
            self.move(x, y)
        else:
            # 有父窗口：使用父窗口全局坐标进行定位（右上角对齐）
            global_top_left = parent_widget.mapToGlobal(QtCore.QPoint(0, 0))
            parent_width = parent_widget.width()
            x = global_top_left.x() + parent_width - self.width() - margin_right
            y = global_top_left.y() + y_offset
            self.move(x, y)
        
        # 添加到活跃列表
        ToastNotification._active_toasts.append(self)
        
        # 显示并淡入
        self.show()
        self.fade_in_animation.start()
        
        # 启动自动关闭定时器
        self.close_timer.start(self.auto_close_duration)
    
    def fade_out(self) -> None:
        """淡出并关闭"""
        self.fade_out_animation.start()
    
    def _on_fade_out_finished(self) -> None:
        """淡出完成后的处理"""
        # 从活跃列表移除
        if self in ToastNotification._active_toasts:
            ToastNotification._active_toasts.remove(self)
        
        # 关闭窗口
        self.close()
        self.deleteLater()
        
        # 重新排列其他Toast
        self._rearrange_toasts()
    
    def _rearrange_toasts(self) -> None:
        """重新排列剩余的Toast（相对于父窗口右上角，自上而下堆叠）"""
        parent_widget = self.parent()
        if parent_widget is None:
            screen_geo = QtGui.QGuiApplication.primaryScreen().availableGeometry()
            base_x = screen_geo.x()
            base_y = screen_geo.y()
            base_width = screen_geo.width()
        else:
            global_top_left = parent_widget.mapToGlobal(QtCore.QPoint(0, 0))
            base_x = global_top_left.x()
            base_y = global_top_left.y()
            base_width = parent_widget.width()
        
        y_offset = 20
        margin_right = 20
        for toast in ToastNotification._active_toasts:
            if toast.isVisible() and toast != self:
                x = base_x + base_width - toast.width() - margin_right
                y = base_y + y_offset
                
                animation = QtCore.QPropertyAnimation(toast, b"pos")
                animation.setDuration(200)
                animation.setEndValue(QtCore.QPoint(x, y))
                animation.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
                animation.start(QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
                
                y_offset += toast.height() + 10
    
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """点击Toast时关闭"""
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.fade_out()
        super().mousePressEvent(event)
    
    @staticmethod
    def show_message(parent: QtWidgets.QWidget, message: str, toast_type: str = "info") -> None:
        """静态方法：显示Toast消息
        
        Args:
            parent: 父窗口
            message: 提示消息
            toast_type: 类型 ("info" | "warning" | "error")
        """
        if not _TOAST_POPUP_ENABLED:
            print(message, flush=True)
            return
        toast = ToastNotification(parent, message, toast_type)
        toast.show_toast()

