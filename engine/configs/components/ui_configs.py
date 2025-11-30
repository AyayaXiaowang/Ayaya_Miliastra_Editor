"""
组件配置 - UI 组件

基于知识库文档和实际游戏编辑界面，定义与“铭牌、气泡”等 UI 相关通用组件
的配置数据结构，用于管理配置与运行时序列化。

说明：
- “铭牌组件”用于在 3D 世界中为实体挂接头顶 UI（如路牌名称、交互提示等），
  由一组“铭牌配置”组成，每个配置描述挂点、可见范围以及具体显示内容。
- “气泡组件”用于为实体挂接临时的对话/提示气泡，目前仍保持占位实现，仅保留原始字典结构。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class NameplateContentType(Enum):
    """铭牌内容类型。

    参考：通用组件 / 铭牌 的编辑界面，目前主要支持“文本框”这一类型，
    预留枚举便于后续扩展图标、进度条等更多表现形式。
    """

    TEXT_BOX = "文本框"


class NameplateTextAlign(Enum):
    """铭牌文本对齐方式。"""

    LEFT = "左对齐"
    CENTER = "居中"
    RIGHT = "右对齐"


@dataclass
class NameplateContent:
    """单条铭牌内容配置。

    对应编辑界面中的“铭牌内容”区域：可以为同一个铭牌配置添加多条内容块，
    每条内容块描述一个文本框的摆放位置、大小和文字样式。
    """

    # 内容序号（用于在同一铭牌配置下唯一标识一条内容）
    content_index: int
    # 选择类型：当前仅支持“文本框”
    content_type: NameplateContentType = NameplateContentType.TEXT_BOX
    # 偏移（相对于挂点的二维偏移，单位：像素）
    offset: List[float] = field(default_factory=lambda: [0.0, 0.0])
    # 大小（宽、高，单位：像素）
    size: List[float] = field(default_factory=lambda: [300.0, 150.0])
    # 背景颜色（例如 #RRGGBBAA，留空表示“无”）
    background_color: str = ""
    # 字号（像素大小）
    font_size: int = 48
    # 文本对齐方式
    text_align: NameplateTextAlign = NameplateTextAlign.CENTER
    # 文本内容模板，可包含变量占位符（例如 {1:s.当前路标名字}）
    text_template: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """序列化为资源配置使用的字典结构。"""
        return {
            "内容序号": self.content_index,
            "选择类型": self.content_type.value,
            "偏移": list(self.offset),
            "大小": list(self.size),
            "背景颜色": self.background_color,
            "字号": self.font_size,
            "对齐": self.text_align.value,
            "文本内容": self.text_template,
        }


@dataclass
class NameplateDefinition:
    """单个铭牌配置定义。

    用于描述一类铭牌在游戏中的“用途”：挂在哪个节点上、在多大范围内可见、
    是否需要通过本地过滤器按条件显示，以及具体的文本内容与样式。
    """

    # 配置序号（同一实体上的铭牌配置从 1 开始递增）
    config_index: int
    # 配置 ID，用于在节点图或运行时代码中引用（例如“铭牌配置ID1”）
    config_id: str
    # 显示名称（编辑器中用于区分用途，例如“当前路标名称”）
    display_name: str = ""
    # 选择挂点（例如 GI_RootNode）
    attach_point: str = "GI_RootNode"
    # 可见半径（米）
    visible_radius: float = 20.0
    # 本地过滤器类型（例如“布尔过滤器”，留空表示不过滤）
    local_filter: str = ""
    # 过滤器节点图配置 ID，用于决定在什么条件下显示该铭牌
    filter_graph_id: str = ""
    # 初始生效：实体创建时该铭牌是否默认显示
    initially_active: bool = True
    # 铭牌内容列表：同一铭牌可以包含多个内容块
    contents: List[NameplateContent] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为资源配置使用的字典结构。"""
        return {
            "配置序号": self.config_index,
            "配置ID": self.config_id,
            "名称": self.display_name,
            "选择挂点": self.attach_point,
            "可见半径": self.visible_radius,
            "本地过滤器": self.local_filter,
            "过滤器节点图": self.filter_graph_id,
            "初始生效": self.initially_active,
            "铭牌内容": [content.to_dict() for content in self.contents],
        }


@dataclass
class NameplateConfig:
    """铭牌组件配置。

    一个实体的“铭牌组件”可以挂接多条铭牌配置：例如同时显示名称、方向指示等，
    并通过“初始生效配置 ID 列表”指定在关卡开始时默认启用哪些铭牌。
    在运行时，可通过服务器节点“设置实体生效铭牌”传入“铭牌配置ID列表”来动态切换。
    """

    # 可用的铭牌配置列表
    nameplates: List[NameplateDefinition] = field(default_factory=list)
    # 初始生效的铭牌配置 ID 列表
    initially_active_config_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "铭牌配置列表": [nameplate.to_dict() for nameplate in self.nameplates],
            "初始生效配置ID列表": list(self.initially_active_config_ids),
        }


@dataclass
class BubbleConfig:
    """气泡组件配置（占位）。

  说明：目前仅保留“气泡设置”字典形式，后续可按铭牌组件的方式拆分为
  结构化的配置数据类。
    """

    # 气泡设置（占位字段）
    bubble_settings: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "气泡设置": self.bubble_settings
        }


__all__ = [
    "NameplateContentType",
    "NameplateTextAlign",
    "NameplateContent",
    "NameplateDefinition",
    "NameplateConfig",
    "BubbleConfig",
]


