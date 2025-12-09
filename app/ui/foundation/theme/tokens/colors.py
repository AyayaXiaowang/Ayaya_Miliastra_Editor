"""Color tokens for the global UI theme.

默认提供浅色主题配色，并支持在应用启动时切换到深色主题。
"""


class Colors:
    """主题配色（支持浅色/深色，通过 `apply_theme_palette` 选择当前调色板）。"""

    # 主题色（冷静的蓝色系）
    PRIMARY = "#3B82F6"         # 主色：蓝 500
    PRIMARY_DARK = "#1D4ED8"    # 深主色：蓝 700
    PRIMARY_LIGHT = "#BFDBFE"   # 浅主色：蓝 200

    SECONDARY = "#6366F1"       # 次要色：靛蓝 500
    SECONDARY_DARK = "#4F46E5"  # 深次要色：靛蓝 600
    SECONDARY_LIGHT = "#C7D2FE" # 浅次要色：靛蓝 300

    ACCENT = "#F59E0B"          # 强调色：琥珀 500（适量使用）
    ACCENT_LIGHT = "#FCD34D"    # 浅强调色：琥珀 300

    # 背景（浅色 UI，深色画布由 BG_DARK 提供）
    BG_MAIN = "#F5F7FB"         # 应用主背景：带轻微蓝调的灰白
    BG_CARD = "#FFFFFF"         # 卡片背景
    BG_CARD_HOVER = "#F7FAFF"   # 卡片悬停（略带蓝调）
    BG_SELECTED = "#EFF6FF"     # 选中背景（蓝 50）
    BG_SELECTED_HOVER = "#DBEAFE"
    BG_INPUT = "#FFFFFF"
    BG_DISABLED = "#E5E7EB"
    BG_HEADER = "#F9FAFB"
    BG_DARK = "#0F172A"         # 深色画布/标签背景：石板 900

    # 文字
    TEXT_PRIMARY = "#111827"    # 主文本：灰 900
    TEXT_SECONDARY = "#6B7280"  # 次文本：灰 500，更柔和
    TEXT_DISABLED = "#9CA3AF"   # 禁用文本：灰 400
    TEXT_HINT = "#9CA3AF"
    TEXT_PLACEHOLDER = "#9CA3AF"  # 输入占位，与禁用文本一致
    TEXT_ON_PRIMARY = "#FFFFFF"
    TEXT_LINK = "#3B82F6"

    # 边框
    BORDER_LIGHT = "#E5E7EB"    # 灰 200
    BORDER_NORMAL = "#D1D5DB"   # 灰 300
    BORDER_DARK = "#9CA3AF"     # 灰 400
    BORDER_FOCUS = "#3B82F6"    # 主色高亮

    # 分隔线
    DIVIDER = "#E5E7EB"
    DIVIDER_DARK = "#CBD5E1"

    # 状态色
    SUCCESS = "#16A34A"         # 绿 600
    SUCCESS_LIGHT = "#22C55E"   # 绿 500
    SUCCESS_BG = "#DCFCE7"      # 绿 100

    WARNING = "#F97316"         # 橙 500
    WARNING_LIGHT = "#FDBA74"   # 橙 300
    WARNING_BG = "#FFFBEB"      # 橙 50

    ERROR = "#DC2626"           # 红 600
    ERROR_LIGHT = "#F87171"     # 红 400
    ERROR_BG = "#FEF2F2"        # 红 50

    INFO = "#0EA5E9"            # 青 500
    INFO_LIGHT = "#38BDF8"      # 青 400
    INFO_BG = "#E0F2FE"         # 青 100

    # 任务类型（与主题色族保持一致）
    CATEGORY = PRIMARY
    CATEGORY_LIGHT = "#E5E7EB"
    TEMPLATE = SECONDARY
    TEMPLATE_LIGHT = "#EEF2FF"
    INSTANCE = "#F97373"
    INSTANCE_LIGHT = "#FECACA"
    COMBAT = WARNING
    COMBAT_LIGHT = WARNING_BG
    MANAGEMENT = "#14B8A6"      # 青绿 500
    MANAGEMENT_LIGHT = "#CCFBF1"
    COMPLETED = "#9CA3AF"

    # 节点类别颜色（用于节点标题栏渐变、添加节点弹窗等）
    NODE_CATEGORY_DEFAULT = "#4A9EFF"
    NODE_CATEGORY_DEFAULT_DARK = "#3A7ACC"
    NODE_CATEGORY_QUERY = "#2D5FE3"
    NODE_CATEGORY_QUERY_DARK = "#1B3FA8"
    NODE_CATEGORY_EVENT = "#FF5E9C"
    NODE_CATEGORY_EVENT_DARK = "#C23A74"
    NODE_CATEGORY_COMPUTE = "#2FAACB"
    NODE_CATEGORY_COMPUTE_DARK = "#1D6F8A"
    NODE_CATEGORY_EXECUTION = "#9CD64B"
    NODE_CATEGORY_EXECUTION_DARK = "#6BA633"
    NODE_CATEGORY_FLOW = "#FF9955"
    NODE_CATEGORY_FLOW_DARK = "#E87722"
    NODE_CATEGORY_COMPOSITE = "#AA55FF"
    NODE_CATEGORY_COMPOSITE_DARK = "#8833DD"
    # 虚拟引脚节点（输入/输出）标题栏渐变
    NODE_CATEGORY_VIRTUAL_INPUT = "#AA55FF"
    NODE_CATEGORY_VIRTUAL_INPUT_DARK = "#8833DD"
    NODE_CATEGORY_VIRTUAL_OUTPUT = "#55AAFF"
    NODE_CATEGORY_VIRTUAL_OUTPUT_DARK = "#3388DD"

    # Todo 步骤类型颜色（任务清单）
    TODO_STEP_TEMPLATE_GRAPH_ROOT = "#0D47A1"
    TODO_STEP_EVENT_FLOW_ROOT = "#006064"
    TODO_STEP_GRAPH_CREATE_NODE = "#1B5E20"
    TODO_STEP_GRAPH_CREATE_AND_CONNECT = "#2E7D32"
    TODO_STEP_GRAPH_CREATE_AND_CONNECT_REVERSE = "#43A047"
    TODO_STEP_GRAPH_CREATE_AND_CONNECT_DATA = "#00796B"
    TODO_STEP_GRAPH_CONNECT = "#BF360C"
    TODO_STEP_GRAPH_CONNECT_MERGED = "#D84315"
    TODO_STEP_GRAPH_CONFIG_NODE = "#512DA8"
    TODO_STEP_GRAPH_CONFIG_NODE_MERGED = "#673AB7"
    TODO_STEP_GRAPH_SET_PORT_TYPES_MERGED = "#0097A7"
    TODO_STEP_GRAPH_ADD_VARIADIC_INPUTS = "#0277BD"
    TODO_STEP_GRAPH_ADD_DICT_PAIRS = "#01579B"
    TODO_STEP_GRAPH_ADD_BRANCH_OUTPUTS = "#FF6F00"
    TODO_STEP_GRAPH_CONFIG_BRANCH_OUTPUTS = "#E65100"
    TODO_STEP_GRAPH_SIGNALS_OVERVIEW = "#006064"
    TODO_STEP_GRAPH_BIND_SIGNAL = "#6A1B9A"
    TODO_STEP_GRAPH_BIND_STRUCT = "#4A148C"

    # 特殊用途
    OVERLAY = "rgba(0, 0, 0, 0.5)"
    SHADOW = "rgba(0, 0, 0, 0.1)"
    SHADOW_DARK = "rgba(0, 0, 0, 0.2)"

    # 画布标尺（GraphView overlay）
    CANVAS_RULER_BACKGROUND = "#2B2B2B"
    CANVAS_RULER_CORNER_BACKGROUND = "#3A3A3A"
    CANVAS_RULER_LINE = "#4A4A4A"
    CANVAS_RULER_TEXT = "#B0B0B0"

    # Y 调试链路高亮调色板
    YDEBUG_CHAIN_1 = "#B388FF"
    YDEBUG_CHAIN_2 = "#00E5FF"
    YDEBUG_CHAIN_3 = "#FF9100"
    YDEBUG_CHAIN_4 = "#FF4081"

    # 节点图标题栏（复合节点银白渐变，适配深色画布）
    NODE_HEADER_COMPOSITE_START = "#F9FAFB"
    NODE_HEADER_COMPOSITE_END = "#E5E7EB"

    # 记录当前是否为深色主题，仅供调试/样式层按需分支使用
    IS_DARK: bool = False

    @classmethod
    def apply_theme_palette(cls, theme_mode: str) -> None:
        """根据主题模式切换当前调色板。

        参数:
            theme_mode: "light" / "dark" / 其他值（默认按浅色处理）
        """
        normalized_mode = theme_mode.lower()
        if normalized_mode == "dark":
            cls._apply_dark_overrides()
            cls.IS_DARK = True
        else:
            cls._reset_to_light()
            cls.IS_DARK = False

    @classmethod
    def _reset_to_light(cls) -> None:
        """恢复到浅色主题的默认配色。"""
        for name, value in _LIGHT_PALETTE.items():
            setattr(cls, name, value)

    @classmethod
    def _apply_dark_overrides(cls) -> None:
        """在浅色基础上叠加深色主题差异值。"""
        cls._reset_to_light()
        for name, value in _DARK_OVERRIDES.items():
            setattr(cls, name, value)


