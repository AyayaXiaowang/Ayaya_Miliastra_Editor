# -*- coding: utf-8 -*-
"""
步骤跳过检查器：判断步骤是否需要跳过执行。

职责：
    - 检查连接步骤的节点可见性
    - 检查节点间距离是否过远
    - 在连续执行/单步执行等模式下统一返回跳过决策与原因
"""

from app.automation.editor.executor_protocol import ViewportController

# 单步执行模式下，用于标记“仅作为上下文参与规划、实际不执行”的跳过原因。
# UI 层可以据此选择是否在任务树中高亮为“跳过”。
SINGLE_STEP_SKIP_REASON = "单步执行模式：仅执行当前选中步骤，其余步骤用于提供上下文但实际跳过"


class SkipDecision:
    """跳过决策封装"""

    def __init__(self, should_skip: bool = False, reason: str = ""):
        self.should_skip = should_skip
        self.reason = reason


class StepSkipChecker:
    """步骤跳过检查器：集中可见性与距离检查逻辑"""

    def __init__(
        self,
        executor,
        graph_model,
        viewport_controller: ViewportController,
        visible_map_provider=None,
    ):
        self.executor = executor
        self.graph_model = graph_model
        # 视口控制器：仅用于视口对齐与坐标查询，避免策略层直接依赖执行器私有方法。
        self.viewport_controller: ViewportController = viewport_controller
        # 可选的可见节点映射提供器，用于在执行线程内复用单步级别的识别结果；
        # 未提供时将直接调用 executor.recognize_visible_nodes。
        self._visible_map_provider = visible_map_provider

    def _get_visible_map(self) -> dict:
        if callable(self._visible_map_provider):
            return self._visible_map_provider()
        return self.executor.recognize_visible_nodes(self.graph_model)

    def check_should_skip(self, step_info: dict, skip_first_create_after_calibration: bool,
                          skip_first_create_todo_id: str | None, step_todo_id: str) -> SkipDecision:
        """检查步骤是否应该跳过

        Args:
            step_info: 步骤详情
            skip_first_create_after_calibration: 校准后是否跳过首个创建步骤
            skip_first_create_todo_id: 首个创建步骤的 todo_id
            step_todo_id: 当前步骤的 todo_id

        Returns:
            SkipDecision: 跳过决策
        """
        step_type = step_info.get("type")

        # 检查0：单步执行模式下，仅允许目标步骤真正执行，其余步骤全部跳过。
        single_target = getattr(self.executor, "_single_step_target_todo_id", "")
        is_single_step_mode = isinstance(single_target, str) and bool(single_target)
        if is_single_step_mode and step_todo_id != single_target:
            return SkipDecision(
                should_skip=True,
                reason=SINGLE_STEP_SKIP_REASON,
            )

        # 检查1: 校准阶段已创建/确认锚点节点，跳过首个创建步骤
        if skip_first_create_after_calibration and step_todo_id == skip_first_create_todo_id:
            if step_type in ("graph_create_node", "graph_create_and_connect"):
                return SkipDecision(should_skip=True, reason="校准阶段已就绪锚点节点：跳过首个创建以避免重复")

        # 检查1.5：单步执行模式下，若目标步骤本身是“创建节点”，且节点已在当前画面中存在，则跳过创建。
        if is_single_step_mode and step_todo_id == single_target:
            if step_type in ("graph_create_node", "graph_create_and_connect"):
                node_id_value = step_info.get("node_id")
                node_id = str(node_id_value or "")
                nodes_attr = getattr(self.graph_model, "nodes", None)
                if node_id and isinstance(nodes_attr, dict) and node_id in nodes_attr:
                    visible_map = self._get_visible_map()
                    info = visible_map.get(node_id, {}) or {}
                    if bool(info.get("visible")):
                        reason_text = (
                            f"单步执行：目标创建节点已在当前画面存在（ID={node_id}），"
                            "跳过创建以避免重复。"
                        )
                        return SkipDecision(should_skip=True, reason=reason_text)

        # 检查2: 连接步骤的节点距离检查
        if step_type == "graph_connect":
            src_id = step_info.get("src_node") or step_info.get("prev_node_id")
            dst_id = step_info.get("dst_node") or step_info.get("node_id")
            if src_id and dst_id:
                too_far, reason = self.executor.will_connect_too_far(self.graph_model, src_id, dst_id, margin_ratio=0.10)
                if too_far:
                    return SkipDecision(should_skip=True, reason=reason)

        # 检查3: 合并连接步骤的节点距离检查
        if step_type == "graph_connect_merged":
            n1 = step_info.get("node1_id")
            n2 = step_info.get("node2_id")
            if n1 and n2:
                too_far, reason = self.executor.will_connect_too_far(self.graph_model, n1, n2, margin_ratio=0.10)
                if too_far:
                    return SkipDecision(should_skip=True, reason=reason)

        return SkipDecision(should_skip=False)

    def ensure_endpoints_visible(self, step_info: dict, log_callback, pause_hook, allow_continue, visual_callback) -> None:
        """确保连接步骤的两端节点可见

        Args:
            step_info: 步骤详情
            log_callback: 日志回调
            pause_hook: 暂停钩子
            allow_continue: 继续检查回调
            visual_callback: 可视化回调
        """
        step_type = step_info.get("type")
        if step_type != "graph_connect":
            return

        src_id = step_info.get("src_node") or step_info.get("prev_node_id")
        dst_id = step_info.get("dst_node") or step_info.get("node_id")
        if not (src_id and dst_id and src_id in self.graph_model.nodes and dst_id in self.graph_model.nodes):
            return

        # 首次检查端点可见性时优先使用线程注入的“单步可见节点缓存”，
        # 在本步内避免与零节点守卫重复构建 visible_map。
        visible_map = self._get_visible_map()
        src_ok = bool(visible_map.get(src_id, {}).get('visible'))
        dst_ok = bool(visible_map.get(dst_id, {}).get('visible'))
        if src_ok and dst_ok:
            return

        src_node = self.graph_model.nodes[src_id]
        dst_node = self.graph_model.nodes[dst_id]
        mid_x = (float(src_node.pos[0]) + float(dst_node.pos[0])) * 0.5
        mid_y = (float(src_node.pos[1]) + float(dst_node.pos[1])) * 0.5
        too_far, distance_reason = self.executor.will_connect_too_far(
            self.graph_model,
            src_id,
            dst_id,
            margin_ratio=0.10,
        )
        if distance_reason:
            log_callback(f"· 连线同屏评估：{distance_reason}")

        log_callback("准备连接：保证端点可见与安全区内…")

        if not too_far:
            log_callback("· 连线前视口对齐：聚焦两端中点，尝试一次性露出两端")
            self.viewport_controller.ensure_program_point_visible(
                mid_x,
                mid_y,
                log_callback=log_callback,
                pause_hook=pause_hook,
                allow_continue=allow_continue,
                visual_callback=visual_callback,
                graph_model=self.graph_model,
                force_pan_if_inside_margin=False,
            )
            visible_map = self.executor.recognize_visible_nodes(self.graph_model)
            src_ok = bool(visible_map.get(src_id, {}).get('visible'))
            dst_ok = bool(visible_map.get(dst_id, {}).get('visible'))
            if src_ok and dst_ok:
                return

        individually_aligned = False
        if not src_ok:
            self.viewport_controller.ensure_program_point_visible(
                src_node.pos[0],
                src_node.pos[1],
                log_callback=log_callback,
                pause_hook=pause_hook,
                allow_continue=allow_continue,
                visual_callback=visual_callback,
                graph_model=self.graph_model,
                force_pan_if_inside_margin=False,
            )
            individually_aligned = True
        if not dst_ok:
            self.viewport_controller.ensure_program_point_visible(
                dst_node.pos[0],
                dst_node.pos[1],
                log_callback=log_callback,
                pause_hook=pause_hook,
                allow_continue=allow_continue,
                visual_callback=visual_callback,
                graph_model=self.graph_model,
                force_pan_if_inside_margin=False,
            )
            individually_aligned = True

        if individually_aligned and not too_far:
            log_callback("· 视口再中心：维持两端同屏准备拖拽")
            self.viewport_controller.ensure_program_point_visible(
                mid_x,
                mid_y,
                log_callback=log_callback,
                pause_hook=pause_hook,
                allow_continue=allow_continue,
                visual_callback=visual_callback,
                graph_model=self.graph_model,
                force_pan_if_inside_margin=False,
            )

