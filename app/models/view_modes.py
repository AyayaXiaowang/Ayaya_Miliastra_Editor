"""视图模式枚举 - 统一管理主窗口的模式切换

此模块定义了主窗口的所有视图模式，消除硬编码的索引值，提升可维护性。

使用方法：
    from app.models.view_modes import ViewMode, VIEW_MODE_CONFIG
    
    # 获取模式索引
    index = ViewMode.TEMPLATE.value
    
    # 获取模式配置
    config = VIEW_MODE_CONFIG[ViewMode.TEMPLATE]
    print(config.display_name)  # "元件库"
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Tuple, Dict


class ViewMode(Enum):
    """视图模式枚举"""
    TEMPLATE = 0           # 元件库
    PLACEMENT = 1          # 实体摆放
    COMBAT = 2             # 战斗预设
    MANAGEMENT = 3         # 管理面板
    TODO = 4               # 任务清单
    COMPOSITE = 5          # 复合节点
    GRAPH_LIBRARY = 6      # 节点图库
    VALIDATION = 7         # 验证面板
    GRAPH_EDITOR = 8       # 节点图编辑器
    PACKAGES = 9           # 项目存档页面
    
    @classmethod
    def from_string(cls, mode_str: str) -> Optional['ViewMode']:
        """从字符串获取模式枚举
        
        Args:
            mode_str: 模式字符串（如 "template", "placement" 等）
        
        Returns:
            对应的ViewMode枚举，如果不存在返回None
        """
        return _STRING_TO_VIEW_MODE.get(mode_str)
    
    @classmethod
    def from_index(cls, index: int) -> Optional['ViewMode']:
        """从索引获取模式枚举
        
        Args:
            index: 模式索引（对应枚举的value）
        
        Returns:
            对应的ViewMode枚举，如果不存在返回None
        """
        return _INDEX_TO_VIEW_MODE.get(index)
    
    def to_string(self) -> str:
        """转换为字符串标识
        
        Returns:
            模式的字符串标识
        """
        return _VIEW_MODE_TO_STRING.get(self, "")


_VIEW_MODE_TO_STRING = {
    ViewMode.TEMPLATE: "template",
    ViewMode.PLACEMENT: "placement",
    ViewMode.COMBAT: "combat",
    ViewMode.MANAGEMENT: "management",
    ViewMode.TODO: "todo",
    ViewMode.COMPOSITE: "composite",
    ViewMode.GRAPH_LIBRARY: "graph_library",
    ViewMode.VALIDATION: "validation",
    ViewMode.GRAPH_EDITOR: "graph_editor",
    ViewMode.PACKAGES: "packages",
}

_STRING_TO_VIEW_MODE = {identifier: mode_enum for mode_enum, identifier in _VIEW_MODE_TO_STRING.items()}
_INDEX_TO_VIEW_MODE = {mode_enum.value: mode_enum for mode_enum in ViewMode}


@dataclass
class ViewModeConfig:
    """视图模式配置"""
    mode: ViewMode
    display_name: str           # 显示名称
    icon: str                   # 图标
    show_property_panel: bool   # 是否显示属性面板
    show_graph_property: bool   # 是否显示图属性面板
    show_composite_panels: bool # 是否显示复合节点相关面板
    show_ui_settings: bool      # 是否显示界面控件设置
    auto_refresh: bool          # 是否自动刷新数据


# 视图模式配置表
VIEW_MODE_CONFIG = {
    ViewMode.TEMPLATE: ViewModeConfig(
        mode=ViewMode.TEMPLATE,
        display_name="元件库",
        icon="📦",
        show_property_panel=True,   # 选中模板时显示
        show_graph_property=False,
        show_composite_panels=False,
        show_ui_settings=False,
        auto_refresh=True,
    ),
    ViewMode.PLACEMENT: ViewModeConfig(
        mode=ViewMode.PLACEMENT,
        display_name="实体摆放",
        icon="🎯",
        show_property_panel=True,   # 选中实例时显示
        show_graph_property=False,
        show_composite_panels=False,
        show_ui_settings=False,
        auto_refresh=True,
    ),
    ViewMode.COMBAT: ViewModeConfig(
        mode=ViewMode.COMBAT,
        display_name="战斗预设",
        icon="⚔️",
        # 战斗预设页面使用专门的“玩家模板详情”面板，不复用模板/实例属性面板
        show_property_panel=False,
        show_graph_property=False,
        show_composite_panels=False,
        show_ui_settings=False,
        auto_refresh=False,
    ),
    ViewMode.MANAGEMENT: ViewModeConfig(
        mode=ViewMode.MANAGEMENT,
        display_name="管理面板",
        icon="🛠️",
        show_property_panel=False,
        show_graph_property=False,
        show_composite_panels=False,
        show_ui_settings=False,      # 界面控件设置由管理页面当前 section 动态控制
        auto_refresh=False,
    ),
    ViewMode.TODO: ViewModeConfig(
        mode=ViewMode.TODO,
        display_name="任务清单",
        icon="📋",
        show_property_panel=False,
        show_graph_property=False,
        show_composite_panels=False,
        show_ui_settings=False,
        auto_refresh=False,
    ),
    ViewMode.COMPOSITE: ViewModeConfig(
        mode=ViewMode.COMPOSITE,
        display_name="复合节点",
        icon="🔗",
        show_property_panel=False,
        show_graph_property=False,
        show_composite_panels=True, # 显示复合节点属性和虚拟引脚
        show_ui_settings=False,
        auto_refresh=False,
    ),
    ViewMode.GRAPH_LIBRARY: ViewModeConfig(
        mode=ViewMode.GRAPH_LIBRARY,
        display_name="节点图库",
        icon="📚",
        show_property_panel=False,
        show_graph_property=True,   # 显示图属性面板
        show_composite_panels=False,
        show_ui_settings=False,
        auto_refresh=True,
    ),
    ViewMode.VALIDATION: ViewModeConfig(
        mode=ViewMode.VALIDATION,
        display_name="验证面板",
        icon="✓",
        show_property_panel=False,
        show_graph_property=False,
        show_composite_panels=False,
        show_ui_settings=False,
        auto_refresh=False,
    ),
    ViewMode.GRAPH_EDITOR: ViewModeConfig(
        mode=ViewMode.GRAPH_EDITOR,
        display_name="节点图编辑",
        icon="🎨",
        show_property_panel=False,
        show_graph_property=False,
        show_composite_panels=False,
        show_ui_settings=False,
        auto_refresh=False,
    ),
    ViewMode.PACKAGES: ViewModeConfig(
        mode=ViewMode.PACKAGES,
        display_name="项目存档",
        icon="🗂️",
        show_property_panel=False,
        show_graph_property=False,
        show_composite_panels=False,
        show_ui_settings=False,
        auto_refresh=True,
    ),
}

    # 右侧面板标签配置（集中声明各模式应显示哪些标签）
    # 可选值：
    #   - "graph_property"        → 节点图属性面板
    #   - "composite_property"    → 复合节点属性面板
    #   - "composite_pins"        → 复合节点虚拟引脚面板
    #   - "ui_settings"           → 界面控件设置面板
    #   - "execution_monitor"     → 执行监控面板（节点图执行专用，由 UI 按当前 Todo 动态插入，而非固定挂在任意模式）
    #   - "player_editor"         → 战斗预设玩家模板详情面板
    #   - "player_class_editor"   → 战斗预设职业详情面板
    #   - "skill_editor"          → 战斗预设技能详情面板
    #   - "item_editor"           → 战斗预设道具详情面板
    #   - "validation_detail"     → 验证问题详情面板（验证模式下用于在右侧展示选中问题的详细信息）
    # 说明：
    #   - 基础“属性”面板（模板/实例）按选择态由 UI 层自行控制，此处不强制；
    #   - 战斗预设模式下的“玩家模板 / 职业 / 技能 / 道具”详情标签同样由选中状态动态控制，
    #     因此在集中配置中不预先挂载，避免在仅选中玩家模板时仍显示空的“职业/技能”页签。
RIGHT_PANEL_TABS: Dict[ViewMode, Tuple[str, ...]] = {
    ViewMode.TEMPLATE: tuple(),
    ViewMode.PLACEMENT: tuple(),
    # 战斗预设模式下右侧标签全部采用按选中对象动态插入的策略
    ViewMode.COMBAT: tuple(),
    ViewMode.MANAGEMENT: tuple(),
    # 任务清单模式下的“执行监控”标签由 UI 根据当前选中的 Todo 类型按需插入
    ViewMode.TODO: tuple(),
    ViewMode.COMPOSITE: ("composite_pins", "composite_property"),
    ViewMode.GRAPH_LIBRARY: ("graph_property", "graph_used_definitions"),
    ViewMode.VALIDATION: ("validation_detail",),
    ViewMode.GRAPH_EDITOR: ("graph_property",),
    ViewMode.PACKAGES: tuple(),
}