# 浅色主题默认调色板快照（用于在浅色/深色之间切换时恢复）
_LIGHT_PALETTE = {
    name: getattr(Colors, name)
    for name in dir(Colors)
    if name.isupper()
}

# 深色主题相对于浅色主题的差异表：未在此处列出的 token 复用浅色值
_DARK_OVERRIDES = {
    # 背景：采用接近 VSCode Dark 的深灰分层，而非纯黑
    "BG_MAIN": "#181818",           # 应用主背景
    "BG_CARD": "#1F1F1F",           # 卡片/对话框背景
    "BG_CARD_HOVER": "#262626",     # 悬停：略亮一档
    "BG_SELECTED": "#264F78",       # 选中背景：偏柔和的蓝灰
    "BG_SELECTED_HOVER": "#31679C", # 选中悬停：稍亮一档
    "BG_INPUT": "#1F1F1F",          # 输入框背景，与卡片一致
    "BG_DISABLED": "#262626",       # 禁用背景：略偏灰的深色
    "BG_HEADER": "#262626",         # 页头/表头背景
    "BG_DARK": "#141414",           # 更深一档，用于画布/强调区域

    # 文字：在深灰背景上使用略压暗的浅灰，避免纯黑↔纯白极端对比
    "TEXT_PRIMARY": "#D4D4D4",      # 主文本：接近 VSCode 的默认前景
    "TEXT_SECONDARY": "#9CA3AF",    # 次文本：中灰
    "TEXT_DISABLED": "#6B7280",     # 禁用文本：更深一档
    "TEXT_HINT": "#9CA3AF",
    "TEXT_PLACEHOLDER": "#6B7280",  # 占位略深，避免过亮

    # 边框与分隔线：中灰层次，拉开层级但不过亮
    "BORDER_LIGHT": "#333333",
    "BORDER_NORMAL": "#3F3F46",
    "BORDER_DARK": "#52525B",
    "DIVIDER": "#2A2A2A",
    "DIVIDER_DARK": "#3F3F46",

    # 状态背景：在深灰上使用更深的色块以保持对比
    "SUCCESS_BG": "#14532D",        # 深绿背景
    "WARNING_BG": "#7C2D12",        # 深橙背景
    "ERROR_BG": "#7F1D1D",          # 深红背景
    "INFO_BG": "#0B1120",           # 深青背景

    # Toast 卡片等阴影在深色背景下略微增强
    "SHADOW": "rgba(0, 0, 0, 0.4)",
    "SHADOW_DARK": "rgba(0, 0, 0, 0.6)",

    # 画布标尺（更深背景 + 亮文字）
    "CANVAS_RULER_BACKGROUND": "#1F1F1F",
    "CANVAS_RULER_CORNER_BACKGROUND": "#2A2A2A",
    "CANVAS_RULER_LINE": "#3F3F46",
    "CANVAS_RULER_TEXT": "#D1D5DB",

    # 节点类别（深色默认使用深色版）
    "NODE_CATEGORY_DEFAULT": "#3A7ACC",
    "NODE_CATEGORY_COMPOSITE": "#8833DD",
}

