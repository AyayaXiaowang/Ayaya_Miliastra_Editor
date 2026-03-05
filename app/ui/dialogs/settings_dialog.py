"""设置对话框 - 用户友好的设置界面"""

from __future__ import annotations

import sys

from PyQt6 import QtCore, QtGui, QtWidgets

from app.runtime.services.graph_data_service import get_shared_graph_data_service
from app.ui.dialogs.settings_dialog_pages_mixin import SettingsDialogPagesMixin
from app.ui.foundation.base_widgets import BaseDialog
from app.ui.foundation.theme_manager import ThemeManager, Sizes
from app.ui.graph.library_mixins import ConfirmDialogMixin
from engine.configs.settings import settings


class SettingsDialog(SettingsDialogPagesMixin, BaseDialog, ConfirmDialogMixin):
    """设置对话框

    提供图形化界面让用户修改程序设置。
    所有设置更改立即生效并保存到配置文件。
    """

    def __init__(self, parent=None):
        super().__init__(
            title="程序设置",
            width=920,
            height=640,
            parent=parent,
        )
        self.setMinimumWidth(880)
        self.setMinimumHeight(600)

        self._build_content()
        self._load_current_settings()

    def _apply_styles(self) -> None:
        """应用主题样式"""
        base_style = (
            ThemeManager.dialog_surface_style(include_tables=False)
            + ThemeManager.list_style()
            + ThemeManager.left_panel_style()
            + ThemeManager.splitter_style()
            + ThemeManager.group_box_style()
        )
        self.setStyleSheet(base_style)

    def _build_content(self) -> None:
        """设置UI布局"""
        layout = self.content_layout

        # 标题
        title_label = QtWidgets.QLabel("程序设置")
        title_label.setStyleSheet(f"{ThemeManager.heading(level=1)} padding: 10px;")
        layout.addWidget(title_label)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # 左侧：分类导航
        nav = QtWidgets.QWidget()
        nav_layout = QtWidgets.QVBoxLayout(nav)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(Sizes.SPACING_MEDIUM)

        nav_title = QtWidgets.QLabel("分类")
        nav_title.setStyleSheet(ThemeManager.heading(level=3))
        nav_layout.addWidget(nav_title)

        self.category_list = QtWidgets.QListWidget()
        # 复用全局左侧面板（leftPanel）选中态样式，避免在对话框内写局部 QSS 造成分叉。
        self.category_list.setObjectName("leftPanel")
        self.category_list.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.category_list.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.category_list.setVerticalScrollMode(
            QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.category_list.setMinimumWidth(180)
        self.category_list.setMaximumWidth(240)
        nav_layout.addWidget(self.category_list, 1)

        nav_hint = QtWidgets.QLabel("修改后点击右下角「确定」保存。")
        nav_hint.setWordWrap(True)
        nav_hint.setStyleSheet(ThemeManager.hint_text_style())
        nav_layout.addWidget(nav_hint)

        splitter.addWidget(nav)

        # 右侧：分组页面
        self.pages_stack = QtWidgets.QStackedWidget()
        splitter.addWidget(self.pages_stack)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([210, 700])
        layout.addWidget(splitter, 1)

        self._build_settings_pages()
        self.category_list.currentRowChanged.connect(self.pages_stack.setCurrentIndex)
        if self.category_list.count() > 0:
            self.category_list.setCurrentRow(0)

        # 底部按钮
        button_layout = QtWidgets.QHBoxLayout()

        # 重置为默认值按钮
        reset_button = QtWidgets.QPushButton("重置为默认值")
        reset_button.clicked.connect(self._reset_to_defaults)
        button_layout.addWidget(reset_button)

        # 清除所有缓存按钮
        clear_cache_button = QtWidgets.QPushButton("清除所有缓存")
        clear_cache_button.setToolTip(
            "清除内存缓存与磁盘上的节点图缓存（app/runtime/cache/graph_cache）"
        )
        clear_cache_button.clicked.connect(self._clear_all_caches)
        button_layout.addWidget(clear_cache_button)

        button_layout.addStretch()

        layout.addLayout(button_layout)

        # 安装滚轮保护占位（具体逻辑由 ThemeManager.apply_app_style 提供的全局过滤器统一处理）
        self._install_wheel_guards()

    def _load_current_settings(self) -> None:
        """加载当前设置到UI"""
        self.tight_block_spacing_checkbox.setChecked(
            getattr(settings, "LAYOUT_TIGHT_BLOCK_PACKING", True)
        )

        x_percent = int(getattr(settings, "LAYOUT_NODE_SPACING_X_PERCENT", 100))
        y_percent = int(getattr(settings, "LAYOUT_NODE_SPACING_Y_PERCENT", 100))
        if x_percent < 10:
            x_percent = 10
        if x_percent > 200:
            x_percent = 200
        if y_percent < 10:
            y_percent = 10
        if y_percent > 200:
            y_percent = 200
        self.layout_spacing_x_slider.setValue(x_percent)
        self.layout_spacing_y_slider.setValue(y_percent)

        self.layout_debug_checkbox.setChecked(settings.LAYOUT_DEBUG_PRINT)
        self.layout_y_debug_overlay_checkbox.setChecked(
            getattr(settings, "SHOW_LAYOUT_Y_DEBUG", False)
        )
        self.graph_ui_verbose_checkbox.setChecked(getattr(settings, "GRAPH_UI_VERBOSE", False))
        self.two_row_field_debug_checkbox.setChecked(
            bool(getattr(settings, "UI_TWO_ROW_FIELD_DEBUG_PRINT", False))
        )
        self.node_loading_checkbox.setChecked(settings.NODE_LOADING_VERBOSE)
        self.validator_verbose_checkbox.setChecked(settings.VALIDATOR_VERBOSE)
        self.dsl_parser_checkbox.setChecked(settings.GRAPH_PARSER_VERBOSE)
        self.dsl_generator_checkbox.setChecked(settings.GRAPH_GENERATOR_VERBOSE)
        self.real_exec_verbose_checkbox.setChecked(settings.REAL_EXEC_VERBOSE)
        gia_node_pos_scale = float(getattr(settings, "UGC_GIA_NODE_POS_SCALE", 2.0) or 2.0)
        if gia_node_pos_scale < 0.1:
            gia_node_pos_scale = 0.1
        if gia_node_pos_scale > 200.0:
            gia_node_pos_scale = 200.0
        self.ugc_gia_node_pos_scale_spinbox.setValue(float(gia_node_pos_scale))
        self.todo_merge_checkbox.setChecked(settings.TODO_MERGE_CONNECTION_STEPS)
        self.todo_event_flow_lazy_load_checkbox.setChecked(
            bool(getattr(settings, "TODO_EVENT_FLOW_LAZY_LOAD_ENABLED", True))
        )
        self.data_node_copy_checkbox.setChecked(settings.DATA_NODE_CROSS_BLOCK_COPY)

        self.local_var_relay_checkbox.setChecked(
            bool(getattr(settings, "LAYOUT_AUTO_INSERT_LOCAL_VAR_RELAY", False))
        )
        relay_distance = int(
            getattr(settings, "LAYOUT_LOCAL_VAR_RELAY_MAX_BLOCK_DISTANCE", 5) or 5
        )
        if relay_distance < 3:
            relay_distance = 3
        if relay_distance > 10:
            relay_distance = 10
        self.local_var_relay_length_slider.setValue(relay_distance)
        self._update_local_var_relay_controls_enabled()

        node_alpha_percent = int(
            float(getattr(settings, "GRAPH_NODE_CONTENT_ALPHA", 0.7)) * 100.0
        )
        if node_alpha_percent < 10:
            node_alpha_percent = 10
        if node_alpha_percent > 100:
            node_alpha_percent = 100
        self.graph_node_opacity_slider.setValue(node_alpha_percent)

        # 画布外观：basic blocks
        self.show_basic_blocks_checkbox.setChecked(bool(getattr(settings, "SHOW_BASIC_BLOCKS", True)))
        basic_block_alpha_percent = int(float(getattr(settings, "BASIC_BLOCK_ALPHA", 0.2)) * 100.0)
        if basic_block_alpha_percent < 0:
            basic_block_alpha_percent = 0
        if basic_block_alpha_percent > 100:
            basic_block_alpha_percent = 100
        self.basic_block_alpha_slider.setValue(basic_block_alpha_percent)

        # 画布性能：常量控件虚拟化 + 快速预览 + 自动适配全图
        self.graph_constant_widget_virtualization_checkbox.setChecked(
            bool(getattr(settings, "GRAPH_CONSTANT_WIDGET_VIRTUALIZATION_ENABLED", True))
        )
        self.graph_fast_preview_checkbox.setChecked(
            bool(getattr(settings, "GRAPH_FAST_PREVIEW_ENABLED", False))
        )
        self.graph_fast_preview_node_threshold_spinbox.setValue(
            int(getattr(settings, "GRAPH_FAST_PREVIEW_NODE_THRESHOLD", 500) or 500)
        )
        self.graph_fast_preview_edge_threshold_spinbox.setValue(
            int(getattr(settings, "GRAPH_FAST_PREVIEW_EDGE_THRESHOLD", 900) or 900)
        )
        self.graph_auto_fit_all_checkbox.setChecked(
            bool(getattr(settings, "GRAPH_AUTO_FIT_ALL_ENABLED", False))
        )
        self.graph_perf_panel_checkbox.setChecked(
            bool(getattr(settings, "GRAPH_PERF_PANEL_ENABLED", False))
        )

        # 全局性能监控（卡顿定位）
        self.app_perf_monitor_enabled_checkbox.setChecked(
            bool(getattr(settings, "APP_PERF_MONITOR_ENABLED", False))
        )
        self.app_perf_overlay_enabled_checkbox.setChecked(
            bool(getattr(settings, "APP_PERF_OVERLAY_ENABLED", False))
        )
        self.app_perf_capture_stacks_checkbox.setChecked(
            bool(getattr(settings, "APP_PERF_CAPTURE_STACKS_ENABLED", True))
        )
        stall_ms = int(getattr(settings, "APP_PERF_STALL_THRESHOLD_MS", 250) or 250)
        if stall_ms < 100:
            stall_ms = 100
        if stall_ms > 5000:
            stall_ms = 5000
        self.app_perf_stall_threshold_spinbox.setValue(stall_ms)

        # 画布 LOD（分层绘制）
        self.graph_lod_enabled_checkbox.setChecked(bool(getattr(settings, "GRAPH_LOD_ENABLED", True)))

        def _clamp_percent(value: int, *, min_value: int, max_value: int) -> int:
            v = int(value)
            if v < int(min_value):
                return int(min_value)
            if v > int(max_value):
                return int(max_value)
            return v

        self.graph_lod_node_details_slider.setValue(
            _clamp_percent(
                int(float(getattr(settings, "GRAPH_LOD_NODE_DETAILS_MIN_SCALE", 0.55)) * 100.0),
                min_value=1,
                max_value=100,
            )
        )
        self.graph_lod_node_title_slider.setValue(
            _clamp_percent(
                int(float(getattr(settings, "GRAPH_LOD_NODE_TITLE_MIN_SCALE", 0.28)) * 100.0),
                min_value=1,
                max_value=100,
            )
        )
        self.graph_lod_port_min_slider.setValue(
            _clamp_percent(
                int(float(getattr(settings, "GRAPH_LOD_PORT_MIN_SCALE", 0.30)) * 100.0),
                min_value=1,
                max_value=100,
            )
        )
        self.graph_lod_port_exit_slider.setValue(
            _clamp_percent(
                int(float(getattr(settings, "GRAPH_LOD_PORT_VISIBILITY_EXIT_SCALE", 0.33)) * 100.0),
                min_value=1,
                max_value=100,
            )
        )
        self.graph_lod_edge_min_slider.setValue(
            _clamp_percent(
                int(float(getattr(settings, "GRAPH_LOD_EDGE_MIN_SCALE", 0.22)) * 100.0),
                min_value=1,
                max_value=100,
            )
        )
        self.graph_lod_edge_exit_slider.setValue(
            _clamp_percent(
                int(float(getattr(settings, "GRAPH_LOD_EDGE_VISIBILITY_EXIT_SCALE", 0.24)) * 100.0),
                min_value=1,
                max_value=100,
            )
        )
        self.graph_lod_edge_hittest_slider.setValue(
            _clamp_percent(
                int(float(getattr(settings, "GRAPH_LOD_EDGE_HITTEST_MIN_SCALE", 0.28)) * 100.0),
                min_value=1,
                max_value=100,
            )
        )
        self.graph_grid_enabled_checkbox.setChecked(bool(getattr(settings, "GRAPH_GRID_ENABLED", True)))
        self.graph_pan_freeze_viewport_checkbox.setChecked(
            bool(getattr(settings, "GRAPH_PAN_FREEZE_VIEWPORT_ENABLED", False))
        )
        self.graph_zoom_freeze_viewport_checkbox.setChecked(
            bool(getattr(settings, "GRAPH_ZOOM_FREEZE_VIEWPORT_ENABLED", False))
        )
        self.graph_pan_hide_icons_checkbox.setChecked(
            bool(getattr(settings, "GRAPH_PAN_HIDE_ICONS_ENABLED", True))
        )
        self.graph_grid_min_px_spinbox.setValue(float(getattr(settings, "GRAPH_GRID_MIN_PX", 12.0) or 12.0))
        self.graph_block_overview_enabled_checkbox.setChecked(
            bool(getattr(settings, "GRAPH_BLOCK_OVERVIEW_ENABLED", True))
        )
        self.graph_block_overview_enter_slider.setValue(
            _clamp_percent(
                int(float(getattr(settings, "GRAPH_BLOCK_OVERVIEW_ENTER_SCALE", 0.10)) * 100.0),
                min_value=1,
                max_value=100,
            )
        )
        self.graph_block_overview_exit_slider.setValue(
            _clamp_percent(
                int(float(getattr(settings, "GRAPH_BLOCK_OVERVIEW_EXIT_SCALE", 0.12)) * 100.0),
                min_value=1,
                max_value=100,
            )
        )
        self.graph_block_overview_grid_min_px_spinbox.setValue(
            float(getattr(settings, "GRAPH_BLOCK_OVERVIEW_GRID_MIN_PX", 24.0) or 24.0)
        )
        self._update_graph_lod_controls_enabled()
        self._update_graph_grid_controls_enabled()
        # 界面主题模式
        current_theme_mode = getattr(settings, "UI_THEME_MODE", "auto")
        idx_theme = self.ui_theme_combo.findData(current_theme_mode)
        self.ui_theme_combo.setCurrentIndex(idx_theme if idx_theme != -1 else 0)
        # 加载步骤模式
        current_mode = getattr(settings, "TODO_GRAPH_STEP_MODE", "ai")
        idx = self.todo_mode_combo.findData(current_mode)
        if idx != -1:
            self.todo_mode_combo.setCurrentIndex(idx)
        else:
            fallback_idx = self.todo_mode_combo.findData("ai")
            self.todo_mode_combo.setCurrentIndex(fallback_idx if fallback_idx != -1 else 0)
        self.auto_save_spinbox.setValue(settings.AUTO_SAVE_INTERVAL)
        # 鼠标执行模式与混合参数
        current_mouse_mode = getattr(settings, "MOUSE_EXECUTION_MODE", "classic")
        idx2 = self.mouse_mode_combo.findData(current_mouse_mode)
        self.mouse_mode_combo.setCurrentIndex(idx2 if idx2 != -1 else 0)
        self.hybrid_steps_spinbox.setValue(int(getattr(settings, "MOUSE_HYBRID_STEPS", 40)))
        self.hybrid_step_sleep_spinbox.setValue(
            float(getattr(settings, "MOUSE_HYBRID_STEP_SLEEP", 0.008))
        )
        self._update_hybrid_controls_enabled()
        # 拖拽策略
        current_drag_mode = getattr(settings, "MOUSE_DRAG_MODE", "auto")
        idx3 = self.drag_mode_combo.findData(current_drag_mode)
        self.drag_mode_combo.setCurrentIndex(idx3 if idx3 != -1 else 0)

    def show_info(self, title: str, message: str) -> None:
        """使用 ConfirmDialogMixin 风格的提示弹窗接口。

        SettingsDialog 同时继承 BaseDialog 与 ConfirmDialogMixin，
        这里显式采用带标题的版本以统一交互文案。
        """
        ConfirmDialogMixin.show_info(self, title, message)

    def _reset_to_defaults(self) -> None:
        """重置为默认值"""
        if self.confirm("确认重置", "确定要将所有设置重置为默认值吗？"):
            settings.reset_to_defaults()
            self._load_current_settings()
            self.show_info("完成", "设置已重置为默认值")

    def _save_and_close(self) -> None:
        """保存设置并关闭对话框"""
        # 检查是否修改了需要重启的设置
        node_loading_changed = (
            self.node_loading_checkbox.isChecked() != settings.NODE_LOADING_VERBOSE
        )
        old_theme_mode = getattr(settings, "UI_THEME_MODE", "auto")

        # 记录“影响 GraphScene/图元装配结构”的旧值：
        # - 这类开关仅做 resync（缩放提示）是不够的，必须重建 GraphScene 才能立即生效；
        # - 典型：YDebug 叠加（禁用批量边层）、basic blocks、常量控件虚拟化、fast preview 等。
        old_scene_build_settings = {
            "SHOW_LAYOUT_Y_DEBUG": bool(getattr(settings, "SHOW_LAYOUT_Y_DEBUG", False)),
            "SHOW_BASIC_BLOCKS": bool(getattr(settings, "SHOW_BASIC_BLOCKS", True)),
            "GRAPH_CONSTANT_WIDGET_VIRTUALIZATION_ENABLED": bool(
                getattr(settings, "GRAPH_CONSTANT_WIDGET_VIRTUALIZATION_ENABLED", True)
            ),
            "GRAPH_FAST_PREVIEW_ENABLED": bool(getattr(settings, "GRAPH_FAST_PREVIEW_ENABLED", False)),
            "GRAPH_FAST_PREVIEW_NODE_THRESHOLD": int(
                getattr(settings, "GRAPH_FAST_PREVIEW_NODE_THRESHOLD", 500) or 500
            ),
            "GRAPH_FAST_PREVIEW_EDGE_THRESHOLD": int(
                getattr(settings, "GRAPH_FAST_PREVIEW_EDGE_THRESHOLD", 900) or 900
            ),
        }

        # 记录关键开关的旧值（用于触发一次性重载）
        old_cross_block_copy = bool(settings.DATA_NODE_CROSS_BLOCK_COPY)
        old_local_var_relay_enabled = bool(
            getattr(settings, "LAYOUT_AUTO_INSERT_LOCAL_VAR_RELAY", False)
        )
        old_local_var_relay_distance = int(
            getattr(settings, "LAYOUT_LOCAL_VAR_RELAY_MAX_BLOCK_DISTANCE", 5) or 5
        )

        # 应用设置
        settings.LAYOUT_TIGHT_BLOCK_PACKING = self.tight_block_spacing_checkbox.isChecked()
        settings.LAYOUT_NODE_SPACING_X_PERCENT = int(self.layout_spacing_x_slider.value())
        settings.LAYOUT_NODE_SPACING_Y_PERCENT = int(self.layout_spacing_y_slider.value())
        settings.LAYOUT_DEBUG_PRINT = self.layout_debug_checkbox.isChecked()
        settings.SHOW_LAYOUT_Y_DEBUG = self.layout_y_debug_overlay_checkbox.isChecked()
        settings.GRAPH_UI_VERBOSE = self.graph_ui_verbose_checkbox.isChecked()
        settings.UI_TWO_ROW_FIELD_DEBUG_PRINT = self.two_row_field_debug_checkbox.isChecked()
        settings.NODE_LOADING_VERBOSE = self.node_loading_checkbox.isChecked()
        settings.VALIDATOR_VERBOSE = self.validator_verbose_checkbox.isChecked()
        settings.GRAPH_PARSER_VERBOSE = self.dsl_parser_checkbox.isChecked()
        settings.GRAPH_GENERATOR_VERBOSE = self.dsl_generator_checkbox.isChecked()
        settings.REAL_EXEC_VERBOSE = self.real_exec_verbose_checkbox.isChecked()
        settings.UGC_GIA_NODE_POS_SCALE = float(self.ugc_gia_node_pos_scale_spinbox.value())
        settings.TODO_MERGE_CONNECTION_STEPS = self.todo_merge_checkbox.isChecked()
        settings.TODO_EVENT_FLOW_LAZY_LOAD_ENABLED = (
            self.todo_event_flow_lazy_load_checkbox.isChecked()
        )
        settings.DATA_NODE_CROSS_BLOCK_COPY = self.data_node_copy_checkbox.isChecked()
        settings.LAYOUT_AUTO_INSERT_LOCAL_VAR_RELAY = self.local_var_relay_checkbox.isChecked()
        settings.LAYOUT_LOCAL_VAR_RELAY_MAX_BLOCK_DISTANCE = int(
            self.local_var_relay_length_slider.value()
        )
        settings.GRAPH_NODE_CONTENT_ALPHA = float(self.graph_node_opacity_slider.value()) / 100.0

        # 画布外观：basic blocks
        settings.SHOW_BASIC_BLOCKS = bool(self.show_basic_blocks_checkbox.isChecked())
        settings.BASIC_BLOCK_ALPHA = float(self.basic_block_alpha_slider.value()) / 100.0

        # 画布性能：常量控件虚拟化 + 快速预览 + 自动适配全图
        settings.GRAPH_CONSTANT_WIDGET_VIRTUALIZATION_ENABLED = bool(
            self.graph_constant_widget_virtualization_checkbox.isChecked()
        )
        settings.GRAPH_FAST_PREVIEW_ENABLED = bool(self.graph_fast_preview_checkbox.isChecked())
        settings.GRAPH_FAST_PREVIEW_NODE_THRESHOLD = int(
            self.graph_fast_preview_node_threshold_spinbox.value()
        )
        settings.GRAPH_FAST_PREVIEW_EDGE_THRESHOLD = int(
            self.graph_fast_preview_edge_threshold_spinbox.value()
        )
        settings.GRAPH_AUTO_FIT_ALL_ENABLED = bool(self.graph_auto_fit_all_checkbox.isChecked())
        settings.GRAPH_PERF_PANEL_ENABLED = bool(self.graph_perf_panel_checkbox.isChecked())

        # 全局性能监控（卡顿定位）
        app_perf_overlay_enabled = bool(self.app_perf_overlay_enabled_checkbox.isChecked())
        app_perf_monitor_enabled = bool(self.app_perf_monitor_enabled_checkbox.isChecked()) or bool(
            app_perf_overlay_enabled
        )
        settings.APP_PERF_MONITOR_ENABLED = bool(app_perf_monitor_enabled)
        settings.APP_PERF_OVERLAY_ENABLED = bool(app_perf_overlay_enabled)
        settings.APP_PERF_STALL_THRESHOLD_MS = int(self.app_perf_stall_threshold_spinbox.value())
        settings.APP_PERF_CAPTURE_STACKS_ENABLED = bool(
            self.app_perf_capture_stacks_checkbox.isChecked()
        )

        # 画布 LOD（分层绘制）
        settings.GRAPH_LOD_ENABLED = bool(self.graph_lod_enabled_checkbox.isChecked())
        settings.GRAPH_LOD_NODE_DETAILS_MIN_SCALE = (
            float(self.graph_lod_node_details_slider.value()) / 100.0
        )
        settings.GRAPH_LOD_NODE_TITLE_MIN_SCALE = (
            float(self.graph_lod_node_title_slider.value()) / 100.0
        )
        port_enter_scale = float(self.graph_lod_port_min_slider.value()) / 100.0
        port_exit_scale = float(self.graph_lod_port_exit_slider.value()) / 100.0
        if port_exit_scale < port_enter_scale:
            port_exit_scale = port_enter_scale
        settings.GRAPH_LOD_PORT_MIN_SCALE = port_enter_scale
        settings.GRAPH_LOD_PORT_VISIBILITY_EXIT_SCALE = port_exit_scale

        edge_enter_scale = float(self.graph_lod_edge_min_slider.value()) / 100.0
        edge_exit_scale = float(self.graph_lod_edge_exit_slider.value()) / 100.0
        if edge_exit_scale < edge_enter_scale:
            edge_exit_scale = edge_enter_scale
        settings.GRAPH_LOD_EDGE_MIN_SCALE = edge_enter_scale
        settings.GRAPH_LOD_EDGE_VISIBILITY_EXIT_SCALE = edge_exit_scale

        edge_hittest_scale = float(self.graph_lod_edge_hittest_slider.value()) / 100.0
        if edge_hittest_scale < edge_enter_scale:
            edge_hittest_scale = edge_enter_scale
        settings.GRAPH_LOD_EDGE_HITTEST_MIN_SCALE = edge_hittest_scale

        settings.GRAPH_GRID_ENABLED = bool(self.graph_grid_enabled_checkbox.isChecked())
        settings.GRAPH_PAN_HIDE_ICONS_ENABLED = bool(self.graph_pan_hide_icons_checkbox.isChecked())
        settings.GRAPH_PAN_FREEZE_VIEWPORT_ENABLED = bool(
            self.graph_pan_freeze_viewport_checkbox.isChecked()
        )
        settings.GRAPH_ZOOM_FREEZE_VIEWPORT_ENABLED = bool(
            self.graph_zoom_freeze_viewport_checkbox.isChecked()
        )
        settings.GRAPH_GRID_MIN_PX = float(self.graph_grid_min_px_spinbox.value())

        settings.GRAPH_BLOCK_OVERVIEW_ENABLED = bool(
            self.graph_block_overview_enabled_checkbox.isChecked()
        )
        overview_enter_scale = float(self.graph_block_overview_enter_slider.value()) / 100.0
        overview_exit_scale = float(self.graph_block_overview_exit_slider.value()) / 100.0
        if overview_exit_scale < overview_enter_scale:
            overview_exit_scale = overview_enter_scale
        settings.GRAPH_BLOCK_OVERVIEW_ENTER_SCALE = overview_enter_scale
        settings.GRAPH_BLOCK_OVERVIEW_EXIT_SCALE = overview_exit_scale
        settings.GRAPH_BLOCK_OVERVIEW_GRID_MIN_PX = float(
            self.graph_block_overview_grid_min_px_spinbox.value()
        )

        should_rebuild_scene = (
            bool(old_scene_build_settings.get("SHOW_LAYOUT_Y_DEBUG", False))
            != bool(getattr(settings, "SHOW_LAYOUT_Y_DEBUG", False))
            or bool(old_scene_build_settings.get("SHOW_BASIC_BLOCKS", True))
            != bool(getattr(settings, "SHOW_BASIC_BLOCKS", True))
            or bool(old_scene_build_settings.get("GRAPH_CONSTANT_WIDGET_VIRTUALIZATION_ENABLED", True))
            != bool(getattr(settings, "GRAPH_CONSTANT_WIDGET_VIRTUALIZATION_ENABLED", True))
            or bool(old_scene_build_settings.get("GRAPH_FAST_PREVIEW_ENABLED", False))
            != bool(getattr(settings, "GRAPH_FAST_PREVIEW_ENABLED", False))
            or int(old_scene_build_settings.get("GRAPH_FAST_PREVIEW_NODE_THRESHOLD", 500))
            != int(getattr(settings, "GRAPH_FAST_PREVIEW_NODE_THRESHOLD", 500) or 500)
            or int(old_scene_build_settings.get("GRAPH_FAST_PREVIEW_EDGE_THRESHOLD", 900))
            != int(getattr(settings, "GRAPH_FAST_PREVIEW_EDGE_THRESHOLD", 900) or 900)
        )

        if should_rebuild_scene:
            parent = self.parent()
            graph_controller = getattr(parent, "graph_controller", None) if parent is not None else None
            rebuild = getattr(graph_controller, "rebuild_scene_for_settings_change", None)
            if callable(rebuild):
                rebuild(preserve_view=True)

        # 让当前打开的图立即按新阈值重新同步 LOD/可见性（避免“改了但不缩放就不生效”的错觉）
        self._resync_active_graph_scene_after_settings_change()
        new_theme_mode = self.ui_theme_combo.currentData()
        settings.UI_THEME_MODE = new_theme_mode
        # 强制启用：资源库自动刷新不再由设置页控制（避免外部修改后不刷新带来的困惑）
        settings.RESOURCE_LIBRARY_AUTO_REFRESH_ENABLED = True
        # 若“结构增强类”的自动排版开关发生变化：在下次自动排版前强制以 .py 重新解析当前图
        # （避免在已加载的增强模型上叠加生成导致节点/连线膨胀或残留）
        should_force_reparse = (
            bool(old_cross_block_copy) != bool(settings.DATA_NODE_CROSS_BLOCK_COPY)
            or bool(old_local_var_relay_enabled) != bool(settings.LAYOUT_AUTO_INSERT_LOCAL_VAR_RELAY)
            or int(old_local_var_relay_distance)
            != int(settings.LAYOUT_LOCAL_VAR_RELAY_MAX_BLOCK_DISTANCE)
        )
        if should_force_reparse:
            parent = self.parent()
            graph_controller = getattr(parent, "graph_controller", None)
            if graph_controller and hasattr(
                graph_controller, "schedule_reparse_on_next_auto_layout"
            ):
                graph_controller.schedule_reparse_on_next_auto_layout()
        # 保存步骤模式
        settings.TODO_GRAPH_STEP_MODE = self.todo_mode_combo.currentData()
        settings.AUTO_SAVE_INTERVAL = self.auto_save_spinbox.value()
        # 保存鼠标执行模式与混合参数
        settings.MOUSE_EXECUTION_MODE = self.mouse_mode_combo.currentData()
        settings.MOUSE_HYBRID_STEPS = int(self.hybrid_steps_spinbox.value())
        settings.MOUSE_HYBRID_STEP_SLEEP = float(self.hybrid_step_sleep_spinbox.value())
        settings.MOUSE_DRAG_MODE = self.drag_mode_combo.currentData()

        # 保存到文件
        if settings.save():
            # 设置已成功保存：确保文件监控侧也处于“资源库自动刷新启用”状态
            parent = self.parent()
            file_watcher_manager = getattr(parent, "file_watcher_manager", None)
            if file_watcher_manager is not None and hasattr(
                file_watcher_manager, "set_resource_auto_refresh_enabled"
            ):
                file_watcher_manager.set_resource_auto_refresh_enabled(True)
            # 如果修改了需要重启的设置，提示用户/询问是否立即重启
            theme_mode_changed = new_theme_mode != old_theme_mode
            if theme_mode_changed:
                reasons: list[str] = []
                if theme_mode_changed:
                    reasons.append("界面主题")
                reasons_text = "\n".join([f"- {x}" for x in reasons]) if reasons else ""

                should_restart = self.confirm(
                    "设置已保存",
                    "您的设置已成功保存。\n\n"
                    "以下设置需要重启程序才能完全生效：\n"
                    f"{reasons_text}\n\n"
                    "是否立即重启程序？",
                )
                self.accept()
                if should_restart:
                    self._restart_application()
                return
            if node_loading_changed:
                self.show_info(
                    "设置已保存",
                    "您的设置已成功保存并立即生效。\n\n注意：\"节点加载详细日志\"选项需要重启程序才能生效。",
                )
            self.accept()
        else:
            self.show_warning(
                "保存失败", "设置已应用但未能保存到配置文件。\n程序重启后将使用默认设置。"
            )
            self.accept()

    def _restart_application(self) -> None:
        """重启整个应用以应用需要启动阶段生效的设置（如界面主题）。

        实现方式：
        - 使用当前 Python 解释器通过 `-m app.cli.run_app` 启动一个新进程；
        - 退出当前 QApplication。
        """
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        QtCore.QProcess.startDetached(sys.executable, ["-m", "app.cli.run_app"])
        app.quit()

    def _update_hybrid_controls_enabled(self) -> None:
        """根据当前鼠标执行模式，启用/禁用混合参数控件"""
        mode = (
            self.mouse_mode_combo.currentData() if hasattr(self, "mouse_mode_combo") else "classic"
        )
        enabled = mode == "hybrid"
        if hasattr(self, "hybrid_params_container"):
            self.hybrid_params_container.setEnabled(bool(enabled))

    def _update_local_var_relay_controls_enabled(self) -> None:
        """根据“长连线中转”开关，启用/禁用阈值滑块与输入框。"""
        enabled = (
            bool(self.local_var_relay_checkbox.isChecked())
            if hasattr(self, "local_var_relay_checkbox")
            else False
        )
        if hasattr(self, "local_var_relay_length_slider"):
            self.local_var_relay_length_slider.setEnabled(enabled)
        if hasattr(self, "local_var_relay_length_spinbox"):
            self.local_var_relay_length_spinbox.setEnabled(enabled)

    def _update_fast_preview_threshold_controls_enabled(self) -> None:
        enabled = (
            bool(self.graph_fast_preview_checkbox.isChecked())
            if hasattr(self, "graph_fast_preview_checkbox")
            else False
        )
        node_box = getattr(self, "graph_fast_preview_node_threshold_spinbox", None)
        edge_box = getattr(self, "graph_fast_preview_edge_threshold_spinbox", None)
        if isinstance(node_box, QtWidgets.QWidget):
            node_box.setEnabled(enabled)
        if isinstance(edge_box, QtWidgets.QWidget):
            edge_box.setEnabled(enabled)

    def _update_basic_block_alpha_controls_enabled(self) -> None:
        enabled = (
            bool(self.show_basic_blocks_checkbox.isChecked())
            if hasattr(self, "show_basic_blocks_checkbox")
            else False
        )
        slider = getattr(self, "basic_block_alpha_slider", None)
        box = getattr(self, "basic_block_alpha_spinbox", None)
        if isinstance(slider, QtWidgets.QWidget):
            slider.setEnabled(enabled)
        if isinstance(box, QtWidgets.QWidget):
            box.setEnabled(enabled)

    def _update_graph_lod_controls_enabled(self) -> None:
        """根据 LOD 总开关启用/禁用子控件。"""
        enabled = (
            bool(self.graph_lod_enabled_checkbox.isChecked())
            if hasattr(self, "graph_lod_enabled_checkbox")
            else False
        )
        container = getattr(self, "graph_lod_params_container", None)
        if isinstance(container, QtWidgets.QWidget):
            container.setEnabled(enabled)
        self._update_graph_block_overview_controls_enabled()

    def _update_graph_block_overview_controls_enabled(self) -> None:
        """根据“鸟瞰模式”开关启用/禁用其参数区。"""
        lod_enabled = (
            bool(self.graph_lod_enabled_checkbox.isChecked())
            if hasattr(self, "graph_lod_enabled_checkbox")
            else False
        )
        overview_enabled = (
            bool(self.graph_block_overview_enabled_checkbox.isChecked())
            if hasattr(self, "graph_block_overview_enabled_checkbox")
            else False
        )
        enabled = bool(lod_enabled and overview_enabled)
        container = getattr(self, "graph_block_overview_params_container", None)
        if isinstance(container, QtWidgets.QWidget):
            container.setEnabled(enabled)

    def _update_graph_grid_controls_enabled(self) -> None:
        """根据“显示画布网格”开关启用/禁用网格参数。"""
        enabled = (
            bool(self.graph_grid_enabled_checkbox.isChecked())
            if hasattr(self, "graph_grid_enabled_checkbox")
            else True
        )
        box = getattr(self, "graph_grid_min_px_spinbox", None)
        if isinstance(box, QtWidgets.QWidget):
            box.setEnabled(enabled)

    def _resync_active_graph_scene_after_settings_change(self) -> None:
        """让当前打开的 GraphScene 重新同步 LOD/可见性与叠加层（无需用户手动缩放触发）。"""
        parent = self.parent()
        if parent is None:
            return

        app_state = getattr(parent, "app_state", None)
        graph_view = getattr(app_state, "graph_view", None) if app_state is not None else None
        if graph_view is None:
            graph_view = getattr(parent, "graph_view", None)
        if graph_view is None:
            # 兜底：从当前 QApplication 找任意 GraphView（避免主窗口结构调整后找不到引用）
            from app.ui.graph.graph_view import GraphView

            app = QtWidgets.QApplication.instance()
            if app is not None:
                for w in list(app.allWidgets() or []):
                    if isinstance(w, GraphView):
                        graph_view = w
                        break
        if graph_view is None or not hasattr(graph_view, "scene"):
            return

        scene = graph_view.scene()
        if scene is None:
            return

        set_hint = getattr(scene, "set_view_scale_hint", None)
        # 关键：使用视图的真实缩放比例（transform.m11），而不是 scene.view_scale_hint（可能尚未通过 paintEvent 同步）。
        current_scale: float | None = None
        get_transform = getattr(graph_view, "transform", None)
        if callable(get_transform):
            transform = get_transform()
            if isinstance(transform, QtGui.QTransform):
                current_scale = float(transform.m11())
        if current_scale is None or current_scale <= 0.0:
            current_scale = float(getattr(scene, "view_scale_hint", 1.0) or 1.0)

        if callable(set_hint):
            set_hint(float(current_scale))
        else:
            setattr(scene, "view_scale_hint", float(current_scale))

        update_scene = getattr(scene, "update", None)
        if callable(update_scene):
            update_scene()

        update_view = getattr(graph_view, "update", None)
        if callable(update_view):
            update_view()

        viewport = getattr(graph_view, "viewport", None)
        if callable(viewport):
            vp = viewport()
            if isinstance(vp, QtWidgets.QWidget):
                vp.update()

        # 画布性能面板：设置里开关后立即刷新可见性（避免需要切换页面才生效）
        refresh_perf = getattr(graph_view, "refresh_perf_panel_visibility", None)
        if callable(refresh_perf):
            refresh_perf()

        # 全局性能悬浮面板：设置里开关后立即刷新可见性（所有页面可见）
        refresh_app_perf = getattr(parent, "refresh_app_performance_monitor_visibility", None)
        if callable(refresh_app_perf):
            refresh_app_perf()

    def _clear_all_caches(self) -> None:
        """清除所有缓存（内存+持久化的节点图缓存）"""
        if not self.confirm(
            "确认清除",
            "确定要清除所有缓存吗？\n\n此操作将删除 app/runtime/cache/graph_cache 下的缓存文件，并清空内存缓存。",
        ):
            return
        parent = self.parent()

        app_state = getattr(parent, "app_state", None) if parent is not None else None
        resource_manager = (
            getattr(app_state, "resource_manager", None)
            if app_state is not None
            else getattr(parent, "resource_manager", None)
        )
        package_index_manager = (
            getattr(app_state, "package_index_manager", None)
            if app_state is not None
            else getattr(parent, "package_index_manager", None)
        )
        if resource_manager is None:
            self.show_warning("无法执行", "未找到资源管理器实例，清除缓存失败。")
            return
        graph_controller = getattr(parent, "graph_controller", None)
        nav_coordinator = getattr(parent, "nav_coordinator", None)
        file_watcher_manager = getattr(parent, "file_watcher_manager", None)
        graph_property_panel = getattr(parent, "graph_property_panel", None)
        had_active_graph = bool(graph_controller and getattr(graph_controller, "current_graph_id", None))
        result = resource_manager.clear_all_caches()
        removed = int(result.get("removed_persistent_files", 0))
        payload_provider = get_shared_graph_data_service(resource_manager, package_index_manager)
        removed_payload_items = int(payload_provider.clear_all_payload_graph_data())
        payload_provider.invalidate_graph()
        payload_provider.invalidate_package_cache()
        if had_active_graph:
            self._reset_graph_editor_after_cache_clear(
                parent,
                graph_controller,
                file_watcher_manager,
                graph_property_panel,
                nav_coordinator,
            )
        extra = ""
        if had_active_graph:
            extra = "\n\n当前打开的节点图已关闭，您已回到节点图列表。请重新打开目标节点图以继续编辑。"
        self.show_info(
            "完成",
            f"已清除所有缓存。\n\n磁盘缓存删除 {removed} 个文件，内存缓存已清空（graph_data: {removed_payload_items} 条）。{extra}",
        )

    def _reset_graph_editor_after_cache_clear(
        self,
        parent,
        graph_controller,
        file_watcher_manager,
        graph_property_panel,
        nav_coordinator,
    ) -> None:
        """清空编辑器状态并返回列表，确保缓存彻底释放。"""
        close_session = getattr(graph_controller, "close_editor_session", None)
        if callable(close_session):
            close_session()
        else:
            graph_controller.current_graph_id = None
            graph_controller.current_graph_container = None
        if file_watcher_manager and hasattr(file_watcher_manager, "setup_file_watcher"):
            file_watcher_manager.setup_file_watcher("")
        if graph_property_panel and hasattr(graph_property_panel, "set_empty_state"):
            graph_property_panel.set_empty_state()
        if hasattr(parent, "register_graph_editor_todo_context"):
            parent.register_graph_editor_todo_context("", {}, "")
        if nav_coordinator and hasattr(nav_coordinator, "navigate_to_mode"):
            nav_coordinator.navigate_to_mode.emit("graph_library")
        elif hasattr(parent, "_navigate_to_mode"):
            parent._navigate_to_mode("graph_library")

    def _install_wheel_guards(self) -> None:
        """设置页遵循全局滚轮防误触规则，此处保持占位以兼容旧代码。"""
        # 全局过滤器已在 ThemeManager.apply_app_style 中安装，这里无需再做额外处理。
        return

