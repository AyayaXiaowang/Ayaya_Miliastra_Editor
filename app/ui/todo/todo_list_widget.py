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

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtWidgets import QAbstractItemView
from PyQt6.QtCore import Qt, pyqtSignal
from typing import Dict, List, Optional

from app.models import TodoItem
from app.ui.foundation.global_hotkey_manager import GlobalHotkeyManager
from app.ui.foundation.theme_manager import Sizes as ThemeSizes
from app.ui.foundation.ui_notifier import notify as notify_with_toast
from app.ui.todo.todo_config import LayoutConstants, TodoStyles
from app.ui.todo.todo_navigation_controller import TodoNavigationController
from app.ui.todo.todo_rich_item_delegate import RichTextItemDelegate
from app.ui.todo.todo_list_orchestrator import TodoListOrchestrator
from app.ui.todo.todo_ui_context import TodoUiContext


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

        # 子组件引用（由 orchestrator 统一创建）
        self.runtime_state = None
        self.tree_manager = None
        self.preview_panel = None
        self.detail_panel = None
        self.executor_bridge = None
        self._context_menu = None

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

        # 执行精简模式：尽可能缩小任务清单页占用空间（隐藏右侧详情/预览，仅保留左侧步骤树）
        self._execution_compact_mode_enabled: bool = False
        self._execution_compact_saved_state: dict | None = None
        # 是否已收到过一次 Todo 数据（即使为空列表也视为“已加载”）
        self._has_loaded_todo_data: bool = False
        # 外部跳转的“待聚焦请求”：用于在 Todo 仍未生成/正在刷新时先记录意图，待数据就绪后再聚焦。
        self._pending_external_focus: tuple[str, dict | None] | None = None

        self._setup_ui()

        # 将领域 wiring 与子组件组装集中到编排层
        self._ui_context = TodoUiContext(self)
        self._orchestrator = TodoListOrchestrator(self._ui_context)

    @property
    def ui_context(self) -> TodoUiContext:
        return self._ui_context
    
    def _setup_ui(self):
        """设置UI"""
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 应用整体样式
        self._apply_styles()
        
        # 使用分割器
        splitter = QtWidgets.QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("todoMainSplitter")
        self._splitter = splitter
        
        # 左侧：任务树（卡片式容器）
        left_card = QtWidgets.QWidget()
        self._left_card = left_card
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
        self._header_widget = header_widget
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
        # 注意：此处不使用“加载中”，避免在无当前存档/未触发生成时造成误导
        self.stats_label = QtWidgets.QLabel("尚未生成任务清单")
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

    @property
    def execution_compact_mode_enabled(self) -> bool:
        return bool(getattr(self, "_execution_compact_mode_enabled", False))

    def set_execution_compact_mode(self, enabled: bool) -> None:
        """执行精简模式（任务清单页侧）。

        目标：为低分辨率执行场景尽可能节省空间：
        - 隐藏右侧详情/预览堆栈（含节点图预览）
        - 压缩左侧步骤树宽度与头部信息
        """
        target_enabled = bool(enabled)
        if target_enabled == self.execution_compact_mode_enabled:
            return
        self._execution_compact_mode_enabled = target_enabled

        splitter = getattr(self, "_splitter", None)
        left_card = getattr(self, "_left_card", None)
        header_widget = getattr(self, "_header_widget", None)

        if target_enabled:
            if self._execution_compact_saved_state is None:
                saved_splitter_sizes = splitter.sizes() if isinstance(splitter, QtWidgets.QSplitter) else []
                saved_splitter_handle_width = splitter.handleWidth() if isinstance(splitter, QtWidgets.QSplitter) else 0
                saved_left_min_width = left_card.minimumWidth() if isinstance(left_card, QtWidgets.QWidget) else 0
                saved_left_max_width = left_card.maximumWidth() if isinstance(left_card, QtWidgets.QWidget) else 0
                saved_header_visible = header_widget.isVisible() if isinstance(header_widget, QtWidgets.QWidget) else True
                saved_right_stack_visible = self.right_stack.isVisible()
                saved_right_stack_min_width = int(self.right_stack.minimumWidth())
                saved_right_stack_max_width = int(self.right_stack.maximumWidth())
                saved_tree_indentation = self.tree.indentation() if hasattr(self, "tree") else 0
                self._execution_compact_saved_state = {
                    "splitter_sizes": saved_splitter_sizes,
                    "splitter_handle_width": int(saved_splitter_handle_width),
                    "left_min_width": int(saved_left_min_width),
                    "left_max_width": int(saved_left_max_width),
                    "header_visible": bool(saved_header_visible),
                    "right_stack_visible": bool(saved_right_stack_visible),
                    "right_stack_min_width": int(saved_right_stack_min_width),
                    "right_stack_max_width": int(saved_right_stack_max_width),
                    "tree_indentation": int(saved_tree_indentation),
                }

            if isinstance(header_widget, QtWidgets.QWidget):
                header_widget.setVisible(False)

            # 隐藏右侧详情/预览：节点图预览与长文档占用较大宽高
            # 注意：在 QSplitter 中仅 setVisible(False) 可能仍会留下占位宽度。
            # 精简模式下将其宽度硬压到 0，避免出现“步骤树右侧空白区”。
            self.right_stack.setMinimumWidth(0)
            self.right_stack.setMaximumWidth(0)
            self.right_stack.setVisible(False)

            if isinstance(left_card, QtWidgets.QWidget):
                left_card.setMinimumWidth(220)
                # 允许左侧树吃满当前可用宽度（避免因 maxWidth 限制导致中间出现空白占位）。
                left_card.setMaximumWidth(QtWidgets.QWIDGETSIZE_MAX)

            if hasattr(self, "tree"):
                # 更紧凑的层级缩进，文本过长按右侧省略
                self.tree.setIndentation(12)
                if hasattr(self.tree, "setTextElideMode"):
                    self.tree.setTextElideMode(Qt.TextElideMode.ElideRight)

            if isinstance(splitter, QtWidgets.QSplitter):
                splitter.setChildrenCollapsible(True)
                splitter.setCollapsible(1, True)
                splitter.setHandleWidth(2)
                splitter.setSizes([260, 0])

            # 进入执行精简模式：若任务清单页当前在前台，则刷新一次当前选中项，
            # 让执行监控面板的“执行/执行剩余”按钮立刻获得正确文案与信号路由（无需用户重新点选）。
            self._refresh_current_selection_view_for_execution_mode()
            # 切换精简模式时，QTreeWidget 的滚动位置可能被重置到顶部；这里确保回到“当前步骤”。
            QtCore.QTimer.singleShot(0, self._scroll_tree_to_current_item)
            return

        # restore
        saved = self._execution_compact_saved_state
        if not isinstance(saved, dict):
            return

        if isinstance(header_widget, QtWidgets.QWidget):
            header_widget.setVisible(bool(saved.get("header_visible", True)))

        self.right_stack.setMinimumWidth(int(saved.get("right_stack_min_width", 0)))
        self.right_stack.setMaximumWidth(int(saved.get("right_stack_max_width", QtWidgets.QWIDGETSIZE_MAX)))
        self.right_stack.setVisible(bool(saved.get("right_stack_visible", True)))

        if isinstance(left_card, QtWidgets.QWidget):
            left_card.setMinimumWidth(int(saved.get("left_min_width", ThemeSizes.LEFT_PANEL_WIDTH)))
            left_card.setMaximumWidth(int(saved.get("left_max_width", left_card.maximumWidth())))

        if hasattr(self, "tree"):
            self.tree.setIndentation(int(saved.get("tree_indentation", LayoutConstants.TREE_INDENTATION)))

        if isinstance(splitter, QtWidgets.QSplitter):
            splitter.setHandleWidth(int(saved.get("splitter_handle_width", 6)))
            splitter_sizes = saved.get("splitter_sizes")
            if isinstance(splitter_sizes, list) and splitter_sizes:
                splitter.setSizes(splitter_sizes)

        self._execution_compact_saved_state = None

        # 退出执行精简模式：若任务清单页当前在前台，则刷新一次当前选中项，
        # 以恢复右侧详情/预览（含共享画布）到“正常模式”的默认展示策略。
        self._refresh_current_selection_view_for_execution_mode()
        QtCore.QTimer.singleShot(0, self._scroll_tree_to_current_item)

    def _scroll_tree_to_current_item(self) -> None:
        """确保左侧步骤树滚动到当前选中项（用于精简模式切换后避免回到顶部）。"""
        if not self._is_active_todo_page():
            return
        if not hasattr(self, "tree"):
            return
        current_item = self.tree.currentItem()
        if current_item is None:
            return
        self.tree.scrollToItem(
            current_item,
            QAbstractItemView.ScrollHint.PositionAtCenter,
        )

    def _is_active_todo_page(self) -> bool:
        """判断任务清单页是否为当前中央堆叠页。

        约定：只有当本页在前台时，才允许触发 show_detail/预览加载，避免误把共享 GraphView 从编辑器页“偷走”。
        """
        main_window = getattr(self, "main_window", None)
        if main_window is None:
            return False
        central_stack = getattr(main_window, "central_stack", None)
        if central_stack is None or not hasattr(central_stack, "currentWidget"):
            return False
        return central_stack.currentWidget() is self

    def _refresh_current_selection_view_for_execution_mode(self) -> None:
        """在精简模式切换时刷新当前选中项的右侧视图与执行入口状态。

        - 仅在任务清单页处于前台时执行，避免影响图编辑器页的共享画布归属。
        - 不吞异常：若内部依赖未就绪，直接让错误暴露出来便于定位初始化顺序问题。
        """
        if not self._is_active_todo_page():
            return
        orchestrator = getattr(self, "_orchestrator", None)
        if orchestrator is None:
            return
        tree_manager = getattr(self, "tree_manager", None)
        if tree_manager is None:
            return

        current_item = self.tree.currentItem() if hasattr(self, "tree") else None
        todo_id = ""
        if current_item is not None:
            raw_id = current_item.data(0, Qt.ItemDataRole.UserRole)
            todo_id = str(raw_id or "")
        if not todo_id:
            todo_id = str(getattr(self, "current_todo_id", "") or "")
        if not todo_id:
            return

        todo = tree_manager.todo_map.get(todo_id)
        if todo is None:
            return

        orchestrator.show_detail(todo)
    
    def _apply_styles(self):
        """应用现代化样式表"""
        self.setStyleSheet(TodoStyles.widget_stylesheet())
    
    def load_todos(self, todos: List[TodoItem], todo_states: Dict[str, bool]):
        """加载任务列表（委托给编排层）。"""
        self._has_loaded_todo_data = True
        self._orchestrator.load_todos(todos, todo_states)
        self._apply_pending_external_focus_if_any()

    def set_stats_status(self, message: str) -> None:
        """更新左侧头部统计徽章文案（用于“生成中/不可用”等非进度状态）。"""
        label = getattr(self, "stats_label", None)
        if label is None:
            return
        label.setText(str(message or ""))

    def show_unavailable_state(self, message: str) -> None:
        """切换到“不可用/未生成”状态并清空旧数据，避免残留内容误导用户。"""
        self._has_loaded_todo_data = False

        tree_manager = getattr(self, "tree_manager", None)
        if tree_manager is not None:
            tree_manager.set_data([], {})

        self.current_detail_info = None
        self.current_todo_id = None
        self.set_stats_status(message)
    
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
        if not getattr(self, "_has_loaded_todo_data", False):
            self.set_stats_status("尚未生成任务清单")
            return

        # 统计所有叶子节点
        leaf_todos = [t for t in self.todos if not t.children]
        total = len(leaf_todos)
        if total <= 0:
            self.set_stats_status("暂无任务")
            return
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
        normalized_todo_id = str(todo_id or "")
        if not normalized_todo_id:
            return

        tree_manager = getattr(self, "tree_manager", None)
        if tree_manager is None:
            # 树尚未就绪（例如 Todo 仍未生成/正在刷新）：先记录意图，待 load_todos() 后重试。
            self._pending_external_focus = (
                normalized_todo_id,
                dict(detail_info) if isinstance(detail_info, dict) else None,
            )
            return

        get_item_by_id = getattr(tree_manager, "get_item_by_id", None)
        item = get_item_by_id(normalized_todo_id) if callable(get_item_by_id) else None
        if item is not None:
            self._orchestrator.focus_task_from_external(normalized_todo_id, detail_info)
            return

        # 事件流子步骤默认 UI 懒加载：第一次进入任务清单时，leaf 步骤的树项可能尚未创建。
        # 若 Todo 数据已存在，则尝试触发懒加载并在目标树项就绪后再聚焦。
        todo_map = getattr(tree_manager, "todo_map", None)
        todo_exists = isinstance(todo_map, dict) and normalized_todo_id in todo_map
        if not todo_exists:
            # Todo 数据本身还没到（或目标已不存在）：等 load_todos() 之后再判断
            self._pending_external_focus = (
                normalized_todo_id,
                dict(detail_info) if isinstance(detail_info, dict) else None,
            )
            return

        ensure_item_built = getattr(tree_manager, "ensure_item_built", None)
        if not callable(ensure_item_built):
            return

        # 先尽量选中其所属事件流根：至少让用户看到“定位中”的展开与上下文
        find_flow_root = getattr(tree_manager, "find_event_flow_root_for_todo", None)
        flow_root = find_flow_root(normalized_todo_id) if callable(find_flow_root) else None
        flow_root_id = str(getattr(flow_root, "todo_id", "") or "") if flow_root is not None else ""
        if flow_root_id:
            self._orchestrator.focus_task_from_external(
                flow_root_id,
                dict(getattr(flow_root, "detail_info", None) or {}),
            )

        def _on_ready(_item: object) -> None:
            if _item is None:
                return
            self._orchestrator.focus_task_from_external(normalized_todo_id, detail_info)

        ensure_item_built(normalized_todo_id, on_ready=_on_ready)
        return

    def _apply_pending_external_focus_if_any(self) -> None:
        pending = getattr(self, "_pending_external_focus", None)
        if pending is None or not isinstance(pending, tuple) or len(pending) != 2:
            return
        todo_id, detail_info = pending
        self._pending_external_focus = None
        if not todo_id:
            return
        # 复用同一套“缺树项/懒加载”处理逻辑，避免事件流子步骤 UI 懒加载下出现空跳转。
        self.focus_task_from_external(str(todo_id or ""), detail_info)
    
    # 执行过程中的回填/暂停/上下文同步由 TodoExecutorBridge 负责
    
    # 查找事件流根已由 TodoTreeManager 提供

    def _should_keep_global_hotkeys_registered(self) -> bool:
        """判断是否需要保持系统级全局热键处于注册状态。

        约定：
        - 当任务清单页可见时：注册热键，用于 Ctrl+[ / Ctrl+] 导航与 Ctrl+P 暂停。
        - 当任务清单页不可见时：仅在执行线程运行中保留热键，使 Ctrl+P 仍可用于运行时暂停。

        说明：
        - Ctrl+P 是高频系统快捷键（常用于“打印”），因此**不应**在非执行场景下长期占用。
        """
        if self.isVisible():
            return True

        executor_bridge = getattr(self, "executor_bridge", None)
        is_execution_running = getattr(executor_bridge, "is_execution_running", None)
        if callable(is_execution_running):
            return bool(is_execution_running())
        return False

    def sync_global_hotkeys(self) -> None:
        """同步全局热键注册状态（见 `_should_keep_global_hotkeys_registered` 约定）。"""
        if self._should_keep_global_hotkeys_registered():
            success = self.hotkey_manager.register_hotkeys()
            return

        self.hotkey_manager.unregister_hotkeys()
    
    def showEvent(self, event: QtGui.QShowEvent) -> None:
        """页面显示事件 - 注册全局热键"""
        super().showEvent(event)
        self.sync_global_hotkeys()
    
    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        """页面隐藏事件 - 注销全局热键"""
        super().hideEvent(event)
        # 注意：执行进行中时不要注销全局热键，否则运行时 Ctrl+P 将失效。
        self.sync_global_hotkeys()

    # 编辑请求桥接：供 preview_panel 调用
    def _open_graph_in_editor(self, graph_id: str, graph_data: dict, container: object) -> None:
        self.ui_context.open_graph_in_editor(graph_id, graph_data, container)

    # === 工具：统一以 TreeManager 数据源为准 ===
    def _get_todo_by_id(self, todo_id: str) -> Optional[TodoItem]:
        if self.tree_manager is None:
            return None
        return self.tree_manager.todo_map.get(todo_id)

    @property
    def todos(self) -> List[TodoItem]:
        """对外暴露的 Todo 列表视图：统一透传 TreeManager 的权威数据。"""
        if self.tree_manager is None:
            return []
        return self.tree_manager.todos

    @property
    def todo_map(self) -> Dict[str, TodoItem]:
        """对外暴露的 todo_id → TodoItem 映射：统一透传 TreeManager 的权威数据。"""
        if self.tree_manager is None:
            return {}
        return self.tree_manager.todo_map

    @property
    def todo_states(self) -> Dict[str, bool]:
        """对外暴露的完成状态映射：统一透传 TreeManager 维护的状态字典。"""
        if self.tree_manager is None:
            return {}
        return self.tree_manager.todo_states

    def has_loaded_todos(self) -> bool:
        """是否已加载过任务清单。"""
        return bool(getattr(self, "_has_loaded_todo_data", False))

    def find_first_todo_for_graph(self, graph_id: str) -> Optional[TodoItem]:
        """根据 graph_id 查找一个可用的 todo（优先叶子步骤，其次父级根）。"""
        return self._orchestrator.find_first_todo_for_graph(graph_id)


