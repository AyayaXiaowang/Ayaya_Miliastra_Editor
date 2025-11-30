"""Highlight manager for Y-debug overlay."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Set

from PyQt6 import QtGui

from ui.scene.interaction_state import YDebugInteractionState


class YDebugHighlightManager:
    """封装链路高亮/清除逻辑，避免 mixin 直接操作细节。"""

    def __init__(
        self,
        state: YDebugInteractionState,
        model_provider: Callable[[], object],
        node_items_provider: Callable[[], Dict[str, object]],
        edge_items_provider: Callable[[], Dict[str, object]],
        update_scene: Callable[[], None],
        clear_port_highlights: Optional[Callable[[], None]] = None,
    ) -> None:
        self.state = state
        self._model_provider = model_provider
        self._node_items_provider = node_items_provider
        self._edge_items_provider = edge_items_provider
        self._update_scene = update_scene
        self._clear_port_highlights_cb = clear_port_highlights
        self._all_chains_active = False
        self._node_color_map: Dict[str, QtGui.QColor] = {}
        self._node_chain_badges: Dict[str, int] = {}
        self._active_chain_id: Optional[int] = None
        self._active_chain_nodes: Dict[str, int] = {}

    @property
    def _debug_map(self) -> Dict:
        model = self._model_provider()
        return getattr(model, "_layout_y_debug_info", {}) or {}

    def apply_all_chains_highlight(self) -> None:
        debug_map = self._debug_map
        active_node_id = self.state.active_node_id
        if not active_node_id or active_node_id not in debug_map:
            return
        active_info = debug_map.get(active_node_id, {})
        active_block_index = active_info.get("block_index")
        active_event_flow_id = active_info.get("event_flow_id")
        node_type = active_info.get("type")
        selected_chain_ids: Set[int] = set()
        if node_type == "flow":
            for info in debug_map.values():
                if not isinstance(info, dict):
                    continue
                for chain in info.get("chains") or []:
                    if not isinstance(chain, dict):
                        continue
                    if chain.get("target_flow") == active_node_id and chain.get("id") is not None:
                        selected_chain_ids.add(int(chain["id"]))
        else:
            for chain in active_info.get("chains") or []:
                if isinstance(chain, dict) and chain.get("id") is not None:
                    selected_chain_ids.add(int(chain["id"]))
        if not selected_chain_ids:
            return
        chain_to_nodes: Dict[int, Set[str]] = {}
        node_to_chain_ids: Dict[str, List[int]] = {}
        chain_to_target_flow: Dict[int, str] = {}
        for node_id, info in debug_map.items():
            if not isinstance(info, dict):
                continue
            if active_block_index is not None and info.get("block_index") != active_block_index:
                continue
            if active_event_flow_id is not None and info.get("event_flow_id") != active_event_flow_id:
                continue
            for chain in info.get("chains") or []:
                if not isinstance(chain, dict):
                    continue
                cid_raw = chain.get("id")
                if cid_raw is None:
                    continue
                cid = int(cid_raw)
                if cid not in selected_chain_ids:
                    continue
                chain_to_nodes.setdefault(cid, set()).add(node_id)
                node_to_chain_ids.setdefault(node_id, []).append(cid)
        if not chain_to_nodes:
            return
        node_items = self._node_items_provider()
        edge_items = self._edge_items_provider()

        # 为每条链记录终点执行节点（target_flow），并将其视为链上的一员参与高亮
        for node_id, info in debug_map.items():
            if not isinstance(info, dict):
                continue
            if active_block_index is not None and info.get("block_index") != active_block_index:
                continue
            if active_event_flow_id is not None and info.get("event_flow_id") != active_event_flow_id:
                continue
            for chain in info.get("chains") or []:
                if not isinstance(chain, dict):
                    continue
                cid_raw = chain.get("id")
                if cid_raw is None:
                    continue
                cid = int(cid_raw)
                if cid not in selected_chain_ids:
                    continue
                target_flow_id = chain.get("target_flow")
                if isinstance(target_flow_id, str) and target_flow_id:
                    if cid not in chain_to_target_flow:
                        chain_to_target_flow[cid] = target_flow_id

        for cid, flow_node_id in chain_to_target_flow.items():
            node_to_chain_ids.setdefault(flow_node_id, []).append(cid)
            chain_to_nodes.setdefault(cid, set()).add(flow_node_id)

        palette_hex = ["#B388FF", "#00E5FF", "#FF9100", "#FF4081"]
        palette = [QtGui.QColor(hex_color) for hex_color in palette_hex]
        chain_color_map: Dict[int, QtGui.QColor] = {}
        for idx, cid in enumerate(sorted(chain_to_nodes.keys())):
            chain_color_map[cid] = palette[idx % len(palette)]
        for edge_item in edge_items.values():
            if hasattr(edge_item, "set_highlight_color"):
                edge_item.set_highlight_color(None)
            base_opacity = 0.2 if getattr(edge_item, "is_flow_edge", False) else 0.15
            edge_item.setOpacity(base_opacity)
        for node_item in node_items.values():
            node_item.setOpacity(0.25)
            for port in getattr(node_item, "_ports_in", []) + getattr(node_item, "_ports_out", []):
                if hasattr(port, "highlight_color") and port.highlight_color is not None:
                    port.highlight_color = None
                    port.update()
        node_color_map: Dict[str, QtGui.QColor] = {}
        node_chain_badges: Dict[str, int] = {}
        for edge_item in edge_items.values():
            if edge_item.is_flow_edge:
                continue
            src_node_id = edge_item.src.node_item.node.id if edge_item.src and edge_item.src.node_item else None
            dst_node_id = edge_item.dst.node_item.node.id if edge_item.dst and edge_item.dst.node_item else None
            if not src_node_id or not dst_node_id:
                continue
            src_set = set(node_to_chain_ids.get(src_node_id, []))
            dst_set = set(node_to_chain_ids.get(dst_node_id, []))
            intersection = src_set & dst_set
            if not intersection:
                continue
            chosen_cid = min(intersection)
            color = chain_color_map.get(chosen_cid)
            if color is None:
                continue
            if hasattr(edge_item, "set_highlight_color"):
                edge_item.set_highlight_color(color)
            edge_item.setOpacity(1.0)
            if edge_item.src:
                edge_item.src.highlight_color = color
                edge_item.src.is_highlighted = True
                edge_item.src.update()
                node_color_map[src_node_id] = color
                self._update_node_badge(node_chain_badges, src_node_id, chosen_cid)
                src_node_item = node_items.get(src_node_id)
                if src_node_item:
                    src_node_item.setOpacity(1.0)
                    src_node_item.update()
            if edge_item.dst:
                edge_item.dst.highlight_color = color
                edge_item.dst.is_highlighted = True
                edge_item.dst.update()
                node_color_map[dst_node_id] = color
                self._update_node_badge(node_chain_badges, dst_node_id, chosen_cid)
                dst_node_item = node_items.get(dst_node_id)
                if dst_node_item:
                    dst_node_item.setOpacity(1.0)
                    dst_node_item.update()
        for node_id in node_to_chain_ids.keys():
            node_item = node_items.get(node_id)
            if node_item:
                node_item.setOpacity(1.0)
                node_item.update()
        self._all_chains_active = True
        self._node_color_map = node_color_map
        self._node_chain_badges = node_chain_badges
        self._update_scene()

    def clear_all_chains_highlight(self) -> None:
        if not self._all_chains_active:
            return
        node_items = self._node_items_provider()
        edge_items = self._edge_items_provider()
        for edge_item in edge_items.values():
            if hasattr(edge_item, "set_highlight_color"):
                edge_item.set_highlight_color(None)
            edge_item.setOpacity(1.0)
            edge_item.update()
        for node_item in node_items.values():
            node_item.setOpacity(1.0)
            node_item.update()
            for port in getattr(node_item, "_ports_in", []) + getattr(node_item, "_ports_out", []):
                if hasattr(port, "highlight_color") and port.highlight_color is not None:
                    port.highlight_color = None
                    port.is_highlighted = False
                    port.update()
        self._all_chains_active = False
        self._node_color_map.clear()
        self._node_chain_badges.clear()
        self._update_scene()

    def highlight_chain(self, chain_id: int) -> None:
        debug_map = self._debug_map
        active_node_id = self.state.active_node_id
        active_info = debug_map.get(active_node_id, {}) if active_node_id else {}
        active_block_index = active_info.get("block_index")
        active_event_flow_id = active_info.get("event_flow_id")
        node_type = active_info.get("type")
        target_flow_scope = None
        for chain in active_info.get("chains") or []:
            if isinstance(chain, dict) and int(chain.get("id", -1)) == int(chain_id):
                target_flow_scope = chain.get("target_flow")
                break
        target_flow_id: Optional[str] = None
        if isinstance(target_flow_scope, str) and target_flow_scope:
            target_flow_id = target_flow_scope
        elif node_type == "flow" and isinstance(active_node_id, str) and active_node_id:
            target_flow_id = active_node_id
        selected_nodes: Dict[str, int] = {}
        for node_id, info in debug_map.items():
            if not isinstance(info, dict):
                continue
            if active_block_index is not None and info.get("block_index") != active_block_index:
                continue
            if active_event_flow_id is not None and info.get("event_flow_id") != active_event_flow_id:
                continue
            for chain in info.get("chains") or []:
                if not isinstance(chain, dict):
                    continue
                if int(chain.get("id", -1)) != int(chain_id):
                    continue
                if target_flow_scope is not None and chain.get("target_flow") != target_flow_scope:
                    continue
                selected_nodes[node_id] = int(chain.get("position", 0))
                break
        # 将终点执行节点（target_flow）也纳入高亮集合
        if target_flow_id and target_flow_id in debug_map and target_flow_id not in selected_nodes:
            selected_nodes[target_flow_id] = 0
        if not selected_nodes:
            return
        self._active_chain_id = int(chain_id)
        self._active_chain_nodes = selected_nodes
        if self._clear_port_highlights_cb:
            self._clear_port_highlights_cb()
        node_items = self._node_items_provider()
        edge_items = self._edge_items_provider()
        for node_id, node_item in node_items.items():
            node_item.setOpacity(1.0 if node_id in selected_nodes else 0.25)
            node_item.update()
        for edge_item in edge_items.values():
            src_node_id = edge_item.src.node_item.node.id if edge_item.src and edge_item.src.node_item else None
            dst_node_id = edge_item.dst.node_item.node.id if edge_item.dst and edge_item.dst.node_item else None
            included = (
                src_node_id in selected_nodes
                and dst_node_id in selected_nodes
                and not edge_item.is_flow_edge
            )
            if included:
                edge_item.setSelected(True)
                edge_item.setOpacity(1.0)
                if edge_item.src:
                    edge_item.src.is_highlighted = True
                    edge_item.src.update()
                if edge_item.dst:
                    edge_item.dst.is_highlighted = True
                    edge_item.dst.update()
            else:
                edge_item.setSelected(False)
                edge_item.setOpacity(0.15)
            edge_item.update()
        self._update_scene()

    def clear_chain_highlight(self) -> None:
        node_items = self._node_items_provider()
        edge_items = self._edge_items_provider()
        for node_item in node_items.values():
            node_item.setOpacity(1.0)
            node_item.update()
        for edge_item in edge_items.values():
            edge_item.setSelected(False)
            edge_item.setOpacity(1.0)
            if hasattr(edge_item, "set_highlight_color"):
                edge_item.set_highlight_color(None)
            edge_item.update()
        if self._clear_port_highlights_cb:
            self._clear_port_highlights_cb()
        self._active_chain_id = None
        self._active_chain_nodes.clear()
        self._update_scene()

    def _update_node_badge(self, storage: Dict[str, int], node_id: str, chain_id: int) -> None:
        existing = storage.get(node_id)
        if existing is None or chain_id < existing:
            storage[node_id] = chain_id


