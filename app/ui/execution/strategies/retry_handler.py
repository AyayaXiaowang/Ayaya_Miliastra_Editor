# -*- coding: utf-8 -*-
"""
回退处理器：封装失败重试逻辑。

职责：
- 以最近成功锚点为基准修正可见性
- 重试失败步骤
- 更新锚点记录
"""

from app.automation.core.executor_protocol import ViewportController


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

    def try_retry_with_anchor_fallback(self, step_info: dict, step_todo_id: str,
                                       step_completed_signal) -> RetryResult:
        """以最近锚点为基准回退并重试

        Args:
            step_info: 步骤详情
            step_todo_id: 步骤ID
            step_completed_signal: 步骤完成信号

        Returns:
            RetryResult: 重试结果
        """
        if self.last_success_anchor_prog_pos is None:
            return RetryResult(success=False, did_retry=False)

        self.monitor.log("↺ 回退：以最近锚点重建可见性后重试当前步骤")
        apx, apy = self.last_success_anchor_prog_pos

        if not self.monitor.is_execution_allowed():
            return RetryResult(success=False, did_retry=True)

        self.viewport_controller.ensure_program_point_visible(
            apx,
            apy,
            log_callback=self.monitor.log,
            pause_hook=self.monitor.wait_if_paused,
            allow_continue=self.monitor.is_execution_allowed,
            visual_callback=self.monitor.update_visual,
            graph_model=self.graph_model,
            force_pan_if_inside_margin=False,
        )
        self.monitor.wait_if_paused()

        success = self.executor.execute_step(
            step_info,
            self.graph_model,
            log_callback=self.monitor.log,
            pause_hook=self.monitor.wait_if_paused,
            allow_continue=self.monitor.is_execution_allowed,
            visual_callback=self.monitor.update_visual,
        )

        step_completed_signal.emit(step_todo_id, success)

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

