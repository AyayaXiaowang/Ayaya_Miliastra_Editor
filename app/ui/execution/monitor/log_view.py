# -*- coding: utf-8 -*-
"""
日志视图控制器（LogViewController）
负责日志记录、筛选、搜索、HTML渲染与步骤上下文管理
"""

from datetime import datetime
from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtCore import Qt

from ui.foundation.theme_manager import Colors


class LogViewController:
    """日志子系统控制器：管理日志记录、筛选、搜索与HTML渲染"""

    def __init__(
        self,
        log_text_browser: QtWidgets.QTextBrowser,
        search_input: QtWidgets.QLineEdit,
        filter_combo: QtWidgets.QComboBox,
    ):
        """
        初始化日志控制器
        
        参数:
            log_text_browser: 日志文本显示控件
            search_input: 搜索输入框
            filter_combo: 筛选下拉框
        """
        self._log_text = log_text_browser
        self._search_input = search_input
        self._filter_combo = filter_combo

        # 日志数据与筛选状态
        self._log_records: list[dict] = []
        self._log_filter_text: str = ""
        self._log_filter_type: str = "全部"
        self._log_case_sensitive: bool = False  # 固定为 False

        # 当前步骤上下文（由外部在步骤开始时注入）
        self._current_step_title: str = ""
        self._current_parent_title: str = ""
        self._current_step_id: str = ""
        self._current_step_tokens_html: str = ""
        self._current_step_tokens_plain: str = ""

        # 连接信号
        self._search_input.textChanged.connect(self._on_search_text_changed)
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)

    def append(
        self,
        message: str,
        context_tokens_html: str = "",
        parent_title: str = "",
        step_title: str = "",
        step_id: str = "",
    ) -> None:
        """
        追加一条日志记录并显示（如果匹配当前筛选条件）
        
        参数:
            message: 日志消息文本
            context_tokens_html: 行首上下文HTML（优先使用）
            parent_title: 父级标题（用于记录）
            step_title: 步骤标题（用于记录）
            step_id: 步骤ID（用于锚点）
        """
        ts = datetime.now().strftime("%H:%M:%S")
        category = self._classify_log_message(message)
        is_success = ("✓" in message) or ("成功" in message)
        is_error = ("✗" in message) or ("失败" in message)

        # 行首上下文：优先使用分段富文本；否则退化为纯文本步骤名
        if context_tokens_html:
            context_html_snapshot = context_tokens_html
        elif self._current_step_tokens_html:
            context_html_snapshot = self._current_step_tokens_html
        elif self._current_step_title or step_title:
            title_text = step_title or self._current_step_title
            context_html_snapshot = (
                f"<span style='color:{Colors.TEXT_SECONDARY};font-weight:600;'>"
                f"{self._escape_html(title_text)}</span> "
            )
        else:
            context_html_snapshot = ""

        record = {
            "ts": ts,
            "msg": message,
            "category": category,
            "is_success": bool(is_success),
            "is_error": bool(is_error),
            # 附带当前步骤上下文（不会影响分类）
            "parent": parent_title or self._current_parent_title,
            "step": step_title or self._current_step_title,
            "step_id": step_id or self._current_step_id,
            "context_html": context_html_snapshot,
        }
        self._log_records.append(record)

        if self._record_matches_current_filter(record):
            html = self._format_log_html(record)
            cursor = self._log_text.textCursor()
            cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
            cursor.insertHtml(html)
            cursor.insertBlock()
            self._log_text.setTextCursor(cursor)
            self._scroll_to_bottom()

    def clear(self) -> None:
        """清空日志记录与显示"""
        self._log_records = []
        self._log_text.clear()

    def set_filter_type(self, filter_type: str) -> None:
        """设置筛选类型（例如："全部"、"仅点击"、"仅OCR"等）"""
        self._log_filter_type = filter_type
        self.rebuild_view()

    def set_filter_text(self, text: str) -> None:
        """设置搜索文本"""
        self._log_filter_text = text or ""
        self.rebuild_view()

    def rebuild_view(self) -> None:
        """根据当前筛选条件重建日志显示"""
        self._log_text.clear()
        cursor = self._log_text.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        for rec in self._log_records:
            if self._record_matches_current_filter(rec):
                cursor.insertHtml(self._format_log_html(rec))
                cursor.insertBlock()
        self._log_text.setTextCursor(cursor)
        self._scroll_to_bottom()

    def set_current_step_context(self, step_title: str, parent_title: str) -> None:
        """
        设置当前步骤上下文（仅显示当前步骤）
        
        参数:
            step_title: 步骤标题
            parent_title: 父级标题
        """
        # 切换步骤时重置上一条的富文本锚点，避免行首标签沿用上一步
        self._current_step_id = ""
        self._current_step_tokens_html = ""
        self._current_step_tokens_plain = ""
        self._current_step_title = str(step_title or "")
        self._current_parent_title = str(parent_title or "")

    def set_current_step_tokens(self, step_id: str, tokens: list) -> None:
        """
        设置用于每行行首展示的分段富文本（动作+节点名），并将其变为可点击锚点
        
        参数:
            step_id: 步骤ID（用于锚点链接）
            tokens: 分段富文本列表 [{ text, color, bg?, bold? }]
        """
        self._current_step_id = str(step_id or "")
        self._current_step_tokens_html = self._tokens_to_anchor_html(self._current_step_id, tokens)
        # 提取纯文本作为标题回退
        if isinstance(tokens, list):
            parts = []
            for t in tokens:
                if isinstance(t, dict):
                    txt = str(t.get("text", "") or "").strip()
                    if txt:
                        parts.append(txt)
            self._current_step_tokens_plain = " ".join(parts)
        else:
            self._current_step_tokens_plain = ""

    def get_current_display_title(self) -> str:
        """获取当前可显示的标题（优先步骤名，回退到tokens纯文本）"""
        title = str(self._current_step_title or "").strip()
        if title:
            return title
        fallback = str(self._current_step_tokens_plain or "").strip()
        return fallback

    def on_anchor_clicked(self, url: QtCore.QUrl) -> str:
        """
        处理锚点点击事件
        
        参数:
            url: 点击的 URL
            
        返回:
            todo_id 字符串，如果不是 todo: 协议则返回空字符串
        """
        if url is None:
            return ""
        if url.scheme() == "todo":
            todo_id = url.path() or url.toString().replace("todo:", "")
            todo_id = todo_id.lstrip(":/")
            return todo_id
        return ""

    # === 私有方法：筛选与分类 ===

    def _on_search_text_changed(self, text: str) -> None:
        """搜索文本变化回调"""
        self._log_filter_text = text or ""
        self.rebuild_view()

    def _on_filter_changed(self) -> None:
        """筛选类型变化回调"""
        self._log_filter_type = str(self._filter_combo.currentText())
        self.rebuild_view()

    def _record_matches_current_filter(self, rec: dict) -> bool:
        """判断记录是否匹配当前筛选条件"""
        # 类型筛选
        t = self._log_filter_type
        c = rec.get("category", "")
        is_success = bool(rec.get("is_success"))
        is_error = bool(rec.get("is_error"))

        if t == "仅鼠标操作" and c not in ("mouse", "click", "drag"):
            return False
        if t == "仅点击" and c != "click":
            return False
        if t == "仅拖拽" and c != "drag":
            return False
        if t == "仅识别/视觉" and c != "recognize":
            return False
        if t == "仅OCR" and c != "ocr":
            return False
        if t == "仅截图" and c != "screenshot":
            return False
        if t == "仅等待" and c != "wait":
            return False
        if t == "仅连接" and c != "connect":
            return False
        if t == "仅创建" and c != "create":
            return False
        if t == "仅参数配置" and c != "config":
            return False
        if t == "仅回退/重试" and c != "retry":
            return False
        if t == "仅校准/视口" and c not in ("calibrate", "viewport"):
            return False
        if t == "仅步骤摘要" and c != "step":
            return False
        if t == "仅成功" and not is_success:
            return False
        if t == "仅失败" and not is_error:
            return False

        # 文本搜索（始终不区分大小写）
        query = self._log_filter_text
        if query:
            hay = rec.get("msg", "")
            if not self._log_case_sensitive:
                hay = hay.lower()
                query = query.lower()
            if query not in hay:
                return False
        return True

    def _classify_log_message(self, message: str) -> str:
        """根据消息内容分类日志（顺序从更具体到更一般）"""
        m = message
        if "执行步骤:" in m:
            return "step"
        if "拖拽连线" in m or "连线" in m:
            return "connect"
        # 先判定拖拽，再判定点击，避免"按住左键拖拽"被误判为点击
        if ("拖拽" in m) or ("拖动" in m) or ("按住" in m) or ("drag" in m):
            return "drag"
        if ("双击" in m) or ("单击" in m) or ("点击" in m) or ("右键" in m) or ("左键" in m) or ("click" in m):
            return "click"
        if "[鼠标]" in m:
            return "mouse"
        if "视觉识别" in m or "识别" in m:
            return "recognize"
        if "OCR" in m:
            return "ocr"
        if "截图" in m:
            return "screenshot"
        if "等待" in m:
            return "wait"
        if "创建" in m:
            return "create"
        if "参数配置" in m or "设置按钮" in m or "变参" in m or "字典" in m or "分支" in m:
            return "config"
        if "回退" in m or "重试" in m or "↺" in m:
            return "retry"
        if "校准" in m:
            return "calibrate"
        if "视口对齐" in m:
            return "viewport"
        return "other"

    def _escape_html(self, text: str) -> str:
        """HTML转义"""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def _format_log_html(self, rec: dict) -> str:
        """格式化单条日志记录为HTML"""
        ts = rec.get("ts", "")
        msg = rec.get("msg", "")
        category = rec.get("category", "other")
        is_success = bool(rec.get("is_success"))
        is_error = bool(rec.get("is_error"))

        # 颜色方案：基于主题 token 的语义配色
        left_colors = {
            "mouse": Colors.PRIMARY_DARK,
            "click": Colors.PRIMARY,
            "drag": Colors.PRIMARY_DARK,
            "recognize": Colors.SECONDARY,
            "ocr": Colors.MANAGEMENT,
            "screenshot": Colors.TEXT_SECONDARY,
            "wait": Colors.WARNING,
            "connect": Colors.WARNING,
            "create": Colors.SUCCESS,
            "config": Colors.SECONDARY_DARK,
            "retry": Colors.WARNING,
            "calibrate": Colors.INFO,
            "viewport": Colors.INFO,
            "step": Colors.TEXT_PRIMARY,
            "other": Colors.TEXT_DISABLED,
        }
        badge_bg = {
            "mouse": (Colors.BG_SELECTED, Colors.PRIMARY_DARK, "鼠标"),
            "click": (Colors.BG_SELECTED, Colors.PRIMARY_DARK, "点击"),
            "drag": (Colors.BG_SELECTED_HOVER, Colors.PRIMARY_DARK, "拖拽"),
            "recognize": (Colors.BG_CARD_HOVER, Colors.SECONDARY_DARK, "识别"),
            "ocr": (Colors.INFO_BG, Colors.INFO, "OCR"),
            "screenshot": (Colors.BG_HEADER, Colors.TEXT_SECONDARY, "截图"),
            "wait": (Colors.WARNING_BG, Colors.WARNING, "等待"),
            "connect": (Colors.WARNING_BG, Colors.WARNING, "连线"),
            "create": (Colors.SUCCESS_BG, Colors.SUCCESS, "创建"),
            "config": (Colors.BG_CARD_HOVER, Colors.SECONDARY_DARK, "参数"),
            "retry": (Colors.WARNING_BG, Colors.WARNING, "重试"),
            "calibrate": (Colors.INFO_BG, Colors.INFO, "校准"),
            "viewport": (Colors.INFO_BG, Colors.INFO, "视口"),
            "step": (Colors.BG_CARD, Colors.TEXT_PRIMARY, "步骤"),
            "other": (Colors.BG_CARD, Colors.TEXT_SECONDARY, "其它"),
        }
        left = left_colors.get(category, Colors.TEXT_DISABLED)
        bg, fg, label = badge_bg.get(category, (Colors.BG_CARD, Colors.TEXT_SECONDARY, ""))

        msg_html = self._escape_html(msg)
        ts_html = f"<span style='color:{Colors.TEXT_SECONDARY};'>[{self._escape_html(ts)}]</span>"

        # 成功/失败强调（文本色）
        text_color = Colors.TEXT_PRIMARY
        if is_success:
            text_color = Colors.SUCCESS
        if is_error:
            text_color = Colors.ERROR

        badge_html = (
            f"<span style='margin-right:6px;background:{bg};color:{fg};border-radius:3px;padding:0 4px;font-size:11px;'>{label}</span>"
            if label
            else ""
        )

        # 行首上下文：使用记录中快照（包含可点击锚点）
        context_html = rec.get("context_html", "")

        return (
            f"<div style='border-left:4px solid {left};padding:2px 6px 2px 8px;margin:2px 0;'>"
            f"{context_html}{badge_html}{ts_html} <span style='color:{text_color};font-weight:600;'>{msg_html}</span>"
            f"</div>"
        )

    def _tokens_to_anchor_html(self, step_id: str, tokens: list) -> str:
        """将分段富文本tokens转为可点击的HTML锚点"""
        if not isinstance(tokens, list) or len(tokens) == 0:
            return ""
        parts: list[str] = []
        for token in tokens:
            if not isinstance(token, dict):
                continue
            txt = str(token.get("text", ""))
            if not txt:
                continue
            color = str(token.get("color", Colors.TEXT_PRIMARY))
            bg = str(token.get("bg", "")) if token.get("bg") else ""
            bold = bool(token.get("bold", False))
            style_bits = [f"color:{color}"]
            if bg:
                style_bits.append(f"background-color:{bg}")
                style_bits.append("padding:0 2px")
                style_bits.append("border-radius:3px")
            if bold:
                style_bits.append("font-weight:600")
            style = ";".join(style_bits)
            parts.append(f"<span style='{style}'>{self._escape_html(txt)}</span>")
        inner = "".join(parts)
        href = f"todo:{self._escape_html(step_id)}" if step_id else "#"
        return f"<a href='{href}' style='text-decoration:none; margin-right:8px;'>{inner}</a>"

    def _scroll_to_bottom(self) -> None:
        """滚动日志到底部"""
        from ui.foundation.scroll_helpers import scroll_to_bottom
        scroll_to_bottom(self._log_text)

