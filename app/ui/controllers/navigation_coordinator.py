"""跳转协调器 - 处理各种跳转和定位逻辑"""

from __future__ import annotations

from typing import Optional, Dict, Callable

from PyQt6 import QtCore

from app.models import UiNavigationRequest
from app.models.todo_detail_info_accessors import get_detail_type, get_graph_id, get_node_id
from app.runtime.services.graph_data_service import GraphDataService, get_shared_graph_data_service


class _GraphDataLoadWorker(QtCore.QThread):
    """后台加载 graph_data（避免 UI 线程同步触发磁盘读取/解析）。"""

    succeeded = QtCore.pyqtSignal(int, str, object, str)  # request_id, graph_id, graph_data, cache_key
    failed = QtCore.pyqtSignal(int, str, str)  # request_id, graph_id, error_text

    def __init__(
        self,
        *,
        request_id: int,
        graph_id: str,
        graph_data_service: GraphDataService,
        cache_root_id: str,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.request_id = int(request_id)
        self.graph_id = str(graph_id or "")
        self.graph_data_service = graph_data_service
        self.cache_root_id = str(cache_root_id or "nav")
        self.setObjectName(f"NavGraphDataLoadWorker#{self.request_id}")

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        if not self.graph_id:
            self.failed.emit(self.request_id, self.graph_id, "graph_id 为空，无法加载节点图数据。")
            return
        service = self.graph_data_service
        if service is None:
            self.failed.emit(self.request_id, self.graph_id, "GraphDataService 不可用，无法加载节点图数据。")
            return

        graph_data = service.load_graph_data(self.graph_id)
        if self.isInterruptionRequested():
            return
        if not isinstance(graph_data, dict):
            error_text = service.get_graph_load_error(self.graph_id) or (
                f"节点图 '{self.graph_id}' 不存在或已被删除。"
            )
            self.failed.emit(self.request_id, self.graph_id, str(error_text))
            return

        cache_root_id = self.cache_root_id
        if not cache_root_id:
            cache_root_id = "nav"
        cache_key = service.store_payload_graph_data(cache_root_id, self.graph_id, graph_data)
        self.succeeded.emit(self.request_id, self.graph_id, graph_data, str(cache_key or ""))


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
    # 战斗预设：按资源类型选择条目（由主窗口负责联动右侧详情面板）
    select_player_template = QtCore.pyqtSignal(str)
    select_player_class = QtCore.pyqtSignal(str)
    select_skill = QtCore.pyqtSignal(str)
    # 新增：复合节点选择（按名称）
    select_composite_name = QtCore.pyqtSignal(str)
    # 新增：管理配置定位（section_key, item_id；item_id 允许为空表示仅切换 section）
    focus_management_section_and_item = QtCore.pyqtSignal(str, str)
    switch_combat_tab = QtCore.pyqtSignal(int)  # 切换战斗预设标签
    
    def __init__(self, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        
        # 用于获取当前包和状态（由主窗口设置）
        self.get_current_package = None
        self.get_current_package_id = None
        self.get_graph_data_service = None
        # 节点图加载（磁盘 IO/解析）异步化：避免 UI 线程同步触发超大图读取导致卡顿/卡死
        self._graph_open_request_id: int = 0
        self._graph_open_worker: Optional[_GraphDataLoadWorker] = None
        self._graph_open_inflight_graph_id: str = ""
        self._graph_open_expected_package_id: str = ""
        self._graph_open_pending: Optional[dict] = None

    def _resolve_graph_data_service(self) -> GraphDataService:
        getter = getattr(self, "get_graph_data_service", None)
        if callable(getter):
            service = getter()
            if service is not None:
                return service
        parent_obj = self.parent()
        resource_manager = getattr(parent_obj, "resource_manager", None) if parent_obj is not None else None
        package_index_manager = (
            getattr(parent_obj, "package_index_manager", None) if parent_obj is not None else None
        )
        return get_shared_graph_data_service(resource_manager, package_index_manager)

    def _cancel_pending_graph_open(self) -> None:
        worker = getattr(self, "_graph_open_worker", None)
        if worker is not None and worker.isRunning():
            worker.requestInterruption()
        self._graph_open_worker = None
        self._graph_open_inflight_graph_id = ""
        self._graph_open_expected_package_id = ""
        self._graph_open_pending = None

    def _open_graph_or_load_async(
        self,
        *,
        graph_id: str,
        detail_info: Optional[dict],
        container: object | None,
        after_open: Optional[Callable[[], None]] = None,
    ) -> None:
        graph_id_text = str(graph_id or "")
        if not graph_id_text:
            return

        graph_data_service = self._resolve_graph_data_service()

        # 先尝试走 payload cache（不触发磁盘加载）
        graph_data = (
            graph_data_service.resolve_payload_graph_data(detail_info) if isinstance(detail_info, dict) else None
        )
        if isinstance(graph_data, dict):
            self.open_graph.emit(graph_id_text, graph_data, container)
            if callable(after_open):
                after_open()
            return

        # 解析“预期 package_id”，用于防止切包后旧请求回调误打开
        expected_package_id = ""
        getter = getattr(self, "get_current_package_id", None)
        if callable(getter):
            expected_package_id = str(getter() or "")

        running_worker = getattr(self, "_graph_open_worker", None)
        if running_worker is not None and running_worker.isRunning():
            if str(getattr(self, "_graph_open_inflight_graph_id", "") or "") == graph_id_text:
                pending = getattr(self, "_graph_open_pending", None)
                if not isinstance(pending, dict):
                    pending = {}
                pending["detail_info"] = detail_info
                pending["container"] = container
                pending["after_open"] = after_open
                pending["expected_package_id"] = expected_package_id
                self._graph_open_pending = pending
                return
            self._cancel_pending_graph_open()

        self._graph_open_request_id = int(getattr(self, "_graph_open_request_id", 0)) + 1
        request_id = int(self._graph_open_request_id)
        self._graph_open_inflight_graph_id = graph_id_text
        self._graph_open_expected_package_id = expected_package_id
        self._graph_open_pending = {
            "detail_info": detail_info,
            "container": container,
            "after_open": after_open,
            "expected_package_id": expected_package_id,
        }

        worker = _GraphDataLoadWorker(
            request_id=request_id,
            graph_id=graph_id_text,
            graph_data_service=graph_data_service,
            cache_root_id="nav",
            parent=self,
        )
        self._graph_open_worker = worker

        def _on_succeeded(_rid: int, loaded_graph_id: str, graph_data_obj: object, cache_key: str) -> None:
            if int(_rid) != int(getattr(self, "_graph_open_request_id", 0)):
                return
            if str(loaded_graph_id or "") != str(graph_id_text or ""):
                return

            pending = getattr(self, "_graph_open_pending", None)
            if not isinstance(pending, dict):
                return

            expected_pid = str(pending.get("expected_package_id") or "")
            current_pid = ""
            getter = getattr(self, "get_current_package_id", None)
            if callable(getter):
                current_pid = str(getter() or "")
            if expected_pid and current_pid and expected_pid != current_pid:
                # 切包后丢弃旧请求
                self._cancel_pending_graph_open()
                return

            if not isinstance(graph_data_obj, dict):
                self._cancel_pending_graph_open()
                return

            # 可选：写回 cache_key（避免后续跳转重复触发加载）
            info_to_write_back = pending.get("detail_info")
            if isinstance(info_to_write_back, dict) and cache_key:
                info_to_write_back["graph_data_key"] = str(cache_key)
                info_to_write_back.pop("graph_data", None)

            container_obj = pending.get("container")
            after_open_cb = pending.get("after_open")

            self._graph_open_worker = None
            self._graph_open_pending = None
            self.open_graph.emit(graph_id_text, graph_data_obj, container_obj)
            if callable(after_open_cb):
                after_open_cb()

        def _on_failed(_rid: int, failed_graph_id: str, _error_text: str) -> None:
            if int(_rid) != int(getattr(self, "_graph_open_request_id", 0)):
                return
            if str(failed_graph_id or "") != str(graph_id_text or ""):
                return
            self._cancel_pending_graph_open()

        def _on_finished() -> None:
            # 兜底清理：异常退出时也不保留 inflight 状态
            if request_id != int(getattr(self, "_graph_open_request_id", 0)):
                return
            self._graph_open_worker = None
            self._graph_open_pending = None

        worker.succeeded.connect(_on_succeeded)
        worker.failed.connect(_on_failed)
        worker.finished.connect(_on_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

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

        # 新请求到来：取消旧的异步图加载，避免旧请求回调误打开
        self._cancel_pending_graph_open()

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

        if resource_kind in ("combat_player_template", "combat_player_class", "combat_skill"):
            self._handle_combat_preset_request(request)
            return

        raise ValueError(f"未知的导航资源类型: {resource_kind}")

    # === 各资源类型处理 ===

    def _handle_graph_request(self, request: UiNavigationRequest) -> None:
        """处理节点图相关导航（含 Todo 步骤与图库/属性面板发起的跳转）。"""
        payload: Dict[str, object] = request.payload or {}
        detail_info = payload if isinstance(payload, dict) else {}

        detail_type = get_detail_type(detail_info)

        # Todo 场景：沿用原有 detail_info 解析规则
        if detail_type:
            self._handle_graph_todo_detail(detail_info)
            return

        # 非 Todo 场景：只打开图，不做特定节点/连线定位
        graph_id = request.graph_id or request.resource_id
        if not graph_id:
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
        self._open_graph_or_load_async(
            graph_id=str(graph_id or ""),
            detail_info=detail_info if isinstance(detail_info, dict) else None,
            container=container,
            after_open=None,
        )

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
        section_key = request.management_section_key or request.resource_id or ""
        item_id = request.management_item_id or ""
        if section_key:
            QtCore.QTimer.singleShot(
                150,
                lambda: self.focus_management_section_and_item.emit(
                    str(section_key or ""), str(item_id or "")
                ),
            )

    def _handle_validation_issue_request(self, request: UiNavigationRequest) -> None:
        """处理从验证面板发起的跳转请求。"""
        detail = request.payload or {}
        self._handle_validation_detail(detail)

    def _handle_combat_request(self, request: UiNavigationRequest) -> None:
        """处理战斗预设相关跳转（目前仅用于玩家编辑器入口）。"""
        self.navigate_to_mode.emit("combat")
        self.open_player_editor.emit()

    def _handle_combat_preset_request(self, request: UiNavigationRequest) -> None:
        """处理战斗预设条目跳转（玩家模板 / 职业 / 技能）。"""
        resource_kind = request.resource_kind
        item_id = request.resource_id or ""
        package_id = request.package_id or ""
        if not item_id:
            return

        # 若指定了目标存档且当前存档不同，先请求加载存档
        if package_id and self.get_current_package_id:
            current_package_id = self.get_current_package_id()
            if package_id != current_package_id:
                self.load_package.emit(package_id)

        # 统一切到战斗预设模式；具体条目选中由主窗口回调处理（含 pending selection 机制）
        self.navigate_to_mode.emit("combat")

        if resource_kind == "combat_player_template":
            QtCore.QTimer.singleShot(150, lambda: self.select_player_template.emit(item_id))
            return
        if resource_kind == "combat_player_class":
            QtCore.QTimer.singleShot(150, lambda: self.select_player_class.emit(item_id))
            return
        if resource_kind == "combat_skill":
            QtCore.QTimer.singleShot(150, lambda: self.select_skill.emit(item_id))
            return

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
        detail_type = get_detail_type(detail_info)

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
            graph_id = get_graph_id(detail_info)
            template_id = detail_info.get("template_id")
            instance_id = detail_info.get("instance_id")

            container = None
            resolved_template = None
            if template_id:
                self.navigate_to_mode.emit("template")
                self.select_template.emit(template_id)
                if self.get_current_package:
                    current_package = self.get_current_package()
                    resolved_template = current_package.get_template(template_id) if current_package else None
                    container = resolved_template
            elif instance_id:
                self.navigate_to_mode.emit("placement")
                self.select_instance.emit(instance_id)
                if self.get_current_package:
                    current_package = self.get_current_package()
                    container = current_package.get_instance(instance_id) if current_package else None

            detail_snapshot = dict(detail_info or {})
            graph_data_fallback = None
            if resolved_template is not None and graph_id:
                default_graphs = getattr(resolved_template, "default_graphs", None)
                if isinstance(default_graphs, dict) and graph_id in default_graphs:
                    candidate = default_graphs.get(graph_id)
                    if isinstance(candidate, dict):
                        graph_data_fallback = candidate

            def _after_open() -> None:
                QtCore.QTimer.singleShot(200, lambda: self._locate_graph_element(detail_snapshot))

            if graph_id and isinstance(graph_data_fallback, dict):
                # 优先使用容器内存中的 default_graphs（不触发磁盘加载）
                self.open_graph.emit(graph_id, graph_data_fallback, resolved_template)
                _after_open()
                return

            if graph_id:
                self._open_graph_or_load_async(
                    graph_id=str(graph_id or ""),
                    detail_info=detail_info if isinstance(detail_info, dict) else None,
                    container=container,
                    after_open=_after_open,
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
        detail_type = get_detail_type(detail_info)
        
        if detail_type == "graph_create_node" or detail_type == "graph_config_node" or detail_type == "graph_config_node_merged" or detail_type == "graph_set_port_types_merged" \
           or detail_type == "graph_add_variadic_inputs" or detail_type == "graph_add_dict_pairs" or detail_type == "graph_add_branch_outputs" \
           or detail_type == "graph_bind_signal" or detail_type == "graph_bind_struct":
            # 定位到节点
            node_id = get_node_id(detail_info)
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

        issue_type = str(detail.get("type", "") or "")

        # 1) 若 detail 明确携带 management 定位信息，优先按显式 key 处理
        management_section_key = detail.get("management_section_key")
        management_item_id = detail.get("management_item_id")
        if isinstance(management_section_key, str) and management_section_key:
            self.navigate_to_mode.emit("management")
            QtCore.QTimer.singleShot(
                150,
                lambda: self.focus_management_section_and_item.emit(
                    str(management_section_key or ""), str(management_item_id or "")
                ),
            )
            return

        container_to_use: object | None = None

        if issue_type == "template":
            template_id = detail.get("template_id")
            if template_id:
                if self.get_current_package:
                    current_package = self.get_current_package()
                    if current_package and template_id in current_package.templates:
                        self.navigate_to_mode.emit("template")
                        self.select_template.emit(str(template_id))
                        container_to_use = current_package.get_template(str(template_id))

        elif issue_type == "instance":
            instance_id = detail.get("instance_id")
            if instance_id:
                if self.get_current_package:
                    current_package = self.get_current_package()
                    if current_package and instance_id in current_package.instances:
                        self.navigate_to_mode.emit("placement")
                        self.select_instance.emit(str(instance_id))
                        container_to_use = current_package.get_instance(str(instance_id))

        elif issue_type == "level_entity":
            self.navigate_to_mode.emit("placement")
            self.select_level_entity.emit()
            if self.get_current_package:
                current_package = self.get_current_package()
                container_to_use = getattr(current_package, "level_entity", None) if current_package else None

        elif issue_type == "attached_graph":
            owner_kind = str(detail.get("owner_kind", "") or "")
            owner_id = str(detail.get("owner_id", "") or "")
            if owner_kind == "template" and owner_id:
                self.navigate_to_mode.emit("template")
                self.select_template.emit(owner_id)
                if self.get_current_package:
                    current_package = self.get_current_package()
                    container_to_use = current_package.get_template(owner_id) if current_package else None
            elif owner_kind == "instance" and owner_id:
                self.navigate_to_mode.emit("placement")
                self.select_instance.emit(owner_id)
                if self.get_current_package:
                    current_package = self.get_current_package()
                    container_to_use = current_package.get_instance(owner_id) if current_package else None
            elif owner_kind == "level":
                self.navigate_to_mode.emit("placement")
                self.select_level_entity.emit()
                if self.get_current_package:
                    current_package = self.get_current_package()
                    container_to_use = getattr(current_package, "level_entity", None) if current_package else None

        elif issue_type == "package_graph_index":
            # 节点图索引声明但未挂载：直接打开图即可
            self._open_graph_from_validation_detail(detail, container=None)
            return

        elif issue_type == "graph":
            # 节点图源码校验/索引问题等：直接打开图（不强依赖容器）
            self._open_graph_from_validation_detail(detail, container=None)
            return

        elif issue_type == "composite_node":
            composite_name = str(detail.get("node_name", "") or "")
            self.navigate_to_mode.emit("composite")
            if composite_name:
                QtCore.QTimer.singleShot(
                    150,
                    lambda: self.select_composite_name.emit(composite_name),
                )
            return

        elif issue_type.startswith("management_"):
            # 兼容旧 detail：按类型映射到管理 section
            section_key = ""
            item_id = ""
            if issue_type == "management_ui_layout":
                section_key = "ui_control_groups"
                item_id = str(detail.get("layout_id", "") or "")
            elif issue_type == "management_level_variable":
                section_key = "variable"
                item_id = str(detail.get("variable_id", "") or "")
            if section_key:
                self.navigate_to_mode.emit("management")
                QtCore.QTimer.singleShot(
                    150,
                    lambda: self.focus_management_section_and_item.emit(section_key, item_id),
                )
            return

        # 2) 图定位：若 detail 携带 graph_id，则打开图并在需要时聚焦节点/连线
        self._open_graph_from_validation_detail(detail, container=container_to_use)

    def _open_graph_from_validation_detail(self, detail: Dict[str, object], *, container: object | None) -> None:
        graph_id_value = detail.get("graph_id") or detail.get("graph_id_value") or detail.get("resource_id")
        graph_id = str(graph_id_value or "")
        if not graph_id:
            return

        detail_snapshot = dict(detail or {})
        node_id = str(detail_snapshot.get("node_id") or "")
        edge_id = str(detail_snapshot.get("edge_id") or "")
        src_node = str(
            detail_snapshot.get("src_node")
            or detail_snapshot.get("source_node_id")
            or detail_snapshot.get("src_node_id")
            or ""
        )
        dst_node = str(
            detail_snapshot.get("dst_node")
            or detail_snapshot.get("target_node_id")
            or detail_snapshot.get("dst_node_id")
            or ""
        )

        def _after_open() -> None:
            if node_id:
                QtCore.QTimer.singleShot(200, lambda: self.focus_node.emit(node_id))
                return
            if src_node and dst_node:
                QtCore.QTimer.singleShot(200, lambda: self.focus_edge.emit(src_node, dst_node, edge_id))

        # 注意：open_graph 会统一触发切换到编辑器模式（由 GraphEditorController 发出信号），
        # 这里不额外 emit navigate_to_mode，避免重复切换。
        self._open_graph_or_load_async(
            graph_id=str(graph_id or ""),
            detail_info=detail_snapshot,
            container=container,
            after_open=_after_open,
        )

