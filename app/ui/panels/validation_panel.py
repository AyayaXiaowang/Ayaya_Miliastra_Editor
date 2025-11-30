"""验证结果面板 - 显示存档验证结果"""

from PyQt6 import QtCore, QtGui, QtWidgets
from typing import Dict, List

from ui.foundation.theme_manager import ThemeManager, Colors, Sizes
from ui.foundation.context_menu_builder import ContextMenuBuilder
from ui.panels.panel_scaffold import PanelScaffold, SectionCard
from engine.validate.comprehensive_validator import ValidationIssue


class ValidationPanel(PanelScaffold):
    """验证结果面板"""
    
    # 信号：跳转到错误位置
    jump_to_issue = QtCore.pyqtSignal(dict)
    
    def __init__(self, parent=None):
        super().__init__(
            parent,
            title="验证状态",
            description="查看存档的结构、配置与引用校验结果",
        )
        self.issues: List[ValidationIssue] = []
        self._build_ui()
        self._update_summary()
    
    def _build_ui(self) -> None:
        self.refresh_button = QtWidgets.QPushButton("重新验证")
        self.refresh_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.refresh_button.clicked.connect(self._on_refresh_clicked)
        self.add_action_widget(self.refresh_button)

        self.summary_badge = self.create_status_badge(
            "ValidationSummaryBadge",
            "✅ 未验证",
        )
        self.set_status_widget(self.summary_badge)

        issues_section = SectionCard("验证问题", "按分类展示全部校验项，双击列表项可定位问题来源")

        self.tree_widget = QtWidgets.QTreeWidget()
        self.tree_widget.setHeaderLabels(["验证结果"])
        self.tree_widget.setAlternatingRowColors(True)
        self.tree_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree_widget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self._show_context_menu)
        issues_section.add_content_widget(self.tree_widget, stretch=1)
        self.body_layout.addWidget(issues_section, 2)

        detail_section = SectionCard("详细信息", "双击问题项查看详细描述与建议")
        self.detail_text = QtWidgets.QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMaximumHeight(100)
        self.detail_text.setPlaceholderText("双击问题项查看详细信息...")
        detail_section.add_content_widget(self.detail_text)
        self.body_layout.addWidget(detail_section)
        self.setMinimumWidth(260)

    def update_issues(self, issues: List[ValidationIssue]):
        """更新问题列表"""
        self.issues = issues
        self._refresh_tree()
        self._update_summary()
    
    def _refresh_tree(self):
        """刷新树形显示"""
        expanded_states = {
            self.tree_widget.topLevelItem(i).text(0): self.tree_widget.topLevelItem(i).isExpanded()
            for i in range(self.tree_widget.topLevelItemCount())
        }
        self.tree_widget.setUpdatesEnabled(False)
        self.tree_widget.clear()
        try:
            if not self.issues:
                item = QtWidgets.QTreeWidgetItem(["✅ 所有验证通过"])
                item.setForeground(0, QtGui.QBrush(QtGui.QColor(0, 150, 0)))
                self.tree_widget.addTopLevelItem(item)
                return

            categorized: Dict[str, List[ValidationIssue]] = {}
            for issue in self.issues:
                categorized.setdefault(issue.category, []).append(issue)

            for category in sorted(categorized.keys()):
                category_issues = categorized[category]
                category_item = QtWidgets.QTreeWidgetItem([f"{category} ({len(category_issues)})"])
                category_item.setExpanded(expanded_states.get(category, True))

                font = category_item.font(0)
                font.setBold(True)
                category_item.setFont(0, font)

                sorted_issues = sorted(
                    category_issues,
                    key=lambda issue: (self._level_priority(issue.level), issue.location),
                )
                for issue in sorted_issues:
                    icon = self._get_level_icon(issue.level)
                    issue_text = f"{icon} {issue.location}"
                    issue_item = QtWidgets.QTreeWidgetItem([issue_text])
                    color = self._get_level_color(issue.level)
                    issue_item.setForeground(0, QtGui.QBrush(color))
                    issue_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, issue)
                    category_item.addChild(issue_item)

                self.tree_widget.addTopLevelItem(category_item)
        finally:
            self.tree_widget.setUpdatesEnabled(True)
    
    def _update_summary(self):
        """更新摘要显示"""
        if not self.issues:
            self.summary_badge.setText("✅ 验证通过")
            self.summary_badge.apply_palette(Colors.SUCCESS_BG, Colors.SUCCESS)
            return
        
        error_count = sum(1 for i in self.issues if i.level == "error")
        warning_count = sum(1 for i in self.issues if i.level == "warning")
        info_count = sum(1 for i in self.issues if i.level == "info")
        
        parts = []
        if error_count > 0:
            parts.append(f"❌ {error_count} 个错误")
        if warning_count > 0:
            parts.append(f"⚠️ {warning_count} 个警告")
        if info_count > 0:
            parts.append(f"ℹ️ {info_count} 个提示")
        
        summary_text = " | ".join(parts)
        self.summary_badge.setText(summary_text)
        
        if error_count > 0:
            self.summary_badge.apply_palette(Colors.ERROR_BG, Colors.ERROR)
        elif warning_count > 0:
            self.summary_badge.apply_palette(Colors.WARNING_BG, Colors.WARNING)
        else:
            self.summary_badge.apply_palette(Colors.INFO_BG, Colors.INFO)
    
    def _get_level_icon(self, level: str) -> str:
        """获取级别图标"""
        return {
            "error": "❌",
            "warning": "⚠️",
            "info": "ℹ️"
        }.get(level, "·")
    
    def _get_level_color(self, level: str) -> QtGui.QColor:
        """获取级别颜色"""
        return {
            "error": QtGui.QColor(220, 50, 50),
            "warning": QtGui.QColor(230, 150, 0),
            "info": QtGui.QColor(50, 120, 200)
        }.get(level, QtGui.QColor(100, 100, 100))

    @staticmethod
    def _level_priority(level: str) -> int:
        return {"error": 0, "warning": 1, "info": 2}.get(level, 3)
    
    def _on_item_double_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int):
        """双击项目"""
        issue = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if issue and isinstance(issue, ValidationIssue):
            # 显示详细信息
            self._show_issue_detail(issue)
            
            # 发送跳转信号
            if issue.detail:
                self.jump_to_issue.emit(issue.detail)
    
    def _show_issue_detail(self, issue: ValidationIssue):
        """显示问题详细信息"""
        detail_parts = []
        detail_parts.append(f"【{issue.category}】{issue.location}")
        detail_parts.append("")
        detail_parts.append(f"问题：{issue.message}")
        
        if issue.suggestion:
            detail_parts.append("")
            detail_parts.append(f"💡 建议：{issue.suggestion}")
        
        if issue.reference:
            detail_parts.append("")
            detail_parts.append(f"📖 参考：{issue.reference}")
        
        self.detail_text.setPlainText("\n".join(detail_parts))
    
    def _show_context_menu(self, pos: QtCore.QPoint):
        """显示右键菜单"""
        item = self.tree_widget.itemAt(pos)
        if not item:
            return
        
        issue = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not issue or not isinstance(issue, ValidationIssue):
            return
        
        builder = ContextMenuBuilder(self)
        if issue.detail:
            builder.add_action("🔍 跳转到此位置", lambda: self.jump_to_issue.emit(issue.detail))
        builder.add_action("📋 复制问题描述", lambda: self._copy_issue_text(issue))
        builder.exec_for(self.tree_widget, pos)
    
    def _copy_issue_text(self, issue: ValidationIssue):
        """复制问题文本"""
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(str(issue))
    
    # 折叠相关行为已删除
    
    def _on_refresh_clicked(self):
        """刷新按钮点击"""
        # 通过父窗口触发验证
        parent_window = self.window()
        if hasattr(parent_window, '_trigger_validation'):
            parent_window._trigger_validation()
    
    def clear(self):
        """清空显示"""
        self.issues = []
        self.tree_widget.clear()
        self.detail_text.clear()
        self.summary_badge.setText("✅ 未验证")
        self.summary_badge.apply_palette(Colors.INFO_BG, Colors.TEXT_PRIMARY)
    
    def get_error_count(self) -> int:
        """获取错误数量"""
        return sum(1 for i in self.issues if i.level == "error")
    
    def get_warning_count(self) -> int:
        """获取警告数量"""
        return sum(1 for i in self.issues if i.level == "warning")
    
    def has_errors(self) -> bool:
        """是否有错误"""
        return self.get_error_count() > 0

