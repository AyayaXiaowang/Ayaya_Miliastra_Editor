# -*- coding: utf-8 -*-
"""
面板 UI 组装与样式
负责创建执行监控面板的所有控件、布局与紧凑化样式
"""

from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtCore import Qt

from app.ui.foundation import fonts as ui_fonts
from app.ui.foundation.theme_manager import Colors, ThemeManager


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
        - step_mode_checkbox: 单步模式复选框
        - stop_button: 终止按钮
        - inspect_button: 检查按钮
        - match_focus_button: 定位镜头按钮
        - test_ocr_button: 测试文字OCR按钮
        - test_settings_button: 测试Settings按钮
        - test_warning_button: 测试Warning按钮
        - test_ocr_zoom_button: OCR缩放按钮
        - test_nodes_button: 测试节点识别按钮
        - test_ports_button: 测试端口识别按钮
        - test_settings_tpl_button: 测试Settings模板按钮
        - test_add_button: 测试Add模板按钮
        - test_search_button: 测试搜索框模板按钮
        - test_window_strict_button: 测试仅窗口截图按钮
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
    layout.addWidget(step_context_label)

    # 截图
    screenshot_label = QtWidgets.QLabel()
    screenshot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    screenshot_label.setMinimumHeight(220)
    screenshot_label.setStyleSheet(
        f"border: 1px solid {Colors.BORDER_DARK}; background-color: {Colors.BG_DARK};"
    )
    screenshot_label.setText("等待截图...")
    screenshot_label.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))
    layout.addWidget(screenshot_label)

    # 控制区（栅格布局，便于窄宽度下不挤压按钮文本）
    controls_widget = QtWidgets.QWidget()
    controls_layout = QtWidgets.QGridLayout(controls_widget)
    controls_layout.setContentsMargins(0, 0, 0, 0)
    controls_layout.setHorizontalSpacing(6)
    controls_layout.setVerticalSpacing(6)

    pause_button = QtWidgets.QPushButton("暂停")
    resume_button = QtWidgets.QPushButton("继续")
    stop_button = QtWidgets.QPushButton("终止")

    step_mode_checkbox = QtWidgets.QCheckBox("单步")
    next_step_button = QtWidgets.QPushButton("下一步")

    # 检查当前页面（截图→识别→叠加展示）
    inspect_button = QtWidgets.QPushButton("检查")
    inspect_button.setToolTip("检查当前页面（截图+识别+叠加）")

    # 匹配并定位镜头
    match_focus_button = QtWidgets.QPushButton("定位镜头")
    match_focus_button.setToolTip("对外部编辑器进行一次识别匹配，并将程序节点图镜头定位到对应区域")

    controls_layout.addWidget(pause_button, 0, 0)
    controls_layout.addWidget(resume_button, 0, 1)
    controls_layout.addWidget(stop_button, 0, 2)

    controls_layout.addWidget(step_mode_checkbox, 1, 0)
    controls_layout.addWidget(next_step_button, 1, 1)
    controls_layout.addWidget(inspect_button, 1, 2)
    controls_layout.addWidget(match_focus_button, 1, 3)
    controls_layout.setColumnStretch(4, 1)

    layout.addWidget(controls_widget)

    # 测试功能（识别类）：OCR / Settings / Warning
    tests_widget = QtWidgets.QWidget()
    tests_layout = QtWidgets.QVBoxLayout(tests_widget)
    tests_layout.setContentsMargins(0, 0, 0, 0)
    tests_layout.setSpacing(6)

    test_row_widget = QtWidgets.QWidget()
    test_row = QtWidgets.QHBoxLayout(test_row_widget)
    test_row.setContentsMargins(0, 0, 0, 0)
    test_row.setSpacing(6)
    test_ocr_button = QtWidgets.QPushButton("测试文字OCR")
    test_ocr_button.setToolTip("对顶部标签栏或指定区域执行一次 OCR，并在监控面板叠加展示识别结果")
    test_row.addWidget(test_ocr_button)

    test_settings_button = QtWidgets.QPushButton("测试Settings")
    test_settings_button.setToolTip("扫描当前图中节点的 Settings 行，标注并输出映射结果")
    test_row.addWidget(test_settings_button)

    test_warning_button = QtWidgets.QPushButton("测试Warning")
    test_warning_button.setToolTip("在节点图区域内进行 Warning 模板匹配，展示命中结果")
    test_row.addWidget(test_warning_button)
    tests_layout.addWidget(test_row_widget)

    # 扩展测试功能（第二行）
    test_row2_widget = QtWidgets.QWidget()
    test_row2 = QtWidgets.QHBoxLayout(test_row2_widget)
    test_row2.setContentsMargins(0, 0, 0, 0)
    test_row2.setSpacing(6)
    test_ocr_zoom_button = QtWidgets.QPushButton("OCR缩放")
    test_ocr_zoom_button.setToolTip("对节点图缩放区域执行 OCR，用于验证 50% 缩放识别链路")
    test_row2.addWidget(test_ocr_zoom_button)

    test_nodes_button = QtWidgets.QPushButton("测试节点识别")
    test_nodes_button.setToolTip("对当前画面进行节点识别并叠加边框与中文标题")
    test_row2.addWidget(test_nodes_button)

    test_ports_button = QtWidgets.QPushButton("测试端口识别")
    test_ports_button.setToolTip("为识别出的每个节点列出端口并叠加显示（含 kind/side/index）")
    test_row2.addWidget(test_ports_button)

    test_ports_deep_button = QtWidgets.QPushButton("深度测试端口识别")
    test_ports_deep_button.setToolTip(
        "在端口识别基础上列出置信度≥70%的所有模板命中，包括被去重抑制的候选，并在标签中标注“因XXX被排除”原因"
    )
    test_row2.addWidget(test_ports_deep_button)
    tests_layout.addWidget(test_row2_widget)

    # 扩展测试功能（第三行：模板类 + 截图测试）
    test_row3_widget = QtWidgets.QWidget()
    test_row3 = QtWidgets.QHBoxLayout(test_row3_widget)
    test_row3.setContentsMargins(0, 0, 0, 0)
    test_row3.setSpacing(6)
    test_settings_tpl_button = QtWidgets.QPushButton("测试Settings模板")
    test_settings_tpl_button.setToolTip("在节点图区域内匹配 Settings 按钮模板")
    test_row3.addWidget(test_settings_tpl_button)

    test_add_button = QtWidgets.QPushButton("测试Add模板")
    test_add_button.setToolTip("在节点图区域内匹配 Add / Add_Multi 模板")
    test_row3.addWidget(test_add_button)

    test_search_button = QtWidgets.QPushButton("测试搜索框模板")
    test_search_button.setToolTip("在窗口内匹配搜索框相关模板（search / search2）")
    test_row3.addWidget(test_search_button)

    test_window_strict_button = QtWidgets.QPushButton("测试只截取程序")
    test_window_strict_button.setToolTip(
        "使用实验性的仅窗口截图方式（PrintWindow），在尽量避免遮挡的前提下抓取一帧并展示到监控面板"
    )
    test_row3.addWidget(test_window_strict_button)
    tests_layout.addWidget(test_row3_widget)

    layout.addWidget(tests_widget)

    # 拖拽测试区：第一行展示当前视口中心坐标与目标坐标输入，第二行放置拖拽控制按钮
    drag_widget = QtWidgets.QWidget()
    drag_layout = QtWidgets.QVBoxLayout(drag_widget)
    drag_layout.setContentsMargins(0, 0, 0, 0)
    drag_layout.setSpacing(6)

    drag_row_widget = QtWidgets.QWidget()
    drag_row = QtWidgets.QHBoxLayout(drag_row_widget)
    drag_row.setContentsMargins(0, 0, 0, 0)
    drag_row.setSpacing(6)
    drag_row.addWidget(QtWidgets.QLabel("拖拽测试:"))
    drag_origin_label = QtWidgets.QLabel("当前中心: 未定位")
    drag_origin_label.setMinimumWidth(160)
    drag_origin_label.setToolTip("最近一次“定位镜头”得到的程序视口中心坐标")
    drag_row.addWidget(drag_origin_label)

    drag_row.addWidget(QtWidgets.QLabel("目标X:"))
    drag_target_x_input = QtWidgets.QLineEdit()
    drag_target_x_input.setPlaceholderText("程序X")
    drag_target_x_input.setFixedWidth(80)
    drag_row.addWidget(drag_target_x_input)

    drag_row.addWidget(QtWidgets.QLabel("目标Y:"))
    drag_target_y_input = QtWidgets.QLineEdit()
    drag_target_y_input.setPlaceholderText("程序Y")
    drag_target_y_input.setFixedWidth(80)
    drag_row.addWidget(drag_target_y_input)

    drag_layout.addWidget(drag_row_widget)

    drag_button_row_widget = QtWidgets.QWidget()
    drag_button_row = QtWidgets.QHBoxLayout(drag_button_row_widget)
    drag_button_row.setContentsMargins(0, 0, 0, 0)
    drag_button_row.setSpacing(6)
    drag_to_target_button = QtWidgets.QPushButton("拖拽到坐标")
    drag_to_target_button.setToolTip("使用执行步骤相同的画布拖拽逻辑，将视口平移到指定程序坐标附近")
    drag_button_row.addWidget(drag_to_target_button)

    drag_left_button = QtWidgets.QPushButton("向左拖拽")
    drag_left_button.setToolTip("以当前中心为基准，向左侧执行一次拖拽测试（步长可通过目标X控制）")
    drag_button_row.addWidget(drag_left_button)

    drag_right_button = QtWidgets.QPushButton("向右拖拽")
    drag_right_button.setToolTip("以当前中心为基准，向右侧执行一次拖拽测试（步长可通过目标X控制）")
    drag_button_row.addWidget(drag_right_button)

    drag_button_row.addStretch(1)
    drag_layout.addWidget(drag_button_row_widget)

    layout.addWidget(drag_widget)

    # 日志：搜索与筛选行
    filters_widget = QtWidgets.QWidget()
    filters_layout = QtWidgets.QVBoxLayout(filters_widget)
    filters_layout.setContentsMargins(0, 0, 0, 0)
    filters_layout.setSpacing(6)

    filter_row_widget = QtWidgets.QWidget()
    filter_row = QtWidgets.QHBoxLayout(filter_row_widget)
    filter_row.setContentsMargins(0, 0, 0, 0)
    filter_row.setSpacing(6)
    log_search_input = QtWidgets.QLineEdit()
    log_search_input.setPlaceholderText("搜索日志文本…")
    filter_row.addWidget(QtWidgets.QLabel("搜索:"))
    filter_row.addWidget(log_search_input, 1)

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
    filter_row.addWidget(QtWidgets.QLabel("筛选:"))
    filter_row.addWidget(log_filter_combo)

    log_clear_button = QtWidgets.QPushButton("清空显示")
    filter_row.addWidget(log_clear_button)
    filters_layout.addWidget(filter_row_widget)

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

    layout.addWidget(filters_widget)

    # 日志正文与执行事件表格：垂直分隔
    log_splitter = QtWidgets.QSplitter(Qt.Orientation.Vertical)

    # 执行事件表格
    events_table = QtWidgets.QTableView()
    events_table.setAlternatingRowColors(True)
    events_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    events_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
    events_table.horizontalHeader().setStretchLastSection(True)
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
    log_splitter.addWidget(events_table)

    # 日志正文（支持可点击锚点）
    log_text = QtWidgets.QTextBrowser()
    # 禁用内部与外部的默认跳转，改由 anchorClicked 信号统一处理
    log_text.setOpenLinks(False)
    log_text.setOpenExternalLinks(False)
    log_text.setAcceptRichText(True)
    log_text.setFont(ui_fonts.monospace_font(9))
    log_splitter.addWidget(log_text)
    log_splitter.setStretchFactor(0, 3)
    log_splitter.setStretchFactor(1, 2)
    layout.addWidget(log_splitter, 1)

    # 初始按钮状态
    pause_button.setEnabled(False)
    resume_button.setEnabled(False)
    next_step_button.setEnabled(False)
    step_mode_checkbox.setEnabled(True)
    stop_button.setEnabled(False)

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
        "pause_button": pause_button,
        "resume_button": resume_button,
        "next_step_button": next_step_button,
        "step_mode_checkbox": step_mode_checkbox,
        "stop_button": stop_button,
        "inspect_button": inspect_button,
        "match_focus_button": match_focus_button,
        "tests_widget": tests_widget,
        "test_ocr_button": test_ocr_button,
        "test_settings_button": test_settings_button,
        "test_warning_button": test_warning_button,
        "test_ocr_zoom_button": test_ocr_zoom_button,
        "test_nodes_button": test_nodes_button,
        "test_ports_button": test_ports_button,
        "test_ports_deep_button": test_ports_deep_button,
        "test_settings_tpl_button": test_settings_tpl_button,
        "test_add_button": test_add_button,
        "test_search_button": test_search_button,
        "test_window_strict_button": test_window_strict_button,
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
        """
        ExecutionMonitorPanel QPushButton {
            padding: 2px 8px;
            font-size: 11px;
            min-height: 28px;
        }
        ExecutionMonitorPanel QCheckBox {
            font-size: 11px;
            padding: 0px 4px;
            margin-left: 4px;
        }
        """
    )

