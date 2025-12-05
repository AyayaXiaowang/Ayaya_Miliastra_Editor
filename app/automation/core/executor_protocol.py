# -*- coding: utf-8 -*-
"""
EditorExecutor 协议定义

定义自动化执行器的显式接口契约，避免跨模块"鸭子类型"隐式依赖。
所有依赖executor的模块应仅依赖此协议，而非具体实现类。

设计原则：
- 最小化接口：仅暴露跨模块调用的必要方法
- 类型安全：为所有参数和返回值提供完整类型注解
- 可测试性：支持通过 Protocol 创建轻量 mock 实现
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Optional, Tuple, Dict, Any, Callable, List
from pathlib import Path
from PIL import Image

from engine.graph.models.graph_model import GraphModel, NodeModel


@dataclass
class AutomationStepContext:
    """
    通用自动化步骤上下文：打包日志/可视化回调与暂停/终止钩子。

    设计目的：
    - 缩短高频“自动化步骤函数”的参数列表，避免在多个位置重复书写
      (log_callback, visual_callback, pause_hook, allow_continue) 组合；
    - 让调用方在构造一次上下文后在同一执行步骤内复用，减少参数顺序
      或默认值不一致导致的错误。
    """

    log_callback: Optional[Callable[[str], None]] = None
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None
    pause_hook: Optional[Callable[[], None]] = None
    allow_continue: Optional[Callable[[], bool]] = None


class EditorExecutorProtocol(Protocol):
    """编辑器执行器协议：定义跨模块依赖的最小接口集"""
    
    # ========== 基础属性 ==========
    workspace_path: Path
    window_title: str
    
    # 坐标映射状态
    scale_ratio: Optional[float]
    origin_node_pos: Optional[Tuple[float, float]]
    drag_distance_per_pixel: Optional[float]
    
    # 模板路径
    search_bar_template_path: Path
    search_bar_template_path2: Path
    node_settings_template_path: Path
    node_warning_template_path: Path
    node_add_template_path: Path
    node_add_multi_template_path: Path
    node_signal_template_path: Path
    
    # 功能开关
    fast_mapping_mode: bool
    fast_create_mode: bool
    skip_color_snap_if_allowed: bool
    zoom_50_confirmed: bool
    fast_chain_mode: bool
    
    # 状态信息
    _last_context_click_editor_pos: Optional[Tuple[int, int]]
    
    # ========== 核心方法：日志与可视化 ==========
    
    def _log(
        self,
        message: str,
        log_callback: Optional[Callable[[str], None]] = None
    ) -> None:
        """统一日志输出：控制台 + 回调"""
        ...
    
    def _emit_visual(
        self,
        screenshot: Image.Image,
        overlays: Optional[dict],
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]]
    ) -> None:
        """统一可视化输出：推送截图与叠加层到监控面板"""
        ...

    def log(
        self,
        message: str,
        log_callback: Optional[Callable[[str], None]] = None
    ) -> None:
        """
        公开日志输出接口：跨模块调用推荐使用本方法，而非直接访问 `_log`。

        约定：
        - 默认同时输出到控制台与可选的 `log_callback`；
        - 语义应与 `_log` 保持一致。
        """
        ...

    def emit_visual(
        self,
        screenshot: Image.Image,
        overlays: Optional[dict],
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]]
    ) -> None:
        """
        公开可视化输出接口：跨模块调用推荐使用本方法，而非直接访问 `_emit_visual`。

        约定：
        - `overlays` 结构与 UI 层保持一致，例如 {'rects': [...], 'circles': [...]}；
        - 语义应与 `_emit_visual` 保持一致。
        """
        ...
    
    # ========== 节点与端口查询 ==========
    
    def _get_node_def_for_model(self, node: NodeModel) -> Any:
        """根据 NodeModel 获取节点定义（含复合节点支持），找不到返回 None"""
        ...
    
    def _extract_chinese(self, text: str) -> str:
        """提取文本中的中文字符"""
        ...
    
    def _find_best_node_bbox(
        self,
        screenshot: Image.Image,
        title_cn: str,
        program_pos: Tuple[float, float],
        debug: Optional[Dict[str, Any]] = None,
        detected_nodes: Optional[list] = None,
    ) -> Tuple[int, int, int, int]:
        """在截图中查找最佳匹配的节点边界框（基于中文名和程序坐标）
        
        Returns:
            (x, y, w, h) 窗口内坐标，未找到返回 (0, 0, 0, 0)
        """
        ...

    def get_node_def_for_model(self, node: NodeModel) -> Any:
        """
        公开节点定义查询接口。

        约定：
        - 语义与 `_get_node_def_for_model` 一致，支持复合节点与作用域变体；
        - 找不到返回 None，而不是抛出异常。
        """
        ...

    def extract_chinese(self, text: str) -> str:
        """
        公开中文提取接口。

        约定：
        - 仅保留中文字符与必要的分隔符，供标题归一化与匹配使用；
        - 语义应与 `_extract_chinese` 保持一致。
        """
        ...

    def find_best_node_bbox(
        self,
        screenshot: Image.Image,
        title_cn: str,
        program_pos: Tuple[float, float],
        debug: Optional[Dict[str, Any]] = None,
        detected_nodes: Optional[list] = None,
    ) -> Tuple[int, int, int, int]:
        """
        公开节点 bbox 查找接口。

        约定：
        - 语义与 `_find_best_node_bbox` 一致，用于在截图中基于标题与程序坐标查找节点位置；
        - 未找到时返回 `(0, 0, 0, 0)`，调用方据此判断失败。
        """
        ...

    def poll_node_candidates(
        self,
        node_title: str,
        timeout_seconds: float,
        log_callback: Optional[Callable[[str], None]] = None,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        match_predicate: Optional[Callable[[str, str], bool]] = None,
    ) -> Tuple[Optional[Image.Image], List[Tuple[int, int, int, int, int, int]]]:
        """
        公开节点候选轮询接口。

        约定：
        - 语义与 `_poll_node_candidates` 一致：在给定超时时间内轮询窗口截图并查找指定中文名节点；
        - 返回 `(screenshot, candidates)`，其中 `candidates` 为窗口内相对坐标系下
          `(x, y, w, h, center_x, center_y)` 六元组列表。
        """
        ...

    def recognize_visible_nodes(
        self,
        graph_model: GraphModel,
    ) -> Dict[str, Dict[str, Any]]:
        """识别当前画面中哪些模型节点可见，并返回可见性与屏幕坐标映射"""
        ...
    
    # ========== 输入操作（含暂停/终止钩子） ==========
    
    def _wait_with_hooks(
        self,
        total_seconds: float,
        pause_hook: Optional[Callable[[], None]],
        allow_continue: Optional[Callable[[], bool]],
        interval_seconds: float = 0.1,
        log_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """分段等待，支持暂停/终止钩子
        
        Returns:
            True 表示正常完成等待，False 表示被终止
        """
        ...

    def wait_with_hooks(
        self,
        total_seconds: float,
        pause_hook: Optional[Callable[[], None]],
        allow_continue: Optional[Callable[[], bool]],
        interval_seconds: float = 0.1,
        log_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        公开的分段等待接口，带暂停/终止钩子。

        约定：
        - 语义与 `_wait_with_hooks` 保持一致，跨模块仅依赖本方法。
        """
        ...
    
    def _input_text_with_hooks(
        self,
        text: str,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        log_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """输入文本（通过剪贴板），支持暂停/终止钩子
        
        Returns:
            True 表示成功输入，False 表示被终止
        """
        ...

    def input_text_with_hooks(
        self,
        text: str,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        log_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        公开的文本输入接口，带暂停/终止钩子。

        约定：
        - 语义与 `_input_text_with_hooks` 保持一致，跨模块仅依赖本方法。
        """
        ...
    
    def _right_click_with_hooks(
        self,
        screen_x: int,
        screen_y: int,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        log_callback: Optional[Callable[[str], None]] = None,
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
        *,
        linger_seconds: float = 0.0
    ) -> bool:
        """右键点击（支持颜色吸附），支持暂停/终止钩子
        
        Returns:
            True 表示成功点击，False 表示失败或被终止
        """
        ...

    def right_click_with_hooks(
        self,
        screen_x: int,
        screen_y: int,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        log_callback: Optional[Callable[[str], None]] = None,
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
        *,
        linger_seconds: float = 0.0
    ) -> bool:
        """
        公开的右键点击接口，带暂停/终止钩子。

        约定：
        - 语义与 `_right_click_with_hooks` 保持一致，跨模块仅依赖本方法。
        """
        ...
    
    # ========== 截图与可视化构建 ==========
    
    def capture_and_emit(
        self,
        label: str = "",
        overlays_builder: Optional[Callable[[Image.Image], Optional[dict]]] = None,
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None
    ) -> Image.Image:
        """一次性完成：窗口截图 → 叠加区域 → 推送到监控
        
        Args:
            label: 区域标签后缀
            overlays_builder: 可选的叠加层构建器，接收截图返回 overlays dict
            visual_callback: 可视化回调
        
        Returns:
            截图对象
        """
        ...

    # ========== 步骤执行入口 ==========

    def execute_step(
        self,
        todo_item: Dict[str, Any],
        graph_model: GraphModel,
        log_callback: Optional[Callable[[str], None]] = None,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
    ) -> bool:
        """执行单个节点图 Todo 步骤"""
        ...

    # ========== 执行线程可注入的上下文字段（仅作类型约束） ==========

    _current_step_index: int
    _node_first_create_step_index: Dict[str, int]
    _single_step_target_todo_id: str

    # ========== 上下文信息辅助 ==========

    def get_last_context_click_editor_pos(self) -> Optional[Tuple[int, int]]:
        """
        获取最近一次用于弹出上下文菜单的编辑器坐标。

        Returns:
            (x, y) 编辑器坐标；若尚未记录则返回 None。
        """
        ...

    def set_last_context_click_editor_pos(self, editor_x: int, editor_y: int) -> None:
        """
        更新最近一次用于弹出上下文菜单的编辑器坐标。

        约定：
        - 实现方通常会将该信息存入内部字段（例如 `_last_context_click_editor_pos`）；
        - 跨模块应仅通过本方法更新，而不是直接写入私有字段。
        """
        ...


class NodeLibraryProvider(Protocol):
    """节点库提供者协议：隔离节点定义查询逻辑"""
    
    def get_node_def_for_model(self, node: NodeModel) -> Any:
        """根据 NodeModel 获取节点定义"""
        ...


class CoordinateMapper(Protocol):
    """坐标映射器协议：隔离坐标转换逻辑"""
    
    scale_ratio: Optional[float]
    origin_node_pos: Optional[Tuple[float, float]]
    
    def convert_program_to_editor_coords(
        self,
        program_x: float,
        program_y: float
    ) -> Tuple[int, int]:
        """程序坐标 → 编辑器坐标"""
        ...
    
    def convert_editor_to_screen_coords(
        self,
        editor_x: int,
        editor_y: int
    ) -> Tuple[int, int]:
        """编辑器坐标 → 屏幕坐标"""
        ...


class ViewportController(Protocol):
    """
    视口控制器协议：统一对外暴露与“编辑器视口与坐标系”相关的能力。

    约定：
    - 任何跨模块希望执行“将某个程序坐标点滚动到安全视口范围内”的操作，
      必须通过本协议，而不是直接访问具体执行器实现上的私有方法
      （例如 `executor._ensure_program_point_visible`）。
    - 视口查询与坐标换算能力也通过本协议暴露，避免上层依赖具体实现类。
    """

    # ========== 视口查询 ==========

    def get_program_viewport_rect(self) -> Tuple[float, float, float, float]:
        """
        获取当前编辑器视口在程序坐标系下的矩形投影。

        Returns:
            (left, top, width, height)
        """
        ...

    # ========== 坐标转换 ==========

    def convert_program_to_editor_coords(
        self,
        program_x: float,
        program_y: float,
    ) -> Tuple[int, int]:
        """程序坐标 → 编辑器窗口坐标"""
        ...

    def convert_editor_to_screen_coords(
        self,
        editor_x: int,
        editor_y: int,
    ) -> Tuple[int, int]:
        """编辑器窗口坐标 → 屏幕绝对坐标"""
        ...

    # ========== 视口对齐 ==========

    def ensure_program_point_visible(
        self,
        program_x: float,
        program_y: float,
        margin_ratio: float = 0.10,
        max_steps: int = 8,
        pan_step_pixels: int = 400,
        log_callback: Optional[Callable[[str], None]] = None,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
        graph_model: Optional[GraphModel] = None,
        force_pan_if_inside_margin: bool = False,
    ) -> None:
        """
        确保指定程序坐标点位于安全视口范围内（通常通过拖拽画布实现）。

        语义与 `EditorExecutor._ensure_program_point_visible` 保持一致：
        - 若点在安全边距之外，会按最多 `max_steps` 迭代平移视口；
        - `margin_ratio` 控制安全区大小，`pan_step_pixels` 控制单步拖拽幅度；
        - `graph_model` 可选，用于在对齐过程中复用可见性与调试信息；
        - `force_pan_if_inside_margin=True` 时，即便点已在安全区内也会做一次轻微平移，
          便于“拖拽测试”等场景直观看到视口移动。
        """
        ...


class EditorExecutorWithViewport(EditorExecutorProtocol, ViewportController, Protocol):
    """
    组合协议：既满足 EditorExecutorProtocol 的执行/查询能力，
    又实现 ViewportController 约定的视口与坐标系能力。

    上层若既需要执行节点图，又要操纵或查询视口，推荐依赖此协议而非具体实现类。
    """


class InputController(Protocol):
    """输入控制器协议：隔离键鼠输入逻辑"""
    
    def input_text_with_hooks(
        self,
        text: str,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        log_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """输入文本"""
        ...
    
    def right_click_with_hooks(
        self,
        screen_x: int,
        screen_y: int,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        log_callback: Optional[Callable[[str], None]] = None,
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
        *,
        linger_seconds: float = 0.0
    ) -> bool:
        """右键点击"""
        ...
    
    def wait_with_hooks(
        self,
        total_seconds: float,
        pause_hook: Optional[Callable[[], None]],
        allow_continue: Optional[Callable[[], bool]],
        interval_seconds: float = 0.1,
        log_callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """分段等待"""
        ...


class VisualReporter(Protocol):
    """可视化报告器协议：隔离可视化输出逻辑"""
    
    def log(
        self,
        message: str,
        log_callback: Optional[Callable[[str], None]] = None
    ) -> None:
        """输出日志"""
        ...
    
    def emit_visual(
        self,
        screenshot: Image.Image,
        overlays: Optional[dict],
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]]
    ) -> None:
        """推送可视化"""
        ...
    
    def capture_and_emit(
        self,
        label: str = "",
        overlays_builder: Optional[Callable[[Image.Image], Optional[dict]]] = None,
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None
    ) -> Image.Image:
        """截图并推送"""
        ...

