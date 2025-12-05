"""虚拟引脚对话框 - 创建和管理虚拟引脚"""

from PyQt6 import QtCore, QtWidgets
from typing import Optional, List
from engine.nodes.advanced_node_features import VirtualPinConfig, MappedPort
from ui.foundation.base_widgets import BaseDialog
from ui.foundation.theme_manager import ThemeManager, Colors


class CreateVirtualPinDialog(BaseDialog):
    """创建虚拟引脚对话框"""
    
    def __init__(self, node_id: str, port_name: str, port_type: str, is_input: bool, parent=None):
        self.node_id = node_id
        self.port_name = port_name
        self.port_type = port_type
        self._is_input = is_input
        
        super().__init__(
            title="创建虚拟引脚",
            width=400,
            height=0,
            parent=parent,
        )
        self.setMinimumWidth(400)
        
        self._build_content()
    
    def _build_content(self) -> None:
        """设置UI"""
        layout = self.content_layout
        
        # 表单
        form_layout = QtWidgets.QFormLayout()
        
        # 引脚名称
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setText(self.port_name)  # 默认使用端口名
        form_layout.addRow("引脚名称:", self.name_edit)
        
        # 引脚描述
        self.description_edit = QtWidgets.QTextEdit()
        self.description_edit.setPlaceholderText("可选填写引脚的用途说明...")
        self.description_edit.setMaximumHeight(80)
        form_layout.addRow("引脚描述:", self.description_edit)
        
        # 内部映射（只读显示）
        mapping_label = QtWidgets.QLabel(f"• {self.node_id}.{self.port_name} ({self.port_type})")
        mapping_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 11px; padding: 5px;"
        )
        form_layout.addRow("内部映射:", mapping_label)
        
        layout.addLayout(form_layout)
        
    
    def get_pin_name(self) -> str:
        """获取引脚名称"""
        return self.name_edit.text().strip()
    
    def get_description(self) -> str:
        """获取引脚描述"""
        return self.description_edit.toPlainText().strip()


class AddToVirtualPinDialog(BaseDialog):
    """添加到现有虚拟引脚对话框"""
    
    def __init__(self, available_pins: List[VirtualPinConfig], 
                 node_id: str, port_name: str, port_type: str, parent=None):
        self.available_pins = available_pins
        self.node_id = node_id
        self.port_name = port_name
        self.port_type = port_type
        
        super().__init__(
            title="添加到现有虚拟引脚",
            width=450,
            height=0,
            parent=parent,
        )
        self.setMinimumWidth(450)
        
        self._build_content()
    
    def _build_content(self) -> None:
        """设置UI"""
        layout = self.content_layout
        
        # 说明
        info_label = QtWidgets.QLabel(
            f"选择要添加到的虚拟引脚：\n"
            f"端口: {self.node_id}.{self.port_name} ({self.port_type})"
        )
        info_label.setStyleSheet(
            f"{ThemeManager.info_label_simple_style()} border-radius: 4px;"
        )
        layout.addWidget(info_label)
        
        # 虚拟引脚列表
        self.pin_list = QtWidgets.QListWidget()
        for pin in self.available_pins:
            mapped_count = len(pin.mapped_ports)
            item_text = f"{pin.pin_name} ({pin.pin_type}) - 已映射 {mapped_count} 个端口"
            item = QtWidgets.QListWidgetItem(item_text)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, pin.pin_index)
            self.pin_list.addItem(item)
        
        layout.addWidget(self.pin_list)
        
        # 合并策略（仅输出引脚）
        if self.available_pins and not self.available_pins[0].is_input:
            strategy_group = QtWidgets.QGroupBox("合并策略")
            strategy_layout = QtWidgets.QVBoxLayout(strategy_group)
            
            self.strategy_buttons = QtWidgets.QButtonGroup()
            
            last_radio = QtWidgets.QRadioButton("取最后一个值（默认）")
            last_radio.setChecked(True)
            last_radio.setProperty("strategy", "last")
            self.strategy_buttons.addButton(last_radio)
            strategy_layout.addWidget(last_radio)
            
            first_radio = QtWidgets.QRadioButton("取第一个值")
            first_radio.setProperty("strategy", "first")
            self.strategy_buttons.addButton(first_radio)
            strategy_layout.addWidget(first_radio)
            
            array_radio = QtWidgets.QRadioButton("合并为数组")
            array_radio.setProperty("strategy", "array")
            self.strategy_buttons.addButton(array_radio)
            strategy_layout.addWidget(array_radio)
            
            layout.addWidget(strategy_group)
        else:
            self.strategy_buttons = None
        
    def get_selected_pin_index(self) -> Optional[int]:
        """获取选中的虚拟引脚序号"""
        current_item = self.pin_list.currentItem()
        if current_item:
            return current_item.data(QtCore.Qt.ItemDataRole.UserRole)
        return None
    
    def get_merge_strategy(self) -> str:
        """获取合并策略"""
        if self.strategy_buttons:
            checked_button = self.strategy_buttons.checkedButton()
            if checked_button:
                return checked_button.property("strategy")
        return "last"

