# -*- coding: utf-8 -*-
"""
EditorExecutor View State Mixin

收敛视口 token、场景级快照、快速链、连续连线缓存等“执行器内部状态”维护逻辑。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from PIL import Image

from app.automation.vision import invalidate_cache

from .automation_step_types import FAST_CHAIN_ELIGIBLE_STEP_TYPES
from .node_snapshot import GraphSceneSnapshot


class EditorExecutorViewStateMixin:
    # 允许参与快速链模式的步骤类型（集中在 automation_step_types 中）
    FAST_CHAIN_NO_WAIT_TYPES = set(FAST_CHAIN_ELIGIBLE_STEP_TYPES)

    fast_chain_mode: bool
    _fast_chain_step_type: str
    _connect_chain_context: Optional[Dict[str, Any]]
    _connect_chain_dirty: bool
    _view_state_token: int
    _last_connect_prepare_token: int
    _last_synced_view_state_token: int
    _scene_snapshot: Optional[GraphSceneSnapshot]
    _recent_node_position_deltas: Dict[str, tuple[float, float]]
    _position_delta_token: int
    _last_recognition_screenshot: Optional[Image.Image]
    _last_recognition_detected: Optional[list]
    scale_ratio: Optional[float]
    origin_node_pos: Optional[Tuple[float, float]]
    drag_distance_per_pixel: Optional[float]
    _last_context_click_editor_pos: Optional[Tuple[int, int]]
    zoom_50_confirmed: bool
    _created_node_history: list[str]
    _created_node_lookup: set[str]

    # ===== 视口 token 与识别预热 token（对外只暴露方法，不暴露内部字段） =====
    def get_view_state_token(self) -> int:
        """获取当前视口 token，用于判断缓存/识别是否可复用。"""
        return int(self._view_state_token)

    def should_prepare_for_connect(self) -> bool:
        """判断是否需要做“连线前识别预热”。"""
        return int(self._last_connect_prepare_token) != int(self._view_state_token)

    def mark_connect_prepared(self) -> None:
        """标记当前视口 token 已完成连线预热。"""
        self._last_connect_prepare_token = int(self._view_state_token)

    def should_sync_visible_nodes_positions(self) -> bool:
        """判断是否需要做“可见节点坐标同步”。"""
        return int(self._last_synced_view_state_token) != int(self._view_state_token)

    def mark_visible_nodes_positions_synced(self) -> None:
        """标记当前视口 token 已完成可见节点坐标同步。"""
        self._last_synced_view_state_token = int(self._view_state_token)

    # ===== 快速链辅助 =====
    def set_fast_chain_step_type(self, step_type: str) -> None:
        """由执行线程注入当前步骤类型，用于限制快速链的生效范围。"""
        self._fast_chain_step_type = str(step_type or "")

    def reset_fast_chain_step_type(self) -> None:
        self._fast_chain_step_type = ""

    def is_fast_chain_step_enabled(self) -> bool:
        """仅当快速链开启且当前步骤属于连接/配置类时才跳过等待。"""
        if not self.fast_chain_mode:
            return False
        return self._fast_chain_step_type in self.FAST_CHAIN_NO_WAIT_TYPES

    # ===== 连续连线缓存 =====
    def invalidate_connect_chain_context(self, reason: str = "") -> None:
        self._connect_chain_context = None
        self._connect_chain_dirty = False

    def begin_connect_chain_step(self) -> Optional[Dict[str, Any]]:
        self._connect_chain_dirty = False
        return self._connect_chain_context

    def complete_connect_chain_step(self, context: Optional[Dict[str, Any]], success: bool) -> None:
        if not success or self._connect_chain_dirty:
            self._connect_chain_context = None
            return
        self._connect_chain_context = context

    def _reset_view_state(self, reason: str = "") -> None:
        """重置与当前编辑器视口绑定的缓存状态。

        - 自增视口 token，并清空最近一次“识别预热”与“已同步视口”的 token
        - 失效场景级截图与节点检测缓存
        - 清空连续连线上下文与节点位移缓存
        - 清空识别阶段的首帧截图与检测结果缓存，避免在视口变化后误用旧画面
        """
        self._view_state_token += 1
        self._last_connect_prepare_token = -1
        self._last_synced_view_state_token = -1
        self._connect_chain_dirty = True
        self._connect_chain_context = None
        self._recent_node_position_deltas.clear()
        self._position_delta_token = -1
        # 视口变化会使上一帧截图与节点检测结果整体失效
        if self._scene_snapshot is not None:
            self._scene_snapshot.invalidate_all(reason or "view_changed")
        # 同步清理“视口识别阶段”缓存的首帧截图与检测结果，避免在视口变化后误用旧画面。
        self._last_recognition_screenshot = None
        self._last_recognition_detected = None

    def mark_view_changed(self, reason: str = "") -> None:
        """标记视口发生变化，由执行步骤或上层在拖拽/缩放后调用。"""
        self._reset_view_state(reason or "view_changed")

    def get_scene_snapshot(self) -> GraphSceneSnapshot:
        """获取当前执行器绑定的场景级快照实例（按需懒初始化）。"""
        if self._scene_snapshot is None:
            self._scene_snapshot = GraphSceneSnapshot(self)
        return self._scene_snapshot

    def invalidate_scene_snapshot(self, reason: str = "") -> None:
        """显式失效场景级快照，用于执行完具有拖拽/布局变更效果的步骤后触发重识别。"""
        if self._scene_snapshot is not None:
            self._scene_snapshot.invalidate_all(reason or "manual")

    def reset_mapping_state(self, log_callback=None) -> None:
        """清空上次执行残留的坐标映射与识别缓存，用于从根步骤开始全量执行前的干净环境。
        - 清空 scale_ratio / origin_node_pos / drag_distance_per_pixel
        - 清空最近一次上下文右键位置
        - 失效视觉识别一步式缓存
        """
        self.scale_ratio = None
        self.origin_node_pos = None
        self.drag_distance_per_pixel = None
        self._last_context_click_editor_pos = None
        invalidate_cache()
        self._log("↻ 已清空上次执行残留：坐标映射与识别缓存已重置", log_callback)
        # 同步复位“缩放一致性已确认”标记，确保单步/新一轮执行前会进行一次检查
        self.zoom_50_confirmed = False
        self.mark_view_changed("reset_mapping_state")
        self._created_node_history.clear()
        self._created_node_lookup.clear()


