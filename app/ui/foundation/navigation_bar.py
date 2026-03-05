"""左侧导航栏"""

from PyQt6 import QtCore, QtWidgets, QtGui
from app.ui.foundation.theme_manager import ThemeManager


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
        # 全局样式表通过 objectName 精确匹配容器背景与分隔线
        self.setObjectName("navigationBar")
        self.setFixedWidth(90)
        # 仅用于“非模式切换”的扩展按钮（例如私有插件入口）
        self.extension_buttons: dict[str, QtWidgets.QAbstractButton] = {}
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
        # 顺序严格保持为：项目存档→元件库→实体摆放→战斗预设→管理→复合节点→节点图库→验证→任务清单
        nav_items: list[tuple[str, str, str]] = [
            ("packages", "🗂️", "项目存档"),
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
    
    def _on_button_clicked(self, mode: str) -> None:
        """按钮点击"""
        self.mode_changed.emit(mode)
    
    def set_current_mode(self, mode: str) -> None:
        """设置当前模式"""
        if mode in self.buttons:
            self.buttons[mode].setChecked(True)

    def ensure_extension_button(
        self,
        *,
        key: str,
        icon_text: str,
        label: str,
        on_click,
        tooltip: str = "",
    ) -> QtWidgets.QAbstractButton:
        """确保一个扩展按钮存在，并放在左侧导航栏底部（stretch 之后）。

        设计目标：
        - 提供稳定的扩展点给私有插件：无需在插件内手写 layout insert hack；
        - 扩展按钮不参与 mode button group（不会触发 mode_changed）。
        """
        key_text = str(key or "").strip()
        if key_text == "":
            raise ValueError("extension button key 不能为空")

        existing = self.extension_buttons.get(key_text)
        if existing is not None:
            return existing

        btn = NavigationButton(str(icon_text or ""), str(label or ""), key_text, self)
        btn.setCheckable(False)
        if str(tooltip or "").strip():
            btn.setToolTip(str(tooltip))

        def _invoke(_checked: bool = False) -> None:
            on_click()

        btn.clicked.connect(_invoke)

        layout = self.layout()
        if isinstance(layout, QtWidgets.QVBoxLayout):
            # 约定：_setup_ui() 在模式按钮后插入一个 stretch。
            # 把扩展按钮放在 stretch 之后，确保它在导航栏最底部（不会挤占模式按钮区域）。
            layout.addWidget(btn)
        else:
            raise RuntimeError("NavigationBar layout 不是 QVBoxLayout，无法注入扩展按钮")

        self.extension_buttons[key_text] = btn
        return btn

