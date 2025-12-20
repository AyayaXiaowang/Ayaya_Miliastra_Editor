"""设置对话框 - 用户友好的设置界面"""

from __future__ import annotations
from PyQt6 import QtCore, QtGui, QtWidgets
import sys

from app.ui.foundation.base_widgets import BaseDialog
from app.ui.foundation.theme_manager import ThemeManager, Colors, Sizes
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
            width=600,
            height=500,
            parent=parent,
        )
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        
        self._build_content()
        self._load_current_settings()
    
    def _apply_styles(self) -> None:
        """应用主题样式"""
        base_style = ThemeManager.dialog_surface_style(include_tables=False)
        self.setStyleSheet(
            base_style
            + f"""
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {Colors.BORDER_LIGHT};
                border-radius: {Sizes.RADIUS_SMALL}px;
                margin-top: {Sizes.SPACING_SMALL}px;
                padding: {Sizes.PADDING_SMALL}px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: {Sizes.SPACING_SMALL}px;
                padding: 0 {Sizes.PADDING_SMALL}px;
            }}
        """
        )
    
    def _build_content(self) -> None:
        """设置UI布局"""
        layout = self.content_layout
        
        # 标题
        title_label = QtWidgets.QLabel("程序设置")
        title_label.setStyleSheet(f"{ThemeManager.heading(level=1)} padding: 10px;")
        layout.addWidget(title_label)
        
        # 设置选项区域（使用滚动区域）
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        scroll_content = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(20)
        
        # ========== 自动排版 ==========
        auto_layout_group = self._create_auto_layout_settings_group()
        scroll_layout.addWidget(auto_layout_group)
        
        # ========== 输出与打印 ==========
        output_group = self._create_output_settings_group()
        scroll_layout.addWidget(output_group)
        
        # ========== 步骤与任务 ==========
        steps_group = self._create_step_settings_group()
        scroll_layout.addWidget(steps_group)
        
        # ========== 执行与系统 ==========
        runtime_group = self._create_runtime_settings_group()
        scroll_layout.addWidget(runtime_group)

        # ========== 资源库更新 ==========
        resource_update_group = self._create_resource_update_settings_group()
        scroll_layout.addWidget(resource_update_group)
        
        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area, 1)
        
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

    def _on_accept(self) -> None:
        """覆写基类接受逻辑，统一走设置保存流程。"""
        self._save_and_close()
    
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

        # 布局Y坐标调试（轻量 Tooltip）
        self.layout_y_debug_overlay_checkbox = QtWidgets.QCheckBox("布局Y坐标调试（节点旁感叹号）")
        self.layout_y_debug_overlay_checkbox.setToolTip(
            "启用后，每个节点左上角显示“!”图标，点击弹出可复制的调试Tooltip，\n"
            "展示当前Y轴分配的关键依据与链信息。轻量无全局避让，点击空白自动关闭。\n"
            "✅ 立即生效，无需重启"
        )
        layout.addWidget(self.layout_y_debug_overlay_checkbox)

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
        self.todo_mode_combo.addItem("AI模式（先创建再连接）", "ai")
        self.todo_mode_combo.setToolTip(
            "选择任务清单的节点图步骤生成顺序。\n"
            "人类模式：按当前逻辑，从前驱/后继拖线并创建。\n"
            "AI模式：先批量创建所有节点，再生成连接步骤，不使用‘连线并创建’。\n"
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
        
        # 说明文本
        info_label = QtWidgets.QLabel(
            "注意：修改此设置后，需要关闭并重新打开存档，\n"
            "或手动触发任务清单重新生成才能看到效果。"
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
    
    def _create_resource_update_settings_group(self) -> QtWidgets.QGroupBox:
        """创建资源库更新策略设置组"""
        group = QtWidgets.QGroupBox("资源库更新（节点图 / 管理配置等）")
        layout = QtWidgets.QVBoxLayout(group)

        description_label = QtWidgets.QLabel(
            "当外部工具修改 assets/资源库 下的节点图、管理配置或战斗预设等资源时，"
            "可以选择是否由程序自动检测并刷新视图，或仅在手动点击顶部“更新”按钮时刷新。"
        )
        description_label.setWordWrap(True)
        description_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;"
        )
        layout.addWidget(description_label)

        mode_layout = QtWidgets.QHBoxLayout()
        mode_label = QtWidgets.QLabel("资源库更新方式：")
        self.resource_update_mode_combo = QtWidgets.QComboBox()
        self.resource_update_mode_combo.addItem(
            "自动更新（推荐）：检测到资源库变更时自动刷新索引与相关视图",
            True,
        )
        self.resource_update_mode_combo.addItem(
            "手动更新：仅在点击顶部工具栏的“更新”按钮时刷新资源库",
            False,
        )
        self.resource_update_mode_combo.setToolTip(
            "自动更新：继续使用文件监控，在外部修改资源库时自动刷新。\n"
            "手动更新：关闭资源库目录自动监控，仅保留当前图文件监控；"
            "当确认外部工具已完成修改时，可通过主窗口顶部的“更新”按钮手动刷新视图。"
        )
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.resource_update_mode_combo)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)

        info_label = QtWidgets.QLabel(
            "说明：切换为“手动更新”后，资源库目录的自动监控将被关闭，"
            "避免频繁刷新带来的性能与日志开销；如需立即查看外部修改结果，"
            "请使用主窗口顶部的“更新”按钮。"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: 10px; padding-left: 20px;"
        )
        layout.addWidget(info_label)

        return group
    
    def _load_current_settings(self) -> None:
        """加载当前设置到UI"""
        self.tight_block_spacing_checkbox.setChecked(
            getattr(settings, "LAYOUT_TIGHT_BLOCK_PACKING", True)
        )
        self.layout_debug_checkbox.setChecked(settings.LAYOUT_DEBUG_PRINT)
        self.layout_y_debug_overlay_checkbox.setChecked(getattr(settings, "SHOW_LAYOUT_Y_DEBUG", False))
        self.graph_ui_verbose_checkbox.setChecked(getattr(settings, "GRAPH_UI_VERBOSE", False))
        self.node_loading_checkbox.setChecked(settings.NODE_LOADING_VERBOSE)
        self.validator_verbose_checkbox.setChecked(settings.VALIDATOR_VERBOSE)
        self.dsl_parser_checkbox.setChecked(settings.GRAPH_PARSER_VERBOSE)
        self.dsl_generator_checkbox.setChecked(settings.GRAPH_GENERATOR_VERBOSE)
        self.real_exec_verbose_checkbox.setChecked(settings.REAL_EXEC_VERBOSE)
        self.todo_merge_checkbox.setChecked(settings.TODO_MERGE_CONNECTION_STEPS)
        self.data_node_copy_checkbox.setChecked(settings.DATA_NODE_CROSS_BLOCK_COPY)
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
        # 资源库自动更新模式
        auto_refresh_enabled = bool(getattr(settings, "RESOURCE_LIBRARY_AUTO_REFRESH_ENABLED", True))
        idx_resource = self.resource_update_mode_combo.findData(auto_refresh_enabled)
        self.resource_update_mode_combo.setCurrentIndex(idx_resource if idx_resource != -1 else 0)
    
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
        old_resource_auto_refresh = bool(getattr(settings, "RESOURCE_LIBRARY_AUTO_REFRESH_ENABLED", True))
        
        # 应用设置
        settings.LAYOUT_TIGHT_BLOCK_PACKING = self.tight_block_spacing_checkbox.isChecked()
        settings.LAYOUT_DEBUG_PRINT = self.layout_debug_checkbox.isChecked()
        settings.SHOW_LAYOUT_Y_DEBUG = self.layout_y_debug_overlay_checkbox.isChecked()
        settings.GRAPH_UI_VERBOSE = self.graph_ui_verbose_checkbox.isChecked()
        settings.NODE_LOADING_VERBOSE = self.node_loading_checkbox.isChecked()
        settings.VALIDATOR_VERBOSE = self.validator_verbose_checkbox.isChecked()
        settings.GRAPH_PARSER_VERBOSE = self.dsl_parser_checkbox.isChecked()
        settings.GRAPH_GENERATOR_VERBOSE = self.dsl_generator_checkbox.isChecked()
        settings.REAL_EXEC_VERBOSE = self.real_exec_verbose_checkbox.isChecked()
        settings.TODO_MERGE_CONNECTION_STEPS = self.todo_merge_checkbox.isChecked()
        settings.DATA_NODE_CROSS_BLOCK_COPY = self.data_node_copy_checkbox.isChecked()
        new_theme_mode = self.ui_theme_combo.currentData()
        settings.UI_THEME_MODE = new_theme_mode
        # 资源库自动刷新模式
        settings.RESOURCE_LIBRARY_AUTO_REFRESH_ENABLED = bool(self.resource_update_mode_combo.currentData())
        # 若跨块复制开关发生变化（True↔False）：在下次自动排版前强制以 .py 重新解析当前图
        if bool(old_cross_block_copy) != bool(settings.DATA_NODE_CROSS_BLOCK_COPY):
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
            # 设置已成功保存，必要时应用资源库自动刷新开关到文件监控
            resource_auto_refresh_changed = (
                bool(old_resource_auto_refresh) != bool(settings.RESOURCE_LIBRARY_AUTO_REFRESH_ENABLED)
            )
            if resource_auto_refresh_changed:
                parent = self.parent()
                file_watcher_manager = getattr(parent, "file_watcher_manager", None)
                if file_watcher_manager is not None and hasattr(
                    file_watcher_manager, "set_resource_auto_refresh_enabled"
                ):
                    file_watcher_manager.set_resource_auto_refresh_enabled(
                        bool(settings.RESOURCE_LIBRARY_AUTO_REFRESH_ENABLED)
                    )
            # 如果修改了需要重启的设置，提示用户/询问是否立即重启
            theme_mode_changed = (new_theme_mode != old_theme_mode)
            if theme_mode_changed:
                # 优先处理主题更改：询问是否立即重启以应用新主题
                should_restart = self.confirm(
                    "设置已保存",
                    "您的设置已成功保存并立即生效。\n\n"
                    "界面主题的更改需要重启程序才能完全生效。\n\n"
                    "是否立即重启程序以应用新的界面主题？",
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


