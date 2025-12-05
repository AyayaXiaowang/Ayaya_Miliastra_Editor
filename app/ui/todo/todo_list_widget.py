"""任务清单组件 - 模拟器到真实编辑器的桥梁

🎯 核心价值
==========
任务清单是本项目最重要的功能，是"模拟器"到"真实编辑器"的桥梁。

工作原理：
1. 用户在模拟器中创建元件、编辑节点图、配置实例等
2. 系统自动分析用户的操作，生成详细的任务清单
3. 任务清单包含具体的操作步骤：创建什么元件、添加什么变量、连接哪些节点等
4. 用户打开真实的千星沙箱编辑器，照着任务清单逐步完成相同操作
5. 最终在真实编辑器中创作出完整作品

为什么需要任务清单：
- 真实编辑器是加密的，无法直接导入导出数据
- 任务清单是人工可读的操作指南，用户可以手动重现
- 支持分步骤勾选完成状态，方便跟踪进度

配置说明：
- 颜色、样式、图标等配置统一在 ui/todo_config.py 中管理
- 修改任务类型颜色/图标请编辑 todo_config.py
- 不要在此文件中硬编码颜色值或魔法数字
"""

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import Qt, pyqtSignal
from typing import Dict, List, Optional

from app.models import TodoItem
from ui.foundation.global_hotkey_manager import GlobalHotkeyManager
from ui.foundation.theme_manager import Sizes as ThemeSizes
from ui.foundation.ui_notifier import notify as notify_with_toast
from ui.todo.todo_config import LayoutConstants, TodoStyles
from ui.todo.todo_navigation_controller import TodoNavigationController
from ui.todo.todo_rich_item_delegate import RichTextItemDelegate
from ui.todo.todo_list_orchestrator import TodoListOrchestrator


