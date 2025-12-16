"""左侧导航栏"""

from PyQt6 import QtCore, QtWidgets, QtGui
from app.ui.foundation.theme_manager import ThemeManager, Colors


class NavigationButton(QtWidgets.QPushButton):
    """导航按钮"""
    
    def __init__(self, icon_text: str, label: str, mode: str, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.setCheckable(True)
        self.setFixedSize(80, 80)
        
        # 设置文本（图标+标签）
        self.setText(f"{icon_text}\n{label}")
        
        # 使用主题管理器集中定义的导航按钮样式
        self.setStyleSheet(ThemeManager.navigation_button_style())


class NavigationBar(QtWidgets.QWidget):
    """左侧垂直导航栏"""
    
    mode_changed = QtCore.pyqtSignal(str)  # 模式切换信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(90)
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """设置UI"""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 10)
        layout.setSpacing(5)

        # 创建按钮组（互斥选择）
        self.button_group = QtWidgets.QButtonGroup(self)
        self.button_group.setExclusive(True)

        # 使用数据驱动的方式定义导航项
        # 顺序严格保持为：存档→元件库→实体摆放→战斗预设→管理→复合节点→节点图库→验证→任务清单
        nav_items: list[tuple[str, str, str]] = [
            ("packages", "🗂️", "存档"),
            ("template", "📦", "元件库"),
            ("placement", "🗺️", "实体摆放"),
            ("combat", "⚔️", "战斗预设"),
            ("management", "⚙️", "管理"),
            ("composite", "🧩", "复合节点"),
            ("graph_library", "📊", "节点图库"),
            ("validation", "🔍", "验证"),
            ("todo", "✓", "任务清单"),
        ]

        # 存储 mode -> 按钮 映射
        self.buttons: dict[str, NavigationButton] = {}

        for mode, icon_text, label in nav_items:
            button = NavigationButton(icon_text, label, mode, self)
            self.buttons[mode] = button
            self.button_group.addButton(button)
            layout.addWidget(button)
        
        layout.addStretch()
        
        # 连接信号
        for mode, button in self.buttons.items():
            button.clicked.connect(lambda checked, m=mode: self._on_button_clicked(m))
        
        # 默认选中第一个
        if "template" in self.buttons:
            self.buttons["template"].setChecked(True)
        
        # 使用主题管理器的背景色
        self.setStyleSheet(f"background: {Colors.BG_CARD}; border-right: 1px solid {Colors.BORDER_LIGHT};")
    
    def _on_button_clicked(self, mode: str) -> None:
        """按钮点击"""
        self.mode_changed.emit(mode)
    
    def set_current_mode(self, mode: str) -> None:
        """设置当前模式"""
        if mode in self.buttons:
            self.buttons[mode].setChecked(True)

