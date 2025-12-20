# -*- coding: utf-8 -*-
"""
面板 UI 组装与样式
负责创建执行监控面板的所有控件、布局与紧凑化样式
"""

from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtCore import Qt

from app.ui.foundation import fonts as ui_fonts
from app.ui.foundation.theme_manager import Colors, ThemeManager


class AspectRatioLabel(QtWidgets.QLabel):
    """保持 16:9 宽高比的 QLabel，用于截图显示区域"""

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self._aspect_ratio = 16 / 9  # 宽高比

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, a0: int) -> int:  # 参数名需与 QLabel 基类匹配
        return int(a0 / self._aspect_ratio)


def build_monitor_ui(parent: QtWidgets.QWidget) -> dict:
    """
    构建执行监控面板的 UI 组装
    
    参数:
        parent: 父级 widget（通常是 ExecutionMonitorPanel 本身）
        
    返回:
        控件引用字典，包含以下键：
        - layout: 主布局
        - status_label: 状态标签
        - progress_label: 进度标签
        - step_context_label: 步骤上下文标签
        - screenshot_label: 截图显示标签
        - pause_button: 暂停按钮
        - resume_button: 继续按钮
        - next_step_button: 下一步按钮
        - stop_button: 终止按钮
        - inspect_button: 检查按钮
        - match_focus_button: 定位镜头按钮
        - tests_menu_button: 测试工具菜单按钮（默认折叠，点击弹出菜单）
        - test_ocr_action: 文字OCR测试动作（QAction）
        - test_settings_action: Settings扫描测试动作（QAction）
        - test_warning_action: Warning模板测试动作（QAction）
        - test_ocr_zoom_action: OCR缩放测试动作（QAction）
        - test_nodes_action: 节点识别测试动作（QAction）
        - test_ports_action: 端口识别测试动作（QAction）
        - test_ports_deep_action: 端口深度识别测试动作（QAction）
        - test_settings_tpl_action: Settings模板匹配测试动作（QAction）
        - test_add_action: Add模板匹配测试动作（QAction）
        - test_search_action: 搜索框模板匹配测试动作（QAction）
        - test_window_strict_action: 仅窗口截图测试动作（QAction）
        - drag_origin_label: 拖拽测试当前视口中心坐标标签
        - drag_target_x_input: 拖拽测试目标X输入框（程序坐标）
        - drag_target_y_input: 拖拽测试目标Y输入框（程序坐标）
        - drag_to_target_button: 拖拽到目标坐标按钮
        - drag_left_button: 向左拖拽测试按钮
        - drag_right_button: 向右拖拽测试按钮
        - log_search_input: 日志搜索输入框
        - log_filter_combo: 日志筛选下拉框
        - log_clear_button: 清空日志按钮
        - log_text: 日志文本浏览器
    """
    layout = QtWidgets.QVBoxLayout(parent)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(8)

    # 顶部状态
    status_row = QtWidgets.QHBoxLayout()
    status_label = QtWidgets.QLabel("准备就绪")
    progress_label = QtWidgets.QLabel("")
    compact_mode_button = QtWidgets.QPushButton("精简")
    compact_mode_button.setCheckable(True)
    compact_mode_button.setToolTip("进入精简模式：缩小窗口，只保留执行控制 / 步骤 / 日志")
    compact_mode_button.setMinimumWidth(56)
    status_row.addWidget(status_label, 1)
    status_row.addWidget(progress_label)
    status_row.addWidget(compact_mode_button)
    layout.addLayout(status_row)

    # 当前步骤上下文（父任务 > 步骤）
    step_context_label = QtWidgets.QLabel("")
    step_context_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
    step_context_label.setWordWrap(True)
    layout.addWidget(step_context_label)

    # 截图区域：放在滚动区域外部，使其始终可见，不被其他控件挡住
    # 使用 AspectRatioLabel 保持 16:9 宽高比
    screenshot_label = AspectRatioLabel()
    screenshot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    # 使用 Preferred 高度策略，配合 heightForWidth 自动按宽度计算高度
    size_policy = QtWidgets.QSizePolicy(
        QtWidgets.QSizePolicy.Policy.Expanding,
        QtWidgets.QSizePolicy.Policy.Preferred,
    )
    size_policy.setHeightForWidth(True)
    screenshot_label.setSizePolicy(size_policy)
    screenshot_label.setMinimumWidth(0)
    screenshot_label.setMinimumHeight(60)
    screenshot_label.setStyleSheet(
        f"border: 1px solid {Colors.BORDER_DARK}; background-color: {Colors.BG_DARK};"
    )
    screenshot_label.setText("等待截图...")
    screenshot_label.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))
    # 截图区域直接加到主布局
    layout.addWidget(screenshot_label)

    # 控制区与其他工具区域放在滚动区域内，避免挡住截图画面
    monitor_scroll_area = QtWidgets.QScrollArea()
    monitor_scroll_area.setObjectName("monitorScrollArea")
    monitor_scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    monitor_scroll_area.setWidgetResizable(True)
    monitor_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    monitor_scroll_area.setMinimumHeight(0)
    monitor_scroll_area.setSizePolicy(
        QtWidgets.QSizePolicy.Policy.Expanding,
        QtWidgets.QSizePolicy.Policy.Expanding,
    )

    scroll_content_widget = QtWidgets.QWidget()
    scroll_content_widget.setObjectName("monitorScrollContent")
    scroll_layout = QtWidgets.QVBoxLayout(scroll_content_widget)
    scroll_layout.setContentsMargins(0, 0, 0, 0)
    scroll_layout.setSpacing(8)

    # 控制区：分组 + 栅格布局，减少长按钮在窄宽度下被挤压的概率
    controls_widget = QtWidgets.QGroupBox("控制")
    controls_widget.setObjectName("monitorControlsGroup")
    controls_layout = QtWidgets.QGridLayout(controls_widget)
    controls_layout.setContentsMargins(0, 0, 0, 0)
    controls_layout.setHorizontalSpacing(6)
    controls_layout.setVerticalSpacing(6)

    execute_button = QtWidgets.QPushButton("执行")
    execute_button.setToolTip("执行当前选中步骤（与任务清单中的执行按钮一致）")
    execute_remaining_button = QtWidgets.QPushButton("执行剩余")
    execute_remaining_button.setToolTip("执行剩余序列（叶子步骤：从此步到末尾；事件流根：执行剩余事件流）")
    # 执行入口仅在精简模式下显示，完整模式隐藏（由面板逻辑控制）
    execute_button.setVisible(False)
    execute_remaining_button.setVisible(False)

    pause_button = QtWidgets.QPushButton("暂停")
    resume_button = QtWidgets.QPushButton("继续")
    stop_button = QtWidgets.QPushButton("终止")
    stop_button.setToolTip("终止当前执行（可随时点击）")

    next_step_button = QtWidgets.QPushButton("下一步")
    next_step_button.setToolTip("单步执行下一步：点击后进入单步，先暂停；再点一次执行一步并在下一步前自动暂停")

    # 检查当前页面（截图→识别→叠加展示）
    inspect_button = QtWidgets.QPushButton("检查")
    inspect_button.setToolTip("检查当前页面（截图+识别+叠加）")

    # 匹配并定位镜头
    match_focus_button = QtWidgets.QPushButton("定位")
    match_focus_button.setToolTip("对外部编辑器进行一次识别匹配，并将程序节点图镜头定位到对应区域")

    # 布局：
    # - 完整模式：第一行“终止 + 检查 + 定位”，第二行“暂停 + 继续 + 下一步”
    # - 精简模式：第一行“执行 + 执行剩余 + 终止”，第二行隐藏
    # 为了在两种模式间复用同一行高度，使用两个“占位堆栈”在同一格切换显示不同按钮。
    primary_left_stack = QtWidgets.QStackedWidget()
    primary_left_stack.setObjectName("monitorPrimaryLeftStack")
    primary_left_stack.setSizePolicy(
        QtWidgets.QSizePolicy.Policy.Expanding,
        QtWidgets.QSizePolicy.Policy.Fixed,
    )
    primary_left_stack.addWidget(inspect_button)
    primary_left_stack.addWidget(execute_button)
    # 默认完整模式：显示“检查”
    primary_left_stack.setCurrentWidget(inspect_button)

    primary_middle_stack = QtWidgets.QStackedWidget()
    primary_middle_stack.setObjectName("monitorPrimaryMiddleStack")
    primary_middle_stack.setSizePolicy(
        QtWidgets.QSizePolicy.Policy.Expanding,
        QtWidgets.QSizePolicy.Policy.Fixed,
    )
    primary_middle_stack.addWidget(match_focus_button)
    primary_middle_stack.addWidget(execute_remaining_button)
    # 默认完整模式：显示“定位”
    primary_middle_stack.setCurrentWidget(match_focus_button)

    controls_layout.addWidget(stop_button, 0, 0)
    controls_layout.addWidget(primary_left_stack, 0, 1)
    controls_layout.addWidget(primary_middle_stack, 0, 2)

    controls_layout.addWidget(pause_button, 1, 0)
    controls_layout.addWidget(resume_button, 1, 1)
    controls_layout.addWidget(next_step_button, 1, 2)

    for column_index in range(3):
        controls_layout.setColumnStretch(column_index, 1)

    scroll_layout.addWidget(controls_widget)

    # 测试功能：不在面板内展开，避免改变窗口最小尺寸导致“阻止缩小/触发自动变大”。
    # 改为单一菜单按钮：点击弹出 QMenu，所有测试入口都在菜单中。
    tests_widget = QtWidgets.QWidget()
    tests_widget.setObjectName("monitorTestsSection")
    tests_layout = QtWidgets.QHBoxLayout(tests_widget)
    tests_layout.setContentsMargins(0, 0, 0, 0)
    tests_layout.setSpacing(6)

    tests_menu_button = QtWidgets.QToolButton()
    tests_menu_button.setObjectName("monitorTestsMenuButton")
    tests_menu_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    tests_menu_button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
    tests_menu_button.setArrowType(Qt.ArrowType.DownArrow)
    tests_menu_button.setText("测试工具")
    tests_menu_button.setToolTip("调试/排障测试入口（点击打开菜单）")
    tests_menu_button.setSizePolicy(
        QtWidgets.QSizePolicy.Policy.Expanding,
        QtWidgets.QSizePolicy.Policy.Fixed,
    )

    tests_menu = QtWidgets.QMenu(tests_menu_button)
    tests_menu.setToolTipsVisible(True)

    test_ocr_action = QtGui.QAction("文字OCR", tests_menu)
    test_ocr_action.setToolTip("对顶部标签栏或指定区域执行一次 OCR，并在监控面板叠加展示识别结果")
    tests_menu.addAction(test_ocr_action)

    test_settings_action = QtGui.QAction("Settings扫描", tests_menu)
    test_settings_action.setToolTip("扫描当前图中节点的 Settings 行，标注并输出映射结果")
    tests_menu.addAction(test_settings_action)

    test_warning_action = QtGui.QAction("Warning模板", tests_menu)
    test_warning_action.setToolTip("在节点图区域内进行 Warning 模板匹配，展示命中结果")
    tests_menu.addAction(test_warning_action)

    test_ocr_zoom_action = QtGui.QAction("OCR缩放", tests_menu)
    test_ocr_zoom_action.setToolTip("对节点图缩放区域执行 OCR，用于验证 50% 缩放识别链路")
    tests_menu.addAction(test_ocr_zoom_action)

    test_nodes_action = QtGui.QAction("节点识别", tests_menu)
    test_nodes_action.setToolTip("对当前画面进行节点识别并叠加边框与中文标题")
    tests_menu.addAction(test_nodes_action)

    test_ports_action = QtGui.QAction("端口识别", tests_menu)
    test_ports_action.setToolTip("为识别出的每个节点列出端口并叠加显示（含 kind/side/index）")
    tests_menu.addAction(test_ports_action)

    test_ports_deep_action = QtGui.QAction("端口深度识别", tests_menu)
    test_ports_deep_action.setToolTip(
        "在端口识别基础上列出置信度≥70%的所有模板命中，包括被去重抑制的候选，并在标签中标注“因XXX被排除”原因"
    )
    tests_menu.addAction(test_ports_deep_action)

    test_settings_tpl_action = QtGui.QAction("Settings模板", tests_menu)
    test_settings_tpl_action.setToolTip("在节点图区域内匹配 Settings 按钮模板")
    tests_menu.addAction(test_settings_tpl_action)

    test_add_action = QtGui.QAction("Add模板", tests_menu)
    test_add_action.setToolTip("在节点图区域内匹配 Add / Add_Multi 模板")
    tests_menu.addAction(test_add_action)

    test_search_action = QtGui.QAction("搜索框模板", tests_menu)
    test_search_action.setToolTip("在窗口内匹配搜索框相关模板（search / search2）")
    tests_menu.addAction(test_search_action)

    test_window_strict_action = QtGui.QAction("仅窗口截图", tests_menu)
    test_window_strict_action.setToolTip(
        "使用实验性的仅窗口截图方式（PrintWindow），在尽量避免遮挡的前提下抓取一帧并展示到监控面板"
    )
    tests_menu.addAction(test_window_strict_action)

    tests_menu_button.setMenu(tests_menu)
    tests_layout.addWidget(tests_menu_button)
    tests_layout.addStretch(1)
    scroll_layout.addWidget(tests_widget)

    # 拖拽测试区：压缩占用高度（从 4 行收敛到 3 行）
    drag_widget = QtWidgets.QGroupBox("拖拽测试")
    drag_widget.setObjectName("monitorDragTestsGroup")
    drag_layout = QtWidgets.QGridLayout(drag_widget)
    drag_layout.setContentsMargins(0, 0, 0, 0)
    drag_layout.setHorizontalSpacing(6)
    drag_layout.setVerticalSpacing(4)

    drag_origin_title_label = QtWidgets.QLabel("中心:")
    drag_origin_title_label.setProperty("muted", "true")

    drag_origin_label = QtWidgets.QLabel("未定位")
    drag_origin_label.setToolTip("最近一次“定位镜头”得到的程序视口中心坐标")
    drag_origin_label.setWordWrap(True)

    drag_target_x_title_label = QtWidgets.QLabel("X:")
    drag_target_x_title_label.setProperty("muted", "true")
    drag_target_x_input = QtWidgets.QLineEdit()
    drag_target_x_input.setPlaceholderText("程序X")
    drag_target_x_input.setMaximumWidth(120)

    drag_target_y_title_label = QtWidgets.QLabel("Y:")
    drag_target_y_title_label.setProperty("muted", "true")
    drag_target_y_input = QtWidgets.QLineEdit()
    drag_target_y_input.setPlaceholderText("程序Y")
    drag_target_y_input.setMaximumWidth(120)

    drag_layout.addWidget(drag_origin_title_label, 0, 0)
    drag_layout.addWidget(drag_origin_label, 0, 1, 1, 3)
    drag_layout.addWidget(drag_target_x_title_label, 1, 0)
    drag_layout.addWidget(drag_target_x_input, 1, 1)
    drag_layout.addWidget(drag_target_y_title_label, 1, 2)
    drag_layout.addWidget(drag_target_y_input, 1, 3)

    drag_button_row_widget = QtWidgets.QWidget()
    drag_button_row = QtWidgets.QHBoxLayout(drag_button_row_widget)
    drag_button_row.setContentsMargins(0, 0, 0, 0)
    drag_button_row.setSpacing(6)

    drag_to_target_button = QtWidgets.QPushButton("拖拽到点")
    drag_to_target_button.setToolTip("使用执行步骤相同的画布拖拽逻辑，将视口平移到指定程序坐标附近")
    drag_button_row.addWidget(drag_to_target_button)

    drag_left_button = QtWidgets.QPushButton("左拖")
    drag_left_button.setToolTip("以当前中心为基准，向左侧执行一次拖拽测试（步长可通过目标X控制）")
    drag_button_row.addWidget(drag_left_button)

    drag_right_button = QtWidgets.QPushButton("右拖")
    drag_right_button.setToolTip("以当前中心为基准，向右侧执行一次拖拽测试（步长可通过目标X控制）")
    drag_button_row.addWidget(drag_right_button)

    drag_button_row.addStretch(1)
    drag_layout.addWidget(drag_button_row_widget, 2, 0, 1, 4)
    drag_layout.setColumnStretch(0, 0)
    drag_layout.setColumnStretch(1, 1)
    drag_layout.setColumnStretch(2, 0)
    drag_layout.setColumnStretch(3, 1)

    scroll_layout.addWidget(drag_widget)

    # 日志：搜索与筛选行
    filters_widget = QtWidgets.QWidget()
    filters_layout = QtWidgets.QVBoxLayout(filters_widget)
    filters_layout.setContentsMargins(0, 0, 0, 0)
    filters_layout.setSpacing(6)

    # 搜索与筛选拆两行：窄宽度下优先保证搜索框可见
    search_row_widget = QtWidgets.QWidget()
    search_row = QtWidgets.QHBoxLayout(search_row_widget)
    search_row.setContentsMargins(0, 0, 0, 0)
    search_row.setSpacing(6)
    log_search_input = QtWidgets.QLineEdit()
    log_search_input.setPlaceholderText("搜索日志文本…")
    search_row.addWidget(QtWidgets.QLabel("搜索:"))
    search_row.addWidget(log_search_input, 1)

    log_filter_combo = QtWidgets.QComboBox()
    log_filter_combo.addItems([
        "全部",
        "仅鼠标操作",
        "仅点击",
        "仅拖拽",
        "仅识别/视觉",
        "仅OCR",
        "仅截图",
        "仅等待",
        "仅连接",
        "仅创建",
        "仅参数配置",
        "仅回退/重试",
        "仅校准/视口",
        "仅步骤摘要",
        "仅成功",
        "仅失败",
    ])
    log_filter_combo.setMinimumWidth(0)
    log_filter_combo.setSizePolicy(
        QtWidgets.QSizePolicy.Policy.Expanding,
        QtWidgets.QSizePolicy.Policy.Fixed,
    )

    log_clear_button = QtWidgets.QPushButton("清空")
    log_clear_button.setToolTip("清空日志显示（不影响已记录的原始日志数据）")
    search_row.addWidget(log_clear_button)
    filters_layout.addWidget(search_row_widget)

    filter_type_row_widget = QtWidgets.QWidget()
    filter_type_row = QtWidgets.QHBoxLayout(filter_type_row_widget)
    filter_type_row.setContentsMargins(0, 0, 0, 0)
    filter_type_row.setSpacing(6)
    filter_type_row.addWidget(QtWidgets.QLabel("筛选:"))
    filter_type_row.addWidget(log_filter_combo, 1)
    filters_layout.addWidget(filter_type_row_widget)

    # 执行事件过滤行（结构化视图）
    event_filter_row_widget = QtWidgets.QWidget()
    event_filter_row = QtWidgets.QHBoxLayout(event_filter_row_widget)
    event_filter_row.setContentsMargins(0, 0, 0, 0)
    event_filter_row.setSpacing(6)
    event_filter_label = QtWidgets.QLabel("执行事件:")
    event_filter_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
    event_filter_row.addWidget(event_filter_label)
    event_errors_only_checkbox = QtWidgets.QCheckBox("仅错误/警告")
    event_filter_row.addWidget(event_errors_only_checkbox)
    event_filter_row.addStretch(1)
    filters_layout.addWidget(event_filter_row_widget)

    scroll_layout.addWidget(filters_widget)

    # 日志正文与执行事件表格：垂直分隔
    # 注意：QSplitter.setCollapsible(index, ...) 只能在 addWidget 之后调用，
    # 否则会在控制台输出 "QSplitter::setCollapsible: Index X out of range" 警告。
    log_splitter = QtWidgets.QSplitter(Qt.Orientation.Vertical)
    log_splitter.setChildrenCollapsible(True)
    log_splitter.setMinimumHeight(0)

    # 执行事件表格
    events_table = QtWidgets.QTableView()
    events_table.setAlternatingRowColors(True)
    events_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    events_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
    header = events_table.horizontalHeader()
    if header is not None:
        header.setStretchLastSection(True)
    palette = events_table.palette()
    palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(Colors.BG_CARD))
    palette.setColor(
        QtGui.QPalette.ColorRole.AlternateBase,
        QtGui.QColor(Colors.BG_MAIN),
    )
    palette.setColor(
        QtGui.QPalette.ColorRole.Text,
        QtGui.QColor(Colors.TEXT_PRIMARY),
    )
    palette.setColor(
        QtGui.QPalette.ColorRole.Highlight,
        QtGui.QColor(Colors.BG_SELECTED),
    )
    palette.setColor(
        QtGui.QPalette.ColorRole.HighlightedText,
        QtGui.QColor(Colors.TEXT_PRIMARY),
    )
    events_table.setPalette(palette)
    events_table.setStyleSheet(ThemeManager.table_style())
    events_table.setMinimumHeight(0)
    log_splitter.addWidget(events_table)

    # 日志正文（支持可点击锚点）
    log_text = QtWidgets.QTextBrowser()
    # 禁用内部与外部的默认跳转，改由 anchorClicked 信号统一处理
    log_text.setOpenLinks(False)
    log_text.setOpenExternalLinks(False)
    log_text.setAcceptRichText(True)
    log_text.setFont(ui_fonts.monospace_font(9))
    log_text.setMinimumHeight(0)
    log_splitter.addWidget(log_text)
    # 现在 splitter 已有两个 child，允许折叠设置才是有效的
    log_splitter.setCollapsible(0, True)
    log_splitter.setCollapsible(1, True)
    log_splitter.setStretchFactor(0, 3)
    log_splitter.setStretchFactor(1, 2)
    scroll_layout.addWidget(log_splitter, 1)

    monitor_scroll_area.setWidget(scroll_content_widget)
    layout.addWidget(monitor_scroll_area, 1)

    # 初始按钮状态
    execute_button.setEnabled(True)
    execute_remaining_button.setEnabled(True)
    pause_button.setEnabled(False)
    resume_button.setEnabled(False)
    next_step_button.setEnabled(False)
    stop_button.setEnabled(False)

    # 样式：执行入口突出，其余为次按钮；终止使用警示色
    execute_button.setProperty("kind", "primary")
    execute_remaining_button.setProperty("kind", "primary")
    stop_button.setProperty("kind", "danger")

    secondary_buttons = [
        compact_mode_button,
        pause_button,
        resume_button,
        next_step_button,
        inspect_button,
        match_focus_button,
        drag_to_target_button,
        drag_left_button,
        drag_right_button,
        log_clear_button,
    ]
    for button in secondary_buttons:
        if isinstance(button, QtWidgets.QAbstractButton):
            button.setProperty("kind", "secondary")
            button.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )

    # 让关键 label 在窄宽度下优先占空间，减少截断
    drag_origin_label.setSizePolicy(
        QtWidgets.QSizePolicy.Policy.Expanding,
        QtWidgets.QSizePolicy.Policy.Fixed,
    )

    # 应用紧凑化控件样式
    _apply_compact_controls_style(parent)

    # 返回所有控件引用
    return {
        "layout": layout,
        "status_label": status_label,
        "progress_label": progress_label,
        "compact_mode_button": compact_mode_button,
        "step_context_label": step_context_label,
        "screenshot_label": screenshot_label,
        "controls_widget": controls_widget,
        "execute_button": execute_button,
        "execute_remaining_button": execute_remaining_button,
        "primary_left_stack": primary_left_stack,
        "primary_middle_stack": primary_middle_stack,
        "pause_button": pause_button,
        "resume_button": resume_button,
        "next_step_button": next_step_button,
        "stop_button": stop_button,
        "inspect_button": inspect_button,
        "match_focus_button": match_focus_button,
        "tests_widget": tests_widget,
        "tests_menu_button": tests_menu_button,
        "test_ocr_action": test_ocr_action,
        "test_settings_action": test_settings_action,
        "test_warning_action": test_warning_action,
        "test_ocr_zoom_action": test_ocr_zoom_action,
        "test_nodes_action": test_nodes_action,
        "test_ports_action": test_ports_action,
        "test_ports_deep_action": test_ports_deep_action,
        "test_settings_tpl_action": test_settings_tpl_action,
        "test_add_action": test_add_action,
        "test_search_action": test_search_action,
        "test_window_strict_action": test_window_strict_action,
        "drag_widget": drag_widget,
        "drag_origin_label": drag_origin_label,
        "drag_target_x_input": drag_target_x_input,
        "drag_target_y_input": drag_target_y_input,
        "drag_to_target_button": drag_to_target_button,
        "drag_left_button": drag_left_button,
        "drag_right_button": drag_right_button,
        "filters_widget": filters_widget,
        "log_search_input": log_search_input,
        "log_filter_combo": log_filter_combo,
        "log_clear_button": log_clear_button,
        "events_table": events_table,
        "event_errors_only_checkbox": event_errors_only_checkbox,
        "log_splitter": log_splitter,
        "log_text": log_text,
    }


