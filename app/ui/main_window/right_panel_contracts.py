"""右侧面板“可见性合同（contract）”。

设计目标：
- 将“除了表里的内容都收起来”的规则显式化（表驱动）。
- 支持“允许并存但不强制打开”的语义（keep vs ensure），以便在 TODO 等场景保持既有行为：
  - keep  : 允许保留/不强制收起的 tab（若已存在则保留）
  - ensure: 必须显示的 tab（若不存在则插入）
  - preferred: 优先切换到的 tab（若可见）

注意：contract 只描述“右侧 tab 的显隐/切换”，不负责具体面板的 set_context/clear/reset。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class RightPanelVisibilityContract:
    """右侧 tab 显隐合同。

    - keep_tab_ids: 应保留的 tab_id 集合；apply 时会移除所有不在其中的已可见 tab。
    - ensure_tab_ids: 必须显示的 tab_id 集合（一般是 keep 的子集）。
    - preferred_tab_id: 若该 tab 可见，apply 后会切换到它。
    """

    keep_tab_ids: tuple[str, ...] = ()
    ensure_tab_ids: tuple[str, ...] = ()
    preferred_tab_id: str | None = None

    @classmethod
    def keep_only(
        cls,
        tab_ids: Iterable[str],
        *,
        preferred_tab_id: str | None = None,
        ensure_tab_ids: Iterable[str] | None = None,
    ) -> "RightPanelVisibilityContract":
        keep = tuple(str(tab_id) for tab_id in tab_ids if isinstance(tab_id, str) and tab_id)
        ensure_iterable = ensure_tab_ids if ensure_tab_ids is not None else keep
        ensure = tuple(
            str(tab_id) for tab_id in ensure_iterable if isinstance(tab_id, str) and tab_id
        )
        preferred = str(preferred_tab_id) if isinstance(preferred_tab_id, str) and preferred_tab_id else None
        return cls(keep_tab_ids=keep, ensure_tab_ids=ensure, preferred_tab_id=preferred)


# === 常用合同（供各事件入口复用，避免散落重复的 hide/show 分支） ======================

# 空合同：右侧不保留任何标签（全部收起）
CONTRACT_HIDE_ALL = RightPanelVisibilityContract()

# 通用“属性”面板：强制展示并切换到它
CONTRACT_SHOW_PROPERTY = RightPanelVisibilityContract.keep_only(
    ("property",),
    preferred_tab_id="property",
)

# 管理模式通用“属性”摘要面板：强制展示并切换到它
CONTRACT_SHOW_MANAGEMENT_PROPERTY = RightPanelVisibilityContract.keep_only(
    ("management_property",),
    preferred_tab_id="management_property",
)

# 图属性面板：强制展示并切换到它
CONTRACT_SHOW_GRAPH_PROPERTY = RightPanelVisibilityContract.keep_only(
    ("graph_property",),
    preferred_tab_id="graph_property",
)

# 验证详情面板：强制展示并切换到它
CONTRACT_SHOW_VALIDATION_DETAIL = RightPanelVisibilityContract.keep_only(
    ("validation_detail",),
    preferred_tab_id="validation_detail",
)

# 复合节点：固定双标签（虚拟引脚 + 属性）
CONTRACT_SHOW_COMPOSITE_DUAL = RightPanelVisibilityContract.keep_only(
    ("composite_pins", "composite_property"),
    preferred_tab_id="composite_pins",
)

# TODO：执行监控（允许与 property 并存，但不强制打开 property，避免抢占）
CONTRACT_TODO_SHOW_EXECUTION_MONITOR = RightPanelVisibilityContract(
    keep_tab_ids=("execution_monitor", "property"),
    ensure_tab_ids=("execution_monitor",),
    preferred_tab_id="execution_monitor",
)

# TODO：隐藏执行监控，但允许保留 property（不强制打开）
CONTRACT_TODO_HIDE_EXECUTION_MONITOR_KEEP_PROPERTY = RightPanelVisibilityContract(
    keep_tab_ids=("property",),
    ensure_tab_ids=(),
    preferred_tab_id=None,
)

# PACKAGES/COMBAT：战斗预设详情（互斥：一次只展示一个）
CONTRACT_SHOW_PLAYER_EDITOR = RightPanelVisibilityContract.keep_only(
    ("player_editor",),
    preferred_tab_id="player_editor",
)
CONTRACT_SHOW_PLAYER_CLASS_EDITOR = RightPanelVisibilityContract.keep_only(
    ("player_class_editor",),
    preferred_tab_id="player_class_editor",
)
CONTRACT_SHOW_SKILL_EDITOR = RightPanelVisibilityContract.keep_only(
    ("skill_editor",),
    preferred_tab_id="skill_editor",
)
CONTRACT_SHOW_ITEM_EDITOR = RightPanelVisibilityContract.keep_only(
    ("item_editor",),
    preferred_tab_id="item_editor",
)



