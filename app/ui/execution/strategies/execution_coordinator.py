# -*- coding: utf-8 -*-
"""
执行协调器：管理执行前的校准、快速映射和单步验证。

职责：
    - 确保画布缩放为 50%
    - 快速映射（识别+几何拟合）
    - 传统锚点校准
    - 单步模式的识别与几何校验
"""


class CalibrationResult:
    """校准结果封装"""
    def __init__(self, success: bool, quick_mapped: bool = False, message: str = ""):
        self.success = success
        self.quick_mapped = quick_mapped
        self.message = message


class ExecutionCoordinator:
    """执行协调器：管理校准、快速映射、单步验证"""

    def __init__(self, executor, graph_model, monitor):
        self.executor = executor
        self.graph_model = graph_model
        self.monitor = monitor

    def ensure_zoom_50(self) -> bool:
        """确保画布缩放为 50%

        Returns:
            bool: 是否成功调整到 50%
        """
        self.monitor.update_status("检查缩放(50%)…")
        ok = self.executor.ensure_zoom_ratio_50(
            log_callback=self.monitor.log,
            pause_hook=self.monitor.wait_if_paused,
            allow_continue=self.monitor.is_execution_allowed,
            visual_callback=self.monitor.update_visual,
        )
        if ok:
            # 标记：本次连续执行期间已确认过 50% 缩放，后续步骤不再重复检查
            setattr(self.executor, "zoom_50_confirmed", True)
        else:
            self.monitor.log("✗ 无法将缩放调整为 50%，终止执行")
            self.monitor.update_status("终止")
        return ok

    def try_quick_mapping(self) -> bool:
        """尝试快速映射（识别+几何拟合）

        Returns:
            bool: 是否成功快速映射
        """
        if not getattr(self.executor, "fast_mapping_mode", True):
            return False

        self.monitor.update_status("快速匹配镜头…")
        ok = self.executor.verify_and_update_view_mapping_by_recognition(
            self.graph_model,
            log_callback=self.monitor.log,
            visual_callback=self.monitor.update_visual,
            allow_degraded_fallback=False,
        )
        if ok:
            self.monitor.log("✓ 快速映射：已根据当前画面更新比例与原点（跳过创建锚点）")
            synced = self.executor.sync_visible_nodes_positions(
                self.graph_model,
                threshold_px=60.0,
                log_callback=self.monitor.log,
            )
            if synced > 0:
                self.monitor.log(f"· 快速映射：已同步可见节点坐标 {synced} 个，防止使用过期坐标")
        return ok

    def calibrate_with_anchor(self, anchor_title: str, anchor_prog_pos: tuple[float, float],
                              should_create_anchor: bool) -> tuple[bool, str | None, tuple[float, float] | None]:
        """使用锚点进行坐标校准与视口定位

        Args:
            anchor_title: 锚点节点标题
            anchor_prog_pos: 锚点程序坐标
            should_create_anchor: 是否创建锚点节点

        Returns:
            tuple[bool, str | None, tuple[float, float] | None]: (成功与否, 锚点标题, 锚点坐标)
        """
        self.monitor.update_status("锚点坐标校准/视口定位…")
        self.monitor.log("开始锚点坐标校准/视口定位（首节点锚点）")
        self.monitor.wait_if_paused()

        if not (anchor_title and anchor_prog_pos):
            self.monitor.log("✗ 无可用锚点节点，无法校准")
            self.monitor.update_status("校准失败")
            return False, None, None

        ok = self.executor.calibrate_coordinates(
            anchor_title,
            anchor_prog_pos,
            log_callback=self.monitor.log,
            create_anchor_node=should_create_anchor,
            pause_hook=self.monitor.wait_if_paused,
            allow_continue=self.monitor.is_execution_allowed,
            visual_callback=self.monitor.update_visual,
            graph_model=self.graph_model,
        )

        if not ok:
            self.monitor.log("✗ 锚点坐标校准/视口定位失败")
            self.monitor.update_status("校准失败")
            return False, None, None

        self.monitor.log("✓ 锚点坐标校准/视口定位完成")
        synced = self.executor.sync_visible_nodes_positions(
            self.graph_model,
            threshold_px=60.0,
            log_callback=self.monitor.log,
        )
        if synced > 0:
            self.monitor.log(f"· 锚点校准：已同步可见节点坐标 {synced} 个，防止使用过期坐标")
        return True, anchor_title, anchor_prog_pos

    def check_skip_first_create_after_calibration(self, anchor_node_id: str | None,
                                                   anchor_prog_pos: tuple[float, float] | None) -> bool:
        """检查校准后是否可以跳过首个创建步骤

        Args:
            anchor_node_id: 锚点节点ID
            anchor_prog_pos: 锚点程序坐标

        Returns:
            bool: 是否可以跳过
        """
        if not anchor_node_id or not anchor_prog_pos:
            return False
        if anchor_node_id not in self.graph_model.nodes:
            return False

        visible_map = self.executor.recognize_visible_nodes(self.graph_model)
        info = visible_map.get(anchor_node_id, {})
        if not info.get('visible') or info.get('bbox') is None:
            return False

        expected_x, expected_y = self.executor.convert_program_to_editor_coords(
            anchor_prog_pos[0], anchor_prog_pos[1]
        )
        left_v, top_v, _, _ = info['bbox']
        dx = float(left_v - expected_x)
        dy = float(top_v - expected_y)
        return (dx * dx + dy * dy) <= (30.0 * 30.0)

    def verify_single_step_mapping(self, *, fail_hard: bool = True) -> bool:
        """单步模式：识别与几何校验

        Args:
            fail_hard: 当识别/几何校验不达标时是否视为致命错误。

        Returns:
            bool: 识别与几何校验是否通过（即便非致命模式下失败也会返回 False）
        """
        self.monitor.log("单步：执行前进行画面识别与几何校验（三阶段：唯一锚点→普通锚点→普通节点兜底）…")
        ok = self.executor.verify_and_update_view_mapping_by_recognition(
            self.graph_model,
            log_callback=self.monitor.log,
            visual_callback=self.monitor.update_visual,
            allow_degraded_fallback=False,
        )
        if not ok:
            if fail_hard:
                self.monitor.log("✗ 识别/几何校验未通过（锚点与普通节点匹配均失败），终止此步")
                self.monitor.update_status("校验失败")
            else:
                self.monitor.log(
                    "⚠ 识别/几何校验未通过（无法从当前画面恢复稳定的视口映射），将在当前校准结果下继续尝试执行此步",
                )
        else:
            self.monitor.log("✓ 识别/几何校验通过，已更新比例与原点")
            synced = self.executor.sync_visible_nodes_positions(
                self.graph_model,
                threshold_px=60.0,
                log_callback=self.monitor.log,
            )
            if synced > 0:
                self.monitor.log(f"· 单步：已同步可见节点坐标 {synced} 个，防止使用过期坐标")
        return ok

