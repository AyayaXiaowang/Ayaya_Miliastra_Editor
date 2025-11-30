"""自动排版控制器

负责节点图的自动排版逻辑（验证、克隆布局、差异合并、同步）。
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from engine.graph import validate_graph
from engine.validate import validate_files

if TYPE_CHECKING:
    from ui.graph.graph_view import GraphView


class AutoLayoutController:
    """自动排版控制器
    
    管理自动排版的完整流程：
    1. 排版前回调（可选重载）
    2. 验证节点图
    3. 克隆模型并执行就地布局
    4. 差异合并（新增/删除节点与连线）
    5. 同步坐标与基本块
    6. 更新图形项
    7. 排版完成回调
    """
    
    _workspace_path = Path(__file__).resolve().parents[5]

    @classmethod
    def run(cls, view: "GraphView") -> None:
        """执行自动排版"""
        # 检查是否有场景
        if not view.scene():
            return
        
        # 排版前回调（例如：按当前设置强制重载 .py → 模型，清理旧副本/缓存）
        if getattr(view, 'on_before_auto_layout', None):
            view.on_before_auto_layout()
        
        # 如果是复合节点编辑器，构建虚拟引脚映射
        virtual_pin_mappings = {}
        scene = view.scene()
        if hasattr(scene, 'is_composite_editor') and scene.is_composite_editor:
            composite_id = scene.composite_edit_context.get('composite_id')
            manager = scene.composite_edit_context.get('manager')
            if composite_id and manager:
                composite = manager.get_composite_node(composite_id)
                if composite:
                    for vpin in composite.virtual_pins:
                        for mapped_port in vpin.mapped_ports:
                            virtual_pin_mappings[(mapped_port.node_id, mapped_port.port_name)] = mapped_port.is_input
        
        errors = cls._collect_validation_errors(view, virtual_pin_mappings)
        
        if errors:
            # 有错误，输出到控制台而不是弹窗；受 GRAPH_UI_VERBOSE 控制
            from engine.configs.settings import settings as _settings_ui

            if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
                print("\n" + "=" * 80)
                print("【自动布局】节点图存在错误，无法自动排版")
                print("=" * 80)
                for error in errors:
                    print(f"  • {error}")
                print("=" * 80 + "\n")
            return
        
        # 没有错误，执行自动排版（基于克隆就地布局 + 差异合并）

        # 在回填坐标前：与“增强版”布局结果进行双向同步（新增与删除）
        # 统一策略：通过引擎 LayoutService 获取增强后的克隆模型（含跨块复制/清理），随后用“差异合并”同步到当前模型。
        from engine.layout import LayoutService
        model_node_ids_before = set(view.scene().model.nodes.keys())
        model_edge_ids_before = set(view.scene().model.edges.keys())
        scene_obj = view.scene()
        node_lib = getattr(scene_obj, "node_library", None) if scene_obj is not None else None
        result = LayoutService.compute_layout(view.scene().model, node_library=node_lib, include_augmented_model=True)
        _augmented = getattr(result, "augmented_model", None)
        if _augmented is None:
            return
        augmented_node_ids = set(_augmented.nodes.keys())
        augmented_edge_ids = set(_augmented.edges.keys())
        
        # 合并新增节点（例如：跨块复制产生的副本）
        nodes_to_add = augmented_node_ids - model_node_ids_before
        for nid in nodes_to_add:
            view.scene().model.nodes[nid] = _augmented.nodes[nid]
        
        # 合并新增连线（例如：副本→副本 或 副本→目标 的新边）
        edges_to_add = augmented_edge_ids - model_edge_ids_before
        for eid in edges_to_add:
            view.scene().model.edges[eid] = _augmented.edges[eid]
        
        # 删除在就地布局中被移除的旧连线（例如：应当被替换/去重的原始跨块边）
        edges_to_remove = model_edge_ids_before - augmented_edge_ids
        if edges_to_remove:
            for eid in list(edges_to_remove):
                # 先移除场景图形项
                edge_item = view.scene().edge_items.pop(eid, None)
                if edge_item:
                    view.scene().removeItem(edge_item)
                # 再移除模型中的边
                view.scene().model.edges.pop(eid, None)
        
        # 删除在就地布局中被清理掉的孤立副本节点（仅删除副本节点，避免误删用户节点）
        nodes_to_remove = model_node_ids_before - augmented_node_ids
        for nid in list(nodes_to_remove):
            node_obj = view.scene().model.nodes.get(nid)
            if node_obj and getattr(node_obj, "is_data_node_copy", False):
                # 先删除与之相关的边的图形项与模型记录
                to_del_edge_ids = [eid for eid, e in view.scene().model.edges.items() if e.src_node == nid or e.dst_node == nid]
                for eid in to_del_edge_ids:
                    edge_item = view.scene().edge_items.pop(eid, None)
                    if edge_item:
                        view.scene().removeItem(edge_item)
                    view.scene().model.edges.pop(eid, None)
                # 移除节点图形项
                node_item = view.scene().node_items.pop(nid, None)
                if node_item:
                    view.scene().removeItem(node_item)
                # 移除节点本身
                view.scene().model.nodes.pop(nid, None)

        # 将坐标与基本块回填到模型（坐标来源统一使用 _augmented，确保与合并来源一致）
        positions_from_augmented = {nid: tuple(node.pos) for nid, node in _augmented.nodes.items()}
        for node_id, pos_tuple in positions_from_augmented.items():
            if node_id in view.scene().model.nodes:
                view.scene().model.nodes[node_id].pos = (float(pos_tuple[0]), float(pos_tuple[1]))
        # 基本块同样来自 _augmented，避免首次点击时坐标/块集合不一致
        view.scene().model.basic_blocks = list(getattr(result, "basic_blocks", None) or _augmented.basic_blocks or [])
        # 回填布局Y调试信息（来自 _augmented）
        debug_map_aug = getattr(_augmented, "_layout_y_debug_info", {}) or {}
        if debug_map_aug:
            setattr(view.scene().model, "_layout_y_debug_info", dict(debug_map_aug))

        # 检查是否有新节点（如副本节点）需要添加到场景
        model_node_ids = set(view.scene().model.nodes.keys())
        scene_node_ids = set(view.scene().node_items.keys())
        new_node_ids = model_node_ids - scene_node_ids
        
        if new_node_ids:
            # 添加新节点（如跨块复制产生的副本）到场景
            for node_id in new_node_ids:
                node = view.scene().model.nodes[node_id]
                view.scene().add_node_item(node)
            
            # 检查是否有新边需要添加（连接副本的边）
            model_edge_ids = set(view.scene().model.edges.keys())
            scene_edge_ids = set(view.scene().edge_items.keys())
            new_edge_ids = model_edge_ids - scene_edge_ids
            
            for edge_id in new_edge_ids:
                edge = view.scene().model.edges[edge_id]
                view.scene().add_edge_item(edge)

        # 同步模型位置到图形项（包括新添加的）
        for node_id, node_item in view.scene().node_items.items():
            if node_id in view.scene().model.nodes:
                model_pos = view.scene().model.nodes[node_id].pos
                node_item.setPos(model_pos[0], model_pos[1])
        
        # 更新所有连线
        for edge_item in list(view.scene().edge_items.values()):
            edge_item.update_path()
        
        # 触发场景重绘以显示基本块
        view.scene().update()
        # 通知外部：自动排版已完成
        if getattr(view, 'on_auto_layout_completed', None):
            view.on_auto_layout_completed()

    @classmethod
    def _collect_validation_errors(
        cls,
        view: "GraphView",
        virtual_pin_mappings: dict[tuple[str, str], bool],
    ) -> list[str]:
        scene = view.scene()
        if scene is None:
            return []
        model = getattr(scene, "model", None)
        if model is None:
            return []
        source_path = cls._resolve_source_file(model) if not virtual_pin_mappings else None
        if source_path:
            report = validate_files([source_path], cls._workspace_path)
            return [issue.message for issue in report.issues if issue.level == "error"]
        return validate_graph(model, virtual_pin_mappings)

    @classmethod
    def _resolve_source_file(cls, model) -> Path | None:
        metadata = getattr(model, "metadata", None) or {}
        source_rel = metadata.get("source_file")
        if not source_rel:
            return None
        candidate = Path(source_rel)
        if not candidate.is_absolute():
            candidate = cls._workspace_path / candidate
        return candidate if candidate.exists() else None

