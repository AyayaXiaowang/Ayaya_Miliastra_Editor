"""跳转协调器 - 处理各种跳转和定位逻辑"""

from __future__ import annotations

from typing import Optional, Dict

from PyQt6 import QtCore

from app.common.graph_data_cache import resolve_graph_data
from app.models import UiNavigationRequest


class NavigationCoordinator(QtCore.QObject):
    """跳转和导航协调器"""
    
    # 信号定义
    navigate_to_mode = QtCore.pyqtSignal(str)  # mode_name
    select_template = QtCore.pyqtSignal(str)  # template_id
    select_instance = QtCore.pyqtSignal(str)  # instance_id
    select_level_entity = QtCore.pyqtSignal()
    open_graph = QtCore.pyqtSignal(str, dict, object)  # graph_id, graph_data, container
    focus_node = QtCore.pyqtSignal(str)  # node_id
    focus_edge = QtCore.pyqtSignal(str, str, str)  # src, dst, edge_id
    load_package = QtCore.pyqtSignal(str)  # package_id
    switch_to_editor = QtCore.pyqtSignal()
    open_player_editor = QtCore.pyqtSignal()  # 打开玩家编辑器
    # 新增：复合节点选择（按名称）
    select_composite_name = QtCore.pyqtSignal(str)
    switch_combat_tab = QtCore.pyqtSignal(int)  # 切换战斗预设标签
    
    def __init__(self, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        
        # 用于获取当前包和状态（由主窗口设置）
        self.get_current_package = None
        self.get_current_package_id = None

    # === 统一入口 ===

    def handle_request(self, request: UiNavigationRequest) -> None:
        """
        统一处理 UI 导航请求。

        设计目标：
        - 将“跳到哪个视图模式 + 选中哪个资源 + 是否需要打开图并定位节点/连线”
          的决策集中在一个入口，便于从单一文件读懂导航规则。
        - 具体分支仍保持现有领域划分（图任务 / 验证 / 管理 / 存档等），
          但都通过 UiNavigationRequest 传入上下文。
        """
        resource_kind = request.resource_kind

        if resource_kind in ("graph", "graph_task"):
            self._handle_graph_request(request)
            return

        if resource_kind in ("template", "instance", "level_entity"):
            self._handle_entity_request(request)
            return

        if resource_kind == "composite":
            self._handle_composite_request(request)
            return

        if resource_kind == "management_section":
            self._handle_management_request(request)
            return

        if resource_kind == "validation_issue":
            self._handle_validation_issue_request(request)
            return

        if resource_kind == "graph_preview":
            self._handle_graph_preview_request(request)
            return

        if resource_kind == "combat":
            self._handle_combat_request(request)
            return

        raise ValueError(f"未知的导航资源类型: {resource_kind}")

    # === 各资源类型处理 ===

    def _handle_graph_request(self, request: UiNavigationRequest) -> None:
        """处理节点图相关导航（含 Todo 步骤与图库/属性面板发起的跳转）。"""
        payload: Dict[str, object] = request.payload or {}
        detail_info = {}
        if isinstance(payload, dict) and "type" in payload:
            detail_info = payload  # Todo 步骤 / 预览上下文等

        detail_type = str(detail_info.get("type", ""))

        # Todo 场景：沿用原有 detail_info 解析规则
        if detail_type:
            self._handle_graph_todo_detail(detail_info)
            return

        # 非 Todo 场景：只打开图，不做特定节点/连线定位
        graph_id = request.graph_id or request.resource_id
        if not graph_id:
            return

        graph_data = resolve_graph_data(detail_info) if detail_info else None
        if graph_data is None:
            return

        container = None
        template_id = str(payload.get("template_id", "") or "")
        instance_id = str(payload.get("instance_id", "") or "")
        if template_id and self.get_current_package:
            current_package = self.get_current_package()
            if current_package:
                container = current_package.get_template(template_id)
        elif instance_id and self.get_current_package:
            current_package = self.get_current_package()
            if current_package:
                container = current_package.get_instance(instance_id)

        # 统一通过 open_graph → GraphEditorController.open_graph_for_editing →
        # switch_to_editor_requested 完成模式切换，避免在此处重复触发导航。
        self.open_graph.emit(graph_id, graph_data, container)

    def _handle_entity_request(self, request: UiNavigationRequest) -> None:
        """处理模板/实例/关卡实体的跳转（来自图属性、图库、存档库等）。"""
        entity_type = request.resource_kind
        entity_id = request.resource_id
        package_id = request.package_id

        if not entity_id:
            return

        # 若指定了目标存档且当前存档不同，先请求加载存档
        if package_id and self.get_current_package_id:
            current_package_id = self.get_current_package_id()
            if package_id != current_package_id:
                self.load_package.emit(package_id)

        if entity_type == "template":
            self.navigate_to_mode.emit("template")
            self.select_template.emit(entity_id)
        elif entity_type == "instance":
            self.navigate_to_mode.emit("placement")
            self.select_instance.emit(entity_id)
        elif entity_type == "level_entity":
            self.navigate_to_mode.emit("placement")
            self.select_level_entity.emit()

    def _handle_composite_request(self, request: UiNavigationRequest) -> None:
        """处理复合节点管理器相关的跳转。"""
        composite_name = request.resource_id or ""
        self.navigate_to_mode.emit("composite")
        if composite_name:
            QtCore.QTimer.singleShot(
                150,
                lambda: self.select_composite_name.emit(composite_name),
            )

    def _handle_management_request(self, request: UiNavigationRequest) -> None:
        """处理管理配置库相关的跳转。"""
        self.navigate_to_mode.emit("management")
        # 具体 section/item 选中由管理库页面与主窗口事件 Mixin 负责，
        # 这里仅切换模式，避免 NavigationCoordinator 反查 UI 结构。

    def _handle_validation_issue_request(self, request: UiNavigationRequest) -> None:
        """处理从验证面板发起的跳转请求。"""
        detail = request.payload or {}
        self._handle_validation_detail(detail)

    def _handle_combat_request(self, request: UiNavigationRequest) -> None:
        """处理战斗预设相关跳转（目前仅用于玩家编辑器入口）。"""
        self.navigate_to_mode.emit("combat")
        self.open_player_editor.emit()

    def _handle_graph_preview_request(self, request: UiNavigationRequest) -> None:
        """处理从只读预览视图发起的跳转（节点 / 连线聚焦）。"""
        # 预览场景下图已由 TodoPreviewPanel 负责加载，跳转只需切到编辑器并聚焦元素。
        self.switch_to_editor.emit()
        if request.desired_focus == "graph_node" and request.node_id:
            QtCore.QTimer.singleShot(
                100,
                lambda: self.focus_node.emit(request.node_id or ""),
            )
            return
        if (
            request.desired_focus == "graph_edge"
            and request.source_node_id
            and request.target_node_id
        ):
            QtCore.QTimer.singleShot(
                100,
                lambda: self.focus_edge.emit(
                    request.source_node_id or "",
                    request.target_node_id or "",
                    request.edge_id or "",
                ),
            )
            return
    
    def _handle_graph_todo_detail(self, detail_info: dict) -> None:
        """内部：处理来自 Todo 步骤的图相关导航逻辑。"""
        detail_type = detail_info.get("type", "")

        if detail_type in [
            "template_graph_root",
            "event_flow_root",
            "graph_create_node",
            "graph_config_node",
            "graph_config_node_merged",
            "graph_set_port_types_merged",
            "graph_connect",
            "graph_connect_merged",
            "graph_create_and_connect",
            "graph_create_and_connect_reverse",
            # 动态端口添加类
            "graph_add_variadic_inputs",
            "graph_add_dict_pairs",
            "graph_add_branch_outputs",
            # 信号相关步骤：信号概览 / 为节点绑定信号
            "graph_signals_overview",
            "graph_bind_signal",
        ]:
            graph_id = detail_info.get("graph_id")
            graph_data = resolve_graph_data(detail_info)
            template_id = detail_info.get("template_id")
            instance_id = detail_info.get("instance_id")

            container = None
            if template_id:
                self.navigate_to_mode.emit("template")
                self.select_template.emit(template_id)
                if self.get_current_package:
                    current_package = self.get_current_package()
                    container = current_package.get_template(template_id) if current_package else None
            elif instance_id:
                self.navigate_to_mode.emit("placement")
                self.select_instance.emit(instance_id)
                if self.get_current_package:
                    current_package = self.get_current_package()
                    container = current_package.get_instance(instance_id) if current_package else None

            if graph_id and graph_data:
                self.open_graph.emit(graph_id, graph_data, container)
                QtCore.QTimer.singleShot(
                    200,
                    lambda: self._locate_graph_element(detail_info),
                )
            else:
                if template_id and graph_id and self.get_current_package:
                    current_package = self.get_current_package()
                    template = current_package.get_template(template_id) if current_package else None
                    if template and graph_id in template.default_graphs:
                        self.open_graph.emit(graph_id, template.default_graphs[graph_id], template)
                        QtCore.QTimer.singleShot(
                            200,
                            lambda: self._locate_graph_element(detail_info),
                        )

        elif detail_type.startswith("template"):
            template_id = detail_info.get("template_id")
            if template_id:
                self.navigate_to_mode.emit("template")
                self.select_template.emit(template_id)

        elif detail_type.startswith("instance"):
            instance_id = detail_info.get("instance_id")
            if instance_id:
                self.navigate_to_mode.emit("placement")
                self.select_instance.emit(instance_id)

        elif detail_type.startswith("composite_"):
            composite_name = detail_info.get("composite_name", "")
            self.navigate_to_mode.emit("composite")
            if composite_name:
                QtCore.QTimer.singleShot(
                    150,
                    lambda: self.select_composite_name.emit(composite_name),
                )

        elif detail_type.startswith("combat"):
            self.navigate_to_mode.emit("combat")

        elif detail_type.startswith("management"):
            self.navigate_to_mode.emit("management")

    def _locate_graph_element(self, detail_info: dict) -> None:
        """在节点图编辑器中定位到具体元素"""
        detail_type = detail_info.get("type", "")
        
        if detail_type == "graph_create_node" or detail_type == "graph_config_node" or detail_type == "graph_config_node_merged" or detail_type == "graph_set_port_types_merged" \
           or detail_type == "graph_add_variadic_inputs" or detail_type == "graph_add_dict_pairs" or detail_type == "graph_add_branch_outputs" \
           or detail_type == "graph_bind_signal":
            # 定位到节点
            node_id = detail_info.get("node_id")
            if node_id:
                self.focus_node.emit(node_id)
        
        elif detail_type == "graph_connect":
            # 定位到连线
            edge_id = detail_info.get("edge_id")
            src_node = detail_info.get("src_node")
            dst_node = detail_info.get("dst_node")
            if src_node and dst_node:
                self.focus_edge.emit(src_node, dst_node, edge_id or "")
    
    def _handle_validation_detail(self, detail: Dict[str, object]) -> None:
        """内部：处理从验证结果面板传入的 detail。"""
        if not detail:
            return

        issue_type = detail.get("type", "")

        if issue_type == "template":
            template_id = detail.get("template_id")
            if template_id:
                if self.get_current_package:
                    current_package = self.get_current_package()
                    if current_package and template_id in current_package.templates:
                        self.navigate_to_mode.emit("template")
                        self.select_template.emit(str(template_id))

        elif issue_type == "instance":
            instance_id = detail.get("instance_id")
            if instance_id:
                if self.get_current_package:
                    current_package = self.get_current_package()
                    if current_package and instance_id in current_package.instances:
                        self.navigate_to_mode.emit("placement")
                        self.select_instance.emit(str(instance_id))

        elif issue_type == "level_entity":
            self.navigate_to_mode.emit("placement")
            self.select_level_entity.emit()

