"""设置对话框 - 用户友好的设置界面"""

from __future__ import annotations
from PyQt6 import QtCore, QtGui, QtWidgets
import sys

from app.ui.foundation.base_widgets import BaseDialog
from app.ui.foundation.theme_manager import ThemeManager, Colors, Sizes
from app.ui.panels.panel_scaffold import build_scrollable_column
from engine.configs.settings import settings
from app.ui.graph.library_mixins import ConfirmDialogMixin
from app.runtime.services.graph_data_service import get_shared_graph_data_service


class SettingsDialog(BaseDialog, ConfirmDialogMixin):
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
        self.category_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.category_list.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
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

    def _build_settings_pages(self) -> None:
        """构建分类页（左侧导航 + 右侧堆叠页面）。"""
        pages: list[tuple[str, list[QtWidgets.QWidget]]] = [
            (
                "性能",
                [
                    self._create_graph_lod_settings_group(),
                    self._create_graph_performance_settings_group(),
                    self._create_app_performance_monitor_settings_group(),
                ],
            ),
            ("排版", [self._create_auto_layout_settings_group()]),
            ("画布", [self._create_graph_appearance_settings_group()]),
            ("任务清单", [self._create_step_settings_group()]),
            ("输出与调试", [self._create_output_settings_group()]),
            ("执行与系统", [self._create_runtime_settings_group()]),
        ]

        for title, groups in pages:
            self.category_list.addItem(title)
            self.pages_stack.addWidget(self._build_scroll_page(groups))

    def _build_scroll_page(self, widgets: list[QtWidgets.QWidget]) -> QtWidgets.QScrollArea:
        """将多个分组控件包装为一个可滚动页面。"""
        scroll_area, _content, content_layout = build_scrollable_column(
            self,
            spacing=Sizes.SPACING_LARGE,
            margins=(0, 0, 0, 0),
            add_trailing_stretch=False,
        )
        for w in widgets:
            content_layout.addWidget(w)
        content_layout.addStretch(1)
        return scroll_area

    def _on_accept(self) -> None:
        """覆写基类接受逻辑，统一走设置保存流程。"""
        self._save_and_close()

    def _build_percent_slider_row(
        self,
        *,
        tooltip: str,
        min_value: int,
        max_value: int,
        tick_interval: int,
        page_step: int,
        suffix: str = "%",
        minimum_width: int = 70,
    ) -> tuple[QtWidgets.QSlider, QtWidgets.QSpinBox, QtWidgets.QWidget]:
        """构建“滑动条 + 数值输入”的百分比行（同步联动）。"""
        slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        slider.setRange(int(min_value), int(max_value))
        slider.setSingleStep(1)
        slider.setPageStep(int(page_step))
        slider.setTickInterval(int(tick_interval))
        slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        slider.setToolTip(str(tooltip or ""))

        spinbox = QtWidgets.QSpinBox()
        spinbox.setRange(int(min_value), int(max_value))
        spinbox.setSingleStep(1)
        if suffix:
            spinbox.setSuffix(str(suffix))
        spinbox.setToolTip(str(tooltip or ""))
        spinbox.setMinimumWidth(int(minimum_width))

        slider.valueChanged.connect(spinbox.setValue)
        spinbox.valueChanged.connect(slider.setValue)

        container = QtWidgets.QWidget()
        container_layout = QtWidgets.QHBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(8)
        container_layout.addWidget(slider, 1)
        container_layout.addWidget(spinbox)
        return slider, spinbox, container
    
    def _create_auto_layout_settings_group(self) -> QtWidgets.QGroupBox:
        """创建自动排版设置组"""
        group = QtWidgets.QGroupBox("自动排版")
        layout = QtWidgets.QVBoxLayout(group)
        # 块间紧凑排列
        self.tight_block_spacing_checkbox = QtWidgets.QCheckBox("块与块之间紧密排列")
        self.tight_block_spacing_checkbox.setToolTip(
            "启用后，在满足端口间距和避免矩形重叠的前提下，自动排版会尽量把块往左贴近上游块，"
            "让列间空隙更小、整体更紧凑。\n"
            "停用时，每列仅使用基础左边界，不再尝试额外左移，便于保留标准列间距。\n"
            "✅ 立即生效，无需重启"
        )
        layout.addWidget(self.tight_block_spacing_checkbox)

        # 数据节点跨块复制
        self.data_node_copy_checkbox = QtWidgets.QCheckBox("数据节点跨块复制")
        self.data_node_copy_checkbox.setToolTip(
            "启用后，当数据节点被多个基本块共享时，会为每个块创建真实副本。\n"
            "✅ 启用（推荐）：每个块拥有独立的数据节点副本，副本只保留连接到自己块的边\n"
            "❌ 禁用：保持旧逻辑，数据节点属于先到块，后续块不复制\n"
            "注意：复制在“分块/块内放置”阶段执行，仅复制纯数据节点，遇到带流程口的节点停止。"
        )
        layout.addWidget(self.data_node_copy_checkbox)

        # 长连线自动生成中转节点（获取局部变量）
        self.local_var_relay_checkbox = QtWidgets.QCheckBox("长连线自动生成局部变量中转节点（获取局部变量）")
        self.local_var_relay_checkbox.setToolTip(
            "启用后：在“跨块复制完成后、块内排版前”，自动扫描同一基本块内跨越过多节点的数据连线，\n"
            "并插入【获取局部变量】节点作为中转，将一条长边拆成多段短边，提升可读性。\n"
            "说明：会尊重【获取局部变量】对数据类型的约束（例如禁止字典类型），不满足则跳过。\n"
            "✅ 立即生效；建议在修改本开关或阈值后执行一次“自动排版”以更新当前图"
        )
        layout.addWidget(self.local_var_relay_checkbox)

        relay_form = QtWidgets.QFormLayout()
        relay_form.setContentsMargins(0, 6, 0, 0)
        relay_form.setHorizontalSpacing(10)
        relay_form.setVerticalSpacing(6)

        relay_tooltip = (
            "单段数据连线允许跨越的最大节点跨度（3~10）。\n"
            "当某条 flow→flow 数据边在同一基本块内跨越的流程节点数 > 该阈值时，\n"
            "会自动插入【获取局部变量】中转节点进行拆分。\n"
            "默认 5。"
        )
        self.local_var_relay_length_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.local_var_relay_length_slider.setRange(3, 10)
        self.local_var_relay_length_slider.setSingleStep(1)
        self.local_var_relay_length_slider.setPageStep(1)
        self.local_var_relay_length_slider.setTickInterval(1)
        self.local_var_relay_length_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        self.local_var_relay_length_slider.setToolTip(relay_tooltip)

        self.local_var_relay_length_spinbox = QtWidgets.QSpinBox()
        self.local_var_relay_length_spinbox.setRange(3, 10)
        self.local_var_relay_length_spinbox.setSingleStep(1)
        self.local_var_relay_length_spinbox.setToolTip(relay_tooltip)
        self.local_var_relay_length_spinbox.setMinimumWidth(70)

        self.local_var_relay_length_slider.valueChanged.connect(self.local_var_relay_length_spinbox.setValue)
        self.local_var_relay_length_spinbox.valueChanged.connect(self.local_var_relay_length_slider.setValue)

        relay_container = QtWidgets.QWidget()
        relay_container_layout = QtWidgets.QHBoxLayout(relay_container)
        relay_container_layout.setContentsMargins(0, 0, 0, 0)
        relay_container_layout.setSpacing(8)
        relay_container_layout.addWidget(self.local_var_relay_length_slider, 1)
        relay_container_layout.addWidget(self.local_var_relay_length_spinbox)

        relay_form.addRow("中转阈值（节点跨度）：", relay_container)
        relay_container_outer = QtWidgets.QWidget()
        relay_container_outer.setLayout(relay_form)
        layout.addWidget(relay_container_outer)

        self.local_var_relay_checkbox.toggled.connect(self._update_local_var_relay_controls_enabled)

        # 布局Y坐标调试（轻量 Tooltip）
        self.layout_y_debug_overlay_checkbox = QtWidgets.QCheckBox("布局Y坐标调试（节点旁感叹号）")
        self.layout_y_debug_overlay_checkbox.setToolTip(
            "启用后，每个节点左上角显示“!”图标，点击弹出可复制的调试Tooltip，\n"
            "展示当前Y轴分配的关键依据与链信息。轻量无全局避让，点击空白自动关闭。\n"
            "✅ 立即生效，无需重启"
        )
        layout.addWidget(self.layout_y_debug_overlay_checkbox)

        # 节点间距倍率（横/纵）
        spacing_form = QtWidgets.QFormLayout()
        spacing_form.setContentsMargins(0, 6, 0, 0)
        spacing_form.setHorizontalSpacing(10)
        spacing_form.setVerticalSpacing(6)

        x_tooltip = (
            "自动排版时，相邻节点之间的【横向】间距倍率。\n"
            "100% 为当前默认效果；200% 将横向间距放大到 2 倍；最小 10%。\n"
            "说明：仅缩放布局算法中的间距常量，不改变节点本身宽度。"
        )
        y_tooltip = (
            "自动排版时，相邻节点之间的【纵向】间距倍率。\n"
            "100% 为当前默认效果；200% 将纵向间距放大到 2 倍；最小 10%。\n"
            "说明：仅缩放布局算法中的间距常量，不改变节点本身高度/端口行高。"
        )

        (
            self.layout_spacing_x_slider,
            self.layout_spacing_x_spinbox,
            x_slider_container,
        ) = self._build_percent_slider_row(
            tooltip=x_tooltip,
            min_value=10,
            max_value=200,
            tick_interval=10,
            page_step=10,
        )
        (
            self.layout_spacing_y_slider,
            self.layout_spacing_y_spinbox,
            y_slider_container,
        ) = self._build_percent_slider_row(
            tooltip=y_tooltip,
            min_value=10,
            max_value=200,
            tick_interval=10,
            page_step=10,
        )

        spacing_form.addRow("节点横向间距：", x_slider_container)
        spacing_form.addRow("节点纵向间距：", y_slider_container)
        spacing_container = QtWidgets.QWidget()
        spacing_container.setLayout(spacing_form)
        layout.addWidget(spacing_container)

        return group

    def _create_graph_lod_settings_group(self) -> QtWidgets.QGroupBox:
        """创建画布 LOD（分层绘制）设置组。"""
        group = QtWidgets.QGroupBox("画布LOD（分层绘制 / 大图性能）")
        layout = QtWidgets.QVBoxLayout(group)

        self.graph_lod_enabled_checkbox = QtWidgets.QCheckBox("启用画布LOD（低倍率自动简化/裁剪）")
        self.graph_lod_enabled_checkbox.setToolTip(
            "启用后：缩放较小时会逐步隐藏端口/连线/文本等细节，并降低命中测试成本，\n"
            "用于提升超大图的缩放/平移流畅度。\n"
            "关闭后：始终按全细节渲染（更直观，但超大图更容易卡顿）。\n"
            "✅ 立即生效，无需重启"
        )
        layout.addWidget(self.graph_lod_enabled_checkbox)

        info = QtWidgets.QLabel(
            "提示：LOD 会分层触发。\n"
            "- 低于“节点细节阈值”：节点只保留标题栏与边框\n"
            "- 低于“端口阈值”：端口/端口按钮会被真正隐藏（setVisible=False）\n"
            "- 低于“连线阈值”：非选中/非高亮连线会被真正隐藏\n"
            "- 更低倍率：可进入“鸟瞰仅显示块颜色”（需要 basic_blocks）"
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;")
        layout.addWidget(info)

        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 6, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)

        # === 节点/端口/边阈值（百分比） ===
        details_tooltip = (
            "节点细节显示阈值（1%~100%）。\n"
            "低于该缩放比例时，节点将跳过端口标签/常量占位文本/验证图标等细节绘制。"
        )
        (
            self.graph_lod_node_details_slider,
            self.graph_lod_node_details_spinbox,
            details_container,
        ) = self._build_percent_slider_row(
            tooltip=details_tooltip,
            min_value=1,
            max_value=100,
            tick_interval=10,
            page_step=5,
        )
        form.addRow("节点细节阈值：", details_container)

        title_tooltip = (
            "节点标题文字显示阈值（1%~100%）。\n"
            "低于该缩放比例时，默认不绘制标题文字（通常已不可读且绘制成本高），\n"
            "仅对选中/搜索命中的节点保留文字。"
        )
        (
            self.graph_lod_node_title_slider,
            self.graph_lod_node_title_spinbox,
            title_container,
        ) = self._build_percent_slider_row(
            tooltip=title_tooltip,
            min_value=1,
            max_value=100,
            tick_interval=10,
            page_step=5,
        )
        form.addRow("标题文字阈值：", title_container)

        port_tooltip = (
            "端口显示阈值（1%~100%）。\n"
            "低于该缩放比例时端口与端口按钮会被真正隐藏（setVisible=False），\n"
            "用于降低超大图下的 item 枚举与绘制开销。"
        )
        (
            self.graph_lod_port_min_slider,
            self.graph_lod_port_min_spinbox,
            port_container,
        ) = self._build_percent_slider_row(
            tooltip=port_tooltip,
            min_value=1,
            max_value=100,
            tick_interval=10,
            page_step=5,
        )
        form.addRow("端口阈值：", port_container)

        port_exit_tooltip = (
            "端口“恢复可见”的回滞阈值（1%~100%）。\n"
            "避免在临界缩放附近频繁切换可见性导致抖动。\n"
            "要求：退出阈值 ≥ 端口阈值。"
        )
        (
            self.graph_lod_port_exit_slider,
            self.graph_lod_port_exit_spinbox,
            port_exit_container,
        ) = self._build_percent_slider_row(
            tooltip=port_exit_tooltip,
            min_value=1,
            max_value=100,
            tick_interval=10,
            page_step=5,
        )
        form.addRow("端口回滞阈值：", port_exit_container)

        edge_tooltip = (
            "连线显示阈值（1%~100%）。\n"
            "低于该缩放比例时非选中/非高亮连线会被真正隐藏（setVisible=False）。"
        )
        (
            self.graph_lod_edge_min_slider,
            self.graph_lod_edge_min_spinbox,
            edge_container,
        ) = self._build_percent_slider_row(
            tooltip=edge_tooltip,
            min_value=1,
            max_value=100,
            tick_interval=10,
            page_step=5,
        )
        form.addRow("连线阈值：", edge_container)

        edge_exit_tooltip = (
            "连线“恢复可见”的回滞阈值（1%~100%）。\n"
            "避免在临界缩放附近频繁切换可见性导致抖动。\n"
            "要求：退出阈值 ≥ 连线阈值。"
        )
        (
            self.graph_lod_edge_exit_slider,
            self.graph_lod_edge_exit_spinbox,
            edge_exit_container,
        ) = self._build_percent_slider_row(
            tooltip=edge_exit_tooltip,
            min_value=1,
            max_value=100,
            tick_interval=10,
            page_step=5,
        )
        form.addRow("连线回滞阈值：", edge_exit_container)

        hittest_tooltip = (
            "连线命中测试阈值（1%~100%）。\n"
            "低于该缩放比例时，非选中/非高亮连线会返回空 shape，降低命中测试开销。\n"
            "建议 ≥ 连线阈值。"
        )
        (
            self.graph_lod_edge_hittest_slider,
            self.graph_lod_edge_hittest_spinbox,
            hittest_container,
        ) = self._build_percent_slider_row(
            tooltip=hittest_tooltip,
            min_value=1,
            max_value=100,
            tick_interval=10,
            page_step=5,
        )
        form.addRow("连线命中阈值：", hittest_container)

        # === 鸟瞰模式（blocks-only）===
        self.graph_block_overview_enabled_checkbox = QtWidgets.QCheckBox(
            "鸟瞰仅显示块颜色（隐藏节点/连线）"
        )
        self.graph_block_overview_enabled_checkbox.setToolTip(
            "启用后：缩小到极小倍率时可进入“仅显示 basic blocks 颜色”的鸟瞰模式。\n"
            "注意：需要当前图包含 basic_blocks，否则不会进入。"
        )
        form.addRow(self.graph_block_overview_enabled_checkbox)

        self.graph_block_overview_params_container = QtWidgets.QWidget()
        block_form = QtWidgets.QFormLayout(self.graph_block_overview_params_container)
        block_form.setContentsMargins(0, 0, 0, 0)
        block_form.setHorizontalSpacing(10)
        block_form.setVerticalSpacing(6)

        enter_tooltip = "进入鸟瞰模式的缩放阈值（1%~100%）。低于该比例会隐藏节点/连线，仅显示块颜色。"
        (
            self.graph_block_overview_enter_slider,
            self.graph_block_overview_enter_spinbox,
            enter_container,
        ) = self._build_percent_slider_row(
            tooltip=enter_tooltip,
            min_value=1,
            max_value=100,
            tick_interval=10,
            page_step=5,
        )
        block_form.addRow("进入阈值：", enter_container)

        exit_tooltip = "退出鸟瞰模式的回滞阈值（1%~100%）。要求：退出阈值 ≥ 进入阈值。"
        (
            self.graph_block_overview_exit_slider,
            self.graph_block_overview_exit_spinbox,
            exit_container,
        ) = self._build_percent_slider_row(
            tooltip=exit_tooltip,
            min_value=1,
            max_value=100,
            tick_interval=10,
            page_step=5,
        )
        block_form.addRow("退出阈值：", exit_container)

        self.graph_block_overview_grid_min_px_spinbox = QtWidgets.QDoubleSpinBox()
        self.graph_block_overview_grid_min_px_spinbox.setRange(8.0, 160.0)
        self.graph_block_overview_grid_min_px_spinbox.setSingleStep(2.0)
        self.graph_block_overview_grid_min_px_spinbox.setDecimals(1)
        self.graph_block_overview_grid_min_px_spinbox.setToolTip(
            "鸟瞰模式下网格线的最小像素间距（通常更大，以进一步降噪提速）。"
        )
        block_form.addRow("鸟瞰网格像素间距：", self.graph_block_overview_grid_min_px_spinbox)

        form.addRow("鸟瞰参数：", self.graph_block_overview_params_container)

        # LOD 参数区（仅受“启用画布LOD”总开关控制）
        self.graph_lod_params_container = QtWidgets.QWidget()
        self.graph_lod_params_container.setLayout(form)
        layout.addWidget(self.graph_lod_params_container)

        # === 画布网格与交互优化（不依赖 LOD 总开关） ===
        extra_form = QtWidgets.QFormLayout()
        extra_form.setContentsMargins(0, 10, 0, 0)
        extra_form.setHorizontalSpacing(10)
        extra_form.setVerticalSpacing(6)

        self.graph_grid_enabled_checkbox = QtWidgets.QCheckBox("显示画布网格")
        self.graph_grid_enabled_checkbox.setToolTip(
            "是否绘制画布网格线（背景底色始终保留）。\n"
            "关闭后可显著降低超大图平移/缩放时的背景绘制开销。"
        )
        self.graph_grid_enabled_checkbox.toggled.connect(self._update_graph_grid_controls_enabled)
        extra_form.addRow(self.graph_grid_enabled_checkbox)

        self.graph_grid_min_px_spinbox = QtWidgets.QDoubleSpinBox()
        self.graph_grid_min_px_spinbox.setRange(4.0, 80.0)
        self.graph_grid_min_px_spinbox.setSingleStep(1.0)
        self.graph_grid_min_px_spinbox.setDecimals(1)
        self.graph_grid_min_px_spinbox.setToolTip(
            "常规模式下网格线在屏幕像素上的最小间距。\n"
            "当缩放导致网格线过密时，会自动放大网格步长以降低绘制开销与噪音。"
        )
        extra_form.addRow("网格最小像素间距：", self.graph_grid_min_px_spinbox)

        self.graph_pan_hide_icons_checkbox = QtWidgets.QCheckBox("平移/缩放期间隐藏端口/图标（提升流畅度）")
        self.graph_pan_hide_icons_checkbox.setToolTip(
            "平移（右键/中键/空格拖拽）或滚轮缩放期间临时隐藏端口圆点/⚙按钮/+按钮等小图元，\n"
            "并让叠加层跳过布局Y调试图标/链路徽标等调试叠层绘制，减少 Qt item 枚举与绘制固定开销。\n"
            "停止交互后按当前 LOD 状态恢复。"
        )
        extra_form.addRow(self.graph_pan_hide_icons_checkbox)

        self.graph_pan_freeze_viewport_checkbox = QtWidgets.QCheckBox("拖拽平移期间冻结为静态快照（极致性能）")
        self.graph_pan_freeze_viewport_checkbox.setToolTip(
            "拖拽平移画布（右键/中键/空格拖拽）期间抓取一张 viewport 快照并冻结为静态画面。\n"
            "拖拽平移过程中不再重绘大量节点/连线，超大图更丝滑。\n"
            "代价：拖拽平移过程中不会显示新进入视口的内容；松手后恢复真实渲染。"
        )
        extra_form.addRow(self.graph_pan_freeze_viewport_checkbox)

        self.graph_zoom_freeze_viewport_checkbox = QtWidgets.QCheckBox("滚轮缩放期间冻结为静态快照（极致性能）")
        self.graph_zoom_freeze_viewport_checkbox.setToolTip(
            "滚轮缩放期间抓取一张 viewport 快照并冻结为静态画面，\n"
            "缩放过程中不重绘大量节点/连线，停止滚轮后恢复真实渲染。\n"
            "代价：缩放过程中不会显示新进入视口的内容。"
        )
        extra_form.addRow(self.graph_zoom_freeze_viewport_checkbox)

        extra_container = QtWidgets.QWidget()
        extra_container.setLayout(extra_form)
        layout.addWidget(extra_container)

        self.graph_lod_enabled_checkbox.toggled.connect(self._update_graph_lod_controls_enabled)
        self.graph_block_overview_enabled_checkbox.toggled.connect(self._update_graph_block_overview_controls_enabled)

        return group

    def _create_graph_performance_settings_group(self) -> QtWidgets.QGroupBox:
        """创建性能相关（大图）设置组。"""
        group = QtWidgets.QGroupBox("画布性能（大图）")
        layout = QtWidgets.QVBoxLayout(group)

        self.graph_constant_widget_virtualization_checkbox = QtWidgets.QCheckBox(
            "行内常量控件虚拟化（推荐）"
        )
        self.graph_constant_widget_virtualization_checkbox.setToolTip(
            "启用后：节点默认不常驻创建 QGraphicsProxyWidget（常量编辑控件），\n"
            "改为占位绘制；点击占位区域才按需创建真实控件，退出编辑后释放。\n"
            "✅ 对超大图性能提升明显；立即生效，无需重启"
        )
        layout.addWidget(self.graph_constant_widget_virtualization_checkbox)

        self.graph_fast_preview_checkbox = QtWidgets.QCheckBox("超大图快速预览（压缩节点/连线）")
        self.graph_fast_preview_checkbox.setToolTip(
            "启用后：当节点图规模非常大且当前会话不可落盘（例如只读预览）时，\n"
            "会自动进入“快速预览/压缩模式”，使用轻量节点与连线图元以提升打开与拖拽流畅度。\n\n"
            "默认关闭：不再自动进入压缩预览，始终显示完整节点（端口/常量控件等），\n"
            "但超大图可能更卡。\n"
            "✅ 立即生效，无需重启"
        )
        layout.addWidget(self.graph_fast_preview_checkbox)

        threshold_form = QtWidgets.QFormLayout()
        threshold_form.setContentsMargins(0, 6, 0, 0)
        threshold_form.setHorizontalSpacing(10)
        threshold_form.setVerticalSpacing(6)

        self.graph_fast_preview_node_threshold_spinbox = QtWidgets.QSpinBox()
        self.graph_fast_preview_node_threshold_spinbox.setRange(50, 20000)
        self.graph_fast_preview_node_threshold_spinbox.setSingleStep(50)
        self.graph_fast_preview_node_threshold_spinbox.setToolTip("快速预览触发阈值：节点数量 ≥ 该值时可自动进入压缩预览。")
        threshold_form.addRow("快速预览节点阈值：", self.graph_fast_preview_node_threshold_spinbox)

        self.graph_fast_preview_edge_threshold_spinbox = QtWidgets.QSpinBox()
        self.graph_fast_preview_edge_threshold_spinbox.setRange(50, 50000)
        self.graph_fast_preview_edge_threshold_spinbox.setSingleStep(50)
        self.graph_fast_preview_edge_threshold_spinbox.setToolTip("快速预览触发阈值：连线数量 ≥ 该值时可自动进入压缩预览。")
        threshold_form.addRow("快速预览连线阈值：", self.graph_fast_preview_edge_threshold_spinbox)

        threshold_container = QtWidgets.QWidget()
        threshold_container.setLayout(threshold_form)
        layout.addWidget(threshold_container)

        self.graph_auto_fit_all_checkbox = QtWidgets.QCheckBox("自动适配全图（镜头缩放到全图）")
        self.graph_auto_fit_all_checkbox.setToolTip(
            "启用后：进入节点图编辑器、以及部分任务清单预览场景会自动执行“适配全图（fit all）”，\n"
            "让全图一屏可见。\n\n"
            "默认关闭：避免超大图进入“压缩状态”，并减少自动触发的全量边界计算带来的卡顿。\n"
            "需要总览时可随时按 Ctrl+0 手动适配全图。\n"
            "✅ 立即生效，无需重启"
        )
        layout.addWidget(self.graph_auto_fit_all_checkbox)

        self.graph_perf_panel_checkbox = QtWidgets.QCheckBox(
            "显示画布性能面板（拖拽/缩放耗时分解）"
        )
        self.graph_perf_panel_checkbox.setToolTip(
            "开启后：在画布左上角显示实时性能面板，帮助定位“拖拽平移/缩放”卡顿来源。\n"
            "面板会统计每帧耗时分解（场景绘制/网格叠层/控件定位/小地图等），并提示最大开销段。\n\n"
            "默认关闭：避免在日常使用中引入额外统计开销。\n"
            "✅ 立即生效，无需重启"
        )
        layout.addWidget(self.graph_perf_panel_checkbox)

        self.graph_fast_preview_checkbox.toggled.connect(
            self._update_fast_preview_threshold_controls_enabled
        )
        self._update_fast_preview_threshold_controls_enabled()

        return group

    def _create_app_performance_monitor_settings_group(self) -> QtWidgets.QGroupBox:
        """创建全局性能监控设置组（用于定位“全页面卡顿”）。"""
        group = QtWidgets.QGroupBox("全局性能监控（卡顿定位）")
        layout = QtWidgets.QVBoxLayout(group)

        self.app_perf_monitor_enabled_checkbox = QtWidgets.QCheckBox(
            "启用全局卡顿监控（记录 UI 主线程阻塞堆栈）"
        )
        self.app_perf_monitor_enabled_checkbox.setToolTip(
            "开启后：程序会以“UI心跳 + 后台watchdog”方式检测主线程是否被阻塞。\n"
            "当事件循环被阻塞超过阈值时，会记录一次卡顿事件，并可在性能面板中查看当时的调用栈。\n\n"
            "默认关闭：避免日常使用的额外统计开销。\n"
            "✅ 立即生效，无需重启"
        )
        layout.addWidget(self.app_perf_monitor_enabled_checkbox)

        self.app_perf_overlay_enabled_checkbox = QtWidgets.QCheckBox(
            "显示全局性能悬浮面板（所有页面）"
        )
        self.app_perf_overlay_enabled_checkbox.setToolTip(
            "开启后：主窗口右上角显示一个小型悬浮面板（所有页面可见），\n"
            "用于实时观察 UI gap / 卡顿次数 / 最近一次卡顿。\n"
            "点击悬浮面板可打开性能详情面板。"
        )
        layout.addWidget(self.app_perf_overlay_enabled_checkbox)

        self.app_perf_capture_stacks_checkbox = QtWidgets.QCheckBox("卡顿时采样主线程堆栈（建议开启）")
        self.app_perf_capture_stacks_checkbox.setToolTip(
            "开启后：当检测到卡顿时，会采样主线程当前调用栈，用于定位“到底卡在哪里”。\n"
            "关闭后：只记录卡顿时长与计数，但无法直接定位具体代码位置。"
        )
        layout.addWidget(self.app_perf_capture_stacks_checkbox)

        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 6, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)

        self.app_perf_stall_threshold_spinbox = QtWidgets.QSpinBox()
        self.app_perf_stall_threshold_spinbox.setRange(100, 5000)
        self.app_perf_stall_threshold_spinbox.setSingleStep(50)
        self.app_perf_stall_threshold_spinbox.setSuffix(" ms")
        self.app_perf_stall_threshold_spinbox.setToolTip(
            "卡顿判定阈值（毫秒）。\n"
            "建议 >=200ms：过低可能因正常调度抖动出现误报；过高则可能漏掉轻微卡顿。"
        )
        form.addRow("卡顿阈值：", self.app_perf_stall_threshold_spinbox)

        form_container = QtWidgets.QWidget()
        form_container.setLayout(form)
        layout.addWidget(form_container)

        button_row = QtWidgets.QWidget(group)
        button_layout = QtWidgets.QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(Sizes.SPACING_MEDIUM)

        self.open_perf_panel_button = QtWidgets.QPushButton("打开性能面板")
        self.open_perf_panel_button.setToolTip("打开全局性能详情面板（可保持在所有页面）")

        def _open_panel() -> None:
            parent = self.parent()
            open_method = getattr(parent, "open_performance_monitor_dialog", None) if parent is not None else None
            if callable(open_method):
                open_method()
                return
            from app.ui.foundation.performance_monitor import get_shared_performance_monitor
            from app.ui.dialogs.performance_monitor_dialog import PerformanceMonitorDialog

            dialog = PerformanceMonitorDialog(monitor=get_shared_performance_monitor(), parent=parent)
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()

        self.open_perf_panel_button.clicked.connect(_open_panel)
        button_layout.addWidget(self.open_perf_panel_button)
        button_layout.addStretch(1)
        layout.addWidget(button_row)

        def _sync_controls() -> None:
            monitor_enabled = bool(self.app_perf_monitor_enabled_checkbox.isChecked())
            overlay_enabled = bool(self.app_perf_overlay_enabled_checkbox.isChecked())
            if overlay_enabled and not monitor_enabled:
                self.app_perf_monitor_enabled_checkbox.setChecked(True)
                monitor_enabled = True
            if not monitor_enabled and overlay_enabled:
                self.app_perf_overlay_enabled_checkbox.setChecked(False)
            self.app_perf_capture_stacks_checkbox.setEnabled(monitor_enabled)
            self.app_perf_stall_threshold_spinbox.setEnabled(monitor_enabled)
            self.open_perf_panel_button.setEnabled(monitor_enabled or bool(self.app_perf_overlay_enabled_checkbox.isChecked()))

        self.app_perf_monitor_enabled_checkbox.toggled.connect(_sync_controls)
        self.app_perf_overlay_enabled_checkbox.toggled.connect(_sync_controls)
        _sync_controls()

        return group

    def _create_graph_appearance_settings_group(self) -> QtWidgets.QGroupBox:
        """创建画布外观相关设置组。"""
        group = QtWidgets.QGroupBox("画布外观")
        layout = QtWidgets.QVBoxLayout(group)

        self.show_basic_blocks_checkbox = QtWidgets.QCheckBox("显示基本块背景（basic blocks）")
        self.show_basic_blocks_checkbox.setToolTip(
            "启用后：在画布背景绘制 basic blocks 的彩色矩形区域，用于总览分块结构。\n"
            "注意：鸟瞰模式下会强制绘制 basic blocks，以避免画布空白。"
        )
        layout.addWidget(self.show_basic_blocks_checkbox)
        self.show_basic_blocks_checkbox.toggled.connect(
            self._update_basic_block_alpha_controls_enabled
        )

        blocks_form = QtWidgets.QFormLayout()
        blocks_form.setContentsMargins(0, 6, 0, 0)
        blocks_form.setHorizontalSpacing(10)
        blocks_form.setVerticalSpacing(6)

        blocks_alpha_tooltip = "基本块背景透明度（0%~100%）。数值越大颜色越实。"
        (
            self.basic_block_alpha_slider,
            self.basic_block_alpha_spinbox,
            blocks_alpha_container,
        ) = self._build_percent_slider_row(
            tooltip=blocks_alpha_tooltip,
            min_value=0,
            max_value=100,
            tick_interval=10,
            page_step=5,
        )
        blocks_form.addRow("基本块透明度：", blocks_alpha_container)

        blocks_form_container = QtWidgets.QWidget()
        blocks_form_container.setLayout(blocks_form)
        layout.addWidget(blocks_form_container)

        description_label = QtWidgets.QLabel(
            "用于调整节点在画布上的半透明效果。\n"
            "数值越大越不透明（越难透过节点看到后面的网格/内容）。"
        )
        description_label.setWordWrap(True)
        description_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;"
        )
        layout.addWidget(description_label)

        form = QtWidgets.QFormLayout()
        form.setContentsMargins(0, 6, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)

        tooltip = (
            "节点内容区背景的不透明度（10%~100%）。\n"
            "默认 70%：保持当前“节点半透明有底色”的观感。\n"
            "数值越大越不透明；数值越小越透明。"
        )

        self.graph_node_opacity_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.graph_node_opacity_slider.setRange(10, 100)
        self.graph_node_opacity_slider.setSingleStep(1)
        self.graph_node_opacity_slider.setPageStep(5)
        self.graph_node_opacity_slider.setTickInterval(10)
        self.graph_node_opacity_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        self.graph_node_opacity_slider.setToolTip(tooltip)

        self.graph_node_opacity_spinbox = QtWidgets.QSpinBox()
        self.graph_node_opacity_spinbox.setRange(10, 100)
        self.graph_node_opacity_spinbox.setSingleStep(1)
        self.graph_node_opacity_spinbox.setSuffix("%")
        self.graph_node_opacity_spinbox.setToolTip(tooltip)
        self.graph_node_opacity_spinbox.setMinimumWidth(70)

        self.graph_node_opacity_slider.valueChanged.connect(
            self.graph_node_opacity_spinbox.setValue
        )
        self.graph_node_opacity_spinbox.valueChanged.connect(
            self.graph_node_opacity_slider.setValue
        )

        container = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self.graph_node_opacity_slider, 1)
        row.addWidget(self.graph_node_opacity_spinbox)

        form.addRow("节点内容区不透明度：", container)
        form_container = QtWidgets.QWidget()
        form_container.setLayout(form)
        layout.addWidget(form_container)

        self._update_basic_block_alpha_controls_enabled()
        return group

    def _create_output_settings_group(self) -> QtWidgets.QGroupBox:
        """创建输出与打印设置组"""
        group = QtWidgets.QGroupBox("输出与打印")
        layout = QtWidgets.QVBoxLayout(group)
        
        # 布局调试打印
        self.layout_debug_checkbox = QtWidgets.QCheckBox("布局调试打印")
        self.layout_debug_checkbox.setToolTip(
            "启用后，自动排版时会打印节点排序、位置计算等详细信息。\n"
            "用于调试布局算法，默认关闭以保持控制台简洁。\n"
            "✅ 立即生效，无需重启"
        )
        layout.addWidget(self.layout_debug_checkbox)

        # 图编辑器详细日志（包含自动排版的错误提示打印）
        self.graph_ui_verbose_checkbox = QtWidgets.QCheckBox("图编辑器详细日志（含自动排版错误打印）")
        self.graph_ui_verbose_checkbox.setToolTip(
            "启用后，图编辑器会在控制台输出更详细的调试信息，\n"
            "包括自动排版的错误原因、节点/连线构建细节等。\n"
            "用于排查自动排版按钮无响应或图形项异常问题。\n"
            "✅ 立即生效，无需重启"
        )
        layout.addWidget(self.graph_ui_verbose_checkbox)

        # TwoRowField 行高调试打印（用于排查表格行高与 sizeHint 不一致）
        self.two_row_field_debug_checkbox = QtWidgets.QCheckBox("TwoRowField 行高调试打印")
        self.two_row_field_debug_checkbox.setToolTip(
            "启用后，两行结构字段表格（TwoRowField）在调整行高时会打印\n"
            "[UI调试/TwoRowField] kind/row_index/hint_height/target_height/actual_height 等信息。\n"
            "用于排查表格行高与子控件 sizeHint 对齐问题，默认关闭以避免刷屏。\n"
            "✅ 立即生效，无需重启"
        )
        layout.addWidget(self.two_row_field_debug_checkbox)

        # 节点加载详细日志
        self.node_loading_checkbox = QtWidgets.QCheckBox("节点加载详细日志（需要重启）")
        self.node_loading_checkbox.setToolTip(
            "启用后，启动时会打印节点定义加载的详细信息。\n"
            "用于调试节点定义问题，默认关闭。\n"
            "⚠️ 需要重启程序才能生效"
        )
        layout.addWidget(self.node_loading_checkbox)
        
        # 验证器详细模式
        self.validator_verbose_checkbox = QtWidgets.QCheckBox("验证器详细模式")
        self.validator_verbose_checkbox.setToolTip(
            "启用后，验证器会输出更详细的验证过程信息。\n"
            "用于调试验证逻辑，默认关闭。\n"
            "✅ 立即生效，无需重启"
        )
        layout.addWidget(self.validator_verbose_checkbox)
        
        # 代码解析详细信息
        self.dsl_parser_checkbox = QtWidgets.QCheckBox("代码解析详细信息")
        self.dsl_parser_checkbox.setToolTip(
            "启用后，解析器会输出详细的解析过程信息。\n"
            "用于调试节点图代码解析问题，默认关闭。\n"
            "✅ 立即生效，无需重启"
        )
        layout.addWidget(self.dsl_parser_checkbox)
        
        # 代码生成详细信息
        self.dsl_generator_checkbox = QtWidgets.QCheckBox("代码生成详细信息")
        self.dsl_generator_checkbox.setToolTip(
            "启用后，代码生成器会输出详细的事件流分析、拓扑排序等信息。\n"
            "用于调试节点图代码生成问题，默认关闭以保持控制台简洁。\n"
            "✅ 立即生效，无需重启"
        )
        layout.addWidget(self.dsl_generator_checkbox)

        # 真实执行调试输出
        self.real_exec_verbose_checkbox = QtWidgets.QCheckBox("真实执行调试输出（识别/拖拽/校验详细日志）")
        self.real_exec_verbose_checkbox.setToolTip(
            "启用后，真实执行器会打印每一步的识别列表、拖拽向量、\n"
            "相位相关位移估计、连线验证指标以及失败截图路径。\n"
            "用于定位真实执行问题，默认关闭以保持输出简洁。\n"
            "✅ 立即生效，无需重启"
        )
        layout.addWidget(self.real_exec_verbose_checkbox)

        # 节点图 GIA 导出：节点坐标缩放（仅影响导入后的分布展示）
        node_pos_scale_layout = QtWidgets.QHBoxLayout()
        node_pos_scale_label = QtWidgets.QLabel("GIA 节点坐标缩放：")
        self.ugc_gia_node_pos_scale_spinbox = QtWidgets.QDoubleSpinBox()
        self.ugc_gia_node_pos_scale_spinbox.setRange(0.1, 200.0)
        self.ugc_gia_node_pos_scale_spinbox.setDecimals(2)
        self.ugc_gia_node_pos_scale_spinbox.setSingleStep(0.1)
        self.ugc_gia_node_pos_scale_spinbox.setSuffix("×")
        self.ugc_gia_node_pos_scale_spinbox.setToolTip(
            "导出节点图 `.gia` 时节点坐标缩放倍数（仅影响编辑器中的分布展示，不影响图逻辑）。\n"
            "- 会对 GraphModel.pos 的 x/y 同步乘法缩放；\n"
            "- 导出时仍会做一次 X 轴居中偏移；\n"
            "- 默认 2.0 为经验值：不缩放时更容易显得“过于紧凑”。\n"
            "取值建议：0.1 ~ 200.0"
        )
        self.ugc_gia_node_pos_scale_spinbox.setMinimumWidth(120)
        node_pos_scale_layout.addWidget(node_pos_scale_label)
        node_pos_scale_layout.addWidget(self.ugc_gia_node_pos_scale_spinbox)
        node_pos_scale_layout.addStretch()
        layout.addLayout(node_pos_scale_layout)
        
        return group
    
    def _create_step_settings_group(self) -> QtWidgets.QGroupBox:
        """创建步骤与任务设置组"""
        group = QtWidgets.QGroupBox("步骤与任务清单")
        layout = QtWidgets.QVBoxLayout(group)
        
        # 步骤生成模式
        mode_layout = QtWidgets.QHBoxLayout()
        mode_label = QtWidgets.QLabel("步骤生成顺序：")
        self.todo_mode_combo = QtWidgets.QComboBox()
        self.todo_mode_combo.addItem("人类模式（连线并创建）", "human")
        self.todo_mode_combo.addItem("AI-先配置后连线", "ai")
        self.todo_mode_combo.addItem("AI-逐个节点模式", "ai_node_by_node")
        self.todo_mode_combo.setToolTip(
            "选择任务清单的节点图步骤生成顺序。\n"
            "人类模式：按当前逻辑，从前驱/后继拖线并创建。\n"
            "AI-先配置后连线：先生成创建节点 + 类型/参数配置步骤，最后统一生成连线步骤。\n"
            "AI-逐个节点模式：每创建一个节点，立即生成该节点的类型/参数配置步骤；连线仍最后统一生成。\n"
            "⚠️ 修改后需要重新生成任务清单。"
        )
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.todo_mode_combo)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)

        # 合并连线步骤
        self.todo_merge_checkbox = QtWidgets.QCheckBox("合并连线步骤（简洁模式）")
        self.todo_merge_checkbox.setToolTip(
            "启用后，同一对节点间的多条连线会合并为一个步骤。\n"
            "例如：从A拖线创建B + A与B的其他连线 → 合并为一个步骤。\n"
            "✅ 简洁模式（默认）：适合用户操作，减少步骤数量\n"
            "❌ 详细模式：每条连线独立步骤，适合自动化脚本或教程\n"
            "⚠️ 需要重新生成任务清单才能生效"
        )
        layout.addWidget(self.todo_merge_checkbox)

        # 事件流子步骤分批加载（动态挂载）
        self.todo_event_flow_lazy_load_checkbox = QtWidgets.QCheckBox(
            "事件流子步骤分批加载（推荐）"
        )
        self.todo_event_flow_lazy_load_checkbox.setToolTip(
            "启用后：展开事件流根时，会分批逐步创建子步骤树项，并显示加载进度，保证 UI 可交互。\n"
            "关闭后：事件流根的全部子步骤会在任务树构建阶段一次性创建。\n"
            "⚠️ 超大事件流下可能出现明显卡顿或短暂无响应。\n"
            "提示：修改后可重新进入任务清单，或刷新任务清单以应用。"
        )
        layout.addWidget(self.todo_event_flow_lazy_load_checkbox)
        
        # 说明文本
        info_label = QtWidgets.QLabel(
            "注意：\n"
            "- 修改【步骤生成顺序 / 合并连线步骤】后，需要重新生成任务清单才能看到效果。\n"
            "- 修改【事件流子步骤分批加载】后，重新进入任务清单或刷新任务清单即可生效。"
        )
        info_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; padding-left: 20px;"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        return group
    
    def _create_runtime_settings_group(self) -> QtWidgets.QGroupBox:
        """创建执行与系统设置组"""
        group = QtWidgets.QGroupBox("执行与系统")
        layout = QtWidgets.QVBoxLayout(group)

        # 界面主题模式
        theme_layout = QtWidgets.QHBoxLayout()
        theme_label = QtWidgets.QLabel("界面主题：")
        self.ui_theme_combo = QtWidgets.QComboBox()
        self.ui_theme_combo.addItem("跟随系统（推荐）", "auto")
        self.ui_theme_combo.addItem("浅色主题", "light")
        self.ui_theme_combo.addItem("深色主题", "dark")
        self.ui_theme_combo.setToolTip(
            "选择界面整体的浅色/深色主题。\n"
            "跟随系统：根据操作系统的浅色/深色模式自动切换。\n"
            "浅色/深色：固定使用对应主题，不随系统变化。\n"
            "⚠️ 更改后需要重新启动程序才能完全生效。"
        )
        theme_layout.addWidget(theme_label)
        theme_layout.addWidget(self.ui_theme_combo)
        theme_layout.addStretch()
        layout.addLayout(theme_layout)

        # 自动保存间隔
        auto_save_layout = QtWidgets.QHBoxLayout()
        auto_save_label = QtWidgets.QLabel("自动保存间隔（秒）：")
        self.auto_save_spinbox = QtWidgets.QDoubleSpinBox()
        self.auto_save_spinbox.setRange(0.0, 60.0)
        self.auto_save_spinbox.setSingleStep(0.5)
        self.auto_save_spinbox.setDecimals(1)
        self.auto_save_spinbox.setToolTip(
            "设置自动保存的时间间隔。\n"
            "0 表示每次修改立即保存（默认），\n"
            "大于0表示间隔指定秒数后保存。\n"
            "✅ 立即生效，无需重启"
        )
        auto_save_layout.addWidget(auto_save_label)
        auto_save_layout.addWidget(self.auto_save_spinbox)
        auto_save_layout.addStretch()
        layout.addLayout(auto_save_layout)

        # 执行步骤方式（鼠标执行模式）
        mouse_mode_layout = QtWidgets.QHBoxLayout()
        mouse_mode_label = QtWidgets.QLabel("执行步骤方式：")
        self.mouse_mode_combo = QtWidgets.QComboBox()
        self.mouse_mode_combo.addItem("经典（不复位，直接移动+点击/拖拽）", "classic")
        self.mouse_mode_combo.addItem("混合（瞬移-复位，轨迹分段平滑）", "hybrid")
        self.mouse_mode_combo.setToolTip(
            "经典：直接移动并完成点击/拖拽，操作结束后鼠标停留在目标处。\n"
            "混合：瞬移到目标执行，拖拽按步进平滑移动，结束后将鼠标复位到原位置。\n"
            "与脚本 test_background_drag_qxsandbox.py 一致的策略。"
        )
        self.mouse_mode_combo.currentIndexChanged.connect(self._update_hybrid_controls_enabled)
        mouse_mode_layout.addWidget(mouse_mode_label)
        mouse_mode_layout.addWidget(self.mouse_mode_combo)
        mouse_mode_layout.addStretch()
        layout.addLayout(mouse_mode_layout)

        # 混合模式参数
        hybrid_params_layout = QtWidgets.QHBoxLayout()
        self.hybrid_params_container = QtWidgets.QWidget()
        hybrid_inner = QtWidgets.QHBoxLayout(self.hybrid_params_container)
        hybrid_inner.setContentsMargins(0, 0, 0, 0)
        hybrid_inner.setSpacing(10)
        hybrid_label = QtWidgets.QLabel("混合模式参数：")
        steps_label = QtWidgets.QLabel("步数")
        self.hybrid_steps_spinbox = QtWidgets.QSpinBox()
        self.hybrid_steps_spinbox.setRange(1, 500)
        self.hybrid_steps_spinbox.setSingleStep(1)
        self.hybrid_steps_spinbox.setToolTip("拖拽期间的分段步数，数值越大轨迹越平滑（默认 40）")
        sleep_label = QtWidgets.QLabel("步间隔(秒)")
        self.hybrid_step_sleep_spinbox = QtWidgets.QDoubleSpinBox()
        self.hybrid_step_sleep_spinbox.setRange(0.000, 0.200)
        self.hybrid_step_sleep_spinbox.setSingleStep(0.001)
        self.hybrid_step_sleep_spinbox.setDecimals(3)
        self.hybrid_step_sleep_spinbox.setToolTip("每一步的等待时间（秒），默认 0.008")
        hybrid_inner.addWidget(hybrid_label)
        hybrid_inner.addWidget(steps_label)
        hybrid_inner.addWidget(self.hybrid_steps_spinbox)
        hybrid_inner.addSpacing(10)
        hybrid_inner.addWidget(sleep_label)
        hybrid_inner.addWidget(self.hybrid_step_sleep_spinbox)
        hybrid_inner.addStretch()
        hybrid_params_layout.addWidget(self.hybrid_params_container)
        layout.addLayout(hybrid_params_layout)

        # 拖拽策略（仅影响拖拽/连线，点击仍由上面的执行步骤方式决定）
        drag_mode_layout = QtWidgets.QHBoxLayout()
        drag_mode_label = QtWidgets.QLabel("拖拽策略：")
        self.drag_mode_combo = QtWidgets.QComboBox()
        self.drag_mode_combo.addItem("自动（跟随执行步骤方式）", "auto")
        self.drag_mode_combo.addItem("瞬移（按下后直接到终点松开）", "instant")
        self.drag_mode_combo.addItem("步进（平滑移动）", "stepped")
        self.drag_mode_combo.setToolTip(
            "自动：拖拽行为跟随‘执行步骤方式’。\n"
            "瞬移：按下后直接瞬移到终点再松开（更快，可能更突兀）。\n"
            "步进：按步进平滑移动（更自然，略慢）。"
        )
        drag_mode_layout.addWidget(drag_mode_label)
        drag_mode_layout.addWidget(self.drag_mode_combo)
        drag_mode_layout.addStretch()
        layout.addLayout(drag_mode_layout)
        
        return group
    
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
        self.layout_y_debug_overlay_checkbox.setChecked(getattr(settings, "SHOW_LAYOUT_Y_DEBUG", False))
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
        relay_distance = int(getattr(settings, "LAYOUT_LOCAL_VAR_RELAY_MAX_BLOCK_DISTANCE", 5) or 5)
        if relay_distance < 3:
            relay_distance = 3
        if relay_distance > 10:
            relay_distance = 10
        self.local_var_relay_length_slider.setValue(relay_distance)
        self._update_local_var_relay_controls_enabled()

        node_alpha_percent = int(float(getattr(settings, "GRAPH_NODE_CONTENT_ALPHA", 0.7)) * 100.0)
        if node_alpha_percent < 10:
            node_alpha_percent = 10
        if node_alpha_percent > 100:
            node_alpha_percent = 100
        self.graph_node_opacity_slider.setValue(node_alpha_percent)

        # 画布外观：basic blocks
        self.show_basic_blocks_checkbox.setChecked(
            bool(getattr(settings, "SHOW_BASIC_BLOCKS", True))
        )
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
        self.graph_lod_enabled_checkbox.setChecked(
            bool(getattr(settings, "GRAPH_LOD_ENABLED", True))
        )

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
        self.graph_grid_enabled_checkbox.setChecked(
            bool(getattr(settings, "GRAPH_GRID_ENABLED", True))
        )
        self.graph_pan_freeze_viewport_checkbox.setChecked(
            bool(getattr(settings, "GRAPH_PAN_FREEZE_VIEWPORT_ENABLED", False))
        )
        self.graph_zoom_freeze_viewport_checkbox.setChecked(
            bool(getattr(settings, "GRAPH_ZOOM_FREEZE_VIEWPORT_ENABLED", False))
        )
        self.graph_pan_hide_icons_checkbox.setChecked(
            bool(getattr(settings, "GRAPH_PAN_HIDE_ICONS_ENABLED", True))
        )
        self.graph_grid_min_px_spinbox.setValue(
            float(getattr(settings, "GRAPH_GRID_MIN_PX", 12.0) or 12.0)
        )
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
        self.hybrid_step_sleep_spinbox.setValue(float(getattr(settings, "MOUSE_HYBRID_STEP_SLEEP", 0.008)))
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
        node_loading_changed = (self.node_loading_checkbox.isChecked() != settings.NODE_LOADING_VERBOSE)
        old_theme_mode = getattr(settings, "UI_THEME_MODE", "auto")
        
        # 记录关键开关的旧值（用于触发一次性重载）
        old_cross_block_copy = bool(settings.DATA_NODE_CROSS_BLOCK_COPY)
        old_local_var_relay_enabled = bool(getattr(settings, "LAYOUT_AUTO_INSERT_LOCAL_VAR_RELAY", False))
        old_local_var_relay_distance = int(getattr(settings, "LAYOUT_LOCAL_VAR_RELAY_MAX_BLOCK_DISTANCE", 5) or 5)
        
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
        settings.LAYOUT_LOCAL_VAR_RELAY_MAX_BLOCK_DISTANCE = int(self.local_var_relay_length_slider.value())
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
        app_perf_monitor_enabled = bool(self.app_perf_monitor_enabled_checkbox.isChecked()) or app_perf_overlay_enabled
        settings.APP_PERF_MONITOR_ENABLED = bool(app_perf_monitor_enabled)
        settings.APP_PERF_OVERLAY_ENABLED = bool(app_perf_overlay_enabled)
        settings.APP_PERF_STALL_THRESHOLD_MS = int(self.app_perf_stall_threshold_spinbox.value())
        settings.APP_PERF_CAPTURE_STACKS_ENABLED = bool(self.app_perf_capture_stacks_checkbox.isChecked())

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

        # 让当前打开的图立即按新阈值重新同步 LOD/可见性（避免“改了但不缩放就不生效”的错觉）
        self._resync_active_graph_scene_after_settings_change()
        new_theme_mode = self.ui_theme_combo.currentData()
        settings.UI_THEME_MODE = new_theme_mode
        # 强制启用：不再由设置页控制
        settings.RESOURCE_LIBRARY_AUTO_REFRESH_ENABLED = True
        settings.PRIVATE_EXTENSION_ENABLED = True
        # 若“结构增强类”的自动排版开关发生变化：在下次自动排版前强制以 .py 重新解析当前图
        # （避免在已加载的增强模型上叠加生成导致节点/连线膨胀或残留）
        should_force_reparse = (
            bool(old_cross_block_copy) != bool(settings.DATA_NODE_CROSS_BLOCK_COPY)
            or bool(old_local_var_relay_enabled) != bool(settings.LAYOUT_AUTO_INSERT_LOCAL_VAR_RELAY)
            or int(old_local_var_relay_distance) != int(settings.LAYOUT_LOCAL_VAR_RELAY_MAX_BLOCK_DISTANCE)
        )
        if should_force_reparse:
            parent = self.parent()
            graph_controller = getattr(parent, "graph_controller", None)
            if graph_controller and hasattr(graph_controller, "schedule_reparse_on_next_auto_layout"):
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
            theme_mode_changed = (new_theme_mode != old_theme_mode)
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
            self.show_warning("保存失败", "设置已应用但未能保存到配置文件。\n程序重启后将使用默认设置。")
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
        mode = self.mouse_mode_combo.currentData() if hasattr(self, 'mouse_mode_combo') else "classic"
        enabled = (mode == "hybrid")
        if hasattr(self, 'hybrid_params_container'):
            self.hybrid_params_container.setEnabled(bool(enabled))

    def _update_local_var_relay_controls_enabled(self) -> None:
        """根据“长连线中转”开关，启用/禁用阈值滑块与输入框。"""
        enabled = bool(self.local_var_relay_checkbox.isChecked()) if hasattr(self, "local_var_relay_checkbox") else False
        if hasattr(self, "local_var_relay_length_slider"):
            self.local_var_relay_length_slider.setEnabled(enabled)
        if hasattr(self, "local_var_relay_length_spinbox"):
            self.local_var_relay_length_spinbox.setEnabled(enabled)

    def _update_fast_preview_threshold_controls_enabled(self) -> None:
        enabled = bool(self.graph_fast_preview_checkbox.isChecked()) if hasattr(self, "graph_fast_preview_checkbox") else False
        node_box = getattr(self, "graph_fast_preview_node_threshold_spinbox", None)
        edge_box = getattr(self, "graph_fast_preview_edge_threshold_spinbox", None)
        if isinstance(node_box, QtWidgets.QWidget):
            node_box.setEnabled(enabled)
        if isinstance(edge_box, QtWidgets.QWidget):
            edge_box.setEnabled(enabled)

    def _update_basic_block_alpha_controls_enabled(self) -> None:
        enabled = bool(self.show_basic_blocks_checkbox.isChecked()) if hasattr(self, "show_basic_blocks_checkbox") else False
        slider = getattr(self, "basic_block_alpha_slider", None)
        box = getattr(self, "basic_block_alpha_spinbox", None)
        if isinstance(slider, QtWidgets.QWidget):
            slider.setEnabled(enabled)
        if isinstance(box, QtWidgets.QWidget):
            box.setEnabled(enabled)

    def _update_graph_lod_controls_enabled(self) -> None:
        """根据 LOD 总开关启用/禁用子控件。"""
        enabled = bool(self.graph_lod_enabled_checkbox.isChecked()) if hasattr(self, "graph_lod_enabled_checkbox") else False
        container = getattr(self, "graph_lod_params_container", None)
        if isinstance(container, QtWidgets.QWidget):
            container.setEnabled(enabled)
        self._update_graph_block_overview_controls_enabled()

    def _update_graph_block_overview_controls_enabled(self) -> None:
        """根据“鸟瞰模式”开关启用/禁用其参数区。"""
        lod_enabled = bool(self.graph_lod_enabled_checkbox.isChecked()) if hasattr(self, "graph_lod_enabled_checkbox") else False
        overview_enabled = bool(self.graph_block_overview_enabled_checkbox.isChecked()) if hasattr(self, "graph_block_overview_enabled_checkbox") else False
        enabled = bool(lod_enabled and overview_enabled)
        container = getattr(self, "graph_block_overview_params_container", None)
        if isinstance(container, QtWidgets.QWidget):
            container.setEnabled(enabled)

    def _update_graph_grid_controls_enabled(self) -> None:
        """根据“显示画布网格”开关启用/禁用网格参数。"""
        enabled = bool(self.graph_grid_enabled_checkbox.isChecked()) if hasattr(self, "graph_grid_enabled_checkbox") else True
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
            getattr(app_state, "resource_manager", None) if app_state is not None else getattr(parent, "resource_manager", None)
        )
        package_index_manager = (
            getattr(app_state, "package_index_manager", None) if app_state is not None else getattr(parent, "package_index_manager", None)
        )
        if resource_manager is None:
            self.show_warning("无法执行", "未找到资源管理器实例，清除缓存失败。")
            return
        graph_controller = getattr(parent, "graph_controller", None)
        nav_coordinator = getattr(parent, "nav_coordinator", None)
        file_watcher_manager = getattr(parent, "file_watcher_manager", None)
        graph_property_panel = getattr(parent, "graph_property_panel", None)
        had_active_graph = bool(
            graph_controller
            and getattr(graph_controller, "current_graph_id", None)
        )
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
            f"已清除所有缓存。\n\n磁盘缓存删除 {removed} 个文件，内存缓存已清空（graph_data: {removed_payload_items} 条）。{extra}"
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


