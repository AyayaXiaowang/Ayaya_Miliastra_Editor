"""端口图形项模块

包含端口显示、虚拟引脚映射、右键菜单等功能。
"""
from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets
from typing import TYPE_CHECKING, Optional, Tuple, Dict

from engine.utils.logging.logger import log_info
from app.ui.graph.virtual_pin_ui_service import (
    get_composite_edit_context,
    find_virtual_pin_for_port,
    build_port_context_menu as build_port_context_menu_from_service,
)
from app.ui.foundation import dialog_utils
from app.ui.graph.graph_palette import GraphPalette

if TYPE_CHECKING:
    from app.ui.graph.graph_scene import GraphScene, NodeGraphicsItem
    from app.ui.foundation.context_menu_builder import ContextMenuBuilder


PORT_RADIUS = 7


class PortGraphicsItem(QtWidgets.QGraphicsItem):
    def __init__(self, node_item: 'NodeGraphicsItem', name: str, is_input: bool, index: int, is_flow: bool = False):
        super().__init__()
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges)
        self.setZValue(20)  # 设置 z-index 高于节点(10)，确保端口可被点击
        self.node_item = node_item
        self.name = name
        self.is_input = is_input
        self.index = index
        self.is_flow = is_flow
        # 端口类型从节点定义获取，不再推断
        self.port_type = None  # 延迟获取，在需要时从节点定义中获取
        self.is_highlighted = False  # 高亮状态
        self.highlight_color: Optional[QtGui.QColor] = None  # 链路着色（覆盖默认高亮色）
        self._update_tooltip()
        self.setAcceptedMouseButtons(QtCore.Qt.MouseButton.LeftButton | QtCore.Qt.MouseButton.RightButton)
        # 调试：仅在复合节点编辑器中打印一次性的角标渲染信息，避免刷屏
        self._printed_exposed_log: bool = False
        self._printed_tooltip_log: bool = False
    
    def _update_tooltip(self) -> None:
        """更新工具提示，显示虚拟引脚信息。"""
        tooltip = self.name

        scene = self.scene()
        if isinstance(scene, QtWidgets.QGraphicsScene):
            context, virtual_pin = find_virtual_pin_for_port(
                scene,
                self.node_item.node.id,
                self.name,
            )
            if context and virtual_pin:
                mapped_count = len(virtual_pin.mapped_ports)
                tooltip = f"{self.name}\n⭐ 虚拟引脚: {virtual_pin.pin_name} (共{mapped_count}个映射)"
                if not self._printed_tooltip_log:
                    log_info(
                        "[角标-Tooltip] 节点[{}]({}).{} → 虚拟引脚='{}', 映射数={}, is_flow={}",
                        self.node_item.node.title,
                        self.node_item.node.id,
                        self.name,
                        virtual_pin.pin_name,
                        mapped_count,
                        self.is_flow,
                    )
                    self._printed_tooltip_log = True
            elif context and not self._printed_tooltip_log:
                log_info(
                    "[角标-Tooltip] 节点[{}]({}).{} 未暴露为虚拟引脚, is_flow={}",
                    self.node_item.node.title,
                    self.node_item.node.id,
                    self.name,
                    self.is_flow,
                )
                self._printed_tooltip_log = True

        self.setToolTip(tooltip)
    
    def _get_port_rect(self) -> QtCore.QRectF:
        """获取端口本身的矩形区域（不包含标签）"""
        if self.is_flow:
            return QtCore.QRectF(-10, -8, 20, 16)
        return QtCore.QRectF(-PORT_RADIUS, -PORT_RADIUS, PORT_RADIUS * 2, PORT_RADIUS * 2)

    def boundingRect(self) -> QtCore.QRectF:
        # 基础端口区域
        base_rect = self._get_port_rect()
        
        # 检查是否在复合节点编辑器中且端口已被暴露
        scene = self.scene()
        if isinstance(scene, QtWidgets.QGraphicsScene):
            _context, virtual_pin = find_virtual_pin_for_port(
                scene,
                self.node_item.node.id,
                self.name,
            )
            if virtual_pin:
                # 端口已暴露，需要扩展边界以包含标签区域
                tag_width = 24
                tag_height = 20
                tag_spacing = 8

                # 计算扩展后的矩形
                left = base_rect.left()
                top = base_rect.top()
                right = base_rect.right()
                bottom = base_rect.bottom()

                if self.is_input:
                    # 输入端口：标签在左侧，向左扩展
                    left = min(left, -tag_width - tag_spacing)
                else:
                    # 输出端口：标签在右侧，向右扩展
                    right = max(right, tag_width + tag_spacing)

                # 垂直方向扩展以包含标签高度
                top = min(top, -tag_height / 2)
                bottom = max(bottom, tag_height / 2)

                return QtCore.QRectF(
                    left,
                    top,
                    right - left,
                    bottom - top,
                )
        
        return base_rect

    def paint(self, painter: QtGui.QPainter, option, widget=None) -> None:
        # 检查是否在复合节点编辑器中且端口已被暴露
        is_exposed = False
        virtual_pin_name = None
        scene = self.scene()
        if isinstance(scene, QtWidgets.QGraphicsScene):
            _context, virtual_pin = find_virtual_pin_for_port(
                scene,
                self.node_item.node.id,
                self.name,
            )
            if virtual_pin:
                is_exposed = True
                virtual_pin_name = virtual_pin.pin_name
                # 仅首次打印角标渲染信息
                if not self._printed_exposed_log:
                    log_info(
                        "[角标-渲染] 节点[{}]({}).{} 已暴露 → 引脚='{}', is_flow={}",
                        self.node_item.node.title,
                        self.node_item.node.id,
                        self.name,
                        virtual_pin_name,
                        self.is_flow,
                    )
                    self._printed_exposed_log = True
            elif self._printed_exposed_log:
                log_info(
                    "[角标-渲染] 节点[{}]({}).{} 角标状态 → 未暴露（之前为已暴露）",
                    self.node_item.node.title,
                    self.node_item.node.id,
                    self.name,
                )
                self._printed_exposed_log = False
        
        # 绘制端口本身（使用固定的端口矩形，不使用扩展后的boundingRect）
        port_rect = self._get_port_rect()
        
        # 本次是否处于"高亮显示"状态（单链或多链着色均视为高亮）
        has_custom_highlight = self.highlight_color is not None
        is_highlight_state = self.is_highlighted or has_custom_highlight
        
        if self.is_flow:
            # rounded diamond-like pill
            if is_highlight_state:
                # 高亮：优先使用自定义颜色
                color = self.highlight_color if has_custom_highlight else QtGui.QColor(GraphPalette.WARN_GOLD)
                painter.setPen(QtGui.QPen(color, 3))
                c = QtGui.QColor(color)
                c.setAlpha(100)
                painter.setBrush(c)  # 半透明填充
            elif is_exposed:
                # 已暴露：使用金色边框和填充
                painter.setPen(QtGui.QPen(QtGui.QColor(GraphPalette.WARN_GOLD), 2))
                fill = QtGui.QColor(GraphPalette.WARN_GOLD)
                fill.setAlpha(GraphPalette.PORT_EXPOSED_FILL_ALPHA)
                painter.setBrush(fill)  # 淡金色填充
            else:
                painter.setPen(QtGui.QPen(QtGui.QColor(GraphPalette.PORT_DEFAULT_OUTPUT), 2))
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(port_rect, 4, 4)
        else:
            if is_highlight_state:
                # 高亮：优先使用自定义颜色
                pen_color = self.highlight_color if has_custom_highlight else QtGui.QColor(GraphPalette.PORT_HIGHLIGHT_DATA)
                c = QtGui.QColor(pen_color)
                c.setAlpha(100)
                painter.setBrush(c)  # 半透明填充
                pen_width = 3
            elif is_exposed:
                # 已暴露：使用金色边框和填充
                pen_color = QtGui.QColor(GraphPalette.WARN_GOLD)
                fill = QtGui.QColor(GraphPalette.WARN_GOLD)
                fill.setAlpha(GraphPalette.PORT_EXPOSED_FILL_ALPHA)
                painter.setBrush(fill)  # 淡金色填充
                pen_width = 2
            else:
                pen_color = (
                    QtGui.QColor(GraphPalette.PORT_DEFAULT_INPUT)
                    if self.is_input
                    else QtGui.QColor(GraphPalette.PORT_DEFAULT_OUTPUT)
                )
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                pen_width = 2
            pen = QtGui.QPen(pen_color)
            pen.setWidth(pen_width)
            painter.setPen(pen)
            painter.drawEllipse(port_rect)
        
        # 绘制引脚编号标记（已暴露的端口）
        if is_exposed and virtual_pin_name:
            painter.save()

            # 获取引脚编号
            context = get_composite_edit_context(scene) if isinstance(scene, QtWidgets.QGraphicsScene) else None
            virtual_pin_for_number = None
            if context is not None:
                composite_id = context["composite_id"]
                manager = context["manager"]
                virtual_pin_for_number = manager.find_port_virtual_pin(
                    composite_id,
                    self.node_item.node.id,
                    self.name,
                )

            if virtual_pin_for_number and context is not None:
                prefix, number = context["manager"].get_pin_display_number(
                    context["composite_id"],
                    virtual_pin_for_number,
                )
                number_text = str(number)

                # 标签尺寸
                tag_width = 24
                tag_height = 20
                tag_radius = tag_height // 2  # 圆角半径

                # 计算标签位置（在端口外侧）
                if self.is_input:
                    # 输入端口：标签在左侧
                    tag_x = -tag_width - 8
                else:
                    # 输出端口：标签在右侧
                    tag_x = 8
                tag_y = -tag_height // 2

                # 绘制标签形状
                tag_rect = QtCore.QRectF(tag_x, tag_y, tag_width, tag_height)

                # 标签背景颜色（金色渐变）
                gradient = QtGui.QLinearGradient(tag_rect.topLeft(), tag_rect.bottomLeft())
                gradient.setColorAt(0, QtGui.QColor(GraphPalette.PORT_EXPOSED_TAG_START))
                gradient.setColorAt(1, QtGui.QColor(GraphPalette.PORT_EXPOSED_TAG_END))
                painter.setBrush(gradient)
                painter.setPen(QtGui.QPen(QtGui.QColor(GraphPalette.PORT_EXPOSED_TAG_OUTLINE), 2))

                # 根据端口类型绘制不同形状
                if self.is_flow:
                    # 流程端口：方形标签
                    painter.drawRoundedRect(tag_rect, 3, 3)
                else:
                    # 数据端口：圆形标签
                    painter.drawRoundedRect(tag_rect, tag_radius, tag_radius)

                # 绘制数字
                painter.setPen(QtGui.QPen(QtGui.QColor(GraphPalette.TEXT_BRIGHT), 1))
                font = QtGui.QFont("Microsoft YaHei UI", 10, QtGui.QFont.Weight.Bold)
                painter.setFont(font)
                painter.drawText(tag_rect, QtCore.Qt.AlignmentFlag.AlignCenter, number_text)

            painter.restore()
    
    def contextMenuEvent(self, event) -> None:
        """右键菜单事件：允许删除多分支节点的分支端口 / 复合节点编辑器中暴露为虚拟引脚"""
        scene = self.scene()
        if not isinstance(scene, QtWidgets.QGraphicsScene):
            super().contextMenuEvent(event)
            return

        from app.ui.foundation.context_menu_builder import ContextMenuBuilder

        builder = build_port_context_menu_from_service(self, scene, builder_cls=ContextMenuBuilder)
        if builder is not None:
            builder.exec_global(event.screenPos())

        super().contextMenuEvent(event)
    
    def _expose_as_new_virtual_pin(self, scene: 'GraphScene') -> None:
        """暴露为新的虚拟引脚"""
        context = get_composite_edit_context(scene)
        if not context:
            return
        composite_id = context["composite_id"]
        manager = context["manager"]
        
        # 获取端口类型
        port_type = self._get_port_type(scene)
        
        # 弹出对话框
        from app.ui.dialogs.virtual_pin_dialog import CreateVirtualPinDialog
        dialog = CreateVirtualPinDialog(
            self.node_item.node.id,
            self.name,
            port_type,
            self.is_input
        )
        
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            pin_name = dialog.get_pin_name()
            description = dialog.get_description()
            
            if not pin_name:
                dialog_utils.show_warning_dialog(None, "错误", "引脚名称不能为空")
                return
            
            # 创建虚拟引脚
            composite = manager.get_composite_node(composite_id)
            if not composite:
                return
            
            # 生成新的引脚序号
            existing_indices = [pin.pin_index for pin in composite.virtual_pins]
            new_index = max(existing_indices) + 1 if existing_indices else 1
            
            # 创建虚拟引脚配置
            from engine.nodes.advanced_node_features import VirtualPinConfig, MappedPort
            virtual_pin = VirtualPinConfig(
                pin_index=new_index,
                pin_name=pin_name,
                pin_type=port_type,
                is_input=self.is_input,
                is_flow=self.is_flow,
                description=description,
                mapped_ports=[
                    MappedPort(
                        node_id=self.node_item.node.id,
                        port_name=self.name,
                        is_input=self.is_input,
                        is_flow=self.is_flow
                    )
                ]
            )
            
            composite.virtual_pins.append(virtual_pin)
            
            # 保存
            manager.update_composite_node(composite_id, composite)
            
            # 刷新显示（更新端口视觉效果和工具提示）
            self._update_tooltip()
            self.update()

            scene._refresh_all_ports([self.node_item.node.id])

            log_info("✅ 创建虚拟引脚: {}", pin_name)
    
    def _add_to_existing_virtual_pin(self, scene: 'GraphScene') -> None:
        """添加到现有虚拟引脚"""
        context = get_composite_edit_context(scene)
        if not context:
            return
        composite_id = context["composite_id"]
        manager = context["manager"]
        
        # 获取可用的虚拟引脚（同方向、同类型）
        available_pins = manager.get_available_virtual_pins(composite_id, self.is_input, self.is_flow)
        if not available_pins:
            return
        
        # 获取端口类型
        port_type = self._get_port_type(scene)
        
        # 弹出对话框
        from app.ui.dialogs.virtual_pin_dialog import AddToVirtualPinDialog
        dialog = AddToVirtualPinDialog(
            available_pins,
            self.node_item.node.id,
            self.name,
            port_type
        )
        
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            pin_index = dialog.get_selected_pin_index()
            merge_strategy = dialog.get_merge_strategy()
            
            if pin_index is None:
                return
            
            # 添加映射
            port_type = self._get_port_type(scene)
            if manager.add_virtual_pin_mapping(
                composite_id,
                pin_index,
                self.node_item.node.id,
                self.name,
                self.is_input,
                port_type,
                self.is_flow
            ):
                # 更新合并策略（仅输出引脚）
                if not self.is_input:
                    composite = manager.get_composite_node(composite_id)
                    if composite:
                        virtual_pin = next((p for p in composite.virtual_pins if p.pin_index == pin_index), None)
                        if virtual_pin:
                            virtual_pin.merge_strategy = merge_strategy
                
                # 保存
                affected_nodes: list[str] = []
                composite = manager.get_composite_node(composite_id)
                if composite:
                    manager.update_composite_node(composite_id, composite)
                    target_pin = next((p for p in composite.virtual_pins if p.pin_index == pin_index), None)
                    if target_pin:
                        affected_nodes = [mapped_port.node_id for mapped_port in target_pin.mapped_ports]
                
                self._update_tooltip()
                self.update()
                scene._refresh_all_ports(affected_nodes or [self.node_item.node.id])
    
    def _remove_virtual_pin_mapping(self, scene: 'GraphScene') -> None:
        """移除虚拟引脚映射"""
        context = get_composite_edit_context(scene)
        if not context:
            return
        composite_id = context["composite_id"]
        manager = context["manager"]
        
        # 查找虚拟引脚
        virtual_pin = manager.find_port_virtual_pin(
            composite_id,
            self.node_item.node.id,
            self.name
        )
        
        if not virtual_pin:
            return
        
        impacted_nodes = [mapped_port.node_id for mapped_port in virtual_pin.mapped_ports]
        # 移除映射
        if manager.remove_virtual_pin_mapping(
            composite_id,
            virtual_pin.pin_index,
            self.node_item.node.id,
            self.name
        ):
            # 如果虚拟引脚没有任何映射了，删除它
            if not virtual_pin.mapped_ports:
                composite = manager.get_composite_node(composite_id)
                if composite:
                    composite.virtual_pins = [p for p in composite.virtual_pins if p.pin_index != virtual_pin.pin_index]
            
            # 保存
            composite = manager.get_composite_node(composite_id)
            affected_nodes = impacted_nodes or [self.node_item.node.id]
            if composite:
                manager.update_composite_node(composite_id, composite)
            
            self._update_tooltip()
            self.update()
            scene._refresh_all_ports(affected_nodes)
    
    def _get_port_type(self, scene: 'GraphScene') -> str:
        """获取端口类型"""
        if self.is_flow:
            return "流程"
        
        # 从节点定义获取端口类型
        node_def = scene.get_node_def(self.node_item.node)
        if node_def:
            port_type = node_def.get_port_type(self.name, self.is_input)
            if port_type:
                return port_type
        
        return "泛型"
    
    def remove_branch_port(self) -> None:
        """删除分支端口"""
        scene = self.scene()
        if not isinstance(scene, QtWidgets.QGraphicsScene):
            return
        
        from app.ui.graph.graph_undo import RemovePortCommand
        
        if hasattr(scene, 'undo_manager') and scene.undo_manager:
            command = RemovePortCommand(
                scene.model,
                scene,
                self.node_item.node.id,
                self.name,
                is_input=False
            )
            scene.undo_manager.execute_command(command)
            if hasattr(scene, 'on_data_changed') and scene.on_data_changed:
                scene.on_data_changed()


