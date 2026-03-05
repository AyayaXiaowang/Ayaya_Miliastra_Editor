# -*- coding: utf-8 -*-
"""
回退处理器：封装失败重试逻辑。

职责：
- 以最近成功锚点为基准修正可见性
- 重试失败步骤
- 更新锚点记录
"""

from app.automation.editor.executor_protocol import ViewportController


class RetryResult:
    """重试结果封装"""
    def __init__(self, success: bool, did_retry: bool = False):
        self.success = success
        self.did_retry = did_retry


class RetryHandler:
    """回退处理器：封装失败重试逻辑"""

    def __init__(
        self,
        executor,
        graph_model,
        monitor,
        viewport_controller: ViewportController,
    ):
        self.executor = executor
        self.graph_model = graph_model
        self.monitor = monitor
        # 视口控制器：用于在重试前基于最近锚点对齐视口。
        self.viewport_controller: ViewportController = viewport_controller
        self.last_success_anchor_title: str | None = None
        self.last_success_anchor_prog_pos: tuple[float, float] | None = None

    def set_anchor(self, title: str, prog_pos: tuple[float, float]) -> None:
        """设置最近成功锚点"""
        self.last_success_anchor_title = title
        self.last_success_anchor_prog_pos = prog_pos

    def try_retry_with_anchor_fallback(self, step_info: dict, step_todo_id: str) -> RetryResult:
        """失败后的重试策略（优先原地恢复映射，其次回退锚点）

        Args:
            step_info: 步骤详情
            step_todo_id: 步骤ID

        Returns:
            RetryResult: 重试结果
        """
        _ = str(step_todo_id or "")
        if not self.monitor.is_execution_allowed():
            return RetryResult(success=False, did_retry=False)

        # 1) 优先：在当前位置重新识别，刷新“程序坐标→窗口坐标”的映射。
        #    目的：当映射漂移导致视口对齐方向错误/节点 ROI 跑出屏幕时，不要盲目拖拽回锚点，
        #    而是先用识别把 origin/scale 拉回可信状态，让后续 ensure_program_point_visible 能重新规划正确的拖拽方向。
        verify_mapping = getattr(self.executor, "verify_and_update_view_mapping_by_recognition", None)
        if callable(verify_mapping):
            self.monitor.log("↺ 回退：在当前位置重新识别校准坐标映射后重试当前步骤")
            ok_fit = bool(
                verify_mapping(
                    self.graph_model,
                    log_callback=self.monitor.log,
                    visual_callback=self.monitor.update_visual,
                    allow_degraded_fallback=True,
                )
            )
            self.monitor.wait_if_paused()

            if not self.monitor.is_execution_allowed():
                return RetryResult(success=False, did_retry=True)

            if ok_fit:
                success = self.executor.execute_step(
                    step_info,
                    self.graph_model,
                    log_callback=self.monitor.log,
                    pause_hook=self.monitor.wait_if_paused,
                    allow_continue=self.monitor.is_execution_allowed,
                    visual_callback=self.monitor.update_visual,
                )
                if success:
                    self.monitor.log("✓ 映射恢复后重试成功")
                else:
                    self.monitor.log("· 映射已恢复，但重试仍失败，将交由上层决定是否继续重试")
                return RetryResult(success=bool(success), did_retry=True)

        # 2) 兜底：若具备最近成功锚点，则把视口回退到锚点附近再重试。
        #    说明：当当前位置可见节点不足、识别无法建立稳定映射时，回到“已成功操作过”的区域更可能恢复后续步骤。
        if self.last_success_anchor_prog_pos is None:
            return RetryResult(success=False, did_retry=True)

        apx, apy = self.last_success_anchor_prog_pos

        if not self.monitor.is_execution_allowed():
            return RetryResult(success=False, did_retry=True)

        if callable(verify_mapping):
            probe_drags_raw = getattr(self.executor, "retry_anchor_probe_max_drags", 3)
            probe_drags = int(probe_drags_raw) if probe_drags_raw is not None else 3
            if probe_drags < 0:
                probe_drags = 0

            if probe_drags > 0:
                self.monitor.log("↺ 回退：映射恢复失败，开始逐步回退（每步后尝试识别恢复映射）")

            for probe_index in range(probe_drags):
                if not self.monitor.is_execution_allowed():
                    return RetryResult(success=False, did_retry=True)

                self.viewport_controller.ensure_program_point_visible(
                    apx,
                    apy,
                    margin_ratio=0.10,
                    max_steps=1,
                    pan_step_pixels=420,
                    log_callback=self.monitor.log,
                    pause_hook=self.monitor.wait_if_paused,
                    allow_continue=self.monitor.is_execution_allowed,
                    visual_callback=self.monitor.update_visual,
                    graph_model=self.graph_model,
                    force_pan_if_inside_margin=False,
                )
                self.monitor.wait_if_paused()

                if not self.monitor.is_execution_allowed():
                    return RetryResult(success=False, did_retry=True)

                self.monitor.log(f"· 回退探测：第 {probe_index + 1}/{probe_drags} 次拖拽后尝试识别恢复映射")
                ok_fit = bool(
                    verify_mapping(
                        self.graph_model,
                        log_callback=self.monitor.log,
                        visual_callback=self.monitor.update_visual,
                        allow_degraded_fallback=True,
                    )
                )
                self.monitor.wait_if_paused()
                if ok_fit:
                    self.monitor.log("✓ 识别恢复成功：将重试当前步骤")
                    success = self.executor.execute_step(
                        step_info,
                        self.graph_model,
                        log_callback=self.monitor.log,
                        pause_hook=self.monitor.wait_if_paused,
                        allow_continue=self.monitor.is_execution_allowed,
                        visual_callback=self.monitor.update_visual,
                    )
                    if success:
                        self.monitor.log("✓ 回退后重试成功")
                        # 若是创建步骤，更新锚点
                        step_type = step_info.get("type")
                        if step_type in ("graph_create_node", "graph_create_and_connect"):
                            node_id = step_info.get("node_id")
                            if node_id and node_id in self.graph_model.nodes:
                                self.last_success_anchor_title = self.graph_model.nodes[node_id].title
                                self.last_success_anchor_prog_pos = self.graph_model.nodes[node_id].pos
                    return RetryResult(success=bool(success), did_retry=True)

            self.monitor.log("↺ 回退：逐步回退未能恢复识别，改为完整回退到最近锚点后再尝试识别")

        self.viewport_controller.ensure_program_point_visible(
            apx,
            apy,
            margin_ratio=0.10,
            max_steps=8,
            pan_step_pixels=420,
            log_callback=self.monitor.log,
            pause_hook=self.monitor.wait_if_paused,
            allow_continue=self.monitor.is_execution_allowed,
            visual_callback=self.monitor.update_visual,
            graph_model=self.graph_model,
            force_pan_if_inside_margin=False,
        )
        self.monitor.wait_if_paused()

        if callable(verify_mapping):
            ok_fit = bool(
                verify_mapping(
                    self.graph_model,
                    log_callback=self.monitor.log,
                    visual_callback=self.monitor.update_visual,
                    allow_degraded_fallback=True,
                )
            )
            self.monitor.wait_if_paused()
            if not ok_fit:
                self.monitor.log("✗ 完整回退后仍无法恢复识别映射，本次回退重试终止")
                return RetryResult(success=False, did_retry=True)

        self.monitor.log("✓ 完整回退后识别恢复：将重试当前步骤")
        success = self.executor.execute_step(
            step_info,
            self.graph_model,
            log_callback=self.monitor.log,
            pause_hook=self.monitor.wait_if_paused,
            allow_continue=self.monitor.is_execution_allowed,
            visual_callback=self.monitor.update_visual,
        )

        if success:
            self.monitor.log("✓ 回退后重试成功")
            # 若是创建步骤，更新锚点
            step_type = step_info.get("type")
            if step_type in ("graph_create_node", "graph_create_and_connect"):
                node_id = step_info.get("node_id")
                if node_id and node_id in self.graph_model.nodes:
                    self.last_success_anchor_title = self.graph_model.nodes[node_id].title
                    self.last_success_anchor_prog_pos = self.graph_model.nodes[node_id].pos

        return RetryResult(success=success, did_retry=True)

    def update_anchor_after_success(self, step_info: dict) -> None:
        """创建成功后更新锚点

        Args:
            step_info: 步骤详情
        """
        step_type = step_info.get("type")
        if step_type not in ("graph_create_node", "graph_create_and_connect"):
            return

        node_id = step_info.get("node_id")
        if node_id and node_id in self.graph_model.nodes:
            self.last_success_anchor_title = self.graph_model.nodes[node_id].title
            self.last_success_anchor_prog_pos = self.graph_model.nodes[node_id].pos

