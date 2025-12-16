"""基础对话框组件。

本模块保留 UI 层仍在复用的两个对话框基类：

- `BaseDialog`：统一的 QDialog 包装，负责通用的标题、按钮与样式。
- `FormDialog`：基于 BaseDialog 的滚动表单版本，供 `FormDialogBuilder`
  以及管理面板的 CRUD 对话框共享。

早期用于容器/列表/工具栏的其他基类已经在工程中完全被
PanelScaffold、SectionCard 等新组件取代，因此在这里移除，避免遗留的、
无人使用的 UI 基类继续占据维护成本。
"""

from PyQt6 import QtCore, QtWidgets
from typing import Optional

from app.ui.foundation.theme_manager import ThemeManager, Sizes
from app.ui.foundation import dialog_utils


class BaseDialog(QtWidgets.QDialog):
    """对话框基类
    
    特性：
    - 统一的对话框样式
    - 自动布局（内容 + 按钮）
    - 标准的确定/取消按钮
    - 可选的滚动区域
    - 内置验证机制
    """
    
    def __init__(
        self,
        title: str = "对话框",
        width: int = 500,
        height: int = 400,
        use_scroll: bool = False,
        buttons: QtWidgets.QDialogButtonBox.StandardButton = None,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(width, height)
        self.setModal(True)
        self.use_scroll = use_scroll
        
        # 默认按钮
        if buttons is None:
            buttons = (
                QtWidgets.QDialogButtonBox.StandardButton.Ok
                | QtWidgets.QDialogButtonBox.StandardButton.Cancel
            )
        self.button_flags = buttons
        
        self._setup_ui()
        self._apply_styles()
    
    def _setup_ui(self):
        """设置UI"""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(
            Sizes.PADDING_LARGE,
            Sizes.PADDING_LARGE,
            Sizes.PADDING_LARGE,
            Sizes.PADDING_LARGE,
        )
        layout.setSpacing(Sizes.SPACING_LARGE)
        
        # 内容区域（可选滚动）
        if self.use_scroll:
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            
            self.content_widget = QtWidgets.QWidget()
            self.content_layout = QtWidgets.QVBoxLayout(self.content_widget)
            self.content_layout.setContentsMargins(0, 0, 0, 0)
            self.content_layout.setSpacing(Sizes.SPACING_MEDIUM)
            
            scroll.setWidget(self.content_widget)
            layout.addWidget(scroll)
        else:
            self.content_widget = QtWidgets.QWidget()
            self.content_layout = QtWidgets.QVBoxLayout(self.content_widget)
            self.content_layout.setContentsMargins(0, 0, 0, 0)
            self.content_layout.setSpacing(Sizes.SPACING_MEDIUM)
            layout.addWidget(self.content_widget)
        
        # 按钮区域
        self.button_box = QtWidgets.QDialogButtonBox(self.button_flags)
        dialog_utils.apply_standard_button_box_labels(self.button_box)
        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
    
    def _apply_styles(self):
        """应用样式"""
        self.setStyleSheet(ThemeManager.dialog_form_style())
    
    def _on_accept(self):
        """接受前验证"""
        if self.validate():
            self.accept()
    
    def validate(self) -> bool:
        """验证对话框输入（子类可重写）"""
        return True
    
    def add_widget(self, widget: QtWidgets.QWidget):
        """添加控件到内容区域"""
        self.content_layout.addWidget(widget)
    
    def add_layout(self, layout: QtWidgets.QLayout):
        """添加布局到内容区域"""
        self.content_layout.addLayout(layout)
    
    def show_error(self, message: str):
        """显示错误消息"""
        dialog_utils.show_warning_dialog(self, "错误", message)
    
    def show_info(self, message: str):
        """显示信息消息"""
        dialog_utils.show_info_dialog(self, "提示", message)


class FormDialog(BaseDialog):
    """表单对话框基类
    
    专门用于表单输入的对话框，提供：
    - 自动滚动支持
    - 表单布局
    - 字段验证
    """
    
    def __init__(
        self,
        title: str = "表单",
        width: int = 500,
        height: int = 600,
        parent=None
    ):
        super().__init__(
            title=title,
            width=width,
            height=height,
            use_scroll=True,
            parent=parent
        )
        self.form_fields = {}  # 存储表单字段：{name: widget}
        
        # 创建表单布局
        self.form_layout = QtWidgets.QFormLayout()
        self.form_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.form_layout.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
        self.form_layout.setVerticalSpacing(Sizes.SPACING_MEDIUM)
        self.content_layout.addLayout(self.form_layout)
    
    def add_form_field(
        self,
        label: str,
        widget: QtWidgets.QWidget,
        field_name: Optional[str] = None
    ):
        """添加表单字段"""
        self.form_layout.addRow(label, widget)
        if field_name:
            self.form_fields[field_name] = widget
    
    def get_field(self, field_name: str) -> Optional[QtWidgets.QWidget]:
        """获取表单字段控件"""
        return self.form_fields.get(field_name)
    
    def add_group_box(self, title: str) -> QtWidgets.QGroupBox:
        """添加分组框"""
        group = QtWidgets.QGroupBox(title)
        self.content_layout.addWidget(group)
        return group

