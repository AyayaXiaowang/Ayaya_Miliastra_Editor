# -*- coding: utf-8 -*-
"""
自动化 UI/交互层通用常量。

集中管理：
- 节点视图几何尺寸（用于屏幕/程序坐标换算、缩放估计）
- 视口平移参数（安全边距比例、单步拖拽像素）
- 节点拖拽与可见性阈值
- 常用等待时间（右键弹窗、输入稳定、缩放稳定等）

仅存放“跨多个模块共享”的固定数值，避免在多文件中硬编码 magic number。
"""

from __future__ import annotations

# =========================
# 节点视图几何尺寸（像素）
# =========================

NODE_VIEW_WIDTH_PX: float = 200.0
NODE_VIEW_HEIGHT_PX: float = 100.0

# =========================
# 视口安全区与平移参数
# =========================

# 程序视口在编辑器窗口中的安全边距比例（左右/上下各保留 10%）
VIEW_SAFE_MARGIN_RATIO_DEFAULT: float = 0.10

# 视口平移最大迭代步数（用于 ensure_program_point_visible）
VIEW_MAX_PAN_STEPS_DEFAULT: int = 8

# 常规视口平移单步拖拽像素
VIEW_PAN_STEP_PX_DEFAULT: int = 400

# 基于“创建锚点”等场景的视口平移步长（略大一些，加快对齐）
VIEW_PAN_STEP_PX_CREATION_ANCHOR: int = 420

# =========================
# 视口对齐鲁棒性保护
# =========================

# 当连续多次拖拽后，画面（ROI）仍几乎无变化时，通常意味着：
# - 拖拽起点落在节点/端口等区域导致“右键拖拽不生效”
# - 编辑器窗口失焦、被遮挡、或右键拖拽行为被 UI 拦截
# 这种情况下继续按“预期位移”更新坐标映射会快速漂移，因此默认触发中止保护。
VIEW_PAN_NO_VISUAL_CHANGE_ABORT_CONSECUTIVE_DEFAULT: int = 2

# 判定“画面无明显变化”的平均像素差阈值（越小越严格）。
# 该值用于多点采样的 mean_abs_diff（0 表示完全一致）。
VIEW_PAN_NO_VISUAL_CHANGE_MEAN_DIFF_THRESHOLD_DEFAULT: float = 1.0

# =========================
# 节点拖拽与位置更新阈值
# =========================

# 仅当屏幕空间偏移超过该像素阈值时，才认为发生了有效拖拽
NODE_DRAG_UPDATE_MIN_SCREEN_PX: float = 16.0

# 仅当程序坐标系下的偏移超过该阈值时，才回写 NodeModel.pos
NODE_DRAG_UPDATE_MIN_PROGRAM_UNITS: float = 8.0

# =========================
# 创建/搜索弹窗相关等待时间（秒）
# =========================

# 右键呼出上下文菜单后，等待弹窗出现的时间
CONTEXT_MENU_APPEAR_WAIT_SECONDS: float = 0.5

# 在候选列表中点击目标项后，为界面稳定预留的等待时间
CANDIDATE_LIST_POST_CLICK_WAIT_SECONDS: float = 0.3

# 节点搜索框输入完成后，为候选列表稳定预留的等待时间
POST_INPUT_STABILIZE_SECONDS_DEFAULT: float = 0.8

# =========================
# 坐标校准与缩放相关等待时间（秒）
# =========================

# 坐标校准流程中，右键呼出锚点菜单后的等待时间
ANCHOR_CREATION_FIRST_WAIT_SECONDS: float = 0.5

# 选择锚点节点候选后，为界面稳定预留的等待时间
ANCHOR_CREATION_POST_SELECT_WAIT_SECONDS: float = 0.5

# 失效 OCR/识别缓存后，等待引擎就绪的时间
OCR_CACHE_FLUSH_WAIT_SECONDS: float = 0.3

# 修改缩放（点击缩放数字或选择 50%）后，为画面稳定预留的时间
ZOOM_ACTION_WAIT_SECONDS: float = 0.5

# =========================
# 可见性/距离阈值（像素）
# =========================

# 判定“节点已经在预期位置附近”的距离阈值（左上角为锚点）
NODE_VISIBILITY_ACCEPT_DISTANCE_PX: float = 30.0