def _apply_compact_controls_style(parent: QtWidgets.QWidget) -> None:
    """应用紧凑化控件样式，避免按钮文本被挤压"""
    parent.setStyleSheet(
        f"""
        {ThemeManager.group_box_style()}

        ExecutionMonitorPanel QPushButton {{
            padding: 2px 10px;
            font-size: 11px;
            min-height: 28px;
        }}

        /* 次按钮：用于大多数调试/测试入口，避免整面板全是“主按钮蓝色” */
        ExecutionMonitorPanel QPushButton[kind="secondary"] {{
            background-color: {Colors.BG_CARD};
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BORDER_LIGHT};
        }}
        ExecutionMonitorPanel QPushButton[kind="secondary"]:hover {{
            background-color: {Colors.BG_CARD_HOVER};
        }}
        ExecutionMonitorPanel QPushButton[kind="secondary"]:pressed {{
            background-color: {Colors.BG_SELECTED_HOVER};
        }}

        /* 主按钮：执行入口 */
        ExecutionMonitorPanel QPushButton[kind="primary"] {{
            background-color: {Colors.PRIMARY};
            color: {Colors.TEXT_ON_PRIMARY};
            border: none;
        }}
        ExecutionMonitorPanel QPushButton[kind="primary"]:hover {{
            background-color: {Colors.PRIMARY_DARK};
        }}
        ExecutionMonitorPanel QPushButton[kind="primary"]:pressed {{
            background-color: {Colors.PRIMARY_DARK};
        }}

        /* 警示按钮：终止 */
        ExecutionMonitorPanel QPushButton[kind="danger"] {{
            background-color: {Colors.ERROR};
            color: {Colors.TEXT_ON_PRIMARY};
            border: none;
        }}
        ExecutionMonitorPanel QPushButton[kind="danger"]:hover {{
            background-color: {Colors.ERROR_LIGHT};
        }}
        ExecutionMonitorPanel QPushButton[kind="danger"]:pressed {{
            background-color: {Colors.ERROR};
        }}

        /* Disabled：无效操作一律置灰，避免“看似可点但无作用”，也解释了 disabled 状态下没有 hover。 */
        ExecutionMonitorPanel QPushButton:disabled {{
            background-color: {Colors.BG_DISABLED};
            color: {Colors.TEXT_DISABLED};
            border: 1px solid {Colors.BORDER_LIGHT};
        }}

        ExecutionMonitorPanel QCheckBox {{
            font-size: 11px;
            padding: 0px 4px;
            margin-left: 4px;
        }}

        ExecutionMonitorPanel QToolButton {{
            border: 1px solid {Colors.BORDER_LIGHT};
            background-color: {Colors.BG_CARD};
            color: {Colors.TEXT_PRIMARY};
            border-radius: 6px;
            padding: 4px 8px;
            font-size: 11px;
            font-weight: bold;
        }}
        ExecutionMonitorPanel QToolButton:hover {{
            background-color: {Colors.BG_CARD_HOVER};
        }}

        ExecutionMonitorPanel QLabel[muted="true"] {{
            color: {Colors.TEXT_SECONDARY};
        }}
        """
    )

