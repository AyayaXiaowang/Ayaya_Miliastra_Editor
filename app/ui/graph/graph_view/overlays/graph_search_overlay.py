from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Optional, TYPE_CHECKING, cast, Any

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from app.ui.foundation.theme_manager import ThemeManager, Colors, Sizes
from app.ui.graph.graph_view.search.graph_search_index import (
    GraphSearchIndex,
    GraphSearchMatch,
    GraphSearchResultItem,
)

if TYPE_CHECKING:
    from app.ui.graph.graph_view import GraphView
    from app.ui.graph.graph_scene import GraphScene


class GraphSearchOverlay(QtWidgets.QFrame):
    """GraphView 画布内搜索浮层（Ctrl+F 呼出）。"""

    _DEFAULT_VISIBLE_RESULT_ROWS: int = 4
    _DEFAULT_PAGE_SIZE: int = 5  # 结果过多时按页加载，避免一次性渲染大量 item
    _MAX_CODE_PREVIEW_LINES: int = 10
    _MAX_CODE_PREVIEW_CHARS: int = 900
    _QUERY_DEBOUNCE_MS: int = 120
    _RESULT_ITEM_LAYOUT_MARGIN_V_PX: int = 6
    _RESULT_ITEM_LAYOUT_SPACING_PX: int = 2

    # 结果列表内“命中高亮”样式（rich text）
    _HIT_HIGHLIGHT_BG: str = "#FFD54F"
    _HIT_HIGHLIGHT_FG: str = "#000000"

    def __init__(self, view: "GraphView"):
        # 注意：不要以 viewport() 作为父控件。
        # QGraphicsView 在平移时可能走 viewport.scroll 的像素滚动优化路径，
        # 会把 viewport 子 widget 的像素一起搬走，导致叠层“跟着画布动”。
        # 作为 GraphView 的直接子控件（viewport 的兄弟层）可天然规避该问题。
        super().__init__(view)
        self._view: GraphView = view

        self._index: Optional[GraphSearchIndex] = None
        self._indexed_model_id: int = 0
        self._indexed_graph_id: str = ""

        self._match: GraphSearchMatch = GraphSearchMatch(
            query="",
            tokens_cf=tuple(),
            source_spans=tuple(),
            node_ids=[],
            edge_ids_to_keep=[],
            var_relation_hints_by_node_id={},
        )
        self._matched_node_set: set[str] = set()
        self._current_index: int = 0
        self._results_expanded: bool = False
        self._results_page_index: int = 0
        self._results_page_size: int = int(self._DEFAULT_PAGE_SIZE)
        self._cached_result_item_height_px: int = 0

        self._cached_source_abs: str = ""
        self._cached_source_lines: list[str] = []

        # 搜索输入防抖：避免每个字符都触发全图匹配/灰显/列表重建导致卡顿
        self._pending_query: str = ""
        self._query_timer = QtCore.QTimer(self)
        self._query_timer.setSingleShot(True)
        self._query_timer.timeout.connect(self._run_pending_query)

        self._build_ui()
        self.hide()

    def _build_ui(self) -> None:
        self.setObjectName("graphSearchOverlay")
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        self.setStyleSheet(
            ThemeManager.input_style()
            + ThemeManager.button_style()
            + ThemeManager.scrollbar_style()
            + ThemeManager.graph_search_overlay_style()
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        self._top_row = QtWidgets.QWidget(self)
        top_row_layout = QtWidgets.QHBoxLayout(self._top_row)
        top_row_layout.setContentsMargins(0, 0, 0, 0)
        top_row_layout.setSpacing(8)

        title = QtWidgets.QLabel("搜索", self)
        font = title.font()
        font.setBold(True)
        title.setFont(font)
        top_row_layout.addWidget(title)

        self._search_edit = QtWidgets.QLineEdit(self)
        self._search_edit.setPlaceholderText("搜索：标题 / ID / GIA序号 / 变量名 / 常量 / 注释 / 行号")
        self._search_edit.setMinimumHeight(Sizes.INPUT_HEIGHT)
        self._search_edit.textChanged.connect(self._on_query_text_changed)
        self._search_edit.installEventFilter(self)
        top_row_layout.addWidget(self._search_edit, 1)

        self._count_label = QtWidgets.QLabel("0/0", self)
        self._count_label.setObjectName("graphSearchCount")
        self._count_label.setMinimumWidth(56)
        self._count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top_row_layout.addWidget(self._count_label)

        self._results_toggle = QtWidgets.QToolButton(self)
        self._results_toggle.setToolTip("展开/收起结果列表")
        self._results_toggle.setCheckable(True)
        self._results_toggle.setChecked(False)
        self._results_toggle.setArrowType(Qt.ArrowType.DownArrow)
        self._results_toggle.toggled.connect(self._on_results_toggled)
        top_row_layout.addWidget(self._results_toggle)

        self._prev_button = QtWidgets.QToolButton(self)
        self._prev_button.setToolTip("上一个（Shift+Enter / Shift+F3）")
        style = self.style() or QtWidgets.QApplication.style()
        if style is None:
            raise RuntimeError("无法获取 Qt 样式（QStyle）。")
        self._prev_button.setIcon(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ArrowUp))
        self._prev_button.clicked.connect(self.goto_prev)
        top_row_layout.addWidget(self._prev_button)

        self._next_button = QtWidgets.QToolButton(self)
        self._next_button.setToolTip("下一个（Enter / F3）")
        self._next_button.setIcon(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ArrowDown))
        self._next_button.clicked.connect(self.goto_next)
        top_row_layout.addWidget(self._next_button)

        self._close_button = QtWidgets.QToolButton(self)
        self._close_button.setToolTip("关闭（Esc）")
        self._close_button.setIcon(
            style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_TitleBarCloseButton)
        )
        self._close_button.clicked.connect(self.close_and_clear)
        top_row_layout.addWidget(self._close_button)

        layout.addWidget(self._top_row)

        # 结果列表（默认折叠，节省每次输入时的 UI 构建成本）
        self._results_container = QtWidgets.QFrame(self)
        results_layout = QtWidgets.QVBoxLayout(self._results_container)
        results_layout.setContentsMargins(0, 2, 0, 0)
        results_layout.setSpacing(4)

        self._results_list = QtWidgets.QListWidget(self._results_container)
        self._results_list.setObjectName("graphSearchResults")
        self._results_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self._results_list.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollMode.ScrollPerItem)
        self._results_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # 分页模式下不需要滚动条；始终保证“整条结果组件”完整显示，不出现半条。
        self._results_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._results_list.setSpacing(0)
        self._results_list.setWordWrap(False)
        self._results_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._results_list.itemActivated.connect(self._on_result_item_activated)
        self._results_list.itemClicked.connect(self._on_result_item_clicked)
        results_layout.addWidget(self._results_list)

        # 分页控制行
        self._page_row = QtWidgets.QWidget(self._results_container)
        page_layout = QtWidgets.QHBoxLayout(self._page_row)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(8)

        self._page_prev_button = QtWidgets.QToolButton(self._page_row)
        self._page_prev_button.setToolTip("上一页")
        self._page_prev_button.setIcon(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ArrowLeft))
        self._page_prev_button.clicked.connect(self._goto_prev_page)
        page_layout.addWidget(self._page_prev_button)

        self._page_label = QtWidgets.QLabel("第 0/0 页（共 0 条）", self._page_row)
        self._page_label.setObjectName("graphSearchPageLabel")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page_layout.addWidget(self._page_label, 1)

        self._page_next_button = QtWidgets.QToolButton(self._page_row)
        self._page_next_button.setToolTip("下一页")
        self._page_next_button.setIcon(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ArrowRight))
        self._page_next_button.clicked.connect(self._goto_next_page)
        page_layout.addWidget(self._page_next_button)

        self._page_row.setVisible(False)
        results_layout.addWidget(self._page_row)

        self._results_container.setVisible(False)
        layout.addWidget(self._results_container)

        self._sync_nav_enabled()

    # --- 生命周期 ---

    def open_and_focus(self) -> None:
        # 先做一次定位（避免 show 时闪到默认 0,0）。
        # show/polish 后的二次定位由 showEvent 里延迟触发，避免 sizeHint 变化导致裁切。
        self.reposition()
        self.show()
        self.raise_()
        self._search_edit.setFocus()
        self._search_edit.selectAll()

    def showEvent(self, event: QtGui.QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        # show/polish 后延迟一次，确保布局与字体度量稳定
        QtCore.QTimer.singleShot(0, self.reposition)

    def close_and_clear(self) -> None:
        if hasattr(self, "_query_timer") and self._query_timer:
            self._query_timer.stop()
        self._pending_query = ""
        self._search_edit.blockSignals(True)
        self._search_edit.setText("")
        self._search_edit.blockSignals(False)
        self._clear_highlight_state()
        self._clear_results_list()
        self.hide()

    def on_scene_changed(self) -> None:
        """GraphView.setScene 后调用：清空索引与高亮状态，避免跨图复用旧结果。"""
        self._index = None
        self._indexed_model_id = 0
        self._indexed_graph_id = ""
        self._cached_source_abs = ""
        self._cached_source_lines = []
        if hasattr(self, "_query_timer") and self._query_timer:
            self._query_timer.stop()
        self._pending_query = ""
        self._clear_highlight_state()
        if hasattr(self, "_search_edit") and self._search_edit is not None:
            self._search_edit.blockSignals(True)
            self._search_edit.setText("")
            self._search_edit.blockSignals(False)

    def reposition(self) -> None:
        # 以 viewport 的几何（在 view 坐标系中）为准定位，确保始终贴合画布区域
        viewport_widget = self._view.viewport() if hasattr(self._view, "viewport") else None
        if viewport_widget is None:
            return
        viewport_geom = viewport_widget.geometry()
        if viewport_geom.isNull():
            return

        margin = 12
        # 位置约束：若视图开启了坐标标尺，则避开顶部/左侧的固定标尺区域，
        # 否则在缩放/重绘时可能被标尺覆盖，看起来像“搜索框消失”。
        show_coordinates = bool(getattr(self._view, "show_coordinates", False))
        ruler_height = 30 if show_coordinates else 0
        ruler_width = 80 if show_coordinates else 0

        x = int(viewport_geom.x() + ruler_width + margin)
        y = int(viewport_geom.y() + ruler_height + margin)

        max_width = 620
        min_width = 320
        available_width = int(viewport_geom.width() - ruler_width - margin * 2)
        if available_width <= 0:
            return
        # 在空间不足时允许缩小，优先保证不超出可用区域
        width = min(max_width, available_width)
        if width < min_width:
            width = available_width
        available_height = int(viewport_geom.height() - (y - viewport_geom.y()) - margin)

        # 结果列表展开时：根据可用高度自适应缩小页大小，避免把顶部搜索栏挤压裁切。
        if bool(getattr(self, "_results_expanded", False)):
            self._ensure_results_page_size_fits_available_height(available_height)

        desired_height = self._compute_desired_height_px()
        min_height = self._minimum_overlay_height_px()
        height = int(min(desired_height, max(int(min_height), int(available_height))))
        self.setGeometry(x, y, width, height)

    def _minimum_overlay_height_px(self) -> int:
        """保证顶部搜索栏完整可见的最小高度（不含结果列表）。"""
        layout = self.layout()
        if layout is None:
            return 64
        margins = layout.contentsMargins()
        height = int(margins.top() + margins.bottom())
        if hasattr(self, "_top_row") and self._top_row is not None:
            height += int(self._top_row.sizeHint().height())
        # 兜底：避免极端情况下过小导致边框/内边距压缩
        return max(48, height)

    def _ensure_results_page_size_fits_available_height(self, available_height: int) -> None:
        """在视口高度受限时，降低每页显示条数以优先保证顶部输入栏完整显示。"""
        if not bool(getattr(self, "_results_expanded", False)):
            return
        if not hasattr(self, "_results_container") or self._results_container is None:
            return
        if not self._results_container.isVisible():
            return
        total = len(list(self._match.node_ids or []))
        if total <= 0:
            return

        current_page_size = max(1, int(getattr(self, "_results_page_size", self._DEFAULT_PAGE_SIZE)))
        max_page_size = max(1, min(int(self._DEFAULT_PAGE_SIZE), int(total)))

        # 从大到小试探：选择“能放下”的最大页大小，减少分页带来的跳转成本。
        picked = 1
        for candidate in range(int(max_page_size), 0, -1):
            if self._required_height_for_page_size(candidate, total_results=total) <= int(available_height):
                picked = int(candidate)
                break

        if int(picked) == int(current_page_size):
            return

        self._results_page_size = int(picked)
        # 让当前选中的全局 index 保持在可见页内
        current_global = max(0, min(int(getattr(self, "_current_index", 0)), total - 1))
        self._results_page_index = int(current_global // int(picked))
        self._rebuild_results_list_page(force=True)

    def _required_height_for_page_size(self, page_size: int, *, total_results: int) -> int:
        """估算在给定页大小下 Overlay 需要的总高度（用于自适应）。"""
        outer_layout = self.layout()
        if outer_layout is None:
            return 64

        margins = outer_layout.contentsMargins()
        spacing = int(outer_layout.spacing())
        top_row_h = int(self._top_row.sizeHint().height()) if hasattr(self, "_top_row") else 0

        height = int(margins.top() + margins.bottom() + top_row_h)

        # 仅计算“展开结果列表”的场景：未展开时高度只需顶部栏即可
        height += spacing

        results_layout = self._results_container.layout() if hasattr(self, "_results_container") else None
        if results_layout is None:
            return max(64, height)

        r_margins = results_layout.contentsMargins()
        r_spacing = int(results_layout.spacing())

        item_h = int(self._result_item_height_px())
        frame_w = int(self._results_list.frameWidth()) if hasattr(self, "_results_list") else 0
        list_h = int(item_h * int(page_size) + frame_w * 2)

        height += int(r_margins.top() + r_margins.bottom() + list_h)

        # 分页行：只有当总结果数超过页大小时才会显示
        if int(total_results) > int(page_size):
            page_row_h = int(self._page_row.sizeHint().height()) if hasattr(self, "_page_row") else 0
            height += int(r_spacing + page_row_h)

        return max(64, height)

    # --- 事件与快捷键 ---

    def eventFilter(self, a0: QtCore.QObject, a1: QtCore.QEvent) -> bool:  # type: ignore[override]
        if a0 is self._search_edit and a1.type() == QtCore.QEvent.Type.KeyPress:
            key_event = a1  # type: ignore[assignment]
            if isinstance(key_event, QtGui.QKeyEvent):
                if key_event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_F3):
                    # 回车/下一个：若有 pending query（防抖未触发），先立即执行一次搜索再导航
                    self._flush_pending_query_if_needed()
                    if key_event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                        self.goto_prev()
                    else:
                        self.goto_next()
                    return True
                if key_event.key() == Qt.Key.Key_Escape:
                    self.close_and_clear()
                    return True
                if key_event.key() == Qt.Key.Key_Down:
                    # UX：不自动展开结果列表；但允许用 ↓ 一键展开并聚焦结果列表
                    self._flush_pending_query_if_needed()
                    if bool(self._match.node_ids):
                        if not bool(getattr(self, "_results_expanded", False)):
                            if hasattr(self, "_results_toggle") and self._results_toggle:
                                self._results_toggle.setChecked(True)
                        self._focus_results_list()
                        return True
        return super().eventFilter(a0, a1)

    # --- 搜索与高亮 ---

    def _ensure_index(self) -> Optional[GraphSearchIndex]:
        scene = self._view.scene()
        if scene is None:
            return None
        model = getattr(scene, "model", None)
        if model is None:
            return None

        model_id = id(model)
        graph_id = str(getattr(model, "graph_id", "") or "")
        if (
            self._index is None
            or self._indexed_model_id != model_id
            or self._indexed_graph_id != graph_id
        ):
            source_text = self._try_get_cached_source_text_for_model(model)
            self._index = GraphSearchIndex.build(model, source_code=source_text)
            self._indexed_model_id = model_id
            self._indexed_graph_id = graph_id
        return self._index

    def _on_query_text_changed(self, text: str) -> None:
        """输入变化：防抖后再执行搜索（避免大图下每字符卡顿）。"""
        query = str(text or "").strip()
        if not query:
            self._pending_query = ""
            if hasattr(self, "_query_timer") and self._query_timer:
                self._query_timer.stop()
            self._clear_highlight_state()
            self._clear_results_list()
            return
        self._pending_query = query
        if hasattr(self, "_query_timer") and self._query_timer:
            self._query_timer.start(int(self._QUERY_DEBOUNCE_MS))

    def _run_pending_query(self) -> None:
        query = str(getattr(self, "_pending_query", "") or "").strip()
        current_text = ""
        if hasattr(self, "_search_edit") and self._search_edit is not None:
            current_text = str(self._search_edit.text() or "").strip()
        if current_text and query != current_text:
            # 若 timer 触发时输入已变化（极端情况），以最新输入为准再延迟一次
            self._pending_query = current_text
            self._query_timer.start(int(self._QUERY_DEBOUNCE_MS))
            return
        if not query:
            return
        self._run_query_now(query)

    def _flush_pending_query_if_needed(self) -> None:
        if hasattr(self, "_query_timer") and self._query_timer and self._query_timer.isActive():
            self._query_timer.stop()
        current_query = str(self._search_edit.text() or "").strip()
        if not current_query:
            return
        last_query = str(getattr(self._match, "query", "") or "")
        if current_query != last_query:
            self._pending_query = current_query
            self._run_query_now(current_query)

    def _run_query_now(self, query: str) -> None:
        query_text = str(query or "").strip()
        if not query_text:
            self._clear_highlight_state()
            self._clear_results_list()
            return

        index = self._ensure_index()
        if index is None:
            self._clear_highlight_state()
            return

        # 重新搜索时：重置分页与当前选择，避免展开列表状态下“页码/选中错乱”
        self._current_index = 0
        self._results_page_index = 0
        match = index.match(query_text)
        self._apply_match(match)

    def _apply_match(self, match: GraphSearchMatch) -> None:
        scene = self._view.scene()
        if scene is None:
            self._clear_highlight_state()
            return
        scene_any = cast(Any, scene)

        new_node_ids = list(match.node_ids or [])
        new_node_set = {str(node_id) for node_id in new_node_ids if node_id}

        # 差量更新节点“搜索命中”描边
        removed = self._matched_node_set - new_node_set
        added = new_node_set - self._matched_node_set

        for node_id in removed:
            node_item = scene_any.get_node_item(node_id) if hasattr(scene_any, "get_node_item") else None
            if node_item is not None and hasattr(node_item, "set_search_highlighted"):
                node_item.set_search_highlighted(False)

        for node_id in added:
            node_item = scene_any.get_node_item(node_id) if hasattr(scene_any, "get_node_item") else None
            if node_item is not None and hasattr(node_item, "set_search_highlighted"):
                node_item.set_search_highlighted(True)

        self._match = match
        self._matched_node_set = new_node_set

        # 灰显非命中元素（无命中则恢复透明度并不保持置灰）
        if new_node_set:
            edge_ids_to_keep = list(match.edge_ids_to_keep or [])
            self._view.dim_unrelated_items(list(new_node_set), edge_ids_to_keep)
        else:
            self._view.restore_all_opacity()

        self._reconcile_current_index()
        self._sync_nav_enabled()
        self._update_count_label()

        # UX：只要有结果，自动展开结果列表（用户不用再点一下“展开”）
        if bool(self._match.node_ids) and (not bool(getattr(self, "_results_expanded", False))):
            if hasattr(self, "_results_toggle") and self._results_toggle:
                # 触发 toggled 信号以构建列表并 reposition
                self._results_toggle.setChecked(True)
                return
        self._maybe_refresh_results_list()

    def _reconcile_current_index(self) -> None:
        node_ids = list(self._match.node_ids or [])
        if not node_ids:
            self._current_index = 0
            return

        current_node_id = ""
        if 0 <= self._current_index < len(node_ids):
            current_node_id = str(node_ids[self._current_index] or "")
        if current_node_id and current_node_id in self._matched_node_set:
            return
        self._current_index = 0

    def _update_count_label(self) -> None:
        total = len(self._match.node_ids or [])
        if total <= 0:
            self._count_label.setText("0/0")
            return
        current = max(0, min(self._current_index, total - 1))
        self._count_label.setText(f"{current + 1}/{total}")

    def _sync_nav_enabled(self) -> None:
        enabled = bool(self._match.node_ids)
        self._prev_button.setEnabled(enabled)
        self._next_button.setEnabled(enabled)
        if hasattr(self, "_results_toggle") and self._results_toggle:
            if not enabled:
                # 无结果时自动收起列表，避免空白区域占位
                self._results_toggle.blockSignals(True)
                self._results_toggle.setChecked(False)
                self._results_toggle.blockSignals(False)
                self._results_expanded = False
                if hasattr(self, "_results_container") and self._results_container:
                    self._results_container.setVisible(False)
            # 结果列表状态可能被“无结果自动收起”这类逻辑直接改写（未走 toggled 信号），
            # 这里统一同步箭头方向，避免出现“列表已收起但箭头仍向上”的错觉。
            self._results_toggle.setArrowType(
                Qt.ArrowType.UpArrow if bool(getattr(self, "_results_expanded", False)) else Qt.ArrowType.DownArrow
            )
            self._results_toggle.setEnabled(enabled)

        if hasattr(self, "_page_row") and self._page_row:
            self._page_row.setVisible(bool(self._results_expanded and enabled))

    def _clear_highlight_state(self) -> None:
        scene = self._view.scene()
        if scene is not None:
            scene_any = cast(Any, scene)
            for node_id in list(self._matched_node_set):
                node_item = scene_any.get_node_item(node_id) if hasattr(scene_any, "get_node_item") else None
                if node_item is not None and hasattr(node_item, "set_search_highlighted"):
                    node_item.set_search_highlighted(False)

        self._match = GraphSearchMatch(
            query="",
            tokens_cf=tuple(),
            source_spans=tuple(),
            node_ids=[],
            edge_ids_to_keep=[],
            var_relation_hints_by_node_id={},
        )
        self._matched_node_set.clear()
        self._current_index = 0
        self._sync_nav_enabled()
        self._update_count_label()

        self._view.restore_all_opacity()

    # --- 导航 ---

    def goto_next(self) -> None:
        self._navigate(+1)

    def goto_prev(self) -> None:
        self._navigate(-1)

    def _navigate(self, delta: int) -> None:
        node_ids = list(self._match.node_ids or [])
        if not node_ids:
            return
        total = len(node_ids)
        self._current_index = (self._current_index + int(delta)) % total
        current_node_id = str(node_ids[self._current_index] or "")
        if not current_node_id:
            return

        # 强调当前节点：复用现有“选中高亮”样式
        self._view.highlight_node(current_node_id)
        # 性能：搜索跳转默认禁用平滑动画（超大图下动画帧会触发大量重绘，体感“很卡”）
        self._view.focus_on_node(current_node_id, use_animation=False)

        self._update_count_label()
        self._sync_results_selection()

    # --- 结果列表 UI ---

    def _on_results_toggled(self, checked: bool) -> None:
        self._results_expanded = bool(checked)
        if hasattr(self, "_results_toggle") and self._results_toggle:
            self._results_toggle.setArrowType(
                Qt.ArrowType.UpArrow if self._results_expanded else Qt.ArrowType.DownArrow
            )
        if hasattr(self, "_results_container") and self._results_container:
            self._results_container.setVisible(self._results_expanded)
        if self._results_expanded:
            self._maybe_refresh_results_list(force=True)
            self._sync_results_selection()
        self.reposition()

    def _maybe_refresh_results_list(self, *, force: bool = False) -> None:
        if not bool(getattr(self, "_results_expanded", False)):
            return
        self._rebuild_results_list_page(force=force)

    def _clear_results_list(self) -> None:
        if hasattr(self, "_results_list") and self._results_list:
            self._results_list.clear()
        self._results_page_index = 0
        if hasattr(self, "_page_row") and self._page_row:
            self._page_row.setVisible(False)

    def _rebuild_results_list_page(self, *, force: bool = False) -> None:
        node_ids = list(self._match.node_ids or [])
        total = len(node_ids)
        if total <= 0:
            self._results_list.clear()
            self._page_row.setVisible(False)
            return

        page_size = max(1, int(getattr(self, "_results_page_size", self._DEFAULT_PAGE_SIZE)))
        total_pages = (total + page_size - 1) // page_size
        self._results_page_index = max(0, min(int(self._results_page_index), total_pages - 1))

        start = self._results_page_index * page_size
        end = min(total, start + page_size)
        page_node_ids = node_ids[start:end]

        if not force and self._results_list.count() == len(page_node_ids):
            # 若页大小未变且 item 数一致，仍可能因 query 变化导致内容变化；
            # 这里不做复杂 diff，统一重建即可（页内 item 数很小）。
            pass

        self._results_list.clear()
        if self._index is None:
            self._page_row.setVisible(False)
            return

        tokens_cf = tuple(getattr(self._match, "tokens_cf", tuple()) or tuple())
        for idx, node_id in enumerate(list(page_node_ids or [])):
            global_index = start + idx + 1
            stable_node_id = str(node_id or "")
            if not stable_node_id:
                continue
            var_relation_hints = {}
            if hasattr(self._match, "var_relation_hints_by_node_id"):
                var_relation_hints = getattr(self._match, "var_relation_hints_by_node_id", {}) or {}
            relation_hints_for_node = tuple(var_relation_hints.get(stable_node_id, tuple()) or tuple())

            item = self._index.build_result_item(
                stable_node_id,
                tokens_cf=tokens_cf,
                var_relation_hints=relation_hints_for_node,
            )

            code_var_names = list(getattr(item, "code_var_names", tuple()) or tuple())
            title = str(getattr(item, "title", "") or "")
            category = str(getattr(item, "category", "") or "")
            export_index = int(getattr(item, "export_index", 0) or 0)
            pos = getattr(item, "pos", (0.0, 0.0))
            pos_x = float(pos[0]) if isinstance(pos, (list, tuple)) and len(pos) >= 2 else 0.0
            pos_y = float(pos[1]) if isinstance(pos, (list, tuple)) and len(pos) >= 2 else 0.0
            line_a = int(getattr(item, "source_lineno", 0) or 0)
            line_b = int(getattr(item, "source_end_lineno", 0) or 0)
            tags = list(getattr(item, "matched_tags", tuple()) or tuple())

            title_display = title.strip() if title.strip() else node_id
            category_display = category.strip()
            short_id, copy_hint = self._format_node_id_for_list(node_id)
            header_plain = self._build_result_header_plain_text(
                global_index=global_index,
                title_display=title_display,
                category_display=category_display,
                copy_hint=copy_hint,
            )

            line_part = ""
            if line_a > 0 and line_b > 0 and line_b != line_a:
                line_part = f"行：{line_a}-{line_b}"
            elif line_a > 0:
                line_part = f"行：{line_a}"

            coord_part = f"坐标：({int(pos_x)},{int(pos_y)})"

            code_var_part = ""
            if code_var_names:
                shown = code_var_names[:2]
                code_var_part = "变量：" + "，".join([str(x) for x in shown if x])
                if len(code_var_names) > 2:
                    code_var_part += "…"

            line2_parts = [p for p in [code_var_part, line_part, coord_part] if p]
            line2 = "  |  ".join(line2_parts)

            tag_part = ""
            if tags:
                shown_tags = tags[:2]
                tag_part = "命中：" + " / ".join([str(t) for t in shown_tags if t])
                if len(tags) > 2:
                    tag_part += "…"
            export_part = f"GIA序号：{int(export_index)}" if int(export_index) > 0 else ""
            line3_parts = [p for p in [tag_part, export_part, (f"id：{short_id}" if short_id else "")] if p]
            line3 = "  |  ".join(line3_parts)

            # 三行布局（自绘 widget）：标题（可高亮）/ 命中原因+命中片段（高亮）/ 元信息
            # 注意：不要把 header_plain 填到 QListWidgetItem 的 text 里。
            # 我们使用 setItemWidget() 自绘三行富文本；若 item.text 仍存在，
            # delegate 仍会绘制一份文本，导致“文本叠在一起”的重影问题。
            list_item = QtWidgets.QListWidgetItem()
            list_item.setData(Qt.ItemDataRole.UserRole, node_id)
            list_item.setData(Qt.ItemDataRole.UserRole + 1, global_index)
            list_item.setData(Qt.ItemDataRole.UserRole + 2, header_plain)

            tooltip_lines: list[str] = [header_plain, f"节点ID: {node_id}"]
            if int(export_index) > 0:
                tooltip_lines.append(f"GIA序号: {int(export_index)}")
            tooltip_lines.append(f"坐标: ({pos_x:.1f}, {pos_y:.1f})")
            if line_part:
                tooltip_lines.append(f"源码: {line_part}")
            port_names = list(getattr(item, "port_names", tuple()) or tuple())
            if port_names:
                tooltip_lines.append("端口:")
                for name in port_names[:16]:
                    tooltip_lines.append(f"  - {name}")
            if code_var_names:
                tooltip_lines.append("代码变量:")
                for name in code_var_names[:10]:
                    tooltip_lines.append(f"  - {name}")
            var_pairs = list(getattr(item, "var_pairs", tuple()) or tuple())
            if var_pairs:
                tooltip_lines.append("变量名:")
                for out_port, var_name in var_pairs[:8]:
                    out_port_text = str(out_port or "")
                    var_text = str(var_name or "")
                    if out_port_text:
                        tooltip_lines.append(f"  - {out_port_text} = {var_text}")
                    else:
                        tooltip_lines.append(f"  - {var_text}")
            const_preview = list(getattr(item, "constant_previews", tuple()) or tuple())
            if const_preview:
                tooltip_lines.append("输入常量:")
                for s in const_preview[:10]:
                    tooltip_lines.append(f"  - {s}")
            comment_preview = str(getattr(item, "comment_preview", "") or "").strip()
            if comment_preview:
                tooltip_lines.append("注释:")
                tooltip_lines.append(f"  {comment_preview}")
            var_relation_hints = list(getattr(item, "var_relation_hints", tuple()) or tuple())
            if var_relation_hints:
                tooltip_lines.append("变量关联:")
                for hint in var_relation_hints[:10]:
                    tooltip_lines.append(f"  - {hint}")
            if tags:
                tooltip_lines.append("命中类型:")
                tooltip_lines.append("  " + " / ".join(tags))

            # 源码片段（调试定位）：基于图的 source_file + 节点行号提取少量行
            code_preview = self._build_code_preview_for_item(item)
            if code_preview:
                tooltip_lines.append("代码片段:")
                tooltip_lines.extend(["  " + ln for ln in code_preview.split("\n") if ln.strip()][:50])
            list_item.setToolTip("\n".join(tooltip_lines))

            list_item.setSizeHint(QtCore.QSize(0, self._result_item_height_px()))
            self._results_list.addItem(list_item)
            self._results_list.setItemWidget(
                list_item,
                self._build_result_item_widget(
                    global_index=global_index,
                    item=item,
                    title_display=title_display,
                    category_display=category_display,
                    copy_hint=copy_hint,
                    line3=line3,
                    tokens_cf=tokens_cf,
                ),
            )

        self._sync_paging_status(total=total, page_size=page_size, total_pages=total_pages)
        self._sync_results_list_height(visible_rows=len(page_node_ids))
        self._sync_results_selection()

    def _sync_results_selection(self) -> None:
        if not bool(getattr(self, "_results_expanded", False)):
            return
        total = len(self._match.node_ids or [])
        if total <= 0:
            return
        current = max(0, min(self._current_index, total - 1))
        page_size = max(1, int(getattr(self, "_results_page_size", self._DEFAULT_PAGE_SIZE)))
        expected_page = current // page_size
        if expected_page != int(self._results_page_index):
            self._results_page_index = int(expected_page)
            self._rebuild_results_list_page(force=True)
        local_row = current - int(self._results_page_index) * page_size
        if 0 <= local_row < self._results_list.count():
            self._results_list.setCurrentRow(local_row)
            current_item = self._results_list.item(local_row)
            if current_item is not None:
                self._results_list.scrollToItem(current_item)

    def _focus_results_list(self) -> None:
        if not bool(getattr(self, "_results_expanded", False)):
            return
        if self._results_list.count() <= 0:
            return
        self._results_list.setFocus()
        self._sync_results_selection()

    def _on_result_item_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        self._activate_result_item(item)

    def _on_result_item_activated(self, item: QtWidgets.QListWidgetItem) -> None:
        self._activate_result_item(item)

    def _activate_result_item(self, item: QtWidgets.QListWidgetItem) -> None:
        if item is None:
            return
        node_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if not node_id:
            return
        row = int(self._results_list.row(item))
        if row >= 0:
            page_size = max(1, int(getattr(self, "_results_page_size", self._DEFAULT_PAGE_SIZE)))
            self._current_index = int(self._results_page_index) * page_size + row
            self._update_count_label()
        # delta=0：聚焦当前项
        self._navigate(0)

    def _result_item_height_px(self) -> int:
        cached = int(getattr(self, "_cached_result_item_height_px", 0) or 0)
        if cached > 0:
            return cached

        # 说明：
        # - 结果项使用 setItemWidget(...) 自绘 3 行富文本 QLabel（包含 <b> 加粗与高亮 span）；
        # - 在某些中文字体/缩放下，QFontMetrics.height() 的估算会略偏小，导致每行字形被裁切；
        # - 使用 lineSpacing()（包含 leading）并额外留出 safety padding，更稳。
        base_font = self._results_list.font()
        base_fm = QtGui.QFontMetrics(base_font)
        base_line_h = int(base_fm.lineSpacing())

        bold_font = QtGui.QFont(base_font)
        bold_font.setBold(True)
        bold_fm = QtGui.QFontMetrics(bold_font)
        bold_line_h = int(bold_fm.lineSpacing())

        # 三行：标题（加粗） + 命中行 + 元信息行
        text_h = int(bold_line_h + base_line_h * 2)
        margins_h = int(self._RESULT_ITEM_LAYOUT_MARGIN_V_PX * 2)
        spacing_h = int(self._RESULT_ITEM_LAYOUT_SPACING_PX * 2)
        safety_h = 8

        height = max(66, int(text_h + margins_h + spacing_h + safety_h))
        self._cached_result_item_height_px = int(height)
        return int(height)

    def _format_node_id_for_list(self, node_id: str) -> tuple[str, str]:
        """将 node_id 分解为“短ID”和“副本提示”。

        目标：
        - 列表中只展示短ID（可辨识/可复述），完整 ID 放在 tooltip。
        - 对 copy_block 副本节点额外提示副本来源，方便区分同名命中。
        """
        nid = str(node_id or "")
        if not nid:
            return ("", "")

        copy_hint = ""
        base = nid
        if "_copy_block_" in nid:
            base, tail = nid.split("_copy_block_", 1)
            copy_hint = f"副本 copy_block_{tail}"

        base_last = base.rsplit("_", 1)[-1] if "_" in base else base
        short_id = base_last if base_last else (base[-8:] if len(base) >= 8 else base)
        return (short_id, copy_hint)

    def _sync_results_list_height(self, *, visible_rows: int) -> None:
        rows = max(1, int(visible_rows))
        item_h = int(self._result_item_height_px())
        list_h = item_h * rows + int(self._results_list.frameWidth()) * 2
        self._results_list.setFixedHeight(list_h)

    def _sync_paging_status(self, *, total: int, page_size: int, total_pages: int) -> None:
        if not hasattr(self, "_page_row") or not self._page_row:
            return
        should_show = bool(total_pages > 1)
        self._page_row.setVisible(bool(self._results_expanded and should_show))
        current_page_display = int(self._results_page_index) + 1
        self._page_label.setText(f"第 {current_page_display}/{total_pages} 页（共 {total} 条）")
        self._page_prev_button.setEnabled(current_page_display > 1)
        self._page_next_button.setEnabled(current_page_display < total_pages)

    def _goto_prev_page(self) -> None:
        if self._results_page_index <= 0:
            return
        page_size = max(1, int(getattr(self, "_results_page_size", self._DEFAULT_PAGE_SIZE)))
        self._results_page_index -= 1
        self._current_index = int(self._results_page_index) * page_size
        self._update_count_label()
        self._rebuild_results_list_page(force=True)

    def _goto_next_page(self) -> None:
        total = len(list(self._match.node_ids or []))
        if total <= 0:
            return
        page_size = max(1, int(getattr(self, "_results_page_size", self._DEFAULT_PAGE_SIZE)))
        total_pages = (total + page_size - 1) // page_size
        if self._results_page_index >= total_pages - 1:
            return
        self._results_page_index += 1
        self._current_index = int(self._results_page_index) * page_size
        self._update_count_label()
        self._rebuild_results_list_page(force=True)

    def _build_result_header_plain_text(
        self,
        *,
        global_index: int,
        title_display: str,
        category_display: str,
        copy_hint: str,
    ) -> str:
        header_parts = [f"{int(global_index)}. {str(title_display or '').strip()}"]
        if str(category_display or "").strip():
            header_parts.append(f"[{str(category_display).strip()}]")
        if str(copy_hint or "").strip():
            header_parts.append(f"({str(copy_hint).strip()})")
        return " ".join([p for p in header_parts if p]).strip()

    def _build_result_item_widget(
        self,
        *,
        global_index: int,
        item: GraphSearchResultItem,
        title_display: str,
        category_display: str,
        copy_hint: str,
        line3: str,
        tokens_cf: tuple[str, ...],
    ) -> QtWidgets.QWidget:
        """为 QListWidgetItem 构建一个透明的三行结果渲染 widget（支持命中高亮）。"""
        widget = QtWidgets.QWidget(self._results_list)
        widget.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(10, int(self._RESULT_ITEM_LAYOUT_MARGIN_V_PX), 10, int(self._RESULT_ITEM_LAYOUT_MARGIN_V_PX))
        layout.setSpacing(int(self._RESULT_ITEM_LAYOUT_SPACING_PX))

        matched_tags = list(getattr(item, "matched_tags", tuple()) or tuple())
        title_should_highlight = bool("标题" in matched_tags) or (
            (not str(getattr(item, "title", "") or "").strip()) and ("ID" in matched_tags)
        )
        category_should_highlight = bool("类别" in matched_tags)

        title_html = (
            self._highlight_tokens_html(title_display, tokens_cf)
            if title_should_highlight
            else html.escape(str(title_display or ""))
        )
        category_html = (
            self._highlight_tokens_html(category_display, tokens_cf)
            if category_should_highlight
            else html.escape(str(category_display or ""))
        )

        header_parts: list[str] = [f"<b>{int(global_index)}. {title_html}</b>"]
        if str(category_display or "").strip():
            header_parts.append(f"<span style='opacity:0.85'>[{category_html}]</span>")
        if str(copy_hint or "").strip():
            header_parts.append(f"<span style='opacity:0.75'>({html.escape(str(copy_hint))})</span>")
        header_html = " ".join([p for p in header_parts if p]).strip()

        primary_tag, snippet_text = self._choose_primary_hit_snippet(item)
        snippet_text = self._truncate_text(snippet_text, 120)
        snippet_html = self._highlight_tokens_html(snippet_text, tokens_cf) if snippet_text else ""
        hit_line_html = (
            f"<span style='opacity:0.9'>命中：</span><b>{html.escape(primary_tag)}</b>"
            + (f"<span style='opacity:0.9'>：</span>{snippet_html}" if snippet_html else "")
        )

        meta_line = str(line3 or "").strip()
        # 也允许在元信息里点到（例如 GIA序号/ID 命中时），这里轻量高亮一次
        meta_html = self._highlight_tokens_html(meta_line, tokens_cf) if meta_line else ""

        label1 = QtWidgets.QLabel(widget)
        label1.setTextFormat(Qt.TextFormat.RichText)
        label1.setText(header_html)
        label1.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        label2 = QtWidgets.QLabel(widget)
        label2.setTextFormat(Qt.TextFormat.RichText)
        label2.setText(hit_line_html)
        label2.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        label3 = QtWidgets.QLabel(widget)
        label3.setTextFormat(Qt.TextFormat.RichText)
        label3.setText(meta_html)
        label3.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        layout.addWidget(label1)
        layout.addWidget(label2)
        layout.addWidget(label3)
        return widget

    def _choose_primary_hit_snippet(self, item: GraphSearchResultItem) -> tuple[str, str]:
        tags = list(getattr(item, "matched_tags", tuple()) or tuple())
        if not tags:
            # 仅行号范围过滤时 tokens 为空，此时 matched_tags 也会为空。
            # 为了让用户知道“为什么会出现在列表里”，这里回退为“源文件/行号”摘要。
            source = ""
            if self._index is not None:
                source = str(getattr(self._index, "source_file", "") or "")
            lo = int(getattr(item, "source_lineno", 0) or 0)
            hi = int(getattr(item, "source_end_lineno", 0) or 0)
            if lo > 0 and hi > 0 and lo != hi:
                return ("源文件/行号", f"{source}:{lo}-{hi}" if source else f"{lo}-{hi}")
            if lo > 0:
                return ("源文件/行号", f"{source}:{lo}" if source else str(lo))
            return ("源文件/行号", source)

        primary = str(tags[0])

        if primary == "标题":
            title = str(getattr(item, "title", "") or "").strip()
            return (primary, title)
        if primary == "类别":
            cat = str(getattr(item, "category", "") or "").strip()
            return (primary, cat)
        if primary == "ID":
            return (primary, str(getattr(item, "node_id", "") or ""))
        if primary == "GIA序号":
            return (primary, str(int(getattr(item, "export_index", 0) or 0)))
        if primary == "代码变量":
            names = list(getattr(item, "code_var_names", tuple()) or tuple())
            return (primary, "，".join([str(x) for x in names[:4] if x]))
        if primary == "变量名":
            pairs = list(getattr(item, "var_pairs", tuple()) or tuple())
            names = [str(var_name or "") for _, var_name in pairs if var_name]
            return (primary, "，".join(names[:4]))
        if primary == "变量关联":
            hints = list(getattr(item, "var_relation_hints", tuple()) or tuple())
            return (primary, " / ".join([str(x) for x in hints[:6] if x]))
        if primary == "常量":
            consts = list(getattr(item, "constant_previews", tuple()) or tuple())
            return (primary, "，".join([str(x) for x in consts[:4] if x]))
        if primary == "端口":
            ports = list(getattr(item, "port_names", tuple()) or tuple())
            return (primary, "，".join([str(x) for x in ports[:6] if x]))
        if primary == "注释":
            return (primary, str(getattr(item, "comment_preview", "") or "").strip())
        if primary == "源文件/行号":
            source = ""
            if self._index is not None:
                source = str(getattr(self._index, "source_file", "") or "")
            lo = int(getattr(item, "source_lineno", 0) or 0)
            hi = int(getattr(item, "source_end_lineno", 0) or 0)
            if lo > 0 and hi > 0 and lo != hi:
                return (primary, f"{source}:{lo}-{hi}" if source else f"{lo}-{hi}")
            if lo > 0:
                return (primary, f"{source}:{lo}" if source else str(lo))
            return (primary, source)
        if primary == "图信息":
            if self._index is None:
                return (primary, "")
            graph_id = str(getattr(self._index, "graph_id", "") or "").strip()
            graph_name = str(getattr(self._index, "graph_name", "") or "").strip()
            merged = " ".join([p for p in [graph_id, graph_name] if p]).strip()
            return (primary, merged)

        return (primary, "")

    def _highlight_tokens_html(self, text: str, tokens_cf: tuple[str, ...]) -> str:
        raw = str(text or "")
        if not raw:
            return ""
        tokens = [str(t) for t in (tokens_cf or tuple()) if str(t)]
        if not tokens:
            return html.escape(raw)

        ranges: list[tuple[int, int]] = []
        for token in tokens:
            pattern = re.escape(str(token))
            if not pattern:
                continue
            for m in re.finditer(pattern, raw, flags=re.IGNORECASE):
                if m.start() < m.end():
                    ranges.append((int(m.start()), int(m.end())))
        if not ranges:
            return html.escape(raw)

        ranges.sort(key=lambda x: (x[0], x[1]))
        merged: list[list[int]] = []
        for s, e in ranges:
            if not merged or s > merged[-1][1]:
                merged.append([int(s), int(e)])
            else:
                merged[-1][1] = max(int(merged[-1][1]), int(e))

        out: list[str] = []
        last = 0
        for s, e in merged:
            if last < s:
                out.append(html.escape(raw[last:s]))
            frag = html.escape(raw[s:e])
            out.append(
                "<span style='"
                f"background-color:{self._HIT_HIGHLIGHT_BG};"
                f"color:{self._HIT_HIGHLIGHT_FG};"
                "padding:0px 1px;"
                "border-radius:2px;"
                "'>"
                f"{frag}"
                "</span>"
            )
            last = e
        if last < len(raw):
            out.append(html.escape(raw[last:]))
        return "".join(out)

    @staticmethod
    def _truncate_text(text: str, max_len: int) -> str:
        t = str(text or "")
        limit = int(max_len)
        if limit <= 0:
            return ""
        if len(t) <= limit:
            return t
        return t[: max(0, limit - 1)] + "…"

    def _build_code_preview_for_item(self, item: GraphSearchResultItem) -> str:
        index = getattr(self, "_index", None)
        if index is None:
            return ""
        source_rel = str(getattr(index, "source_file", "") or "").strip()
        if not source_rel:
            return ""
        lo = int(getattr(item, "source_lineno", 0) or 0)
        hi = int(getattr(item, "source_end_lineno", 0) or 0)
        if lo <= 0:
            return ""
        if hi <= 0:
            hi = lo

        scene = self._view.scene()
        layout_ctx = getattr(scene, "layout_registry_context", None) if scene is not None else None
        workspace_path = getattr(layout_ctx, "workspace_path", None)
        if not isinstance(workspace_path, Path):
            return ""

        abs_path = (workspace_path / Path(source_rel)).resolve()
        abs_str = str(abs_path)
        if not abs_path.exists():
            return ""

        if abs_str != self._cached_source_abs:
            content = abs_path.read_text(encoding="utf-8")
            self._cached_source_abs = abs_str
            self._cached_source_lines = content.splitlines()

        lines = list(self._cached_source_lines or [])
        if not lines:
            return ""

        start_line = max(1, lo)
        end_line = max(start_line, hi)
        # 限制预览行数，避免 tooltip 过长
        max_lines = int(self._MAX_CODE_PREVIEW_LINES)
        if end_line - start_line + 1 > max_lines:
            end_line = start_line + max_lines - 1

        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line)
        snippet_lines: list[str] = []
        for line_no in range(start_idx + 1, end_idx + 1):
            raw = lines[line_no - 1]
            snippet_lines.append(f"{line_no:>4}: {raw}")

        text = "\n".join(snippet_lines).rstrip()
        if len(text) > int(self._MAX_CODE_PREVIEW_CHARS):
            text = text[: int(self._MAX_CODE_PREVIEW_CHARS) - 1] + "…"
        return text

    def _compute_desired_height_px(self) -> int:
        layout = self.layout()
        if layout is None:
            return 64
        margins = layout.contentsMargins()
        spacing = int(layout.spacing())
        height = int(margins.top() + margins.bottom())
        if hasattr(self, "_top_row") and self._top_row is not None:
            height += int(self._top_row.sizeHint().height())
        if bool(getattr(self, "_results_expanded", False)) and hasattr(self, "_results_container") and self._results_container:
            if self._results_container.isVisible():
                height += spacing
                height += int(self._results_container.sizeHint().height())
        return max(64, height)

    def _try_get_cached_source_text_for_model(self, model: object) -> str:
        """为 GraphSearchIndex 构建索引提供源码全文（用于提取左值变量名与支持 @file.py 查询）。"""
        meta = getattr(model, "metadata", None) or {}
        if not isinstance(meta, dict):
            return ""
        source_rel = str(meta.get("source_file", "") or "").strip()
        if not source_rel:
            return ""

        scene = self._view.scene()
        layout_ctx = getattr(scene, "layout_registry_context", None) if scene is not None else None
        workspace_path = getattr(layout_ctx, "workspace_path", None)
        if not isinstance(workspace_path, Path):
            return ""

        abs_path = (workspace_path / Path(source_rel)).resolve()
        if not abs_path.exists():
            return ""

        abs_str = str(abs_path)
        if abs_str != self._cached_source_abs:
            content = abs_path.read_text(encoding="utf-8")
            self._cached_source_abs = abs_str
            self._cached_source_lines = content.splitlines()
            return content

        return "\n".join(list(self._cached_source_lines or []))


