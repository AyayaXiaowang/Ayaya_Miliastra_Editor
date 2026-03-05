"""复合节点虚拟引脚面板 - 显示在主窗口右侧标签页"""

from __future__ import annotations
from PyQt6 import QtCore, QtWidgets
from typing import Optional

from app.ui.foundation.style_mixins import StyleMixin
from app.ui.foundation.theme_manager import ThemeManager
from engine.nodes.advanced_node_features import CompositeNodeConfig
from app.ui.composite.composite_node_preview_widget import CompositeNodePreviewWidget


class CompositeNodePinPanel(QtWidgets.QWidget, StyleMixin):
    """复合节点虚拟引脚面板
    
    显示虚拟引脚的预览图和详细列表
    """
    
    # 信号：引脚已更新
    pin_updated = QtCore.pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.current_composite: Optional[CompositeNodeConfig] = None
        self.composite_widget = None  # 关联的复合节点管理器widget
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """设置UI"""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 标题
        title_label = QtWidgets.QLabel("虚拟引脚管理")
        title_label.setStyleSheet(ThemeManager.heading(level=2))
        title_label.setContentsMargins(5, 5, 5, 5)
        layout.addWidget(title_label)
        
        # 提示标签
        hint_label = QtWidgets.QLabel("💡 右键内部节点端口可暴露为虚拟引脚 | 右键引脚可合并或删除")
        hint_label.setStyleSheet(ThemeManager.hint_text_style())
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)
        
        # 预览组件（上方预览图 + 下方引脚表格）
        self.preview_widget = CompositeNodePreviewWidget()
        self.preview_widget.pin_updated.connect(self._on_pin_updated)
        layout.addWidget(self.preview_widget)

        # 应用统一面板样式（主题 token + 基础控件一致性）
        self.apply_panel_style()
    
    def set_composite_widget(self, widget) -> None:
        """设置关联的复合节点管理器"""
        self.composite_widget = widget
        self.preview_widget.set_composite_widget(widget)
    
    def load_composite(self, composite: CompositeNodeConfig) -> None:
        """加载复合节点数据"""
        if composite is None:
            self.clear()
            return
        
        self.current_composite = composite

        # 调试输出：帮助定位“画布上只显示部分流程引脚”等问题
        pins = composite.virtual_pins or []
        print(
            f"[CompositePinPanel] 加载复合节点: {composite.node_name} "
            f"({composite.composite_id}), 虚拟引脚数量={len(pins)}"
        )
        for pin in pins:
            direction = "输入" if pin.is_input else "输出"
            kind = "流程" if pin.is_flow else "数据"
            mapped_count = len(getattr(pin, "mapped_ports", []) or [])
            print(
                f"[CompositePinPanel]  - 索引={pin.pin_index}, 方向={direction}, "
                f"类型={kind}, 名称={pin.pin_name}, 映射端口数={mapped_count}"
            )

        self.preview_widget.load_composite(composite)
    
    def clear(self) -> None:
        """清空面板"""
        self.current_composite = None
        self.preview_widget.load_composite(None)
    
    def _on_pin_updated(self) -> None:
        """引脚更新（由预览组件触发）"""
        # 通知内部编辑器刷新端口显示
        if self.composite_widget and hasattr(self.composite_widget, 'graph_scene'):
            scene = self.composite_widget.graph_scene
            if scene and hasattr(scene, '_refresh_all_ports'):
                scene._refresh_all_ports()
        
        self.pin_updated.emit()