class TodoListWidget(QtWidgets.QWidget):
    """任务清单组件 - 左侧任务树 + 右侧详情面板（薄宿主，主要负责 UI 布局与对外 API）。"""

    # 信号
    todo_checked = pyqtSignal(str, bool)  # todo_id, checked
    jump_to_task = pyqtSignal(dict)  # detail_info

    def __init__(self, parent=None):
        super().__init__(parent)
        # 保存对主窗口的引用，用于数据同步
        self.main_window = None
        # 资源访问依赖：由主窗口在创建页面时注入，供详情/树等子组件读取
        self.resource_manager = None
        self.current_graph_id = None
        self.current_template_or_instance = None

        # 运行时监控窗口引用（供桥接层读取）
        self._monitor_window = None

        # 全局热键管理器
        self.hotkey_manager = GlobalHotkeyManager(self)
        self.nav_controller = TodoNavigationController(self)
        self.hotkey_manager.prev_hotkey_triggered.connect(
            self.nav_controller.navigate_to_prev_task
        )
        self.hotkey_manager.next_hotkey_triggered.connect(
            self.nav_controller.navigate_to_next_task
        )
        # Ctrl+P 全局暂停：路由到执行监控面板
        self.hotkey_manager.ctrl_p_hotkey_triggered.connect(
            self.nav_controller.on_global_ctrl_p
        )

        # 富文本分段角色（避免与 UserRole 冲突）
        self.RICH_SEGMENTS_ROLE: int = int(Qt.ItemDataRole.UserRole) + 1

        self._setup_ui()

        # 将领域 wiring 与子组件组装集中到编排层
        self._orchestrator = TodoListOrchestrator(self)
    
    def _setup_ui(self):
        """设置UI"""
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 应用整体样式
        self._apply_styles()
        
        # 使用分割器
        splitter = QtWidgets.QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧：任务树（卡片式容器）
        left_card = QtWidgets.QWidget()
        # 设为最小宽度，允许通过分割条向更大方向拖拽
        left_card.setMinimumWidth(ThemeSizes.LEFT_PANEL_WIDTH)
        left_card.setObjectName("leftCard")
        left_card_layout = QtWidgets.QVBoxLayout(left_card)
        # 统一边距，避免视觉宽度偏差与双层内边距
        left_card_layout.setContentsMargins(0, 0, 0, 0)
        left_card_layout.setSpacing(12)
        
        # 标题和统计容器
        header_widget = QtWidgets.QWidget()
        header_widget.setObjectName("headerWidget")
        header_layout = QtWidgets.QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        
        # 标题
        self.title_label = QtWidgets.QLabel("任务清单")
        self.title_label.setObjectName("titleLabel")
        font = self.title_label.font()
        font.setPointSize(18)
        font.setBold(True)
        self.title_label.setFont(font)
        header_layout.addWidget(self.title_label)
        
        # 统计标签（徽章样式）
        self.stats_label = QtWidgets.QLabel("加载中...")
        self.stats_label.setObjectName("statsLabel")
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        header_layout.addWidget(self.stats_label)
        
        left_card_layout.addWidget(header_widget)
        
        # 任务树
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setObjectName("todoTree")
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.setIndentation(LayoutConstants.TREE_INDENTATION)
        # 统一行高以降低大树的重绘成本；关闭展开动画避免交互卡顿
        self.tree.setUniformRowHeights(True)
        self.tree.setAnimated(False)
        left_card_layout.addWidget(self.tree)
        # 安装分段文本绘制委托（仅第0列）
        # 置灰标记角色约定为 RICH_SEGMENTS_ROLE + 1，由 TodoTreeManager 负责写入。
        self._rich_delegate = RichTextItemDelegate(
            self.RICH_SEGMENTS_ROLE,
            self.tree,
        )
        self.tree.setItemDelegateForColumn(0, self._rich_delegate)
        
        # 右侧：使用堆叠布局（QStackedWidget）切换详情和预览
        self.right_stack = QtWidgets.QStackedWidget()
        # 注意：具体的详情/预览子页由上方子模块插入
        
        # 添加到主分割器
        splitter.addWidget(left_card)
        splitter.addWidget(self.right_stack)
        splitter.setStretchFactor(0, LayoutConstants.SPLITTER_LEFT_STRETCH)
        splitter.setStretchFactor(1, LayoutConstants.SPLITTER_RIGHT_STRETCH)
        splitter.setSizes([LayoutConstants.SPLITTER_LEFT_WIDTH, LayoutConstants.SPLITTER_RIGHT_WIDTH])
        
        layout.addWidget(splitter)
        
        self.current_detail_info = None
        self.current_todo_id: Optional[str] = None
    
    def _apply_styles(self):
        """应用现代化样式表"""
        self.setStyleSheet(TodoStyles.widget_stylesheet())
    
    def load_todos(self, todos: List[TodoItem], todo_states: Dict[str, bool]):
        """加载任务列表（委托给编排层）。"""
        self._orchestrator.load_todos(todos, todo_states)
    
    # 树构建/懒加载/样式均由 TodoTreeManager 负责
    
    # 由 TodoTreeManager 处理树项展开的懒加载

    # 节点名/类别与 GraphModel 相关逻辑下沉到 TodoTreeManager

    

    # 树项富文本 tokens 已由 TodoTreeManager 提供 ensure_tokens_for_todo()
    
    # 父级样式/图标获取由 TodoTreeManager 管理

    # 右键菜单已由 TodoContextMenu 承担

    # 模板图根定位下沉到 TodoTreeManager

    # 执行相关逻辑由 TodoExecutorBridge 统一处理

    # 选择恢复逻辑下沉到执行桥

    def _notify(self, message: str, toast_type: str = "info") -> None:
        """统一提示：委托给通用 UI 通知工具。"""
        notify_with_toast(self, message, toast_type)
    # 勾选与增量刷新由 TodoTreeManager 负责
    
    # 父子联动与整树刷新由 TodoTreeManager 负责
    
    # 递归刷新交由 TodoTreeManager 管理

    # 详情统计/汇总逻辑已在 TodoDetailPanel 中封装
    
    def _update_stats(self):
        """更新统计信息"""
        # 统计所有叶子节点
        leaf_todos = [t for t in self.todos if not t.children]
        total = len(leaf_todos)
        completed = sum(1 for t in leaf_todos if self.todo_states.get(t.todo_id, False))
        
        percentage = int(completed / total * 100) if total > 0 else 0
        
        # 根据完成度显示不同的文本
        if percentage == 100:
            progress_text = "全部完成"
        elif percentage >= 75:
            progress_text = "即将完成"
        elif percentage >= 50:
            progress_text = "进行中"
        elif percentage >= 25:
            progress_text = "刚起步"
        else:
            progress_text = "准备启动"
        
        self.stats_label.setText(f"{progress_text} • {completed}/{total} ({percentage}%)")
    
    # 预览加载/聚焦/高亮与“编辑到图编辑器”逻辑均由 TodoPreviewPanel + 主窗口协调器负责
    # 任务清单预览图为只读，不直接在此组件内处理编辑跳转

    # === 全局热键导航功能 ===
    
    def focus_task_from_external(self, todo_id: str, detail_info: Optional[dict] = None) -> None:
        """外部入口：例如节点图编辑器可调用此方法跳回指定步骤。"""
        self._orchestrator.focus_task_from_external(todo_id, detail_info)
    
    # 执行过程中的回填/暂停/上下文同步由 TodoExecutorBridge 负责
    
    # 查找事件流根已由 TodoTreeManager 提供
    
    def showEvent(self, event: QtGui.QShowEvent) -> None:
        """页面显示事件 - 注册全局热键"""
        super().showEvent(event)
        # 注册热键
        success = self.hotkey_manager.register_hotkeys()
        if success:
            print("[任务清单] 全局热键已注册 (Ctrl+[ / Ctrl+] / Ctrl+P)")
        else:
            print("[任务清单] 全局热键注册失败")
    
    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        """页面隐藏事件 - 注销全局热键"""
        super().hideEvent(event)
        # 注销热键
        self.hotkey_manager.unregister_hotkeys()
        print("[任务清单] 全局热键已注销")

    # 编辑请求桥接：供 preview_panel 调用
    def _open_graph_in_editor(self, graph_id: str, graph_data: dict, container: object) -> None:
        if not self.main_window:
            return
        if self.current_todo_id and self.current_detail_info and hasattr(self.main_window, 'register_graph_editor_todo_context'):
            current_todo = self._get_todo_by_id(self.current_todo_id)
            todo_title = current_todo.title if current_todo else ""
            self.main_window.register_graph_editor_todo_context(self.current_todo_id, self.current_detail_info, todo_title)
        if hasattr(self.main_window, 'nav_coordinator'):
            from PyQt6 import QtCore as _QtCore
            _QtCore.QTimer.singleShot(30, lambda: self.main_window.nav_coordinator.open_graph.emit(graph_id, graph_data, container))
        elif hasattr(self.main_window, 'graph_controller'):
            self.main_window.graph_controller.open_graph_for_editing(graph_id, graph_data, container)

    # === 工具：统一以 TreeManager 数据源为准 ===
    def _get_todo_by_id(self, todo_id: str) -> Optional[TodoItem]:
        if hasattr(self, "tree_manager") and hasattr(self.tree_manager, "todo_map"):
            return self.tree_manager.todo_map.get(todo_id)
        return None

    @property
    def todos(self) -> List[TodoItem]:
        """对外暴露的 Todo 列表视图：统一透传 TreeManager 的权威数据。"""
        if hasattr(self, "tree_manager") and hasattr(self.tree_manager, "todos"):
            return self.tree_manager.todos
        return []

    @property
    def todo_map(self) -> Dict[str, TodoItem]:
        """对外暴露的 todo_id → TodoItem 映射：统一透传 TreeManager 的权威数据。"""
        if hasattr(self, "tree_manager") and hasattr(self.tree_manager, "todo_map"):
            return self.tree_manager.todo_map
        return {}

    @property
    def todo_states(self) -> Dict[str, bool]:
        """对外暴露的完成状态映射：统一透传 TreeManager 维护的状态字典。"""
        if hasattr(self, "tree_manager") and hasattr(self.tree_manager, "todo_states"):
            return self.tree_manager.todo_states
        return {}

    def has_loaded_todos(self) -> bool:
        """是否已加载过任务清单。"""
        return len(self.todos) > 0

    def find_first_todo_for_graph(self, graph_id: str) -> Optional[TodoItem]:
        """根据 graph_id 查找一个可用的 todo（优先叶子步骤，其次父级根）。"""
        return self._orchestrator.find_first_todo_for_graph(graph_id)


