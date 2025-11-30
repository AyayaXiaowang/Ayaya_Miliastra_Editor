"""Color tokens for the global UI theme."""


class Colors:
    """浅色主题配色（偏现代、低饱和，兼顾深色画布对比度）。"""

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

    # 特殊用途
    OVERLAY = "rgba(0, 0, 0, 0.5)"
    SHADOW = "rgba(0, 0, 0, 0.1)"
    SHADOW_DARK = "rgba(0, 0, 0, 0.2)"

    # 节点图标题栏（复合节点银白渐变，适配深色画布）
    NODE_HEADER_COMPOSITE_START = "#F9FAFB"
    NODE_HEADER_COMPOSITE_END = "#E5E7EB"