class BranchPortValueEdit(QtWidgets.QGraphicsTextItem):
    """多分支节点端口的匹配值编辑框"""
    def __init__(self, node_item: 'NodeGraphicsItem', port_name: str, parent=None):
        super().__init__(parent)
        self.node_item = node_item
        self.port_name = port_name  # 当前端口名称
        self.setDefaultTextColor(QtGui.QColor(GraphPalette.WARN_GOLD))  # 金黄色，表示这是流程端口相关
        self.setFont(QtGui.QFont('Consolas', 8))
        self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditorInteraction)
        self.setPlainText(port_name)  # 默认显示端口名称
        
        # 设置文本框样式和交互
        self.setZValue(25)
        self.setTextWidth(70)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        
        # 设置提示
        self.setToolTip("编辑分支匹配值（修改后将重命名端口）")
    
    def keyPressEvent(self, event) -> None:
        """处理按键事件"""
        if event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            # 回车时失去焦点，触发重命名
            self.clearFocus()
            event.accept()
            return
        
        super().keyPressEvent(event)
    
    def focusOutEvent(self, event) -> None:
        """失去焦点时保存并重命名端口"""
        # 清除任何残留的文本选择并恢复默认前景色，避免选区导致的永久变白
        cursor = self.textCursor()
        if cursor.hasSelection():
            cursor.clearSelection()
            self.setTextCursor(cursor)
        doc_cursor = self.textCursor()
        doc_cursor.select(QtGui.QTextCursor.SelectionType.Document)
        fmt = QtGui.QTextCharFormat()
        fmt.setForeground(QtGui.QBrush(QtGui.QColor(Colors.ACCENT)))
        doc_cursor.mergeCharFormat(fmt)
        doc_cursor.clearSelection()
        self.setTextCursor(doc_cursor)
        new_value = self.toPlainText().strip()
        
        # 如果值没有变化，不做处理
        if new_value == self.port_name:
            super().focusOutEvent(event)
            return
        
        # 如果新值为空，恢复原值
        if not new_value:
            self.setPlainText(self.port_name)
            super().focusOutEvent(event)
            return
        
        # 检查新端口名是否已存在
        node = self.node_item.node
        if node.has_output_port(new_value):
            # 端口已存在，恢复原值
            dialog_utils.show_warning_dialog(
                None,
                "端口已存在",
                f"分支'{new_value}'已经存在，无法重命名。"
            )
            self.setPlainText(self.port_name)
            super().focusOutEvent(event)
            return
        
        # 执行端口重命名
        self._rename_port(new_value)
        
        super().focusOutEvent(event)
    
    def _rename_port(self, new_name: str) -> None:
        """重命名端口"""
        scene = self.node_item.scene()
        if not scene:
            return
        
        node = self.node_item.node
        old_name = self.port_name
        
        from app.ui.graph.graph_undo import RenamePortCommand

        if hasattr(scene, 'undo_manager') and scene.undo_manager:
            command = RenamePortCommand(
                scene.model,
                scene,
                node.id,
                old_name,
                new_name,
                is_input=False
            )
            scene.undo_manager.execute_command(command)
            if hasattr(scene, 'on_data_changed'):
                scene.on_data_changed()
            
            # 更新当前编辑框的端口名称引用
            self.port_name = new_name

