"""控制器设置与信号连接 Mixin"""
from __future__ import annotations

from engine.graph.models.graph_model import GraphModel
from app.ui.graph.graph_scene import GraphScene

from app.ui.controllers import (
    PackageController,
    GraphEditorController,
    NavigationCoordinator,
    FileWatcherManager,
)
from app.models.edit_session_capabilities import EditSessionCapabilities
from app.models.view_modes import ViewMode
from app.runtime.services.graph_data_service import get_shared_graph_data_service


class ControllerSetupMixin:
    """控制器初始化和信号连接 Mixin"""

    def _setup_controllers(self) -> None:
        """初始化所有控制器"""
        app_state = self.app_state

        # 存档控制器
        self.package_controller = PackageController(
            app_state.workspace_path,
            app_state.resource_manager,
            app_state.package_index_manager,
            self,
        )
        # 设置回调函数
        self.package_controller.get_current_graph_container = self._get_current_resource_container
        self.package_controller.get_property_panel_object_type = (
            lambda: self.property_panel.object_type
        )
        if hasattr(self, "refresh_resource_library"):
            self.package_controller.on_external_resource_change = self.refresh_resource_library

        # 图编辑控制器
        graph_view = app_state.graph_view
        initial_scene = graph_view.scene()
        if initial_scene is None:
            raise ValueError("GraphView 尚未绑定任何 Scene，无法初始化 GraphEditorController")
        if not isinstance(initial_scene, GraphScene):
            raise TypeError(f"GraphView.scene() 不是 GraphScene: {type(initial_scene)}")
        initial_model = getattr(initial_scene, "model", None)
        if not isinstance(initial_model, GraphModel):
            raise TypeError(f"GraphScene.model 不是 GraphModel: {type(initial_model)}")

        self.graph_controller = GraphEditorController(
            app_state.resource_manager,
            initial_model,
            initial_scene,
            graph_view,
            app_state.node_library,
            edit_session_capabilities=EditSessionCapabilities.interactive_preview(),
            parent=self,
        )
        # 自动排版完成后：刷新持久化缓存，确保下次打开直接使用最新位置
        if hasattr(graph_view, "on_auto_layout_completed"):
            graph_view.on_auto_layout_completed = self.graph_controller.refresh_persistent_cache_after_layout
        # 自动排版前：允许控制器执行一次性准备（例如从 True→False 关闭跨块复制后强制重载当前图）
        graph_view.on_before_auto_layout = self.graph_controller.prepare_for_auto_layout
        # 设置回调函数
        self.graph_controller.get_current_package = (
            lambda: self.package_controller.current_package
        )
        self.graph_controller.get_property_panel_object_type = (
            lambda: self.property_panel.object_type
        )
        # “添加节点”入口由 GraphEditorController 按 EditSessionCapabilities 统一控制（禁止此处直接写回调，避免语义分裂）
        # 连接视图的双击跳转信号
        graph_view.jump_to_graph_element.connect(self._on_jump_to_graph_element)

        # 跳转协调器
        self.nav_coordinator = NavigationCoordinator(self)
        self.nav_coordinator.get_current_package = (
            lambda: self.package_controller.current_package
        )
        self.nav_coordinator.get_current_package_id = (
            lambda: self.package_controller.current_package_id
        )
        self.nav_coordinator.get_graph_data_service = (
            lambda: get_shared_graph_data_service(app_state.resource_manager, app_state.package_index_manager)
        )

        # 文件监控管理器
        self.file_watcher_manager = FileWatcherManager(
            app_state.resource_manager,
            self,
        )
        self.file_watcher_manager.get_current_graph_id = (
            lambda: self.graph_controller.current_graph_id
        )
        # 注意：GraphEditorController 在加载图时会重建 scene/model，因此这里必须走 controller 的当前 scene。
        self.file_watcher_manager.get_scene = self.graph_controller.get_current_scene
        self.file_watcher_manager.get_view = lambda: self.graph_controller.view
        # 当资源库发生外部变更时，触发主窗口统一的资源刷新入口
        if hasattr(self, "refresh_resource_library"):
            self.file_watcher_manager.on_resource_library_changed = self.refresh_resource_library

    def _get_current_resource_container(self):
        """
        提供给 PackageController 的统一“当前编辑对象”获取入口。

        优先使用右侧属性面板当前选中的对象（模板/实例/关卡实体），
        仅当属性面板没有上下文时，才回退到“当前打开节点图”的容器对象。

        这样可以保证：
        - 在实体摆放/元件库等模式下修改基础信息（名称/描述/GUID 等）时，
          始终写回当前属性面板正在编辑的对象，不会被后台仍然打开的其它图上下文抢占；
        - 在仅打开节点图而未选中任何模板/实例时，仍能保存该图所隶属的容器对象。
        """
        current_mode = None
        if hasattr(self, "central_stack"):
            mode_index = self.central_stack.currentIndex()
            current_mode = ViewMode.from_index(mode_index)

        # 非图编辑器模式下：以属性面板当前对象为主
        if current_mode is not ViewMode.GRAPH_EDITOR and hasattr(self, "property_panel"):
            panel_object = getattr(self.property_panel, "current_object", None)
            if panel_object is not None:
                return panel_object

        # 图编辑器模式或属性面板没有上下文时：回退到当前图的容器对象
        return getattr(self.graph_controller, "current_graph_container", None)

    def _connect_controller_signals(self) -> None:
        """连接控制器信号"""
        # === 存档控制器信号 ===
        self.package_controller.package_loaded.connect(self._on_package_loaded)
        self.package_controller.package_saved.connect(self._on_package_saved)
        self.package_controller.package_list_changed.connect(self._refresh_package_list)
        self.package_controller.title_update_requested.connect(self._update_window_title)
        self.package_controller.request_save_current_graph.connect(
            self.graph_controller.save_current_graph
        )

        # === 图编辑控制器信号 ===
        self.graph_controller.graph_loaded.connect(self._on_graph_loaded)
        self.graph_controller.graph_saved.connect(self._on_graph_saved)
        self.graph_controller.graph_runtime_cache_updated.connect(self._on_graph_runtime_cache_updated)
        self.graph_controller.validation_triggered.connect(self._trigger_validation)
        # 切换到编辑器时，通过导航统一入口，确保左侧导航同步高亮、中央与右侧面板一致切换
        self.graph_controller.switch_to_editor_requested.connect(
            lambda: self._navigate_to_mode("graph_editor")
        )
        self.graph_controller.title_update_requested.connect(self._update_window_title)
        self.graph_controller.save_status_changed.connect(self._on_save_status_changed)

        # === 跳转协调器信号 ===
        self.nav_coordinator.navigate_to_mode.connect(self._navigate_to_mode)
        self.nav_coordinator.select_template.connect(self.template_widget.select_template)
        self.nav_coordinator.select_instance.connect(self.placement_widget.select_instance)
        self.nav_coordinator.select_level_entity.connect(self._on_level_entity_selected)
        self.nav_coordinator.open_graph.connect(self._on_open_graph_request)
        self.nav_coordinator.focus_node.connect(self._focus_node)
        self.nav_coordinator.focus_edge.connect(self._focus_edge)
        # 切包统一走主窗口的保护入口（未保存提示 + 保存/不保存/取消），避免旁路直切导致数据丢失。
        request_load_package = getattr(self, "_request_load_package", None)
        if callable(request_load_package):
            self.nav_coordinator.load_package.connect(request_load_package)
        else:
            self.nav_coordinator.load_package.connect(self.package_controller.load_package)
        self.nav_coordinator.switch_to_editor.connect(
            lambda: self._navigate_to_mode("graph_editor")
        )
        self.nav_coordinator.open_player_editor.connect(self._open_player_editor)
        # 战斗预设条目跳转（来自节点图引用列表/存档库等）：复用已有选中处理逻辑
        self.nav_coordinator.select_player_template.connect(self._on_player_template_selected)
        self.nav_coordinator.select_player_class.connect(self._on_player_class_selected)
        self.nav_coordinator.select_skill.connect(self._on_skill_selected)
        # 复合节点选择
        self.nav_coordinator.select_composite_name.connect(self._on_select_composite_name)
        management_widget = getattr(self, "management_widget", None)
        focus_method = getattr(management_widget, "focus_section_and_item", None) if management_widget is not None else None
        if callable(focus_method):
            self.nav_coordinator.focus_management_section_and_item.connect(focus_method)

        # === 文件监控管理器信号 ===
        self.file_watcher_manager.show_toast.connect(self._show_toast)
        self.file_watcher_manager.graph_reloaded.connect(self._on_graph_reloaded)
        self.file_watcher_manager.force_save_requested.connect(
            self.graph_controller.save_current_graph
        )

        # === 图属性面板信号（用于图库统计同步） ===
        #
        # 背景：节点图库列表页使用 `load_graph_metadata()` 的轻量缓存展示 node/edge 统计；
        # 当右侧图属性面板触发真实解析并生成持久化 graph_cache 后，旧的轻量统计需要被失效，
        # 否则会出现“左侧卡片与右侧基本信息不一致”的体验。
        graph_property_panel = getattr(self, "graph_property_panel", None)
        payload_loaded_handler = getattr(self, "_on_graph_property_panel_payload_loaded", None)
        if graph_property_panel is not None and callable(payload_loaded_handler):
            # 使用 UISetupMixin 提供的可选信号连接器，避免散落 hasattr 判断
            self._connect_optional_signal(graph_property_panel, "graph_data_loaded", payload_loaded_handler)

