"""冲突解决对话框 - 当本地修改与外部修改冲突时显示"""

from PyQt6 import QtCore, QtGui, QtWidgets
from datetime import datetime
from app.ui.foundation.base_widgets import BaseDialog
from app.ui.foundation.theme_manager import ThemeManager


class ConflictResolutionDialog(BaseDialog):
    """冲突解决对话框"""
    
    def __init__(
        self,
        parent: QtWidgets.QWidget,
        graph_name: str,
        local_modified_time: datetime | None = None,
        external_modified_time: datetime | None = None,
    ) -> None:
        """初始化对话框
        
        Args:
            parent: 父窗口
            graph_name: 节点图名称
            local_modified_time: 本地修改时间
            external_modified_time: 外部修改时间
        """
        self.graph_name = graph_name
        self.local_modified_time = local_modified_time
        self.external_modified_time = external_modified_time
        self.user_choice = None  # "keep_local" | "use_external"
        
        super().__init__(
            title="节点图冲突",
            width=450,
            height=0,
            parent=parent,
        )
        self.setMinimumWidth(450)
        
        self._build_content()
        self._apply_styles()
    
    def _apply_styles(self) -> None:
        """应用主题样式"""
        self.setStyleSheet(ThemeManager.dialog_surface_style(include_tables=False))
    
    def _build_content(self) -> None:
        """设置UI"""
        layout = self.content_layout
        layout.setSpacing(15)
        
        # 标题
        title_label = QtWidgets.QLabel("⚠ 节点图冲突检测")
        title_label.setObjectName("conflictDialogTitle")
        title_font = QtGui.QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # 分隔线
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        layout.addWidget(line)
        
        # 说明文本
        description_label = QtWidgets.QLabel(
            f"节点图 <b>{self.graph_name}</b> 在外部被修改了，\n"
            "但您当前也有未保存的本地修改。\n\n"
            "请选择要保留哪个版本："
        )
        description_label.setWordWrap(True)
        description_label.setObjectName("conflictDialogDescription")
        layout.addWidget(description_label)
        
        # 时间信息（如果有）
        if self.local_modified_time or self.external_modified_time:
            time_info_widget = QtWidgets.QWidget()
            time_info_widget.setObjectName("conflictTimeInfoBox")
            time_info_layout = QtWidgets.QVBoxLayout(time_info_widget)
            time_info_layout.setContentsMargins(15, 10, 15, 10)
            time_info_layout.setSpacing(5)
            
            if self.local_modified_time:
                local_time_label = QtWidgets.QLabel(
                    f"📝 本地修改时间: {self._format_time(self.local_modified_time)}"
                )
                local_time_label.setObjectName("conflictTimeLabel")
                time_info_layout.addWidget(local_time_label)
            
            if self.external_modified_time:
                external_time_label = QtWidgets.QLabel(
                    f"🌐 外部修改时间: {self._format_time(self.external_modified_time)}"
                )
                external_time_label.setObjectName("conflictTimeLabel")
                time_info_layout.addWidget(external_time_label)
            
            layout.addWidget(time_info_widget)
        
        # 按钮容器
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(10)
        
        # 保留本地修改按钮
        self.keep_local_button = QtWidgets.QPushButton("保留我的修改")
        self.keep_local_button.setMinimumHeight(35)
        self.keep_local_button.setProperty("kind", "primary")
        self.keep_local_button.clicked.connect(self._on_keep_local)
        button_layout.addWidget(self.keep_local_button)
        
        # 使用外部版本按钮
        self.use_external_button = QtWidgets.QPushButton("使用外部版本")
        self.use_external_button.setMinimumHeight(35)
        self.use_external_button.setProperty("kind", "secondary")
        self.use_external_button.clicked.connect(self._on_use_external)
        button_layout.addWidget(self.use_external_button)
        
        layout.addLayout(button_layout)
        
        # 提示文本
        hint_label = QtWidgets.QLabel(
            "提示：选择\"保留我的修改\"会覆盖外部版本，\n"
            "选择\"使用外部版本\"会放弃您的本地修改。"
        )
        hint_label.setObjectName("conflictDialogHint")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)
    
    def _format_time(self, dt: datetime) -> str:
        """格式化时间"""
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    
    def _on_keep_local(self) -> None:
        """选择保留本地修改"""
        self.user_choice = "keep_local"
        self.accept()
    
    def _on_use_external(self) -> None:
        """选择使用外部版本"""
        self.user_choice = "use_external"
        self.accept()
    
    def get_user_choice(self) -> str:
        """获取用户选择
        
        Returns:
            "keep_local" | "use_external" | None (如果取消)
        """
        return self.user_choice

