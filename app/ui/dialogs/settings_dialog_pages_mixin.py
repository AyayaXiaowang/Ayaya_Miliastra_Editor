"""SettingsDialog 的“页面/分组构建”混入。

本模块只负责设置对话框的 UI 组装（控件创建 + signal 连接）：
- 左侧分类页 & 右侧滚动页
- 各分类下的 groupbox/控件构建

设置的读取/写回与跨模块副作用（重启、清缓存、同步 GraphScene 等）保留在
`app.ui.dialogs.settings_dialog.SettingsDialog` 主类中，避免 UI 构建与业务动作互相污染。
"""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from app.ui.foundation.theme_manager import Colors, Sizes
from app.ui.panels.panel_scaffold import build_scrollable_column


class SettingsDialogPagesMixin:
    """提供 SettingsDialog 的页面与分组 UI 构建方法。"""

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

        self.local_var_relay_length_slider.valueChanged.connect(
            self.local_var_relay_length_spinbox.setValue
        )
        self.local_var_relay_length_spinbox.valueChanged.connect(
            self.local_var_relay_length_slider.setValue
        )

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

        enter_tooltip = (
            "进入鸟瞰模式的缩放阈值（1%~100%）。低于该比例会隐藏节点/连线，仅显示块颜色。"
        )
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

        self.graph_pan_hide_icons_checkbox = QtWidgets.QCheckBox(
            "平移/缩放期间隐藏端口/图标（提升流畅度）"
        )
        self.graph_pan_hide_icons_checkbox.setToolTip(
            "平移（右键/中键/空格拖拽）或滚轮缩放期间临时隐藏端口圆点/⚙按钮/+按钮等小图元，\n"
            "并让叠加层跳过布局Y调试图标/链路徽标等调试叠层绘制，减少 Qt item 枚举与绘制固定开销。\n"
            "停止交互后按当前 LOD 状态恢复。"
        )
        extra_form.addRow(self.graph_pan_hide_icons_checkbox)

        self.graph_pan_freeze_viewport_checkbox = QtWidgets.QCheckBox(
            "拖拽平移期间冻结为静态快照（极致性能）"
        )
        self.graph_pan_freeze_viewport_checkbox.setToolTip(
            "拖拽平移画布（右键/中键/空格拖拽）期间抓取一张 viewport 快照并冻结为静态画面。\n"
            "拖拽平移过程中不再重绘大量节点/连线，超大图更丝滑。\n"
            "代价：拖拽平移过程中不会显示新进入视口的内容；松手后恢复真实渲染。"
        )
        extra_form.addRow(self.graph_pan_freeze_viewport_checkbox)

        self.graph_zoom_freeze_viewport_checkbox = QtWidgets.QCheckBox(
            "滚轮缩放期间冻结为静态快照（极致性能）"
        )
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
        self.graph_block_overview_enabled_checkbox.toggled.connect(
            self._update_graph_block_overview_controls_enabled
        )

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
        self.graph_fast_preview_node_threshold_spinbox.setToolTip(
            "快速预览触发阈值：节点数量 ≥ 该值时可自动进入压缩预览。"
        )
        threshold_form.addRow(
            "快速预览节点阈值：", self.graph_fast_preview_node_threshold_spinbox
        )

        self.graph_fast_preview_edge_threshold_spinbox = QtWidgets.QSpinBox()
        self.graph_fast_preview_edge_threshold_spinbox.setRange(50, 50000)
        self.graph_fast_preview_edge_threshold_spinbox.setSingleStep(50)
        self.graph_fast_preview_edge_threshold_spinbox.setToolTip(
            "快速预览触发阈值：连线数量 ≥ 该值时可自动进入压缩预览。"
        )
        threshold_form.addRow(
            "快速预览连线阈值：", self.graph_fast_preview_edge_threshold_spinbox
        )

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
            open_method = (
                getattr(parent, "open_performance_monitor_dialog", None) if parent is not None else None
            )
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
            self.open_perf_panel_button.setEnabled(
                monitor_enabled or bool(self.app_perf_overlay_enabled_checkbox.isChecked())
            )

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
        self.show_basic_blocks_checkbox.toggled.connect(self._update_basic_block_alpha_controls_enabled)

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
        description_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;")
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

        self.graph_node_opacity_slider.valueChanged.connect(self.graph_node_opacity_spinbox.setValue)
        self.graph_node_opacity_spinbox.valueChanged.connect(self.graph_node_opacity_slider.setValue)

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
        self.todo_event_flow_lazy_load_checkbox = QtWidgets.QCheckBox("事件流子步骤分批加载（推荐）")
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

