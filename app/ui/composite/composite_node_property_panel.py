"""复合节点属性面板 - 显示在主窗口右侧标签页"""

from __future__ import annotations
from PyQt6 import QtCore, QtGui, QtWidgets
from typing import Optional, List, Dict, Set

from ui.foundation.theme_manager import ThemeManager, Sizes
from ui.foundation.style_mixins import StyleMixin
from ui.panels.package_membership_selector import build_package_membership_row
from engine.nodes.advanced_node_features import CompositeNodeConfig
from engine.resources.package_index_manager import PackageIndexManager


class CompositeNodePropertyPanel(QtWidgets.QWidget, StyleMixin):
    """复合节点属性面板
    
    显示和编辑复合节点的基本信息和虚拟引脚预览
    """
    
    # 信号：属性已更新
    property_updated = QtCore.pyqtSignal()
    # 信号：所属存档变更 (composite_id, package_id, is_checked)
    package_membership_changed = QtCore.pyqtSignal(str, str, bool)
    
    def __init__(self, package_index_manager: Optional[PackageIndexManager] = None, parent=None):
        super().__init__(parent)
        
        self.current_composite: Optional[CompositeNodeConfig] = None
        self.composite_widget = None  # 关联的复合节点管理器widget
        self._package_index_manager: Optional[PackageIndexManager] = package_index_manager
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """设置UI"""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 标题
        title_label = QtWidgets.QLabel("复合节点属性")
        title_label.setStyleSheet(f"{ThemeManager.heading(level=2)} padding: 5px;")
        layout.addWidget(title_label)

        # 面板级“所属存档”选择行（位于标题下方，基本信息分组之外）
        self._build_package_membership_row(layout)
        
        # 基本信息
        info_group = QtWidgets.QGroupBox("基本信息")
        info_layout = QtWidgets.QFormLayout(info_group)
        
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("输入节点名称")
        self.name_edit.textChanged.connect(self._on_name_changed)
        info_layout.addRow("节点名称:", self.name_edit)
        
        self.description_edit = QtWidgets.QTextEdit()
        self.description_edit.setPlaceholderText("输入节点描述")
        self.description_edit.setMaximumHeight(80)
        self.description_edit.setMinimumHeight(80)
        self.description_edit.textChanged.connect(self._on_description_changed)
        info_layout.addRow("描述:", self.description_edit)
        
        self.scope_label = QtWidgets.QLabel("server（仅服务器）")
        self.scope_label.setStyleSheet(f"{ThemeManager.hint_text_style()} font-style: italic;")
        info_layout.addRow("作用域:", self.scope_label)
        
        layout.addWidget(info_group)
        
        # 添加弹性空间
        layout.addStretch()
        
        # 应用主题样式
        self.apply_panel_style()

    def _build_package_membership_row(self, parent_layout: QtWidgets.QVBoxLayout) -> None:
        """构建位于面板顶部的“所属存档”选择行，使其位置与其他属性面板保持一致。"""
        (
            self._package_membership_widget,
            self._package_label,
            self.package_selector,
        ) = build_package_membership_row(
            parent_layout,
            self,
            self._on_package_membership_selector_changed,
        )
    
    def set_composite_widget(self, widget) -> None:
        """设置关联的复合节点管理器"""
        self.composite_widget = widget
    
    def set_package_index_manager(self, manager: Optional[PackageIndexManager]) -> None:
        """设置存档索引管理器（可在主窗口初始化阶段注入）"""
        self._package_index_manager = manager
    
    def load_composite(self, composite: CompositeNodeConfig) -> None:
        """加载复合节点数据"""
        self.current_composite = composite
        
        # 暂时断开信号，避免加载时触发更新
        self.name_edit.blockSignals(True)
        self.description_edit.blockSignals(True)
        
        # 更新基本信息
        self.name_edit.setText(composite.node_name)
        self.description_edit.setPlainText(composite.node_description)
        
        # 恢复信号
        self.name_edit.blockSignals(False)
        self.description_edit.blockSignals(False)

        # 加载所属存档信息
        self._reload_package_membership()
    
    def clear(self) -> None:
        """清空面板"""
        self.current_composite = None
        self.name_edit.clear()
        self.description_edit.clear()
        self.package_selector.clear_membership()
    
    def _on_name_changed(self) -> None:
        """节点名称改变"""
        if not self.current_composite or not self.composite_widget:
            return
        
        new_name = self.name_edit.text()
        new_description = self.description_edit.toPlainText()
        self.composite_widget.update_composite_basic_info(new_name, new_description)
        
        self.property_updated.emit()
    
    def _on_description_changed(self) -> None:
        """节点描述改变"""
        if not self.current_composite or not self.composite_widget:
            return
        
        new_name = self.name_edit.text()
        new_description = self.description_edit.toPlainText()
        self.composite_widget.update_composite_basic_info(new_name, new_description)
        self.property_updated.emit()
    
    def _on_package_membership_selector_changed(self, package_id: str, is_checked: bool) -> None:
        """所属存档复选项改变时发信号，由主窗口统一写入 PackageIndex"""
        if not self.current_composite or not package_id:
            return
        composite_id = self.current_composite.composite_id
        self.package_membership_changed.emit(composite_id, package_id, is_checked)
    
    def _reload_package_membership(self) -> None:
        """重新加载当前复合节点的存档归属（仅依赖 PackageIndexManager）"""
        if not self._package_index_manager or not self.current_composite:
            self.package_selector.clear_membership()
            return
        
        packages: List[dict] = self._package_index_manager.list_packages()
        membership: Set[str] = set()
        
        for pkg_info in packages:
            package_id = pkg_info.get("package_id", "")
            if not package_id:
                continue
            resources = self._package_index_manager.get_package_resources(package_id)
            if resources and self.current_composite.composite_id in getattr(resources, "composites", []):
                membership.add(package_id)
        
        self.package_selector.set_packages(packages)
        self.package_selector.set_membership(membership)

