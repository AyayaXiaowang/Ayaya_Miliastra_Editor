"""Tooltip overlay rendering for Y-debug interactions."""

from __future__ import annotations

from typing import Callable, Optional
from html import escape

from PyQt6 import QtCore, QtGui, QtWidgets

from ui.foundation.theme_manager import Colors
from ui.scene.interaction_state import YDebugInteractionState


class YDebugTooltipHeader(QtWidgets.QFrame):
    """Tooltip 顶部标题栏，支持拖拽移动。"""

    def __init__(
        self,
        tooltip_frame: QtWidgets.QFrame,
        parent: Optional[QtWidgets.QWidget] = None,
        on_frame_moved: Optional[Callable[[QtCore.QPoint], None]] = None,
    ) -> None:
        super().__init__(parent)
        self._tooltip_frame = tooltip_frame
        self._press_global_pos: Optional[QtCore.QPoint] = None
        self._frame_start_pos: Optional[QtCore.QPoint] = None
        self._on_frame_moved = on_frame_moved

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._press_global_pos = event.globalPosition().toPoint()
            self._frame_start_pos = self._tooltip_frame.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            if self._press_global_pos is None or self._frame_start_pos is None:
                super().mouseMoveEvent(event)
                return
            current_global_pos = event.globalPosition().toPoint()
            delta = current_global_pos - self._press_global_pos
            new_pos = self._frame_start_pos + delta
            self._tooltip_frame.move(new_pos)
            if self._on_frame_moved:
                self._on_frame_moved(new_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._press_global_pos = None
            self._frame_start_pos = None
        super().mouseReleaseEvent(event)


class YDebugTooltipOverlay:
    """封装布局Y调试 Tooltip 的创建、定位与富文本交互。"""

    def __init__(
        self,
        state: YDebugInteractionState,
        view_provider: Callable[[], list],
        node_lookup: Callable[[str], Optional[object]],
        model_provider: Callable[[], object],
        highlight_manager,
    ) -> None:
        self.state = state
        self._view_provider = view_provider
        self._node_lookup = node_lookup
        self._model_provider = model_provider
        self._highlight_manager = highlight_manager
        self._widget: Optional[QtWidgets.QFrame] = None
        self._label: Optional[QtWidgets.QLabel] = None

    def open(self, node_id: str, anchor_scene_pos: QtCore.QPointF) -> None:
        debug_map = getattr(self._model_provider(), "_layout_y_debug_info", {}) or {}
        info = debug_map.get(node_id)
        views = self._view_provider()
        if not info or not views:
            return
        view = views[0]
        if self._widget:
            self.close()
        self.state.set_active_node(node_id)
        self.state.reset_tooltip_geometry()
        self.state.set_anchor_scene_pos(anchor_scene_pos)
        node_item = self._node_lookup(node_id)
        if node_item:
            node_rect_scene = node_item.sceneBoundingRect()
            node_rect_view = view.mapFromScene(node_rect_scene).boundingRect()
            self.state.set_anchor_view_rect(node_rect_view)
        self._ensure_widget(view)
        if not self._label:
            return
        self._label.setText(self._format_layout_text(info))
        self._widget.adjustSize()
        self._apply_size_constraints(view)
        self.reposition(force_initial=True)
        self._widget.show()
        self._widget.raise_()

    def close(self) -> None:
        if self._widget:
            self._widget.hide()
        self._highlight_manager.clear_chain_highlight()
        self.state.reset_tooltip_geometry()
        self.state.set_active_node(None)

    def refresh(self) -> None:
        if not self._widget or not self._label or not self.state.active_node_id:
            return
        debug_map = getattr(self._model_provider(), "_layout_y_debug_info", {}) or {}
        info = debug_map.get(self.state.active_node_id)
        if not info:
            return
        self._label.setText(self._format_layout_text(info))
        views = self._view_provider()
        if views:
            self._widget.adjustSize()
            self._apply_size_constraints(views[0])
            self.reposition()

    def reposition(self, force_initial: bool = False) -> None:
        if not self._widget:
            return
        anchor = self.state.tooltip_anchor_scene_pos
        views = self._view_provider()
        if anchor is None or not views:
            return
        view = views[0]
        widget_size = self._widget.size()
        preferred_quadrant = None if force_initial else self.state.tooltip_orientation
        base_pos, quadrant = self._calculate_base_pos(view, anchor, widget_size, preferred_quadrant)
        self.state.set_orientation(quadrant)
        self.state.set_last_auto_pos(base_pos)
        manual_offset = self.state.tooltip_manual_offset
        final_pos = QtCore.QPoint(base_pos.x() + manual_offset.x(), base_pos.y() + manual_offset.y())
        final_pos = self._clamp_to_viewport(view, widget_size, final_pos)
        self._widget.move(final_pos)

    def handle_manual_move(self, new_pos: QtCore.QPoint) -> None:
        last_auto = self.state.tooltip_last_auto_pos
        if last_auto is None:
            return
        offset = new_pos - last_auto
        self.state.set_manual_offset(offset)

    def handle_link(self, href: str) -> None:
        if not href:
            return
        href = href.strip()
        node_id = self.state.active_node_id
        if href.startswith("chain:"):
            chain_id = href.split(":", 1)[1].strip()
            if chain_id.isdigit():
                self._highlight_manager.clear_all_chains_highlight()
                self._highlight_manager.highlight_chain(int(chain_id))
        elif href == "page_prev" and node_id:
            current_index = self.state.get_page_index(node_id)
            self.state.set_page_index(node_id, max(0, current_index - 1))
            self.refresh()
        elif href == "page_next" and node_id:
            current_index = self.state.get_page_index(node_id)
            self.state.set_page_index(node_id, current_index + 1)
            self.refresh()
        elif href == "highlight_all":
            self._highlight_manager.apply_all_chains_highlight()
        elif href == "clear_all":
            self._highlight_manager.clear_all_chains_highlight()

    def _ensure_widget(self, view: QtWidgets.QGraphicsView) -> None:
        if self._widget:
            return
        frame = QtWidgets.QFrame(view.viewport())
        frame.setObjectName("yDebugTooltip")
        frame.setStyleSheet(
            f"QFrame#yDebugTooltip {{ background-color: rgba(30,30,30,230);"
            f" border: 1px solid {Colors.PRIMARY_LIGHT}; border-radius: 6px; }}"
            f" QLabel {{ color: {Colors.TEXT_ON_PRIMARY}; background: transparent; }}"
            f" QPushButton {{ border: none; color: {Colors.TEXT_ON_PRIMARY}; padding: 2px 6px; }}"
            f" QPushButton:hover {{ color: {Colors.TEXT_ON_PRIMARY}; }}"
        )
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        header = YDebugTooltipHeader(frame, frame, self.handle_manual_move)
        header_layout = QtWidgets.QHBoxLayout(header)
        header_layout.setContentsMargins(4, 4, 4, 4)
        title_label = QtWidgets.QLabel("详细信息", header)
        font = title_label.font()
        font.setBold(True)
        title_label.setFont(font)
        close_button = QtWidgets.QToolButton(header)
        close_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        close_button.setAutoRaise(False)
        close_button.setFixedSize(22, 22)
        style = QtWidgets.QApplication.style()
        close_button.setIcon(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_TitleBarCloseButton))
        close_button.setIconSize(QtCore.QSize(14, 14))
        close_button.setToolTip("关闭布局Y调试卡片")
        close_button.setStyleSheet(
            "QToolButton { border-radius: 11px; border: 1px solid rgba(255,255,255,70);"
            " background-color: rgba(255,255,255,25); padding: 0px; }"
            "QToolButton:hover { background-color: rgba(255,255,255,60);"
            " border: 1px solid rgba(255,255,255,130); }"
        )
        close_button.clicked.connect(self.close)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(close_button)
        layout.addWidget(header)
        scroll = QtWidgets.QScrollArea(frame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; }"
            "QScrollArea > QWidget { background: transparent; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        content = QtWidgets.QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        label = QtWidgets.QLabel(content)
        label.setWordWrap(True)
        label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
            | QtCore.Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        label.linkActivated.connect(self.handle_link)
        base_font = label.font()
        base_size = base_font.pointSizeF()
        base_font.setPointSizeF(base_size * 1.4 if base_size > 0 else 14)
        label.setFont(base_font)
        content_layout.addWidget(label)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        self._widget = frame
        self._label = label

    def _apply_size_constraints(self, view: QtWidgets.QGraphicsView) -> None:
        if not self._widget:
            return
        max_width = int(420 * 2.0)
        vp_size = view.viewport().size()
        max_height = int(vp_size.height() * 0.6)
        if self._widget.width() > max_width:
            self._widget.resize(max_width, self._widget.sizeHint().height())
        if self._widget.height() > max_height:
            self._widget.resize(self._widget.width(), max_height)

    def _build_candidate_point(
        self,
        anchor_view_pos: QtCore.QPoint,
        widget_size: QtCore.QSize,
        offset: int,
        quadrant: int,
        node_rect_view: Optional[QtCore.QRect] = None,
    ) -> QtCore.QPoint:
        ax, ay = anchor_view_pos.x(), anchor_view_pos.y()
        if quadrant == 0:
            px, py = ax + offset, ay + offset
        elif quadrant == 1:
            px, py = ax + offset, ay - widget_size.height() - offset
        elif quadrant == 2:
            px, py = ax - widget_size.width() - offset, ay + offset
        else:
            px, py = ax - widget_size.width() - offset, ay - widget_size.height() - offset
        if quadrant in (2, 3) and node_rect_view is not None:
            safe_gap = 12
            right_limit = node_rect_view.left() - safe_gap
            px = min(px, right_limit - widget_size.width())
        return QtCore.QPoint(int(px), int(py))

    def _calculate_base_pos(
        self,
        view: QtWidgets.QGraphicsView,
        anchor_scene_pos: QtCore.QPointF,
        widget_size: QtCore.QSize,
        preferred_quadrant: Optional[int] = None,
    ) -> tuple[QtCore.QPoint, int]:
        view_pos = view.mapFromScene(anchor_scene_pos)
        vp_rect = view.viewport().rect()
        offset = 12
        candidate_order = [preferred_quadrant] if preferred_quadrant is not None else [0, 1, 2, 3]
        candidate_order = [q for q in candidate_order if q is not None] or [0, 1, 2, 3]
        node_rect_view = self.state.tooltip_anchor_view_rect
        fallback_point = None
        fallback_quadrant = None
        for quadrant in candidate_order:
            pt = self._build_candidate_point(
                self._normalize_view_point(view_pos), widget_size, offset, quadrant, node_rect_view
            )
            rect = QtCore.QRect(pt, widget_size)
            if preferred_quadrant is not None:
                return pt, quadrant
            if vp_rect.contains(rect):
                return pt, quadrant
            if fallback_point is None:
                fallback_point = pt
                fallback_quadrant = quadrant
        if fallback_point is None or fallback_quadrant is None:
            fallback_quadrant = candidate_order[0]
            fallback_point = self._build_candidate_point(
                self._normalize_view_point(view_pos), widget_size, offset, fallback_quadrant, node_rect_view
            )
        return fallback_point, fallback_quadrant

    @staticmethod
    def _normalize_view_point(point: QtCore.QPoint | QtCore.QPointF) -> QtCore.QPoint:
        if isinstance(point, QtCore.QPointF):
            return point.toPoint()
        return QtCore.QPoint(int(point.x()), int(point.y()))

    def _clamp_to_viewport(
        self,
        view: QtWidgets.QGraphicsView,
        widget_size: QtCore.QSize,
        point: QtCore.QPoint,
    ) -> QtCore.QPoint:
        vp_rect = view.viewport().rect()
        max_x = max(0, vp_rect.width() - widget_size.width())
        max_y = max(0, vp_rect.height() - widget_size.height())
        return QtCore.QPoint(max(0, min(max_x, point.x())), max(0, min(max_y, point.y())))

    def _format_layout_text(self, info) -> str:
        if not isinstance(info, dict):
            return str(info)

        def fmt_y(value):
            return f"{float(value):.1f}" if value is not None else "-"

        parts: list[str] = []

        # 节点基础信息：名称与唯一 ID
        node_id = self.state.active_node_id
        node_title_text = ""
        model = self._model_provider()
        nodes_dict = getattr(model, "nodes", {}) if model is not None else {}
        if node_id and isinstance(nodes_dict, dict):
            node_obj = nodes_dict.get(node_id)
            if node_obj is not None:
                raw_title = getattr(node_obj, "title", "")
                if raw_title is not None:
                    node_title_text = str(raw_title).strip()
        if node_title_text or node_id:
            if node_title_text:
                parts.append(
                    f"<div><span style='font-weight:bold;'>节点：</span>{escape(node_title_text)}</div>"
                )
            if node_id:
                parts.append(f"<div>— 节点ID：{escape(str(node_id))}</div>")

        block_index = info.get("block_index")
        block_id = info.get("block_id")
        event_title = info.get("event_flow_title")
        event_id = info.get("event_flow_id")
        if block_index is not None or block_id:
            if block_index and block_id:
                parts.append(f"<div>— 所属块：第 {int(block_index)} 块（{block_id}）</div>")
            elif block_index:
                parts.append(f"<div>— 所属块：第 {int(block_index)} 块</div>")
            elif block_id:
                parts.append(f"<div>— 所属块：{block_id}</div>")
        if isinstance(event_title, str) and event_title.strip():
            parts.append(f"<div>— 所属事件流：{event_title.strip()}</div>")
        elif isinstance(event_id, str) and event_id.strip():
            parts.append(f"<div>— 所属事件流：{event_id.strip()}</div>")
        else:
            parts.append("<div>— 所属事件流：-</div>")
        controls_html = (
            f"<span style='margin-left:10px;'>"
            f"<a href='highlight_all' style='color:{Colors.PRIMARY_LIGHT};'>高亮全部</a> · "
            f"<a href='clear_all' style='color:{Colors.PRIMARY_LIGHT};'>清除</a></span>"
        )
        node_type = info.get("type")
        if node_type != "flow":
            chains = info.get("chains")
            parts.append(f"<div>— 关联链路：{controls_html}</div>")
            parts.extend(self._render_chain_list(chains))
        else:
            parts.append(f"<div>— 关联链路：{controls_html}</div>")
            parts.extend(self._render_flow_chains(info))
        final_y = info.get("final_y")
        if final_y is not None:
            parts.append(f"<div style='margin-top:6px;'>— 最终位置：Y = {fmt_y(final_y)} 像素</div>")
        node_width = info.get("node_width")
        node_height = info.get("node_height")
        if node_width is not None and node_height is not None:
            parts.append(f"<div>— 节点尺寸：{int(node_width)} × {int(node_height)} 像素</div>")
        cand = info.get("candidates") or {}
        column_bottom = cand.get("column_bottom", info.get("strict_column_bottom"))
        chain_port = cand.get("chain_port", info.get("start_y_from_chain_ports"))
        chain_port_min = cand.get("chain_port_min")
        single_target = cand.get("single_target", info.get("start_y_from_single_target"))
        multi_mid = cand.get("multi_targets_mid", info.get("start_y_from_multi_targets_mid"))
        base_y = info.get("base_y")
        any_candidate = any(
            v is not None for v in [column_bottom, chain_port, chain_port_min, single_target, multi_mid, base_y]
        )
        if any_candidate:
            parts.append("<div style='margin-top:6px;'>— 位置依据（候选值，仅供理解）：</div>")
            if column_bottom is not None:
                parts.append(f"<div style='margin-left:1.5em;'>· 同列之下的安全起点（列底）：{fmt_y(column_bottom)}</div>")
            if chain_port is not None:
                parts.append(f"<div style='margin-left:1.5em;'>· 对齐右侧关联端口（端口位置+间距）：{fmt_y(chain_port)}</div>")
            if chain_port_min is not None:
                parts.append(f"<div style='margin-left:1.5em;'>· 多条链端口中的较小值：{fmt_y(chain_port_min)}</div>")
            if single_target is not None:
                parts.append(f"<div style='margin-left:1.5em;'>· 唯一目标节点对齐：{fmt_y(single_target)}</div>")
            if multi_mid is not None:
                parts.append(f"<div style='margin-left:1.5em;'>· 多输出时优先使用中点：{fmt_y(multi_mid)}</div>")
            if base_y is not None:
                parts.append(f"<div style='margin-left:1.5em;'>· 候选合并后的基础结果：{fmt_y(base_y)}</div>")
        if info.get("forced_by_multi_targets"):
            parts.append("<div>— 本节点受到“多输出中点优先”规则影响。</div>")
        return "".join(parts)

    def _render_chain_list(self, chains) -> list[str]:
        parts: list[str] = []
        if isinstance(chains, list) and chains:
            page_size = 10
            total_items = len(chains)
            total_pages = (total_items + page_size - 1) // page_size
            page_index = self.state.get_page_index(self.state.active_node_id)
            page_index = max(0, min(page_index, max(0, total_pages - 1)))
            start_index = page_index * page_size
            end_index = min(start_index + page_size, total_items)
            for idx, chain in enumerate(chains[start_index:end_index], start=start_index):
                cid = chain.get("id")
                pos_in_chain = chain.get("position")
                consumer_port_idx = chain.get("consumer_port_index")
                consumer_port_name = chain.get("consumer_port_name")
                if cid is None:
                    continue
                chain_anchor = (
                    f"<a href='chain:{int(cid)}' style='color:{Colors.INFO_LIGHT}; text-decoration:none;'>链 {int(cid)}（链内序号 {int(pos_in_chain)}）</a>"
                    if pos_in_chain is not None
                    else f"<a href='chain:{int(cid)}' style='color:{Colors.INFO_LIGHT}; text-decoration:none;'>链 {int(cid)}</a>"
                )
                if consumer_port_idx is not None and consumer_port_name:
                    parts.append(
                        f"<div style='margin-left:1.5em;'>· {chain_anchor}：连接到端口 {int(consumer_port_idx)}（{consumer_port_name}）</div>"
                    )
                else:
                    parts.append(f"<div style='margin-left:1.5em;'>· {chain_anchor}</div>")
            if total_pages > 1:
                nav_bits = [
                    f"<span style='color:{Colors.TEXT_SECONDARY};'>第 {page_index + 1}/{total_pages} 页</span>"
                ]
                if page_index > 0:
                    nav_bits.append(
                        f"<a href='page_prev' style='margin-left:10px; color:{Colors.PRIMARY_LIGHT};'>上一页</a>"
                    )
                if page_index < total_pages - 1:
                    nav_bits.append(
                        f"<a href='page_next' style='margin-left:10px; color:{Colors.PRIMARY_LIGHT};'>下一页</a>"
                    )
                parts.append(f"<div style='margin-left:1.5em; margin-top:4px;'>{' '.join(nav_bits)}</div>")
        elif isinstance(chains, list):
            parts.append("<div style='margin-left:1.5em;'>· 未找到关联链路：该节点未被任何数据链引用。</div>")
        else:
            parts.append("<div style='margin-left:1.5em;'>· 未提供链路明细：当前节点类型未记录链路。</div>")
        return parts

    def _render_flow_chains(self, info: dict) -> list[str]:
        debug_map = getattr(self._model_provider(), "_layout_y_debug_info", {}) or {}
        inbound_chains: dict[int, dict] = {}
        flow_id = self.state.active_node_id
        for entry in debug_map.values():
            if not isinstance(entry, dict):
                continue
            for chain in entry.get("chains") or []:
                if not isinstance(chain, dict):
                    continue
                if chain.get("target_flow") == flow_id:
                    cid = chain.get("id")
                    if cid is None:
                        continue
                    cid = int(cid)
                    inbound_chains.setdefault(
                        cid,
                        {
                            "id": cid,
                            "consumer_port_index": chain.get("consumer_port_index"),
                            "consumer_port_name": chain.get("consumer_port_name"),
                        },
                    )
        parts: list[str] = []
        if inbound_chains:
            chain_ids = sorted(inbound_chains.keys())
            page_size = 10
            total_items = len(chain_ids)
            total_pages = (total_items + page_size - 1) // page_size
            page_index = self.state.get_page_index(self.state.active_node_id)
            page_index = max(0, min(page_index, max(0, total_pages - 1)))
            start_index = page_index * page_size
            end_index = min(start_index + page_size, total_items)
            for cid in chain_ids[start_index:end_index]:
                chain = inbound_chains[cid]
                chain_anchor = (
                    f"<a href='chain:{int(cid)}' style='color:{Colors.INFO_LIGHT}; text-decoration:none;'>链 {int(cid)}</a>"
                )
                if chain.get("consumer_port_index") is not None and chain.get("consumer_port_name"):
                    parts.append(
                        f"<div style='margin-left:1.5em;'>· {chain_anchor}：连接到端口 {int(chain['consumer_port_index'])}（{chain['consumer_port_name']}）</div>"
                    )
                else:
                    parts.append(f"<div style='margin-left:1.5em;'>· {chain_anchor}</div>")
            if total_pages > 1:
                nav_bits = [
                    f"<span style='color:{Colors.TEXT_SECONDARY};'>第 {page_index + 1}/{total_pages} 页</span>"
                ]
                if page_index > 0:
                    nav_bits.append(
                        f"<a href='page_prev' style='margin-left:10px; color:{Colors.PRIMARY_LIGHT};'>上一页</a>"
                    )
                if page_index < total_pages - 1:
                    nav_bits.append(
                        f"<a href='page_next' style='margin-left:10px; color:{Colors.PRIMARY_LIGHT};'>下一页</a>"
                    )
                parts.append(f"<div style='margin-left:1.5em; margin-top:4px;'>{' '.join(nav_bits)}</div>")
        else:
            parts.append("<div style='margin-left:1.5em;'>· 未找到关联链路：该流程节点当前没有数据输入链路。</div>")
        return parts


