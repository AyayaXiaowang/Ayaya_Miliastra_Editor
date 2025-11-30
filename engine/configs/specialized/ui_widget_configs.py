"""
界面控件配置系统
基于知识库：概念介绍/资产/界面控件
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum


# ============================================================================
# 界面控件基础定义
# ============================================================================

class WidgetType(str, Enum):
    """界面控件类型"""
    INTERACTION_BUTTON = "交互按钮"
    CARD_SELECTOR = "卡牌选择器"
    POPUP = "弹窗"
    TEXT_BOX = "文本框"
    SCOREBOARD = "计分板"
    TIMER = "计时器"
    PROGRESS_BAR = "进度条"


class WidgetDisplayMode(str, Enum):
    """显示模式"""
    ALWAYS = "始终显示"
    TRIGGER = "触发显示"
    CONDITION = "条件显示"


class AnchorPoint(str, Enum):
    """锚点位置"""
    TOP_LEFT = "左上"
    TOP_CENTER = "上中"
    TOP_RIGHT = "右上"
    MIDDLE_LEFT = "中左"
    CENTER = "中心"
    MIDDLE_RIGHT = "中右"
    BOTTOM_LEFT = "左下"
    BOTTOM_CENTER = "下中"
    BOTTOM_RIGHT = "右下"


# ============================================================================
# 交互按钮界面控件
# ============================================================================

@dataclass
class InteractionButtonConfig:
    """交互按钮配置"""
    button_text: str
    button_icon: Optional[str] = None
    position: Tuple[float, float] = (0.0, 0.0)
    anchor: AnchorPoint = AnchorPoint.CENTER
    enabled: bool = True
    visible: bool = True
    
    # 交互设置
    on_click_event: Optional[str] = None  # 点击时触发的事件
    cooldown: float = 0.0  # 冷却时间(s)
    
    doc_reference: str = "交互按钮界面控件.md"


# ============================================================================
# 卡牌选择器界面控件
# ============================================================================

class CardSelectionMode(str, Enum):
    """卡牌选择模式"""
    SINGLE = "单选"
    MULTIPLE = "多选"


@dataclass
class CardConfig:
    """卡牌配置"""
    card_id: int
    card_image: str
    card_title: str
    card_description: str
    custom_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CardSelectorConfig:
    """卡牌选择器配置"""
    selector_title: str
    cards: List[CardConfig] = field(default_factory=list)
    selection_mode: CardSelectionMode = CardSelectionMode.SINGLE
    max_selections: int = 1
    confirm_button_text: str = "确认"
    cancel_button_text: str = "取消"
    
    # 显示设置
    position: Tuple[float, float] = (0.0, 0.0)
    size: Tuple[float, float] = (800.0, 600.0)
    
    doc_reference: str = "卡牌选择器界面控件.md"


# ============================================================================
# 弹窗界面控件
# ============================================================================

class PopupType(str, Enum):
    """弹窗类型"""
    INFO = "信息提示"
    WARNING = "警告"
    ERROR = "错误"
    CONFIRM = "确认对话框"
    CUSTOM = "自定义"


@dataclass
class PopupButtonConfig:
    """弹窗按钮配置"""
    button_text: str
    on_click_action: str  # 点击时执行的动作


@dataclass
class PopupConfig:
    """弹窗配置"""
    popup_type: PopupType
    title: str
    message: str
    buttons: List[PopupButtonConfig] = field(default_factory=list)
    
    # 显示设置
    auto_close: bool = False
    auto_close_delay: float = 3.0  # 自动关闭延时(s)
    modal: bool = True  # 模态窗口
    
    doc_reference: str = "弹窗界面控件.md"


# ============================================================================
# 文本框界面控件
# ============================================================================

class TextBoxType(str, Enum):
    """文本框类型"""
    SINGLE_LINE = "单行"
    MULTI_LINE = "多行"
    PASSWORD = "密码"
    NUMBER = "数字"


@dataclass
class TextBoxConfig:
    """文本框配置"""
    text_box_type: TextBoxType
    placeholder: str = ""
    default_value: str = ""
    max_length: int = 100
    
    # 验证设置
    required: bool = False
    validation_pattern: Optional[str] = None  # 正则表达式
    
    # 显示设置
    position: Tuple[float, float] = (0.0, 0.0)
    size: Tuple[float, float] = (200.0, 40.0)
    
    doc_reference: str = "文本框界面控件.md"


# ============================================================================
# 计分板界面控件
# ============================================================================

class ScoreboardSortMode(str, Enum):
    """计分板排序模式"""
    DESCENDING = "降序"
    ASCENDING = "升序"
    NONE = "不排序"


@dataclass
class ScoreboardColumn:
    """计分板列配置"""
    column_name: str
    column_width: float
    data_type: str = "字符串"  # 字符串/整数/浮点数


@dataclass
class ScoreboardConfig:
    """计分板配置"""
    scoreboard_title: str
    columns: List[ScoreboardColumn] = field(default_factory=list)
    sort_mode: ScoreboardSortMode = ScoreboardSortMode.DESCENDING
    sort_column_index: int = 0
    max_rows: int = 10
    
    # 显示设置
    position: Tuple[float, float] = (0.0, 0.0)
    size: Tuple[float, float] = (600.0, 400.0)
    visible: bool = True
    
    doc_reference: str = "计分板界面控件.md"


# ============================================================================
# 计时器界面控件
# ============================================================================

class TimerMode(str, Enum):
    """计时器模式"""
    COUNT_DOWN = "倒计时"
    COUNT_UP = "正计时"


class TimerDisplayFormat(str, Enum):
    """计时器显示格式"""
    HMS = "时:分:秒"
    MS = "分:秒"
    S = "秒"


@dataclass
class TimerConfig:
    """计时器配置"""
    timer_mode: TimerMode
    initial_value: float = 0.0  # 初始值(秒)
    display_format: TimerDisplayFormat = TimerDisplayFormat.MS
    
    # 倒计时特定
    countdown_target: float = 0.0  # 目标值(秒)
    on_complete_event: Optional[str] = None  # 完成时触发的事件
    
    # 显示设置
    position: Tuple[float, float] = (0.0, 0.0)
    font_size: int = 24
    color: str = "#FFFFFF"
    
    doc_reference: str = "计时器界面控件.md"


# ============================================================================
# 进度条界面控件
# ============================================================================

class ProgressBarOrientation(str, Enum):
    """进度条方向"""
    HORIZONTAL = "横向"
    VERTICAL = "纵向"


class ProgressBarFillMode(str, Enum):
    """进度条填充模式"""
    LEFT_TO_RIGHT = "从左到右"
    RIGHT_TO_LEFT = "从右到左"
    BOTTOM_TO_TOP = "从下到上"
    TOP_TO_BOTTOM = "从上到下"


@dataclass
class ProgressBarConfig:
    """进度条配置"""
    orientation: ProgressBarOrientation
    fill_mode: ProgressBarFillMode
    min_value: float = 0.0
    max_value: float = 100.0
    current_value: float = 0.0
    
    # 外观设置
    position: Tuple[float, float] = (0.0, 0.0)
    size: Tuple[float, float] = (200.0, 20.0)
    background_color: str = "#808080"
    fill_color: str = "#00FF00"
    show_text: bool = True
    text_format: str = "{value}/{max}"  # 显示格式
    
    doc_reference: str = "进度条界面控件.md"


# ============================================================================
# 界面控件组/布局系统
# 注意：此处定义的是简化的运行时配置版本，用于序列化/反序列化
# 完整的编辑器数据模型请参考：core.configs.components.ui_control_group_model
# 高级概念配置请参考：core.configs.specialized.additional_advanced_configs.UIWidgetGroupConfig
# ============================================================================

@dataclass
class SimpleWidgetGroupConfig:
    """界面控件组配置（简化版，用于基础序列化）
    注意：这是简化的运行时配置，与 UIControlGroupTemplate（编辑器模型）和 UIWidgetGroupConfig（高级概念）不同
    原名：WidgetGroupConfig
    """
    group_name: str
    group_id: int
    widgets: List[Dict[str, Any]] = field(default_factory=list)
    enabled: bool = True
    visible: bool = True
    
    doc_reference: str = "界面控件组.md"


@dataclass
class SimpleUILayoutConfig:
    """界面布局配置（简化版，用于基础序列化）
    注意：这是简化的运行时配置，与 UILayout（编辑器模型）和 UIWidgetGroupConfig（高级概念）不同。
    """
    layout_name: str
    layout_id: int
    widget_groups: List[int] = field(default_factory=list)  # 包含的控件组ID
    
    doc_reference: str = "界面布局.md"

# ============================================================================
# 验证函数
# ============================================================================

def validate_widget_position(position: Tuple[float, float], anchor: AnchorPoint) -> List[str]:
    """验证控件位置"""
    errors = []
    
    x, y = position
    if x < 0 or x > 1920 or y < 0 or y > 1080:  # 假设最大分辨率
        errors.append(
            f"[控件位置警告] 控件位置可能超出屏幕范围\n"
            f"位置：({x}, {y})\n"
            f"锚点：{anchor.value}"
        )
    
    return errors


def validate_scoreboard_config(config: ScoreboardConfig) -> List[str]:
    """验证计分板配置"""
    errors = []
    
    if not config.columns:
        errors.append("[计分板错误] 计分板至少需要一列")
    
    if config.sort_column_index >= len(config.columns):
        errors.append(
            f"[计分板错误] 排序列索引超出范围\n"
            f"排序列：{config.sort_column_index}\n"
            f"总列数：{len(config.columns)}"
        )
    
    return errors


if __name__ == "__main__":
    print("=== 界面控件配置系统测试 ===\n")
    
    # 测试交互按钮
    print("1. 交互按钮：")
    button = InteractionButtonConfig(
        button_text="开始游戏",
        position=(960.0, 540.0),
        anchor=AnchorPoint.CENTER,
        on_click_event="game_start"
    )
    print(f"   按钮文本：{button.button_text}")
    print(f"   位置：{button.position}")
    print(f"   锚点：{button.anchor.value}")
    
    # 测试卡牌选择器
    print("\n2. 卡牌选择器：")
    card_selector = CardSelectorConfig(
        selector_title="选择你的角色",
        cards=[
            CardConfig(card_id=1, card_image="warrior.png", card_title="战士", card_description="近战强者"),
            CardConfig(card_id=2, card_image="mage.png", card_title="法师", card_description="远程魔法")
        ],
        selection_mode=CardSelectionMode.SINGLE,
        size=(800.0, 600.0)
    )
    print(f"   标题：{card_selector.selector_title}")
    print(f"   卡牌数量：{len(card_selector.cards)}")
    print(f"   选择模式：{card_selector.selection_mode.value}")
    
    # 测试计分板
    print("\n3. 计分板：")
    scoreboard = ScoreboardConfig(
        scoreboard_title="玩家排行榜",
        columns=[
            ScoreboardColumn(column_name="玩家", column_width=150.0),
            ScoreboardColumn(column_name="分数", column_width=100.0, data_type="整数"),
            ScoreboardColumn(column_name="击杀", column_width=80.0, data_type="整数")
        ],
        sort_mode=ScoreboardSortMode.DESCENDING,
        sort_column_index=1,
        max_rows=10
    )
    print(f"   标题：{scoreboard.scoreboard_title}")
    print(f"   列数：{len(scoreboard.columns)}")
    print(f"   排序模式：{scoreboard.sort_mode.value}")
    
    # 测试进度条
    print("\n4. 进度条：")
    progress_bar = ProgressBarConfig(
        orientation=ProgressBarOrientation.HORIZONTAL,
        fill_mode=ProgressBarFillMode.LEFT_TO_RIGHT,
        max_value=100.0,
        current_value=75.0,
        fill_color="#00FF00"
    )
    print(f"   方向：{progress_bar.orientation.value}")
    print(f"   当前值：{progress_bar.current_value}/{progress_bar.max_value}")
    
    print("\n✅ 界面控件配置系统测试完成")

