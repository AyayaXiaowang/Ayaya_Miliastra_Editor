"""场景对象管理 Mixin

提供add_edge_item、copy/paste、delete、高亮、更新验证等对象管理能力。
假设宿主场景提供: model, node_items, edge_items, undo_manager 等。
"""

from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets
from typing import Optional, List, TYPE_CHECKING
from ui.graph.items.edge_item import EdgeGraphicsItem
from ui.graph.items.port_item import PortGraphicsItem
from engine.graph.common import (
    FLOW_PORT_PLACEHOLDER,
    FLOW_BRANCH_PORT_ALIASES,
    FLOW_IN_PORT_NAMES,
    FLOW_OUT_PORT_NAMES,
)
from engine.utils.logging.logger import log_warn

if TYPE_CHECKING:
    from ui.graph.items.node_item import NodeGraphicsItem
    from engine.graph.models.graph_model import EdgeModel


class SceneModelOpsMixin:
    """场景对象管理 Mixin
    
    要求宿主类提供以下属性:
    - model: GraphModel
    - node_items: dict[str, NodeGraphicsItem]
    - edge_items: dict[str, EdgeGraphicsItem]
    - undo_manager: UndoRedoManager
    - read_only: bool
    - clipboard_nodes: list[dict]
    - clipboard_edges: list[dict]
    - last_mouse_scene_pos: Optional[QPointF]
    - validation_issues: dict[str, List]
    """
    
    def add_edge_item(self, edge: EdgeModel) -> Optional[EdgeGraphicsItem]:
        src_item = self.node_items.get(edge.src_node)
        dst_item = self.node_items.get(edge.dst_node)
        if not src_item or not dst_item:
            log_warn(
                "[GraphScene] 无法创建连线，节点未找到: src='{}', dst='{}'",
                edge.src_node,
                edge.dst_node,
            )
            return None
        
        # 处理 flow 端口与分支端口的特殊情况：统一使用集中定义的名称/占位符
        src_port: Optional[PortGraphicsItem]
        if edge.src_port == FLOW_PORT_PLACEHOLDER:
            # 占位符 "flow"：映射到节点的主流程输出口（若不存在则创建一个“流程出”以保证 UI 连线可见）
            if src_item._flow_out is None:
                flow_out = PortGraphicsItem(
                    src_item,
                    FLOW_OUT_PORT_NAMES[0],
                    False,
                    len(src_item._ports_out),
                    is_flow=True,
                )
                flow_out.setParentItem(src_item)
                flow_out.setPos(src_item._rect.width() / 2, src_item._rect.height())
                src_item._ports_out.append(flow_out)
                src_item._flow_out = flow_out
            src_port = src_item._flow_out
        elif edge.src_port in FLOW_BRANCH_PORT_ALIASES:
            # 分支/循环类流程端口：优先复用现有端口，其次在 UI 层补一个同名流程口以保证连线可见
            src_port = next((p for p in src_item._ports_out if p.name == edge.src_port), None)
            if src_port is None:
                branch_port = PortGraphicsItem(
                    src_item,
                    edge.src_port,
                    False,
                    len(src_item._ports_out),
                    is_flow=True,
                )
                branch_port.setParentItem(src_item)
                port_index = len(src_item._ports_out)
                branch_port.setPos(
                    src_item._rect.width() / 2 + port_index * 30,
                    src_item._rect.height(),
                )
                src_item._ports_out.append(branch_port)
                src_port = branch_port
        else:
            # 普通输出端口: 通过名称直接查找
            src_port = next((p for p in src_item._ports_out if p.name == edge.src_port), None)
        
        # 处理目标端口：同样支持 "flow" 占位符映射到标准流程入口名集合
        if edge.dst_port == FLOW_PORT_PLACEHOLDER:
            if dst_item._flow_in is None:
                # 缺失时在 UI 层补一个“流程入”流程入口
                flow_in = PortGraphicsItem(
                    dst_item,
                    FLOW_IN_PORT_NAMES[0],
                    True,
                    len(dst_item._ports_in),
                    is_flow=True,
                )
                flow_in.setParentItem(dst_item)
                flow_in.setPos(dst_item._rect.width() / 2, 0)
                dst_item._ports_in.append(flow_in)
                dst_item._flow_in = flow_in
            dst_port = dst_item._flow_in
        else:
            dst_port = next((p for p in dst_item._ports_in if p.name == edge.dst_port), None)
        
        if not src_port or not dst_port:
            log_warn(
                "[GraphScene] 端口未找到，跳过 UI 连线: src_port='{}' (可用: {}), "
                "dst_port='{}' (可用: {})",
                edge.src_port,
                [p.name for p in src_item._ports_out],
                edge.dst_port,
                [p.name for p in dst_item._ports_in],
            )
            return None
        
        e = EdgeGraphicsItem(src_port, dst_port, edge.id)
        self.addItem(e)
        self.edge_items[edge.id] = e
        # 在邻接索引中登记新连线，后续拖动节点时可以 O(度数) 刷新连线路径
        if hasattr(self, "_register_edge_for_nodes"):
            # GraphScene 提供该辅助方法
            self._register_edge_for_nodes(e)
        # 重新布局目标节点,以隐藏已连接端口的输入框
        dst_item._layout_ports()
        from engine.configs.settings import settings as _settings_ui
        if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
            print(f"已添加连接线: {edge.src_node}.{edge.src_port} -> {edge.dst_node}.{edge.dst_port}")
        return e
    
    def delete_selected_items(self) -> None:
        """删除所有选中的节点和连线"""
        from ui.graph.items.node_item import NodeGraphicsItem
        from ui.graph.graph_undo import DeleteNodeCommand, DeleteEdgeCommand
        
        selected_items = self.selectedItems()
        for item in selected_items:
            if isinstance(item, NodeGraphicsItem):
                node_id = item.node.id
                # 使用命令模式删除节点
                cmd = DeleteNodeCommand(self.model, self, node_id)
                self.undo_manager.execute_command(cmd)
            elif isinstance(item, EdgeGraphicsItem):
                edge_id = item.edge_id
                # 使用命令模式删除连线
                cmd = DeleteEdgeCommand(self.model, self, edge_id)
                self.undo_manager.execute_command(cmd)
    
    def delete_selected_nodes(self) -> None:
        """删除所有选中的节点(向后兼容)"""
        self.delete_selected_items()
    
    def _update_scene_rect(self) -> None:
        """更新场景矩形以包含所有节点,并保持大量的扩展空间"""
        items_rect = self.itemsBoundingRect()
        if not items_rect.isEmpty():
            # 在内容周围添加大量空白区域(10倍的扩展)
            expansion = max(items_rect.width(), items_rect.height()) * 10
            # 至少保持10000的扩展
            expansion = max(expansion, 10000)
            expanded_rect = items_rect.adjusted(-expansion, -expansion, expansion, expansion)
            self.setSceneRect(expanded_rect)
        else:
            # 如果没有内容,设置一个默认的大场景
            self.setSceneRect(-10000, -10000, 20000, 20000)
    
    def _remove_node_graphics(self, node_id: str) -> None:
        """从场景中移除节点的图形项"""
        # 移除相关的连线,并记录受影响的节点
        edges_to_remove = []
        affected_nodes = set()
        for edge_id, edge_item in self.edge_items.items():
            if edge_item.src.node_item.node.id == node_id or edge_item.dst.node_item.node.id == node_id:
                edges_to_remove.append(edge_id)
                # 记录目标节点,稍后需要重新布局
                if edge_item.dst.node_item.node.id != node_id:
                    affected_nodes.add(edge_item.dst.node_item.node.id)
        
        for edge_id in edges_to_remove:
            edge_item = self.edge_items.pop(edge_id, None)
            if edge_item:
                if hasattr(self, "_unregister_edge_for_nodes"):
                    self._unregister_edge_for_nodes(edge_item)
                self.removeItem(edge_item)
        
        # 移除节点
        node_item = self.node_items.pop(node_id, None)
        if node_item:
            self.removeItem(node_item)
        
        # 重新布局受影响的节点,以显示之前被隐藏的输入框
        for affected_node_id in affected_nodes:
            if affected_node_id in self.node_items:
                self.node_items[affected_node_id]._layout_ports()
        
        # 更新小地图(重置缓存以确保小地图范围能够缩小)
        for view in self.views():
            if hasattr(view, 'mini_map') and view.mini_map:
                view.mini_map.reset_cached_rect()
    
    def get_node_item(self, node_id: str) -> Optional['NodeGraphicsItem']:
        """获取节点图形项"""
        return self.node_items.get(node_id)
    
    def highlight_node(self, node_id: str) -> None:
        """高亮显示指定节点"""
        # 先清除所有高亮
        self.clear_highlights()
        
        node_item = self.node_items.get(node_id)
        if node_item:
            # 设置节点为选中状态(会显示高亮边框)
            node_item.setSelected(True)
    
    def highlight_edge(self, edge_id: str) -> None:
        """高亮显示指定连线"""
        # 先清除所有高亮
        self.clear_highlights()
        
        edge_item = self.edge_items.get(edge_id)
        if edge_item:
            # 设置连线为选中状态
            edge_item.setSelected(True)
            # 同时高亮连接的两个节点
            edge = self.model.edges.get(edge_id)
            if edge:
                src_node_item = self.node_items.get(edge.src_node)
                dst_node_item = self.node_items.get(edge.dst_node)
                if src_node_item:
                    src_node_item.setSelected(True)
                if dst_node_item:
                    dst_node_item.setSelected(True)
                
                # 高亮连接的端口
                self.highlight_port(edge.src_node, edge.src_port, is_input=False)
                self.highlight_port(edge.dst_node, edge.dst_port, is_input=True)
    
    def highlight_port(self, node_id: str, port_name: str, is_input: bool) -> None:
        """高亮显示指定端口
        
        Args:
            node_id: 节点ID
            port_name: 端口名称
            is_input: 是否为输入端口
        """
        node_item = self.node_items.get(node_id)
        if not node_item:
            return

        target_port = node_item.get_port_by_name(port_name, is_input=is_input)
        if not target_port:
            return
        target_port.is_highlighted = True
        target_port.update()
    
    def clear_highlights(self) -> None:
        """清除所有高亮"""
        self.clearSelection()
        
        # 清除所有端口的高亮状态
        for node_item in self.node_items.values():
            # 清除输入端口高亮
            for port_item in node_item._ports_in:
                if port_item.is_highlighted:
                    port_item.is_highlighted = False
                    port_item.update()
            
            # 清除输出端口高亮
            for port_item in node_item._ports_out:
                if port_item.is_highlighted:
                    port_item.is_highlighted = False
                    port_item.update()
            
            # 清除流程端口高亮
            if node_item._flow_in and node_item._flow_in.is_highlighted:
                node_item._flow_in.is_highlighted = False
                node_item._flow_in.update()
            
            if node_item._flow_out and node_item._flow_out.is_highlighted:
                node_item._flow_out.is_highlighted = False
                node_item._flow_out.update()
    
    def copy_selected_nodes(self) -> None:
        """复制选中的节点"""
        from ui.graph.items.node_item import NodeGraphicsItem
        from engine.configs.settings import settings as _settings_ui
        
        if self.read_only:
            return
        
        selected_items = self.selectedItems()
        selected_node_ids = [
            item.node.id for item in selected_items if isinstance(item, NodeGraphicsItem)
        ]
        
        if not selected_node_ids:
            if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
                print("[复制] 没有选中任何节点")
            return
        
        node_index_map = {node_id: index for index, node_id in enumerate(selected_node_ids)}
        
        # 复制节点数据
        self.clipboard_nodes = []
        for node_id in selected_node_ids:
            node = self.model.nodes.get(node_id)
            if node:
                # 序列化节点数据
                node_data = {
                    "title": node.title,
                    "category": node.category,
                    "inputs": [p.name for p in node.inputs],
                    "outputs": [p.name for p in node.outputs],
                    "pos": node.pos,
                    "constants": node.input_constants.copy()
                }
                self.clipboard_nodes.append(node_data)
        
        # 复制选中节点之间的连线
        self.clipboard_edges = []
        for edge_id, edge in self.model.edges.items():
            src_index = node_index_map.get(edge.src_node)
            dst_index = node_index_map.get(edge.dst_node)
            if src_index is None or dst_index is None:
                continue
            edge_data = {
                "src_index": src_index,
                "src_port": edge.src_port,
                "dst_index": dst_index,
                "dst_port": edge.dst_port,
            }
            self.clipboard_edges.append(edge_data)
        
        if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
            print(
                f"[复制] 已复制 {len(self.clipboard_nodes)} 个节点和 "
                f"{len(self.clipboard_edges)} 条连线"
            )
    
    def paste_nodes(self) -> None:
        """粘贴节点到鼠标位置"""
        from ui.graph.graph_undo import AddNodeCommand, AddEdgeCommand
        from engine.configs.settings import settings as _settings_ui
        
        if self.read_only or not self.clipboard_nodes:
            return
        
        # 确定粘贴位置
        if self.last_mouse_scene_pos:
            paste_center = self.last_mouse_scene_pos
        else:
            # 如果没有鼠标位置记录,粘贴到视图中心
            for view in self.views():
                view_center = view.viewport().rect().center()
                paste_center = view.mapToScene(view_center)
                break
            else:
                paste_center = QtCore.QPointF(0, 0)
        
        # 计算原始节点的中心位置
        if self.clipboard_nodes:
            original_positions = [QtCore.QPointF(node["pos"][0], node["pos"][1]) for node in self.clipboard_nodes]
            original_center_x = sum(p.x() for p in original_positions) / len(original_positions)
            original_center_y = sum(p.y() for p in original_positions) / len(original_positions)
            original_center = QtCore.QPointF(original_center_x, original_center_y)
        else:
            original_center = QtCore.QPointF(0, 0)
        
        # 计算偏移量
        offset = paste_center - original_center
        
        # 粘贴节点
        new_node_ids = []
        for node_data in self.clipboard_nodes:
            node_id = self.model.gen_id("node")
            new_pos_x = node_data["pos"][0] + offset.x()
            new_pos_y = node_data["pos"][1] + offset.y()
            
            # 使用命令模式添加节点
            cmd = AddNodeCommand(
                self.model,
                self,
                node_id,
                node_data["title"],
                node_data["category"],
                node_data["inputs"],
                node_data["outputs"],
                pos=(new_pos_x, new_pos_y)
            )
            self.undo_manager.execute_command(cmd)
            
            # 恢复常量值
            new_node = self.model.nodes.get(node_id)
            if new_node:
                new_node.constants = node_data["constants"].copy()
                # 更新图形项中的常量显示
                node_item = self.node_items.get(node_id)
                if node_item:
                    node_item._layout_ports()
            
            new_node_ids.append(node_id)
        
        # 粘贴连线
        for edge_data in self.clipboard_edges:
            src_index = edge_data["src_index"]
            dst_index = edge_data["dst_index"]
            
            # 检查索引是否有效
            if src_index < len(new_node_ids) and dst_index < len(new_node_ids):
                src_node_id = new_node_ids[src_index]
                dst_node_id = new_node_ids[dst_index]
                edge_id = self.model.gen_id("edge")
                
                cmd = AddEdgeCommand(
                    self.model,
                    self,
                    edge_id,
                    src_node_id,
                    edge_data["src_port"],
                    dst_node_id,
                    edge_data["dst_port"]
                )
                self.undo_manager.execute_command(cmd)
        
        # 清除当前选择并选中新粘贴的节点
        self.clearSelection()
        for node_id in new_node_ids:
            node_item = self.node_items.get(node_id)
            if node_item:
                node_item.setSelected(True)
        
        if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
            print(f"[粘贴] 已粘贴 {len(new_node_ids)} 个节点")
    
    def update_validation(self, issues: List) -> None:
        """更新验证结果并刷新节点显示
        
        Args:
            issues: ValidationIssue列表,来自ComprehensiveValidator
        """
        # 清空旧的验证结果
        self.validation_issues = {}
        
        # 按节点ID分组
        for issue in issues:
            if hasattr(issue, 'detail') and isinstance(issue.detail, dict):
                node_id = issue.detail.get("node_id")
                if node_id:
                    if node_id not in self.validation_issues:
                        self.validation_issues[node_id] = []
                    self.validation_issues[node_id].append(issue)
        
        # 触发所有节点重绘,以显示验证警告
        for node_item in self.node_items.values():
            node_item.update()

