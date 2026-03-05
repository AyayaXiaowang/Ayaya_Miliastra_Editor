"""端口图形项模块

包含端口显示、虚拟引脚映射、右键菜单等功能。
"""
from __future__ import annotations

import time

from PyQt6 import QtCore, QtGui, QtWidgets
from typing import TYPE_CHECKING, Optional, Tuple, Dict

from engine.utils.logging.logger import log_info
from app.ui.graph.virtual_pin_ui_service import (
    get_composite_edit_context,
    find_virtual_pin_for_port,
    build_port_context_menu as build_port_context_menu_from_service,
)
from app.ui.foundation import dialog_utils
from app.ui.foundation import fonts as ui_fonts
from app.ui.foundation.theme_manager import Colors
from app.ui.graph.graph_palette import GraphPalette
from engine.configs.settings import settings as _settings_ui

if TYPE_CHECKING:
    from app.ui.graph.graph_scene import GraphScene, NodeGraphicsItem
    from app.ui.foundation.context_menu_builder import ContextMenuBuilder


PORT_RADIUS = 7


def _build_event_mapping_tooltip_lines(*, node: object, scene: object) -> list[str]:
    node_def_ref = getattr(node, "node_def_ref", None)
    kind = str(getattr(node_def_ref, "kind", "") or "").strip() if node_def_ref is not None else ""
    if kind != "event":
        return []

    event_key = str(getattr(node_def_ref, "key", "") or "").strip()
    category = str(getattr(node, "category", "") or "").strip()
    title = str(getattr(node, "title", "") or "").strip()
    mapped_builtin_key = f"{category}/{title}" if (category and title) else ""

    mapping_hit: Optional[bool] = None
    node_library = getattr(scene, "node_library", None)
    if isinstance(node_library, dict) and mapped_builtin_key:
        mapping_hit = node_library.get(mapped_builtin_key) is not None

    hit_text = "unknown" if mapping_hit is None else ("hit" if mapping_hit else "miss")
    return [
        f"🧭 event映射: event_key={event_key or '(empty)'} mapped_builtin_key={mapped_builtin_key or '(empty)'} mapping={hit_text}"
    ]


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
        # 虚拟引脚暴露状态缓存（避免在 paint/boundingRect 中反复查询映射服务）
        self._cached_is_exposed: bool = False
        self._cached_virtual_pin_name: str = ""
    
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
            # 缓存暴露状态，供 paint/boundingRect 使用（避免重复 find_virtual_pin_for_port）
            self._cached_is_exposed = bool(context and virtual_pin)
            self._cached_virtual_pin_name = str(getattr(virtual_pin, "pin_name", "") or "") if virtual_pin else ""
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
                self._cached_is_exposed = False
                self._cached_virtual_pin_name = ""
                log_info(
                    "[角标-Tooltip] 节点[{}]({}).{} 未暴露为虚拟引脚, is_flow={}",
                    self.node_item.node.title,
                    self.node_item.node.id,
                    self.name,
                    self.is_flow,
                )
                self._printed_tooltip_log = True

        event_lines = _build_event_mapping_tooltip_lines(node=self.node_item.node, scene=scene)
        if event_lines:
            tooltip = f"{tooltip}\n" + "\n".join(event_lines)

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
        if bool(getattr(self, "_cached_is_exposed", False)):
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

    def shape(self) -> QtGui.QPainterPath:  # type: ignore[override]
        """命中测试形状。

        LOD：当缩放低于阈值时返回空 shape，避免“端口不可见但仍可被点击/命中”。
        """
        scene_ref_for_perf = self.scene()
        monitor = getattr(scene_ref_for_perf, "_perf_monitor", None) if scene_ref_for_perf is not None else None
        inc = getattr(monitor, "inc", None) if monitor is not None else None
        accum = getattr(monitor, "accum_ns", None) if monitor is not None else None
        t_total0 = time.perf_counter_ns() if monitor is not None else 0
        if callable(inc):
            inc("items.shape.port.calls", 1)

        if bool(getattr(_settings_ui, "GRAPH_LOD_ENABLED", True)):
            scene_ref = self.scene()
            scale_hint = float(getattr(scene_ref, "view_scale_hint", 1.0) or 1.0) if scene_ref is not None else 1.0
            # 端口可见性阈值：端口隐藏应以端口自身的阈值为准（默认 30%），
            # 不与“节点细节阈值”绑定，避免节点进入低细节模式后端口过早消失。
            port_min_scale = float(getattr(_settings_ui, "GRAPH_LOD_PORT_MIN_SCALE", 0.30))
            if scale_hint < port_min_scale:
                if monitor is not None and callable(accum):
                    accum("items.shape.port.lod_skip", int(time.perf_counter_ns() - int(t_total0)))
                return QtGui.QPainterPath()

        rect = self._get_port_rect()
        path = QtGui.QPainterPath()
        if self.is_flow:
            path.addRoundedRect(rect, 4.0, 4.0)
        else:
            path.addEllipse(rect)
        if monitor is not None and callable(accum):
            accum("items.shape.port.total", int(time.perf_counter_ns() - int(t_total0)))
        return path

    def paint(self, painter: QtGui.QPainter, option, widget=None) -> None:
        scene_ref_for_perf = self.scene()
        monitor = getattr(scene_ref_for_perf, "_perf_monitor", None) if scene_ref_for_perf is not None else None
        inc = getattr(monitor, "inc", None) if monitor is not None else None
        accum = getattr(monitor, "accum_ns", None) if monitor is not None else None
        track = getattr(monitor, "track_slowest", None) if monitor is not None else None
        t_total0 = time.perf_counter_ns() if monitor is not None else 0
        if callable(inc):
            inc("items.paint.port.calls", 1)

        # LOD：低倍率缩放时不绘制端口/角标，减少超大图重绘开销
        if bool(getattr(_settings_ui, "GRAPH_LOD_ENABLED", True)):
            t0 = time.perf_counter_ns() if monitor is not None else 0
            scale_hint = float(painter.worldTransform().m11())
            port_min_scale = float(getattr(_settings_ui, "GRAPH_LOD_PORT_MIN_SCALE", 0.30))
            if scale_hint < port_min_scale:
                if monitor is not None and callable(accum):
                    accum("items.paint.port.lod_gate", int(time.perf_counter_ns() - int(t0)))
                    dt_total_ns = int(time.perf_counter_ns() - int(t_total0))
                    accum("items.paint.port.total", dt_total_ns)
                return
            if monitor is not None and callable(accum):
                accum("items.paint.port.lod_gate", int(time.perf_counter_ns() - int(t0)))

        # 检查是否在复合节点编辑器中且端口已被暴露
        is_exposed = bool(getattr(self, "_cached_is_exposed", False))
        virtual_pin_name = str(getattr(self, "_cached_virtual_pin_name", "") or "") if is_exposed else ""
        
        # 绘制端口本身（使用固定的端口矩形，不使用扩展后的boundingRect）
        port_rect = self._get_port_rect()
        
        # 本次是否处于"高亮显示"状态（单链或多链着色均视为高亮）
        has_custom_highlight = self.highlight_color is not None
        is_highlight_state = self.is_highlighted or has_custom_highlight
        
        if monitor is not None and callable(accum):
            t0 = time.perf_counter_ns()
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
        if monitor is not None and callable(accum):
            accum("items.paint.port.shape", int(time.perf_counter_ns() - int(t0)))
        
        # 绘制引脚编号标记（已暴露的端口）
        if is_exposed and virtual_pin_name:
            t_tag0 = time.perf_counter_ns() if monitor is not None else 0
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
                font = ui_fonts.ui_font(10, bold=True)
                painter.setFont(font)
                painter.drawText(tag_rect, QtCore.Qt.AlignmentFlag.AlignCenter, number_text)

            painter.restore()
            if monitor is not None and callable(accum):
                accum("items.paint.port.virtual_pin_tag", int(time.perf_counter_ns() - int(t_tag0)))

        if monitor is not None and callable(accum):
            dt_total_ns = int(time.perf_counter_ns() - int(t_total0))
            accum("items.paint.port.total", dt_total_ns)
            if callable(track):
                node_obj = getattr(getattr(self, "node_item", None), "node", None)
                node_id = str(getattr(node_obj, "id", "") or "")
                track(f"port:{node_id}.{self.name}", dt_total_ns)
    
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
        from app.ui.graph.items.port_type_resolver import resolve_effective_port_type_for_scene

        return resolve_effective_port_type_for_scene(
            scene,
            self.node_item.node,
            self.name,
            is_input=self.is_input,
            is_flow=self.is_flow,
        )
    
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
        self.setFont(ui_fonts.monospace_font(8))
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

