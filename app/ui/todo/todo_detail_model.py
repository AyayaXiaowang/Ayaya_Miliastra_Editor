from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class ParagraphStyle(str, Enum):
    """段落样式语义标签。

    仅表达“语义用途”，具体颜色/字号由视图层结合 Theme 决定。
    """

    NORMAL = "normal"
    EMPHASIS = "emphasis"
    HINT = "hint"


@dataclass
class DetailBlock:
    """详情文档中的基础内容块基类。"""


@dataclass
class ParagraphBlock(DetailBlock):
    """普通文本段落。"""

    text: str
    style: ParagraphStyle = ParagraphStyle.NORMAL


@dataclass
class BulletListBlock(DetailBlock):
    """简单项目符号列表。"""

    items: List[str] = field(default_factory=list)


@dataclass
class TableBlock(DetailBlock):
    """只读表格数据块。

    目前仅保存表头与字符串单元格内容，不包含任何呈现层样式信息。
    """

    headers: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)


@dataclass
class DetailSection:
    """详情文档中的一个逻辑分节，对应原来的 h3/h4 标题块。"""

    title: Optional[str] = None
    # 语义层级：3≈主标题、4≈子标题，其它值由视图层自行决定呈现样式
    level: int = 3
    blocks: List[DetailBlock] = field(default_factory=list)


@dataclass
class DetailDocument:
    """Todo 详情页的结构化文档模型。

    该模型完全不依赖 Qt，仅描述“要显示什么”：
    - 顶层由若干 DetailSection 组成
    - 每个分节下包含 Paragraph/Table/BulletList 等内容块
    """

    sections: List[DetailSection] = field(default_factory=list)

    def is_empty(self) -> bool:
        if not self.sections:
            return True
        for section in self.sections:
            has_title = bool(section.title)
            if has_title or section.blocks:
                return False
        return True


