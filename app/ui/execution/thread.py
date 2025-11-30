# -*- coding: utf-8 -*-
"""
执行线程：后台执行节点图步骤的独立可测单元

原为 ExecutionRunner._Thread 内嵌类，现提取为独立模块以提升可测试性与可维护性。

设计目标：
- 单一职责：仅负责执行流程编排，不处理信号转发
- 可测试性：无 Qt 信号依赖，所有回调通过构造函数注入
- 可替换性：通过协议依赖 executor，而非具体实现
"""

from typing import Any, Callable, Optional, Dict
from PyQt6 import QtCore
from PyQt6.QtCore import pyqtSignal
from PIL import Image

from .strategies import (
    AnchorSelector,
    StepSummaryBuilder,
    ExecutionCoordinator,
    StepSkipChecker,
    RetryHandler,
)
from app.automation.core.executor_protocol import EditorExecutorProtocol
from engine.graph.models.graph_model import GraphModel
from engine.configs.settings import settings
from app.automation import capture as editor_capture
from app.automation.vision import list_nodes


class ExecutionThread(QtCore.QThread):
    """执行线程：在后台顺序执行节点图步骤
    
    职责：
    1. 锚点选择与坐标校准
    2. 画布缩放检查
    3. 快速映射（识别+几何拟合）
    4. 逐步执行步骤（创建/连接/配置）
    5. 失败时的回退重试
    
    线程安全性：
    - 通过 PyQt6 信号机制与主线程通信
    - 所有 UI 更新通过 monitor 对象间接触发
    """
    
    # 信号定义
    step_will_start = pyqtSignal(str)  # todo_id
    step_completed = pyqtSignal(str, bool)  # todo_id, success
    step_skipped = pyqtSignal(str, str)  # todo_id, reason
    
    def __init__(
        self,
        executor: EditorExecutorProtocol,
        graph_model: GraphModel,
        steps: list,
        monitor: Any,
        *,
        fast_chain_mode: bool = False,
    ):
        """初始化执行线程
        
        Args:
            executor: 执行器实例（符合 EditorExecutorProtocol 协议）
            graph_model: 图模型
            steps: 待执行步骤列表（List[TodoItem]）
            monitor: 监控对象，需实现以下方法：
                - start_monitoring()
                - stop_monitoring()
                - update_status(str)
                - log(str)
                - wait_if_paused()
                - is_execution_allowed() -> bool
                - update_visual(Image, overlays)
        """
        super().__init__()
        self.executor = executor
        self.graph_model = graph_model
        self.steps = steps
        self.monitor = monitor
        self.fast_chain_mode = fast_chain_mode

        # 单步执行过程中的“可见节点映射”缓存，仅用于线程内的守卫与跳过检查：
        # - 同一执行步内的零节点守卫与跳过检查共享一次 recognize_visible_nodes 结果；
        # - 进入具体执行器步骤前不会在核心层复用，自动化内核仍按自身快照与缓存策略工作。
        self._step_visible_map_cache: Optional[Dict[str, Dict[str, Any]]] = None

        # 策略对象（依赖注入，便于测试替换）
        self.anchor_selector = AnchorSelector(graph_model)
        self.summary_builder = StepSummaryBuilder(graph_model)
        self.coordinator = ExecutionCoordinator(executor, graph_model, monitor)
        # 视口控制与执行解耦：策略层通过 ViewportController 协议访问视口能力，
        # 但实际传入的实现仍为同一个 EditorExecutor 实例，保证视口状态与执行状态一致。
        self.skip_checker = StepSkipChecker(executor, graph_model, executor)
        self.retry_handler = RetryHandler(executor, graph_model, monitor, executor)
        # 为执行器构建“节点首次创建步骤索引”，便于在创建节点时过滤“未来步骤中的节点”作为前置参考
        node_first_create_index: Dict[str, int] = self._build_node_first_create_step_index(self.steps)
        if hasattr(self.executor, "__dict__"):
            setattr(self.executor, "_node_first_create_step_index", dict(node_first_create_index))
        # 记录“步骤列表中首个创建类步骤”的索引，用于零节点识别守卫
        self._first_create_step_index: Optional[int] = None
        if node_first_create_index:
            try:
                self._first_create_step_index = min(int(idx) for idx in node_first_create_index.values())
            except Exception:
                self._first_create_step_index = None
    
    def _build_node_first_create_step_index(self, steps: list) -> Dict[str, int]:
        """基于步骤列表构建 node_id -> 首次创建步骤索引 的映射。

        约定：
        - 仅统计真正“创建节点”的步骤类型：graph_create_node / graph_create_and_connect。
        - 同一节点若在后续步骤中再次出现（例如连接或配置），不会覆盖更早的创建索引。
        - 当执行的是“仅此一步”时，steps 只包含这一项，此时无法区分前后顺序，
          但映射仍然有效（仅在连续执行场景中用于过滤“未来节点”）。
        """
        log_callback = getattr(self.monitor, "log", None)
        mapping: Dict[str, int] = {}
        for step_index, todo in enumerate(steps):
            detail_info = getattr(todo, "detail_info", None) or {}
            step_type = str(detail_info.get("type", ""))
            if step_type == "graph_create_node" or step_type == "graph_create_and_connect":
                node_id_value = detail_info.get("node_id")
                node_id = str(node_id_value or "")
                if node_id and node_id not in mapping:
                    mapping[node_id] = step_index
                    if callable(log_callback):
                        todo_id = getattr(todo, "todo_id", "")
                        title = getattr(todo, "title", "")
                        log_callback(
                            f"[CREATE-INDEX] step_index={step_index}, "
                            f"todo_id='{todo_id}', title='{title}', "
                            f"type='{step_type}', node_id='{node_id}'"
                        )
        return mapping
    
    def run(self) -> None:
        """执行主流程：锚点选择 → 快速映射 → 逐步执行
        
        流程阶段：
        1. 预处理执行器模式（如快速链）
        2. 选择锚点（多层退化策略，仅用于规划与日志）
        3. 确保画布缩放为 50%
        4. 尝试快速映射（识别+几何拟合）
        5. 单步模式下进行识别与几何校验（快速映射失败时）
        6. 逐步执行，失败时回退重试
        """
        # 阶段1: 预处理执行器模式
        previous_fast_chain_mode = getattr(self.executor, "fast_chain_mode", False)
        if self.fast_chain_mode:
            self.executor.fast_chain_mode = True
            self.monitor.log("⚡ 快速链模式：跳过连接/参数步骤的缓冲等待")
        
        try:
            # 阶段2: 选择锚点
            anchor_info = self.anchor_selector.select_anchor(self.steps)

            # 阶段3: 确保画布缩放为 50%
            if not self.coordinator.ensure_zoom_50():
                return

            # 阶段4: 始终优先尝试快速映射（识别+几何拟合），基于当前画面节点分布建立映射
            first_step = self.steps[0] if self.steps else None
            first_step_info = getattr(first_step, "detail_info", None) or {}
            first_step_type = first_step_info.get("type")

            quick_mapped = self.coordinator.try_quick_mapping()

            # 阶段5: 单步模式的识别与几何校验（仅在快速映射失败时生效）
            skip_first_create_after_calibration = False
            if (len(self.steps) == 1) and (not quick_mapped):
                # 单步执行时，无论步骤类型，都先进行一次识别+几何校验；
                # 对于“仅此一步且为创建类”的场景，识别失败视为软失败：给出警告但继续尝试创建，
                # 以支持“空画布上首次放置锚点”的典型用法。
                is_create_step = first_step_type in ("graph_create_node", "graph_create_and_connect")
                check_ok = self.coordinator.verify_single_step_mapping(
                    fail_hard=not is_create_step,
                )
                if not check_ok and (not is_create_step):
                    return

            # 阶段6: 逐步执行
            self._execute_steps_loop(anchor_info, skip_first_create_after_calibration)
            
        finally:
            # 恢复快速链标志
            self.executor.fast_chain_mode = previous_fast_chain_mode
            # 清理由执行线程注入到执行器的临时上下文字段，避免跨次执行残留
            if hasattr(self.executor, "__dict__"):
                if getattr(self.executor, "_current_step_index", None) is not None:
                    try:
                        delattr(self.executor, "_current_step_index")
                    except AttributeError:
                        self.executor._current_step_index = -1
                if getattr(self.executor, "_node_first_create_step_index", None) is not None:
                    try:
                        delattr(self.executor, "_node_first_create_step_index")
                    except AttributeError:
                        self.executor._node_first_create_step_index = {}
                if getattr(self.executor, "_single_step_target_todo_id", None) is not None:
                    try:
                        delattr(self.executor, "_single_step_target_todo_id")
                    except AttributeError:
                        self.executor._single_step_target_todo_id = ""
            # 延迟停止监控（避免UI线程冲突）
            QtCore.QTimer.singleShot(0, self.monitor.stop_monitoring)
    
    def _execute_steps_loop(
        self,
        anchor_info: Any,
        skip_first_create_after_calibration: bool
    ) -> None:
        """逐步执行循环
        
        Args:
            anchor_info: 锚点信息（含 skip_first_todo_id）
            skip_first_create_after_calibration: 是否跳过首个创建步骤
        """
        for step_index, step_todo in enumerate(self.steps):
            # 每步开始前清空“单步可见节点缓存”，保证守卫与跳过检查只共享当前步内的一次识别结果。
            self._step_visible_map_cache = None
            # 检查是否被终止
            if not self.monitor.is_execution_allowed():
                break
            step_info = step_todo.detail_info or {}
            if hasattr(self.executor, "__dict__"):
                setattr(self.executor, "_current_step_index", step_index)
            log_callback = getattr(self.monitor, "log", None)
            if callable(log_callback):
                primary_node_id_value = (
                    step_info.get("node_id")
                    or step_info.get("src_node")
                    or step_info.get("dst_node")
                    or step_info.get("node1_id")
                    or step_info.get("node2_id")
                )
                primary_node_id = str(primary_node_id_value or "")
                step_type = step_info.get("type")
                log_callback(
                    f"[STEP-CTX] current_step_index={step_index}, "
                    f"todo_id='{step_todo.todo_id}', title='{step_todo.title}', "
                    f"type='{step_type}', node_id='{primary_node_id}'"
                )
            self._update_fast_chain_scope(step_info.get("type"))
            
            # 发射"将开始"事件（允许UI在单步模式下先行暂停）
            self.step_will_start.emit(step_todo.todo_id)
            self.monitor.wait_if_paused()
            self.monitor.update_status("执行步骤...")
            self.monitor.log(f"执行步骤: {step_todo.title}")
            
            # 检查是否需要跳过此步骤
            skip_decision = self.skip_checker.check_should_skip(
                step_info,
                skip_first_create_after_calibration,
                anchor_info.skip_first_todo_id,
                step_todo.todo_id
            )
            if skip_decision.should_skip:
                self.monitor.log(f"· {skip_decision.reason}")
                self.step_skipped.emit(step_todo.todo_id, skip_decision.reason)
                continue

            # 零节点识别守卫：除首个创建步骤外，若当前画面检测不到任何节点则立即终止执行
            guard_ok, guard_reason = self._check_zero_nodes_guard(step_index, step_todo, step_info)
            if not guard_ok:
                summary_text = self.summary_builder.build_summary(step_info)
                reason_txt = guard_reason or "当前页面未识别到任何节点"
                self.monitor.log(f"✗ 步骤执行失败：{summary_text}｜原因：{reason_txt}")
                self.step_completed.emit(step_todo.todo_id, False)
                self.monitor.update_status("执行失败")
                break
            
            # 确保连接步骤的端点可见
            self.skip_checker.ensure_endpoints_visible(
                step_info,
                self.monitor.log,
                self.monitor.wait_if_paused,
                self.monitor.is_execution_allowed,
                self.monitor.update_visual
            )
            
            # 执行步骤
            success, last_issue = self._execute_single_step(step_info)
            
            # 成功时更新锚点
            if success:
                self.retry_handler.update_anchor_after_success(step_info)
            
            # 输出摘要（首轮执行的结果说明）
            summary_text = self.summary_builder.build_summary(step_info)
            if success:
                self.monitor.log(f"✓ 步骤执行成功：{summary_text}")
            else:
                reason_txt = last_issue if last_issue else "未提供原因（请查看上方详细日志）"
                self.monitor.log(f"✗ 步骤执行失败：{summary_text}｜原因：{reason_txt}")
            
            # 首次执行结果回填给外层（包括失败态）
            self.step_completed.emit(step_todo.todo_id, success)
            
            # 失败时按统一上限尝试回退重试：所有步骤最多自动再跑 N 次
            if not success:
                max_retry = self._get_max_step_retry_limit()
                retry_success = False
                # 统一使用相同的“自动再跑次数”上限，避免有的步骤多次重试、有的只重试一次
                for _ in range(max(0, max_retry)):
                    retry_result = self.retry_handler.try_retry_with_anchor_fallback(
                        step_info,
                        step_todo.todo_id,
                        self.step_completed,
                    )
                    if retry_result.success:
                        retry_success = True
                        break
                    # 若当前环境根本无法回退重试（无锚点等），无需空转后续循环
                    if not retry_result.did_retry:
                        break
                if retry_success:
                    continue
                # 若在统一次数上限内仍未成功，则终止整个执行
                self.monitor.update_status("执行失败")
                break
        else:
            # 正常完成所有步骤
            self.monitor.update_status("执行完成")
        self._update_fast_chain_scope("")
    
    def _get_max_step_retry_limit(self) -> int:
        """获取单个步骤在真实执行中的最大自动重试次数。
        
        配置来源：engine.configs.settings.REAL_EXEC_MAX_STEP_RETRY
        - 配置为 0 或负数时视为不自动重试（仅首轮执行一次）；
        - 默认值为 3。
        """
        try:
            value = getattr(settings, "REAL_EXEC_MAX_STEP_RETRY", 3)
            return int(value) if value is not None else 3
        except Exception:
            return 3
    
    def _execute_single_step(
        self,
        step_info: dict
    ) -> tuple[bool, Optional[str]]:
        """执行单个步骤，捕获最后一条错误信息
        
        Args:
            step_info: 步骤详情
        
        Returns:
            (success, last_issue)
            - success: 是否成功
            - last_issue: 最后一条错误/警告信息，无则为 None
        """
        # 捕获本步最后一条错误/警告信息
        last_issue_container: list[Optional[str]] = [None]
        
        def log_with_capture(message: str) -> None:
            """日志回调包装：捕获错误/警告信息"""
            self.monitor.log(message)
            if isinstance(message, str):
                txt = message.strip()
                if txt.startswith("✗") or txt.startswith("⚠") or ("失败" in txt):
                    last_issue_container[0] = txt

        # 单步执行模式：在真正执行前输出一帧“当前可见节点ID”调试图，便于对齐与核对 node_id 映射
        if isinstance(self.steps, list) and len(self.steps) == 1:
            debug_capture = getattr(self.executor, "debug_capture_visible_node_ids", None)
            if callable(debug_capture):
                debug_capture(
                    self.graph_model,
                    log_callback=getattr(self.monitor, "log", None),
                    visual_callback=self.monitor.update_visual,
                )

        # 执行步骤
        success = self.executor.execute_step(
            step_info,
            self.graph_model,
            log_callback=log_with_capture,
            pause_hook=self.monitor.wait_if_paused,
            allow_continue=self.monitor.is_execution_allowed,
            visual_callback=self.monitor.update_visual,
        )
        
        return success, last_issue_container[0]

    def _update_fast_chain_scope(self, step_type: Any) -> None:
        if step_type:
            setter = getattr(self.executor, "set_fast_chain_step_type", None)
            if callable(setter):
                setter(str(step_type))
            return
        resetter = getattr(self.executor, "reset_fast_chain_step_type", None)
        if callable(resetter):
            resetter()
            return
        setter = getattr(self.executor, "set_fast_chain_step_type", None)
        if callable(setter):
            setter("")

    def _check_zero_nodes_guard(
        self,
        step_index: int,
        step_todo: Any,
        step_info: dict,
    ) -> tuple[bool, Optional[str]]:
        """
        零节点识别守卫：
        - 仅在执行线程上下文中生效；
        - 若当前不是“步骤列表中的首个创建类步骤”，且窗口截图中节点检测结果为 0，
          则视为环境异常（未打开正确节点图 / 视口被遮挡），直接终止执行。

        Returns:
            (ok, reason)
            - ok: 是否允许在当前执行循环中继续处理这一 Todo 步骤
            - reason: 若不允许，给出人类可读的失败原因
        """
        # 若图模型本身无节点，则保持兼容旧行为，不做额外限制
        nodes_attr = getattr(self.graph_model, "nodes", None)
        if not isinstance(nodes_attr, dict) or len(nodes_attr) == 0:
            return True, None

        step_type = step_info.get("type")
        is_create_step = step_type in ("graph_create_node", "graph_create_and_connect")
        # 仅当存在创建类步骤时才计算“首个创建步骤索引”
        first_create_index = self._first_create_step_index
        is_first_create_step = (
            is_create_step
            and isinstance(first_create_index, int)
            and int(step_index) == int(first_create_index)
        )
        # 规则豁免：首个创建步骤允许在空画布/无节点检测结果下继续执行
        if is_first_create_step:
            return True, None

        # 使用执行器的可见节点识别结果统计“当前画面中模型节点的可见数量”，
        # 并在执行线程内部通过“单步缓存”复用同一执行步内的可见性映射，
        # 避免零节点守卫与后续跳过检查在 UI 线程层面对同一帧画面重复构建 visible_map。
        try:
            visible_map = self._get_or_compute_step_visible_map()
        except Exception as exc:  # 防御性：视觉识别链路异常也视为致命错误
            return (
                False,
                f"当前页面节点识别失败：{exc}，请检查沙箱窗口与节点图状态",
            )

        visible_count = 0
        if isinstance(visible_map, dict):
            for info in visible_map.values():
                if isinstance(info, dict) and bool(info.get("visible")):
                    visible_count += 1
        if visible_count == 0:
            title = getattr(step_todo, "title", "") or ""
            return (
                False,
                f"当前页面未识别到任何节点（检测到 0 个可见节点），无法继续执行步骤「{title}」。"
                "请确认沙箱编辑器窗口处于前台，并且已打开对应的节点图。",
            )

        return True, None

    def _get_or_compute_step_visible_map(self) -> Dict[str, Dict[str, Any]]:
        """
        在线程内部统一获取当前执行步使用的可见节点映射。

        设计要点：
        - 若本步已计算过可见节点映射，则直接复用缓存；
        - 若尚未计算，则委托执行器的 recognize_visible_nodes 完成识别；
        - 映射结构与含义完全由自动化核心定义，此处仅负责在同一步内复用结果。
        """
        if self._step_visible_map_cache is not None:
            return self._step_visible_map_cache
        visible_map = self.executor.recognize_visible_nodes(self.graph_model)
        if isinstance(visible_map, dict):
            self._step_visible_map_cache = visible_map
        else:
            self._step_visible_map_cache = {}
        return self._step_visible_map_cache

