"""控制器设置与信号连接 Mixin"""
from __future__ import annotations

from app.ui.controllers import (
    PackageController,
    GraphEditorController,
    NavigationCoordinator,
    FileWatcherManager,
)
from app.models.view_modes import ViewMode
from app.runtime.services.graph_data_service import get_shared_graph_data_service


class ControllerSetupMixin:
    """控制器初始化和信号连接 Mixin"""

    def _setup_controllers(self) -> None:
        """初始化所有控制器"""
        # 存档控制器
        self.package_controller = PackageController(
            self.workspace_path,
            self.resource_manager,
            self.package_index_manager,
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
        self.graph_controller = GraphEditorController(
            self.resource_manager,
            self.model,
            self.scene,
            self.view,
            self.library,
            self,
        )
        # 自动排版完成后：刷新持久化缓存，确保下次打开直接使用最新位置
        if hasattr(self.view, 'on_auto_layout_completed'):
            self.view.on_auto_layout_completed = self.graph_controller.refresh_persistent_cache_after_layout
        # 自动排版前：允许控制器执行一次性准备（例如从 True→False 关闭跨块复制后强制重载当前图）
        self.view.on_before_auto_layout = self.graph_controller.prepare_for_auto_layout
        # 设置回调函数
        self.graph_controller.get_current_package = (
            lambda: self.package_controller.current_package
        )
        self.graph_controller.get_property_panel_object_type = (
            lambda: self.property_panel.object_type
        )
        # 设置视图的添加节点回调
        self.view.on_add_node_callback = self.graph_controller.add_node_at_position
        # 连接视图的双击跳转信号
        self.view.jump_to_graph_element.connect(self._on_jump_to_graph_element)

        # 跳转协调器
        self.nav_coordinator = NavigationCoordinator(self)
        self.nav_coordinator.get_current_package = (
            lambda: self.package_controller.current_package
        )
        self.nav_coordinator.get_current_package_id = (
            lambda: self.package_controller.current_package_id
        )
        self.nav_coordinator.get_graph_data_service = (
            lambda: get_shared_graph_data_service(self.resource_manager, self.package_index_manager)
        )

        # 文件监控管理器
        self.file_watcher_manager = FileWatcherManager(
            self.resource_manager,
            self,
        )
        self.file_watcher_manager.get_current_graph_id = (
            lambda: self.graph_controller.current_graph_id
        )
        self.file_watcher_manager.get_scene = lambda: self.scene
        self.file_watcher_manager.get_view = lambda: self.view
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
        self.nav_coordinator.load_package.connect(self.package_controller.load_package)
        self.nav_coordinator.switch_to_editor.connect(
            lambda: self.central_stack.setCurrentIndex(ViewMode.GRAPH_EDITOR.value)
        )
        self.nav_coordinator.open_player_editor.connect(self._open_player_editor)
        # 复合节点选择
        self.nav_coordinator.select_composite_name.connect(self._on_select_composite_name)

        # === 文件监控管理器信号 ===
        self.file_watcher_manager.show_toast.connect(self._show_toast)
        self.file_watcher_manager.graph_reloaded.connect(self._on_graph_reloaded)
        self.file_watcher_manager.force_save_requested.connect(
            self.graph_controller.save_current_graph
        )

