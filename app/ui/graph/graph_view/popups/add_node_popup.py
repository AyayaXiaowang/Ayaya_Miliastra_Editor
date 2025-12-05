from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from engine.nodes.node_definition_loader import group_by_category
from engine.nodes.port_type_system import can_connect_ports
from ui.foundation.theme_manager import Colors, Sizes, Gradients

if TYPE_CHECKING:
    from engine.nodes.node_definition_loader import NodeDef


class AddNodePopup(QtWidgets.QWidget):
    """添加节点的浮动菜单（非模态）"""
    def __init__(self, library: dict, scene_pos: QtCore.QPointF, on_add_callback: Callable, parent=None, filter_port_type: Optional[str] = None, is_output: bool = True, current_scope: str = "server"):
        super().__init__(parent, QtCore.Qt.WindowType.Popup | QtCore.Qt.WindowType.FramelessWindowHint)
        self.library = library
        self.scene_pos = scene_pos
        self.on_add_callback = on_add_callback
        self.filter_port_type = filter_port_type  # 过滤端口类型
        self.is_output = is_output  # 起始端口是否是输出（决定新节点需要什么类型的端口）
        self.current_scope = current_scope  # 当前节点图作用域
        
        self.setWindowTitle("添加节点" + (f" (过滤: {filter_port_type})" if filter_port_type else ""))
        self.resize(400, 500)

        # 设置样式：统一接入主题配色，确保深浅主题下都具备足够对比度
        self.setStyleSheet(
            f"""
            QWidget {{
                background-color: {Colors.BG_DARK};
                border: {Sizes.BORDER_THIN}px solid {Colors.BORDER_DARK};
                border-radius: {Sizes.RADIUS_MEDIUM}px;
                color: {Colors.TEXT_PRIMARY};
            }}
            QLineEdit {{
                background-color: {Colors.BG_INPUT};
                color: {Colors.TEXT_PRIMARY};
                border: {Sizes.BORDER_THIN}px solid {Colors.BORDER_LIGHT};
                border-radius: {Sizes.RADIUS_SMALL}px;
                padding: {Sizes.PADDING_SMALL}px;
            }}
            QLineEdit:focus {{
                border: {Sizes.BORDER_THIN}px solid {Colors.BORDER_FOCUS};
            }}
            QTreeWidget {{
                background-color: {Colors.BG_CARD};
                color: {Colors.TEXT_PRIMARY};
                border: {Sizes.BORDER_THIN}px solid {Colors.BORDER_LIGHT};
                border-radius: {Sizes.RADIUS_SMALL}px;
            }}
            QTreeWidget::item {{
                padding: {Sizes.PADDING_TINY}px {Sizes.PADDING_SMALL}px;
                color: {Colors.TEXT_PRIMARY};
            }}
            QTreeWidget::item:selected {{
                background: {Gradients.primary_vertical()};
                color: {Colors.TEXT_ON_PRIMARY};
            }}
        """
        )
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # 搜索框
        self.search_input = QtWidgets.QLineEdit(self)
        self.search_input.setPlaceholderText("搜索节点... (支持模糊搜索)")
        # 显式启用输入法支持，确保可以输入中文
        self.search_input.setAttribute(QtCore.Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        layout.addWidget(self.search_input)
        
        # 分类树形列表
        self.tree_widget = QtWidgets.QTreeWidget(self)
        self.tree_widget.setHeaderLabel("节点列表")
        layout.addWidget(self.tree_widget)
        
        # 信号连接
        self.search_input.textChanged.connect(self._filter_nodes)
        self.tree_widget.itemClicked.connect(self._on_item_clicked)
        self.tree_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        
        # 初始化节点列表
        self._populate_tree()
    
    def showEvent(self, event: QtGui.QShowEvent) -> None:
        """窗口显示时，确保搜索框获得焦点"""
        super().showEvent(event)
        # 使用 QTimer 延迟设置焦点，确保窗口完全显示后再设置
        # 这对于Tool类型窗口尤其重要，避免焦点被其他事件抢占
        QtCore.QTimer.singleShot(50, self._set_search_focus)
    
    def _set_search_focus(self) -> None:
        """设置搜索框焦点"""
        if self.isVisible():
            self.search_input.setFocus()
            self.search_input.activateWindow()
    
    def _populate_tree(self, filter_text: str = "") -> None:
        """填充树形列表"""
        self.tree_widget.clear()
        
        # 按类别分组
        grouped = group_by_category(self.library)
        
        # 记录端口类型过滤条件（仅在 GRAPH_UI_VERBOSE 打开时输出调试信息）
        if self.filter_port_type:
            from engine.configs.settings import settings as _settings_ui

            if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
                print(
                    f"[节点过滤] 需要端口类型: {self.filter_port_type}, "
                    f"方向: {'输出' if self.is_output else '输入'}"
                )
        
        # 类别颜色映射
        category_colors = {
            "事件节点": "#FF5E9C",
            "执行节点": "#9CD64B",
            "查询节点": "#2D5FE3",
            "运算节点": "#2FAACB",
            "流程控制节点": "#FF9955",
            "复合节点": "#AA55FF",  # 紫色，表示复合节点
        }
        
        for category, nodes in sorted(grouped.items()):
            # 如果有搜索过滤，检查是否有匹配的节点
            if filter_text:
                matching_nodes = [
                    node for node in nodes 
                    if filter_text.lower() in node.name.lower() or 
                       filter_text.lower() in category.lower()
                ]
                if not matching_nodes:
                    continue
            else:
                matching_nodes = nodes
            
            # 过滤作用域：只显示在当前作用域可用的节点
            scope_filtered_nodes = [
                node for node in matching_nodes 
                if node.is_available_in_scope(self.current_scope)
            ]
            matching_nodes = scope_filtered_nodes
            if not matching_nodes:
                continue
            
            # 如果有类型过滤，进一步筛选节点
            if self.filter_port_type:
                filtered_nodes = []
                for node in matching_nodes:
                    # 检查节点是否有兼容的端口
                    has_compatible_port = False
                    # 如果起始端口是输出，检查节点的输入端口
                    if self.is_output:
                        for port_name in node.inputs:
                            # 从节点定义获取端口类型
                            port_type = node.get_port_type(port_name, is_input=True)
                            # 使用与连接相同的判断逻辑
                            if can_connect_ports(self.filter_port_type, port_type):
                                has_compatible_port = True
                                break
                    # 如果起始端口是输入，检查节点的输出端口
                    else:
                        for port_name in node.outputs:
                            # 从节点定义获取端口类型
                            port_type = node.get_port_type(port_name, is_input=False)
                            # 使用与连接相同的判断逻辑
                            if can_connect_ports(port_type, self.filter_port_type):
                                has_compatible_port = True
                                break
                    
                    if has_compatible_port:
                        filtered_nodes.append(node)
                
                matching_nodes = filtered_nodes
                if not matching_nodes:
                    continue
            
            # 创建类别项
            category_item = QtWidgets.QTreeWidgetItem([category])
            category_color = category_colors.get(category, "#4A9EFF")
            category_item.setForeground(0, QtGui.QBrush(QtGui.QColor(category_color)))
            font = category_item.font(0)
            font.setBold(True)
            category_item.setFont(0, font)
            self.tree_widget.addTopLevelItem(category_item)
            
            # 添加节点
            for node in matching_nodes:
                node_item = QtWidgets.QTreeWidgetItem([node.name])
                # 直接存放 NodeDef 对象，避免因同名变体（@server/@client）导致的键冲突与误取
                node_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, node)
                # 节点使用相同的类别颜色，但稍微暗一些
                node_color = QtGui.QColor(category_color)
                node_color.setAlpha(180)
                node_item.setForeground(0, QtGui.QBrush(node_color))
                category_item.addChild(node_item)
            
            # 默认情况下折叠分类；当存在搜索关键字时自动展开，便于查看匹配结果
            if filter_text:
                category_item.setExpanded(True)

        # 额外分组：复合节点（身份分组）
        composite_nodes_all = [n for n in self.library.values() if getattr(n, "is_composite", False)]

        # 搜索过滤
        if filter_text:
            composite_nodes = [
                n for n in composite_nodes_all
                if (filter_text.lower() in n.name.lower() or "复合节点".startswith(filter_text.lower()))
            ]
        else:
            composite_nodes = composite_nodes_all

        # 作用域过滤
        composite_nodes = [n for n in composite_nodes if n.is_available_in_scope(self.current_scope)]

        # 端口类型兼容性过滤（与上面保持一致）
        if self.filter_port_type:
            filtered = []
            for node in composite_nodes:
                has_compatible_port = False
                if self.is_output:
                    for port_name in node.inputs:
                        port_type = node.get_port_type(port_name, is_input=True)
                        if can_connect_ports(self.filter_port_type, port_type):
                            has_compatible_port = True
                            break
                else:
                    for port_name in node.outputs:
                        port_type = node.get_port_type(port_name, is_input=False)
                        if can_connect_ports(port_type, self.filter_port_type):
                            has_compatible_port = True
                            break
                if has_compatible_port:
                    filtered.append(node)
            composite_nodes = filtered

        if composite_nodes:
            category = "复合节点"
            category_item = QtWidgets.QTreeWidgetItem([category])
            category_color = category_colors.get(category, "#4A9EFF")
            category_item.setForeground(0, QtGui.QBrush(QtGui.QColor(category_color)))
            font = category_item.font(0)
            font.setBold(True)
            category_item.setFont(0, font)
            self.tree_widget.addTopLevelItem(category_item)

            for node in sorted(composite_nodes, key=lambda n: n.name):
                node_item = QtWidgets.QTreeWidgetItem([node.name])
                node_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, node)
                node_color = QtGui.QColor(category_color)
                node_color.setAlpha(180)
                node_item.setForeground(0, QtGui.QBrush(node_color))
                category_item.addChild(node_item)

            if filter_text:
                category_item.setExpanded(True)
    
    def _filter_nodes(self, text: str) -> None:
        """根据搜索文本过滤节点"""
        self._populate_tree(text.strip())
    
    def _on_item_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        """单击项目

        设计约定：
        - 顶层分类行（无绑定 NodeDef，仅作为分组标题）单击时，整行用于展开/收起；
        - 具体节点行仍仅作为选中，不触发展开/收起，避免误操作。
        """
        node_def: Optional["NodeDef"] = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if node_def is None and item.childCount() > 0:
            item.setExpanded(not item.isExpanded())
    
    def _on_item_double_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        """双击项目时添加节点"""
        node_def = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if node_def:
            self.on_add_callback(node_def, self.scene_pos)
            self.close()
    
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """处理键盘事件"""
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.close()
        elif event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            # 回车键添加当前选中的节点
            current_item = self.tree_widget.currentItem()
            if current_item:
                node_def = current_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if node_def:
                    self.on_add_callback(node_def, self.scene_pos)
                    self.close()
        else:
            super().keyPressEvent(event)
    
    def focusOutEvent(self, event: QtGui.QFocusEvent) -> None:
        """失去焦点时自动关闭窗口，模拟 Popup 行为"""
        # 使用 QTimer 延迟检查，避免在窗口内部切换焦点时误关闭
        # 例如从搜索框切换到树形列表时不应该关闭
        QtCore.QTimer.singleShot(100, self._check_and_close)
        super().focusOutEvent(event)
    
    def _check_and_close(self) -> None:
        """检查焦点是否仍在窗口内，如果不在则关闭"""
        # 获取当前拥有焦点的窗口部件
        focused_widget = QtWidgets.QApplication.focusWidget()
        # 如果焦点不在当前窗口或其子部件上，则关闭
        if focused_widget is None or not self.isAncestorOf(focused_widget):
            # 额外检查：确保焦点不是在窗口本身上
            if focused_widget != self:
                self.close()

