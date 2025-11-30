"""主窗口 - 使用 Mixin 架构"""
from __future__ import annotations

from pathlib import Path

from PyQt6 import QtWidgets

from engine.nodes.node_registry import get_node_registry
from engine.graph.models.graph_model import GraphModel
from engine.configs.settings import settings
from engine.resources.resource_manager import ResourceManager
from engine.resources.package_index_manager import PackageIndexManager
from ui.graph.graph_scene import GraphScene
from ui.graph.graph_view import GraphView
from ui.devtools.view_inspector import WidgetHoverInspector

# 导入所有Mixin
from .controller_setup_mixin import ControllerSetupMixin
from .ui_setup_mixin import UISetupMixin
from .mode_switch_mixin import ModeSwitchMixin
from .event_handler_mixin import EventHandlerMixin


APP_TITLE = "小王千星工坊"


class MainWindowV2(
    ControllerSetupMixin,
    UISetupMixin,
    ModeSwitchMixin,
    EventHandlerMixin,
    QtWidgets.QMainWindow,
):
    """主窗口 V2 - 支持模式切换（Mixin架构）
    
    职责拆分：
    - ControllerSetupMixin: 控制器初始化和信号连接
    - UISetupMixin: UI组件创建和布局
    - ModeSwitchMixin: 视图模式切换和右侧面板管理
    - EventHandlerMixin: UI事件和信号响应
    - MainWindowV2: 核心初始化和属性定义
    """

    def __init__(self, workspace: Path):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1800, 1000)

        # 保存工作空间路径
        self.workspace_path = workspace

        # 初始化全局设置
        settings.set_config_path(workspace)
        settings.load()  # 加载用户设置

        # 加载节点定义（集中式注册表）
        registry = get_node_registry(workspace, include_composite=True)
        self.library = registry.get_library()

        # 资源管理器和存档索引管理器
        self.resource_manager = ResourceManager(workspace)
        self.package_index_manager = PackageIndexManager(workspace, self.resource_manager)

        # 节点图编辑相关
        self.model = GraphModel()
        self.scene = GraphScene(self.model, node_library=self.library)
        self.view = GraphView(self.scene)
        self.view.node_library = self.library
        # 任务清单 → 节点图编辑器联动上下文
        self._graph_editor_todo_context = None
        self.graph_editor_todo_button = None
        # UI 开发者工具：悬停检查器（通过 F12 快捷键开关）
        self._widget_hover_inspector = WidgetHoverInspector(self)
        self._dev_tools_enabled = False

        # 初始化控制器（必须在UI之前，因为UI中会引用控制器）
        self._setup_controllers()

        # 设置UI
        self._setup_ui()
        self._setup_menubar()
        self._setup_toolbar()

        # 应用全局主题样式
        self._apply_global_theme()

        # 连接控制器信号
        self._connect_controller_signals()

        # 加载最近的存档或创建默认存档
        self.package_controller.load_initial_package()

    def _on_dev_tools_toggled(self, enabled: bool) -> None:
        """F12 开关：启用或关闭 UI 悬停检查器。"""
        self._dev_tools_enabled = enabled
        self._widget_hover_inspector.set_enabled(enabled)
    
    def refresh_resource_library(self) -> None:
        """重建资源索引并刷新当前视图绑定的资源数据。

        设计意图：
        - 当 `assets/资源库` 下的 JSON 资源被外部工具修改时，立即让 ResourceManager 与
          各视图模型/库页面基于磁盘最新内容重建视图，而无需重启应用；
        - 保持当前存档/视图模式不变，仅刷新其内部数据来源。
        """
        # 1. 重建资源索引并清空内存缓存
        self.resource_manager.rebuild_index()
        self.resource_manager.clear_cache()

        # 2. 清理当前 PackageView / GlobalResourceView / UnclassifiedResourceView 的懒加载缓存
        current_package = getattr(self.package_controller, "current_package", None)
        if hasattr(current_package, "clear_cache"):
            current_package.clear_cache()

        # 懒加载的全局资源视图在部分页面中作为只读数据源使用，同样需要失效其缓存。
        if hasattr(self, "_global_resource_view"):
            global_view = getattr(self, "_global_resource_view", None)
            if hasattr(global_view, "clear_cache"):
                global_view.clear_cache()

        # 3. 让与“当前视图”绑定的各库页面重新从视图模型加载数据
        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if current_package_id:
            # 复用现有的包加载完成逻辑，保持模板库/实体摆放/战斗预设/管理库/节点图库一致刷新。
            self._on_package_loaded(current_package_id)

        # 4. 节点图库与存档库依赖 ResourceManager / PackageIndexManager 的聚合结果，
        #    在资源索引变化后也需要刷新以反映最新落盘状态。
        if hasattr(self, "graph_library_widget"):
            self.graph_library_widget.refresh()
        if hasattr(self, "package_library_widget"):
            self.package_library_widget.refresh()

