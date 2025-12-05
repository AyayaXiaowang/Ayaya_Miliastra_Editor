"""节点图编辑控制器 - 管理节点图的编辑逻辑"""

from __future__ import annotations

from typing import Optional
from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from engine.graph.models.graph_model import GraphModel
from engine.graph.models.graph_config import GraphConfig
from engine.layout import layout_by_event_regions
from engine.resources.resource_manager import ResourceManager, ResourceType
from engine.signal import compute_signal_schema_hash
from engine.graph.common import (
    SIGNAL_SEND_NODE_TITLE,
    SIGNAL_LISTEN_NODE_TITLE,
    SIGNAL_SEND_STATIC_INPUTS,
    SIGNAL_LISTEN_STATIC_OUTPUTS,
)
from ui.graph.graph_undo import AddNodeCommand
from engine.nodes.node_definition_loader import NodeDef
from ui.graph.graph_scene import GraphScene
from ui.graph.graph_view import GraphView
from ui.graph.scene_builder import populate_scene_from_model
from ui.controllers.graph_error_tracker import get_instance as get_error_tracker
from ui.foundation import dialog_utils
from app.common.graph_data_cache import drop_graph_data_for_graph


class GraphEditorController(QtCore.QObject):
    """节点图编辑管理控制器"""
    
    # 信号定义
    graph_loaded = QtCore.pyqtSignal(str)  # graph_id
    graph_saved = QtCore.pyqtSignal(str)  # graph_id
    graph_validated = QtCore.pyqtSignal(list)  # issues
    validation_triggered = QtCore.pyqtSignal()
    switch_to_editor_requested = QtCore.pyqtSignal()  # 切换到编辑页面
    title_update_requested = QtCore.pyqtSignal(str)  # 更新窗口标题
    save_status_changed = QtCore.pyqtSignal(str)  # "saved" | "unsaved" | "saving"
    
    def __init__(
        self,
        resource_manager: ResourceManager,
        model: GraphModel,
        scene: GraphScene,
        view: GraphView,
        node_library: dict,
        parent: Optional[QtCore.QObject] = None
    ):
        super().__init__(parent)
        
        self.resource_manager = resource_manager
        self.model = model
        self.scene = scene
        self.view = view
        self.node_library = node_library
        # 额外场景参数（例如复合节点编辑上下文）
        self._scene_extra_options: dict = {}
        
        # 当前节点图状态
        self.current_graph_id: Optional[str] = None
        self.current_graph_container = None  # 存储当前编辑的对象（template或instance）
        self.last_saved_hash: Optional[str] = None  # 上次保存的内容哈希
        # 逻辑只读模式：开启后UI不允许编辑逻辑，保存仅更新变量/元数据
        self.logic_read_only: bool = True
        
        # 用于获取存档（由主窗口设置）
        self.get_current_package = None
        self.get_property_panel_object_type = None
        
        # 错误跟踪器（单例）
        self.error_tracker = get_error_tracker()
        # 自动保存防抖计时器（根据全局设置控制）
        self._save_debounce_timer: Optional[QtCore.QTimer] = None
        # 下次自动排版前是否强制从 .py 重新解析（忽略持久化缓存）
        self._force_reparse_on_next_auto_layout: bool = False

    def schedule_reparse_on_next_auto_layout(self) -> None:
        """安排在下一次自动排版前强制从 .py 重新解析当前图（忽略持久化缓存）。"""
        self._force_reparse_on_next_auto_layout = True

    # ===== 信号 schema 版本控制：仅在版本不一致时刷新信号端口 =====

    def _maybe_sync_signals_for_model(self) -> None:
        """在图加载后按需根据信号定义刷新信号节点端口。

        - 若当前上下文无法获取包视图，则退回到旧行为：始终刷新一次信号端口；
        - 若可获取 `{signal_id: SignalConfig}` 字典，则基于 compute_signal_schema_hash
          计算当前 schema 版本；
          · 若 GraphModel.metadata 中未记录或版本不一致，则执行一次端口同步；
          · 若版本一致但检测到“旧缓存缺少参数端口”，同样强制执行一次端口同步，
            防止早期版本写入的 graph_cache 避开了新的动态端口补全逻辑。
        """
        scene = self.scene
        model = self.model
        if scene is None or model is None:
            return

        # 未注入 current_package 获取回调时，保持旧行为，避免影响只读预览等场景。
        get_current_package = getattr(self, "get_current_package", None)
        if not callable(get_current_package):
            scene._on_signals_updated_from_manager()  # type: ignore[call-arg]
            return

        current_package = get_current_package()
        if current_package is None:
            scene._on_signals_updated_from_manager()  # type: ignore[call-arg]
            return

        signals_dict = getattr(current_package, "signals", None)
        if not isinstance(signals_dict, dict):
            scene._on_signals_updated_from_manager()  # type: ignore[call-arg]
            return

        current_hash = compute_signal_schema_hash(signals_dict)
        metadata = model.metadata or {}
        last_hash_value = metadata.get("signal_schema_hash")

        # 当 schema 哈希已一致时，额外检查一次发送/监听信号节点是否已具备
        # 当前信号定义声明的全部参数端口；若发现缺失，视为旧缓存并强制重同步。
        need_force_resync: bool = False
        if isinstance(last_hash_value, str) and last_hash_value == current_hash:
            bindings = model.get_signal_bindings()

            for node_id, node in model.nodes.items():
                node_title = getattr(node, "title", "") or ""
                if node_title not in (SIGNAL_SEND_NODE_TITLE, SIGNAL_LISTEN_NODE_TITLE):
                    continue

                binding_info = bindings.get(str(node_id)) or {}
                signal_id_value = binding_info.get("signal_id")
                if not isinstance(signal_id_value, str) or not signal_id_value:
                    continue

                signal_config = signals_dict.get(signal_id_value)
                if signal_config is None:
                    continue

                parameters = getattr(signal_config, "parameters", []) or []
                param_names: list[str] = []
                for param in parameters:
                    name_value = getattr(param, "name", "")
                    if isinstance(name_value, str) and name_value:
                        param_names.append(name_value)
                if not param_names:
                    continue

                if node_title == SIGNAL_SEND_NODE_TITLE:
                    static_inputs = set(SIGNAL_SEND_STATIC_INPUTS)
                    existing_names = {
                        str(getattr(port, "name", ""))
                        for port in (getattr(node, "inputs", []) or [])
                        if hasattr(port, "name")
                    }
                else:
                    static_inputs = set(SIGNAL_LISTEN_STATIC_OUTPUTS)
                    existing_names = {
                        str(getattr(port, "name", ""))
                        for port in (getattr(node, "outputs", []) or [])
                        if hasattr(port, "name")
                    }

                for param_name in param_names:
                    if param_name in static_inputs:
                        continue
                    if param_name not in existing_names:
                        need_force_resync = True
                        break
                if need_force_resync:
                    break

            if not need_force_resync:
                # 当前图已经对齐到这一版信号定义，且端口结构完整，直接使用现有模型。
                return

        # schema 版本缺失、不一致，或检测到旧缓存缺少参数端口：
        # 执行一次端口同步，然后记录最新版本哈希。
        scene._on_signals_updated_from_manager()  # type: ignore[call-arg]
        metadata["signal_schema_hash"] = current_hash
        model.metadata = metadata

    def prepare_for_auto_layout(self) -> None:
        """在自动排版前按需（一次性标记）重建模型：清缓存→从 .py 解析→替换到场景。
        
        说明：
        - 默认不重载，避免打断当前视图缩放/中心导致“居中偏移”的体验问题。
        - 当设置页面触发一次性标记（例如 DATA_NODE_CROSS_BLOCK_COPY 从 True→False）时，
          才进行清缓存与重载；重载前后会保存并恢复视图缩放与中心点，保持画面稳定。
        """
        if not self.current_graph_id:
            self._force_reparse_on_next_auto_layout = False
            return
        
        # 仅当被安排“下一次自动排版前强制重解析”时才执行重载
        should_reparse = bool(self._force_reparse_on_next_auto_layout)
        if not should_reparse:
            return
        
        # 保存当前视图的缩放与中心（场景坐标系下的中心点）
        prev_center_scene = None
        prev_scale = 1.0
        if self.view is not None:
            viewport_center = self.view.viewport().rect().center()
            prev_center_scene = self.view.mapToScene(viewport_center)
            prev_scale = self.view.transform().m11()
        
        # 清除该图的内存与持久化缓存，使后续加载直接解析 .py
        self.resource_manager.clear_cache(ResourceType.GRAPH, self.current_graph_id)
        self.resource_manager.clear_persistent_graph_cache_for(self.current_graph_id)
        
        # 重新加载并替换到场景（使用解析结果中的 data 字段）
        fresh = self.resource_manager.load_resource(ResourceType.GRAPH, self.current_graph_id)
        if fresh and isinstance(fresh, dict):
            graph_data = fresh.get("data") or {}
            if graph_data:
                self.load_graph(self.current_graph_id, graph_data, container=self.current_graph_container)
        
        # 恢复视图缩放与中心，避免用户视角跳变
        if self.view is not None and prev_center_scene is not None:
            self.view.resetTransform()
            self.view.scale(float(prev_scale), float(prev_scale))
            self.view.centerOn(prev_center_scene)
        
        # 清除一次性标记
        self._force_reparse_on_next_auto_layout = False

    def load_graph_for_composite(
        self,
        composite_id: str,
        graph_data: dict,
        *,
        composite_edit_context: dict,
    ) -> None:
        """加载复合节点子图到编辑器（含预排版与复合上下文注入）。

        设计目标：
        - 由控制器统一负责对子图做一次事件区域预排版（layout_by_event_regions）；
        - 将复合节点专用的 composite_edit_context 通过 scene_extra_options 注入 GraphScene；
        - UI 层仅关心“当前选中的复合节点 ID 与其子图数据”，不再手动构造场景与批量 add_node/add_edge。
        """
        if not graph_data:
            raise ValueError("复合节点子图数据为空")
        if not isinstance(graph_data, dict):
            raise ValueError(f"复合节点子图数据类型错误: {type(graph_data)}")

        # 1) 在当前进程内对复合节点子图做一次事件区域预排版（不落盘，仅调整位置语义）。
        pre_layout_model = GraphModel.deserialize(graph_data)
        layout_by_event_regions(pre_layout_model)
        layouted_graph_data = pre_layout_model.serialize()

        # 2) 注入复合节点编辑上下文：由 GraphScene 消费，用于端口同步与虚拟引脚回调。
        merged_options: dict = dict(self._scene_extra_options) if self._scene_extra_options else {}
        merged_options["composite_edit_context"] = dict(composite_edit_context or {})
        self.set_scene_extra_options(merged_options)

        # 3) 复用通用 load_graph 流程，确保布局/场景装配/小地图等行为与普通图一致。
        effective_graph_id = composite_id or "composite_graph"
        self.load_graph(effective_graph_id, layouted_graph_data, container=None)

    def load_graph(self, graph_id: str, graph_data: dict, container=None) -> None:
        """加载节点图
        
        Args:
            graph_id: 节点图ID
            graph_data: 节点图数据
            container: 容器对象（模板或实例）
        """
        print(f"[加载] 开始加载节点图: {graph_id}")
        
        # 1. 验证数据完整性
        if not graph_data:
            raise ValueError("节点图数据为空")
        
        if not isinstance(graph_data, dict):
            raise ValueError(f"节点图数据类型错误: {type(graph_data)}")
        
        # 2. 清空场景并反序列化模型
        self.scene.clear()
        self.model = GraphModel.deserialize(graph_data)
        
        # 3. 同步复合节点的端口定义（确保使用最新的虚拟引脚定义）
        if self.node_library:
            updated_count = self.model.sync_composite_nodes_from_library(self.node_library)
            if updated_count > 0:
                print(f"[加载] 同步了 {updated_count} 个复合节点的端口定义")
        
        # 3.1 加载编辑器时，直接使用引擎层已计算好的布局结果（含跨块复制与副本清理），
        #     不在 UI 层重复执行布局，避免“第二次布局”带来的副本残留或视图与缓存不一致。
        #     若需要重新排版，由视图层的“自动排版”按钮统一走 AutoLayoutController 流程。
        
        # 4. 创建新的场景
        # 允许交互：即使处于逻辑只读模式，也开放场景交互（拖拽/连线/增删）
        # 基础的信号编辑上下文始终注入，复合节点等场景可通过 _scene_extra_options 覆盖/扩展。
        signal_edit_context = {
            "get_current_package": self.get_current_package,
            "main_window": self.parent(),
        }
        scene_options = dict(self._scene_extra_options) if self._scene_extra_options else {}
        scene_options["signal_edit_context"] = signal_edit_context

        self.scene = GraphScene(
            self.model,
            read_only=False,
            node_library=self.node_library,
            **scene_options,
        )
        
        # 5. 设置自动保存回调
        self.scene.undo_manager.on_change_callback = self._on_graph_modified
        self.scene.on_data_changed = self._on_graph_modified
        
        # 6. 设置视图
        self.view.setScene(self.scene)
        self.view.node_library = self.node_library
        # 根据图元数据设置当前作用域（server/client），用于“添加节点”菜单过滤
        scope = (self.model.metadata or {}).get("graph_type", "server")
        if scope in ("server", "client"):
            self.view.current_scope = scope
        # 允许交互：视图非只读，并恢复添加节点入口
        self.view.read_only = False
        self.view.on_add_node_callback = self.add_node_at_position
        
        # 7. 添加节点和连线到场景（批量插入优化）
        # 在批量构建期间禁用视图更新/场景信号与索引，减少卡顿
        self.view.setUpdatesEnabled(False)
        old_on_change_cb = self.scene.undo_manager.on_change_callback
        old_on_data_changed = self.scene.on_data_changed
        self.scene.undo_manager.on_change_callback = None
        self.scene.on_data_changed = None
        self.scene.setItemIndexMethod(QtWidgets.QGraphicsScene.ItemIndexMethod.NoIndex)
        populate_scene_from_model(self.scene, enable_batch_mode=True)

        # 在批量装配完成后，仅当“信号 schema 版本”与当前包不一致时，才根据信号定义
        # 为“发送信号/监听信号”节点补全参数端口，避免在信号未变更时重复扰动端口结构。
        if hasattr(self.scene, "_on_signals_updated_from_manager"):
            self._maybe_sync_signals_for_model()

        # 恢复索引/信号并强制刷新（并确保小地图可见）
        self.scene.setItemIndexMethod(QtWidgets.QGraphicsScene.ItemIndexMethod.BspTreeIndex)
        self.scene.undo_manager.on_change_callback = old_on_change_cb
        self.scene.on_data_changed = old_on_data_changed
        self.view.setUpdatesEnabled(True)
        self.view.viewport().update()
        # 小地图在批量构建期间可能未及时绘制，这里显式刷新与置顶
        if hasattr(self.view, 'mini_map') and self.view.mini_map:
            from ui.graph.graph_view.assembly.view_assembly import ViewAssembly
            ViewAssembly.update_mini_map_position(self.view)
            self.view.mini_map.show()
            self.view.mini_map.raise_()
        
        # 8. 更新当前图状态
        self.current_graph_id = graph_id
        self.current_graph_container = container
        
        # 9. 初始化内容哈希（加载后的初始状态视为已保存）
        self.last_saved_hash = self.model.get_content_hash()
        self.save_status_changed.emit("saved")
        
        from engine.configs.settings import settings as _settings_ui
        if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
            print(f"[加载] 完成，加载了 {len(self.scene.node_items)} 个节点")
        
        # 10. 加载完成后清除错误状态（如果有的话）
        self.error_tracker.clear_error(graph_id)
        
        # 11. 加载完成后触发验证（只读模式下不做UI验证）
        if not self.logic_read_only:
            self.validate_current_graph()
        
        # 12. 发送加载完成信号
        self.graph_loaded.emit(graph_id)
    
    def save_current_graph(self) -> None:
        """保存当前节点图（仅当内容变化时）
        
        统一保存入口：所有节点图保存必须通过此方法
        - 保存前：验证数据完整性
        - 保存中：序列化并生成代码
        - 保存后：验证结果并更新UI
        """
        if not self.current_graph_id:
            return
        
        # 计算当前内容哈希（不含位置信息）
        current_hash = self.model.get_content_hash()
        if current_hash == self.last_saved_hash:
            return
        
        current_graph_data = self.model.serialize()
        if not current_graph_data.get("graph_id") or not current_graph_data.get("graph_name"):
            print(f"⚠️  [保存] 数据不完整，取消保存: graph_id={current_graph_data.get('graph_id')}, graph_name={current_graph_data.get('graph_name')}")
            return
        
        # 只读模式：不对磁盘上的节点图做任何写入，仅更新内部“已保存”状态
        if self.logic_read_only:
            print(f"[保存] 逻辑只读模式，跳过写入磁盘: {self.current_graph_id}")
            # 把当前内存快照视为“已保存”，用于 is_dirty / 状态徽章 判断
            self.last_saved_hash = current_hash
            self.save_status_changed.emit("saved")
            return
        
        # 非只读：正常保存
        print(f"[保存] 检测到内容变化，开始保存: {self.current_graph_id}")
        self.save_status_changed.emit("saving")
        save_ok = self.resource_manager.save_resource(
            ResourceType.GRAPH,
            self.current_graph_id,
            current_graph_data
        )
        if not save_ok:
            error_message = f"节点图 '{current_graph_data.get('graph_name', self.current_graph_id)}' 无法通过验证，保存已取消。"
            print(f"❌ [保存] 保存被阻止: {self.current_graph_id}")
            print(f"   原因: 验证失败")
            self.save_status_changed.emit("unsaved")
            self.error_tracker.mark_error(
                self.current_graph_id,
                error_message,
                "validation_failed"
            )
            return
        saved_data = self.resource_manager.load_resource(ResourceType.GRAPH, self.current_graph_id)
        if not saved_data:
            error_message = "节点图保存后无法重新加载（文件系统错误）"
            print(f"❌ [保存] 保存失败，无法重新加载: {self.current_graph_id}")
            self.save_status_changed.emit("unsaved")
            self.error_tracker.mark_error(
                self.current_graph_id,
                error_message,
                "file_system_error"
            )
            return
        self.last_saved_hash = current_hash
        self.save_status_changed.emit("saved")
        print(f"✅ [保存] 完成: {self.current_graph_id}")
        self.error_tracker.clear_error(self.current_graph_id)
        self.validate_current_graph()
        self.graph_saved.emit(self.current_graph_id)
    
    def validate_current_graph(self) -> None:
        """验证当前编辑的节点图并更新UI显示"""
        if not self.get_current_package or not self.get_property_panel_object_type:
            return
        
        current_package = self.get_current_package()
        if not current_package or not self.current_graph_container:
            return
        
        # 获取当前节点图数据
        graph_data = self.model.serialize()
        
        # 确定实体类型
        object_type = self.get_property_panel_object_type()
        if object_type == "level_entity":
            entity_type = "关卡"
        elif object_type == "template":
            entity_type = self.current_graph_container.entity_type
        elif object_type == "instance":
            # 实例需要从模板获取类型
            template = current_package.get_template(self.current_graph_container.template_id)
            entity_type = template.entity_type if template else "未知"
        else:
            entity_type = "未知"
        
        # 执行验证（只验证当前图）
        from engine.validate.comprehensive_validator import ComprehensiveValidator
        validator = ComprehensiveValidator(current_package, self.resource_manager, verbose=False)
        
        # 通过公共方法调用引擎与现有规则，生成 UI 可用问题列表
        validator.issues = []  # 清空问题列表
        container_name = self.current_graph_container.name if hasattr(self.current_graph_container, 'name') else "当前对象"
        location = f"{container_name} > 节点图 '{self.current_graph_id}'"
        detail = {
            "type": object_type,
            "graph_name": self.current_graph_id
        }
        
        # 使用新入口：引擎结构校验 + 挂载/作用域/结构告警/端口一致性
        validator.validate_graph_for_ui(self.model, entity_type, location, detail)
        
        # 更新节点图UI的验证显示
        self.scene.update_validation(validator.issues)
        
        # 发送验证完成信号
        self.graph_validated.emit(validator.issues)
    
    def add_node_at_position(self, node_def: NodeDef, scene_pos: QtCore.QPointF) -> None:
        """添加节点"""
        print(f"[添加节点] 准备添加节点: {node_def.name}")
        print(f"[添加节点] 添加前Model中有 {len(self.model.nodes)} 个节点")
        
        node_id = self.model.gen_id("node")
        cmd = AddNodeCommand(
            self.model,
            self.scene,
            node_id,
            node_def.name,
            node_def.category,
            node_def.inputs,
            node_def.outputs,
            pos=(scene_pos.x(), scene_pos.y())
        )
        self.scene.undo_manager.execute_command(cmd)
        
        print(f"[添加节点] 添加后Model中有 {len(self.model.nodes)} 个节点")
        print(f"[添加节点] Scene.model中有 {len(self.scene.model.nodes)} 个节点")

    def _compute_logic_hash_from_data(self, data: dict) -> str:
        """计算仅包含逻辑结构（节点/连线/常量等，不含位置与变量）的哈希"""
        import json
        import hashlib
        nodes_part = [
            {
                "id": n.get("id"),
                "title": n.get("title"),
                "category": n.get("category"),
                "composite_id": n.get("composite_id"),
                "inputs": n.get("inputs", []),
                "outputs": n.get("outputs", []),
                "input_constants": n.get("input_constants", {}),
                "is_virtual_pin": n.get("is_virtual_pin"),
                "virtual_pin_index": n.get("virtual_pin_index"),
                "virtual_pin_type": n.get("virtual_pin_type"),
                "is_virtual_pin_input": n.get("is_virtual_pin_input"),
                "custom_var_names": n.get("custom_var_names"),
                "custom_comment": n.get("custom_comment"),
                "inline_comment": n.get("inline_comment"),
            }
            for n in sorted(data.get("nodes", []), key=lambda x: x.get("id"))
        ]
        edges_part = [
            {
                "src_node": e.get("src_node"),
                "src_port": e.get("src_port"),
                "dst_node": e.get("dst_node"),
                "dst_port": e.get("dst_port"),
            }
            for e in sorted(data.get("edges", []), key=lambda x: x.get("id", ""))
        ]
        logic = {
            "nodes": nodes_part,
            "edges": edges_part,
        }
        content_str = json.dumps(logic, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(content_str.encode("utf-8")).hexdigest()

    def _compute_variables_hash_from_data(self, data: dict) -> str:
        """计算变量部分哈希"""
        import json
        import hashlib
        vars_part = data.get("graph_variables", [])
        content_str = json.dumps(vars_part, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(content_str.encode("utf-8")).hexdigest()
    
    def _show_save_error_dialog(self, title: str, message: str) -> None:
        """显示保存失败的错误对话框
        
        Args:
            title: 对话框标题
            message: 错误消息
        """
        parent_widget = self.view.window() if self.view is not None else None
        dialog_utils.show_error_dialog(parent_widget, title, message)
    
    def _on_graph_modified(self) -> None:
        """节点图被修改时的回调 - 触发自动保存"""
        # 标记为脏状态
        self.mark_as_dirty()
        # 变量编辑会通过属性面板显式调用保存；只读模式不在此处触发自动保存
        if not self.logic_read_only:
            # 基于全局设置的自动保存防抖（单位：秒；0 表示立即保存）
            from engine.configs.settings import settings as _settings
            interval_seconds = float(getattr(_settings, "AUTO_SAVE_INTERVAL", 0.0) or 0.0)
            if interval_seconds <= 0.0:
                self.save_current_graph()
                return
            # 延迟保存：合并短时间内的频繁修改
            if self._save_debounce_timer is None:
                self._save_debounce_timer = QtCore.QTimer(self)
                self._save_debounce_timer.setSingleShot(True)
                self._save_debounce_timer.timeout.connect(self.save_current_graph)
            # 重启计时器
            self._save_debounce_timer.start(int(interval_seconds * 1000))
    
    def mark_as_dirty(self) -> None:
        """标记节点图为未保存状态"""
        if self.is_dirty:
            return  # 已经是脏状态，不重复发送信号
        self.save_status_changed.emit("unsaved")
    
    def mark_as_saved(self) -> None:
        """标记节点图为已保存状态"""
        self.save_status_changed.emit("saved")
    
    @property
    def is_dirty(self) -> bool:
        """判断是否有未保存的修改"""
        if not self.current_graph_id or not self.last_saved_hash:
            return False
        current_hash = self.model.get_content_hash()
        return current_hash != self.last_saved_hash
    
    def open_graph_for_editing(self, graph_id: str, graph_data: dict, container=None) -> None:
        """打开节点图进行编辑（从属性面板触发）"""
        print(f"[EDITOR] open_graph_for_editing: graph_id={graph_id}, container={'Y' if container else 'N'}")
        # 保存当前节点图
        if self.current_graph_id and self.current_graph_container:
            self.save_current_graph()
        
        # 切换到节点图编辑页面
        self.switch_to_editor_requested.emit()
        print("[EDITOR] 已发出 switch_to_editor_requested 信号")
        
        # 加载节点图
        self.load_graph(graph_id, graph_data, container)
        print("[EDITOR] 已加载图数据到编辑视图")

        # 首次进入编辑视图后，自动适配全图到可视区域（延迟到下一帧，确保视口尺寸有效）
        QtCore.QTimer.singleShot(100, lambda: self.view and self.view.fit_all(use_animation=False))
    
    def open_independent_graph(self, graph_id: str, graph_data: dict, graph_name: str) -> None:
        """打开独立节点图（从节点图库触发）"""
        # 如目标与当前相同：直接切换到编辑器，避免重复装载
        if self.current_graph_id == graph_id:
            self.switch_to_editor_requested.emit()
            self.title_update_requested.emit(f"节点图: {graph_name}")
            QtCore.QTimer.singleShot(100, lambda: self.view and self.view.fit_all(use_animation=False))
            return
        
        # 保存当前节点图
        if self.current_graph_id and self.current_graph_container:
            self.save_current_graph()
        
        # 加载节点图配置
        graph_config = GraphConfig.deserialize(graph_data)
        
        # 切换到节点图编辑页面
        self.switch_to_editor_requested.emit()
        
        # 加载节点图数据（独立节点图没有容器）
        self.load_graph(graph_id, graph_config.data, container=None)
        
        # 切换进入编辑视图后，自动适配全图
        QtCore.QTimer.singleShot(100, lambda: self.view and self.view.fit_all(use_animation=False))
        
        # 更新窗口标题
        self.title_update_requested.emit(f"节点图: {graph_name}")
    
    def close_editor_session(self) -> None:
        """关闭当前节点图编辑会话并恢复空场景，用于清理缓存或强制返回列表。"""
        had_graph = bool(self.current_graph_id)
        if had_graph:
            self.save_current_graph()
        if self._save_debounce_timer and self._save_debounce_timer.isActive():
            self._save_debounce_timer.stop()
        if self.scene:
            self.scene.clear()
            if hasattr(self.scene, "node_items"):
                self.scene.node_items.clear()
            if hasattr(self.scene, "edge_items"):
                self.scene.edge_items.clear()
            if hasattr(self.scene, "undo_manager") and self.scene.undo_manager:
                self.scene.undo_manager.clear()
        self.model = GraphModel()
        self.scene = GraphScene(self.model, read_only=True, node_library=self.node_library)
        self.scene.undo_manager.on_change_callback = None
        self.scene.on_data_changed = None
        if self.view is not None:
            self.view.setScene(self.scene)
            self.view.read_only = True
            self.view.on_add_node_callback = None
            self.view.resetTransform()
            self.view.viewport().update()
        self.current_graph_id = None
        self.current_graph_container = None
        self.last_saved_hash = None
        self._force_reparse_on_next_auto_layout = False
        self.save_status_changed.emit("saved")
        self.title_update_requested.emit("节点图: 未打开")
    
    def refresh_persistent_cache_after_layout(self) -> None:
        """将当前模型写入持久化缓存（用于自动排版后覆盖缓存）。
        
        位置变化不落盘，但希望下次打开时直接使用最新位置，
        因此在自动排版完成后，将当前 GraphModel 序列化并写入 runtime/cache/graph_cache。
        """
        if not self.current_graph_id or not self.model:
            return
        graph_data = self.model.serialize()
        result_data = {
            "graph_id": self.current_graph_id,
            "name": graph_data.get("graph_name", self.current_graph_id),
            "graph_type": graph_data.get("metadata", {}).get("graph_type", "server"),
            "folder_path": graph_data.get("metadata", {}).get("folder_path", ""),
            "description": graph_data.get("description", ""),
            "data": graph_data,
            "metadata": {}
        }
        self.resource_manager.update_persistent_graph_cache(self.current_graph_id, result_data)
        print(f"[缓存] 已刷新持久化缓存（自动排版后）: {self.current_graph_id}")
        # 使任务清单等上下文中的图数据缓存失效，避免继续使用旧布局。
        drop_graph_data_for_graph(self.current_graph_id)
        parent_window = self.parent()
        if parent_window is not None and hasattr(parent_window, "todo_widget"):
            todo_widget = getattr(parent_window, "todo_widget")
            if todo_widget is not None and hasattr(todo_widget, "tree_manager"):
                tree_manager = getattr(todo_widget, "tree_manager")
                graph_support = getattr(tree_manager, "_graph_support", None)
                if graph_support is not None and hasattr(graph_support, "_graph_model_cache"):
                    model_cache = getattr(graph_support, "_graph_model_cache")
                    if isinstance(model_cache, dict) and self.current_graph_id in model_cache:
                        model_cache.pop(self.current_graph_id, None)
        # 自动排版完成后：在编辑视图中自动适配全图并居中显示
        if self.view is not None:
            QtCore.QTimer.singleShot(100, lambda: self.view and self.view.fit_all(use_animation=False))

    def get_current_model(self) -> GraphModel:
        """获取当前模型"""
        return self.model
    
    def get_current_scene(self) -> GraphScene:
        """获取当前场景"""
        return self.scene

    def set_scene_extra_options(self, options: dict) -> None:
        """设置场景额外参数（例如复合节点编辑上下文）
        
        Args:
            options: 传入 GraphScene 的关键字参数字典
        """
        self._scene_extra_options = options or {}

