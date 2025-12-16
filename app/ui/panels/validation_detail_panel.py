"""验证问题详情面板 - 作为右侧标签页展示选中问题的详细信息。"""

from __future__ import annotations

from typing import Optional

from PyQt6 import QtWidgets

from app.ui.foundation.theme_manager import Colors
from app.ui.panels.panel_scaffold import PanelScaffold, SectionCard
from engine.validate.comprehensive_types import ValidationIssue


class ValidationDetailPanel(PanelScaffold):
    """验证问题详情面板。

    作为主窗口右侧的“详细信息”标签使用，由验证页面在用户双击问题项时
    通过 `set_issue()` 注入当前选中的 `ValidationIssue`。
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(
            parent,
            title="验证详情",
            description="在左侧列表中双击验证问题后，这里会显示详细描述与建议。",
        )
        self.current_issue: Optional[ValidationIssue] = None
        self._build_ui()

    def _build_ui(self) -> None:
        """构建面板 UI 结构。"""
        self.status_badge = self.create_status_badge(
            "ValidationDetailStatusBadge",
            "未选择问题",
        )
        self.set_status_widget(self.status_badge)

        detail_section = SectionCard(
            "问题详细信息",
            "展示当前选中验证问题的级别、位置、描述与建议。",
        )
        self.detail_text = QtWidgets.QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setPlaceholderText(
            "在左侧验证结果列表中双击某个问题，这里会显示对应的详细信息。"
        )
        detail_section.add_content_widget(self.detail_text)
        self.body_layout.addWidget(detail_section, 1)

        self._apply_neutral_state()

    def _apply_neutral_state(self) -> None:
        """应用“未选择问题”的状态样式。"""
        self.status_badge.setText("未选择问题")
        self.status_badge.apply_palette(Colors.INFO_BG, Colors.TEXT_SECONDARY)
        self.detail_text.clear()

    def set_issue(self, issue: Optional[ValidationIssue]) -> None:
        """设置当前选中的验证问题并刷新显示。"""
        self.current_issue = issue
        if issue is None:
            self._apply_neutral_state()
            return

        self._update_status_badge_for_issue(issue)
        self._update_detail_text_for_issue(issue)

    def _update_status_badge_for_issue(self, issue: ValidationIssue) -> None:
        """根据问题级别更新状态徽章。"""
        level = (issue.level or "").lower()
        if level == "error":
            text = "错误"
            bg = Colors.ERROR_BG
            fg = Colors.ERROR
        elif level == "warning":
            text = "警告"
            bg = Colors.WARNING_BG
            fg = Colors.WARNING
        elif level == "info":
            text = "提示"
            bg = Colors.INFO_BG
            fg = Colors.INFO
        else:
            text = level or "未知级别"
            bg = Colors.INFO_BG
            fg = Colors.TEXT_PRIMARY

        self.status_badge.setText(f"{text}：{issue.category}")
        self.status_badge.apply_palette(bg, fg)

    def _update_detail_text_for_issue(self, issue: ValidationIssue) -> None:
        """根据问题内容构建详情文本。"""
        lines: list[str] = []

        level_display = {
            "error": "错误",
            "warning": "警告",
            "info": "提示",
        }.get((issue.level or "").lower(), issue.level or "未知级别")

        lines.append(f"级别：{level_display}")
        lines.append(f"分类：{issue.category}")
        location_text = issue.location or ""
        lines.append(f"位置：{location_text or '（无具体位置）'}")

        lines.append("")
        lines.append(f"问题：{issue.message}")

        if getattr(issue, "suggestion", ""):
            lines.append("")
            lines.append(f"建议：{issue.suggestion}")

        if getattr(issue, "reference", ""):
            lines.append("")
            lines.append(f"参考：{issue.reference}")

        self.detail_text.setPlainText("\n".join(lines))


