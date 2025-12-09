"""
统一面板骨架组件

提供 PanelScaffold 与 SectionCard：
- PanelScaffold：统一右侧面板的标题、描述、操作区与内容边距。
- SectionCard：带标题/描述的卡片容器，常用于分区信息或表单。
"""

from PyQt6 import QtCore, QtWidgets

from ui.foundation.theme_manager import Colors, Sizes
from ui.foundation.style_mixins import StyleMixin


class PanelScaffold(QtWidgets.QWidget, StyleMixin):
    """右侧面板统一骨架"""

    def __init__(self, parent: QtWidgets.QWidget | None = None, *, title: str = "", description: str = "") -> None:
        super().__init__(parent)

        self._title_text = title
        self._description_text = description

        self._build_layout()
        self.apply_widget_style()
        self.set_title(title)
        self.set_description(description)

    def _build_layout(self) -> None:
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(
            Sizes.SPACING_LARGE, Sizes.SPACING_LARGE, Sizes.SPACING_LARGE, Sizes.SPACING_LARGE
        )
        self.main_layout.setSpacing(Sizes.SPACING_LARGE)

        self._header_frame = QtWidgets.QFrame()
        self._header_frame.setObjectName("PanelScaffoldHeader")
        header_layout = QtWidgets.QVBoxLayout(self._header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(Sizes.SPACING_SMALL)

        header_row = QtWidgets.QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(Sizes.SPACING_LARGE)

        header_text_layout = QtWidgets.QVBoxLayout()
        header_text_layout.setContentsMargins(0, 0, 0, 0)
        header_text_layout.setSpacing(2)

        self.title_label = QtWidgets.QLabel()
        title_font = self.title_label.font()
        title_font.setPointSize(Sizes.FONT_TITLE)
        title_font.setBold(True)
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        header_text_layout.addWidget(self.title_label)

        self.description_label = QtWidgets.QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet(
            f"color: {Colors.TEXT_SECONDARY}; font-size: {Sizes.FONT_NORMAL}px;"
        )
        header_text_layout.addWidget(self.description_label)

        header_row.addLayout(header_text_layout, 1)

        self.actions_layout = QtWidgets.QHBoxLayout()
        self.actions_layout.setContentsMargins(0, 0, 0, 0)
        self.actions_layout.setSpacing(Sizes.SPACING_SMALL)
        header_row.addLayout(self.actions_layout)
        header_row.setAlignment(self.actions_layout, QtCore.Qt.AlignmentFlag.AlignRight)

        header_layout.addLayout(header_row)

        divider = QtWidgets.QFrame()
        divider.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        divider.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
        divider.setStyleSheet(f"color: {Colors.DIVIDER}; background-color: {Colors.DIVIDER};")
        divider.setFixedHeight(1)
        header_layout.addWidget(divider)

        self.main_layout.addWidget(self._header_frame)

        self.status_container = QtWidgets.QFrame()
        self.status_container.setVisible(False)
        self.status_layout = QtWidgets.QHBoxLayout(self.status_container)
        self.status_layout.setContentsMargins(0, 0, 0, 0)
        self.status_layout.setSpacing(0)
        self.main_layout.addWidget(self.status_container)

        self.body_container = QtWidgets.QWidget()
        self.body_layout = QtWidgets.QVBoxLayout(self.body_container)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(Sizes.SPACING_LARGE)
        self.main_layout.addWidget(self.body_container, 1)

    def set_title(self, title: str) -> None:
        self._title_text = title
        self.title_label.setText(title)

    def set_description(self, description: str) -> None:
        self._description_text = description
        self.description_label.setVisible(bool(description))
        self.description_label.setText(description)

    def add_action_widget(self, widget: QtWidgets.QWidget) -> None:
        """在标题右侧添加操作按钮/下拉等控件"""
        self.actions_layout.addWidget(widget)

    def set_status_widget(self, widget: QtWidgets.QWidget | None) -> None:
        """在标题与正文之间展示状态信息（Badge/提示条）"""
        self._clear_layout(self.status_layout)
        if widget is None:
            self.status_container.setVisible(False)
            return
        self.status_layout.addWidget(widget)
        self.status_container.setVisible(True)

    def create_status_badge(
        self,
        object_name: str,
        text: str,
        *,
        background_color: str = Colors.INFO_BG,
        text_color: str = Colors.TEXT_PRIMARY,
    ) -> "StatusBadge":
        """创建并挂载一个标准状态徽章。"""
        badge = StatusBadge(text, object_name=object_name)
        badge.apply_palette(background_color, text_color)
        self.set_status_widget(badge)
        return badge

    def build_status_badge(self, object_name: str, default_text: str = "未选中") -> "StatusBadge":
        """便捷方法：创建并返回状态徽章（不自动挂载）。
        
        用于子类需要保留 badge 引用但稍后才挂载的场景。
        """
        badge = StatusBadge(default_text, object_name=object_name)
        badge.apply_palette(Colors.INFO_BG, Colors.TEXT_PRIMARY)
        return badge

    def update_status_badge_style(
        self, 
        badge: "StatusBadge", 
        background_color: str, 
        text_color: str
    ) -> None:
        """统一的状态徽章样式更新方法。"""
        badge.apply_palette(background_color, text_color)

    @staticmethod
    def _clear_layout(layout: QtWidgets.QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
            if item.layout():
                PanelScaffold._clear_layout(item.layout())


class SectionCard(QtWidgets.QFrame):
    """统一的卡片式分区，包含标题、描述与内容区域"""

    def __init__(
        self,
        title: str = "",
        description: str = "",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SectionCard")
        self.setStyleSheet(
            f"""
            QFrame#SectionCard {{
                background-color: {Colors.BG_CARD};
                border-radius: {Sizes.RADIUS_MEDIUM}px;
                border: 1px solid {Colors.BORDER_LIGHT};
            }}
        """
        )

        self._title_label: QtWidgets.QLabel | None = None
        self._description_label: QtWidgets.QLabel | None = None

        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(
            Sizes.PADDING_LARGE, Sizes.PADDING_LARGE, Sizes.PADDING_LARGE, Sizes.PADDING_LARGE
        )
        self.main_layout.setSpacing(Sizes.SPACING_MEDIUM)

        if title:
            self._title_label = QtWidgets.QLabel(title)
            title_font = self._title_label.font()
            title_font.setPointSize(Sizes.FONT_LARGE)
            title_font.setBold(True)
            self._title_label.setFont(title_font)
            self._title_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
            self.main_layout.addWidget(self._title_label)

        if description:
            self._description_label = QtWidgets.QLabel(description)
            self._description_label.setWordWrap(True)
            self._description_label.setStyleSheet(
                f"color: {Colors.TEXT_SECONDARY}; font-size: {Sizes.FONT_NORMAL}px;"
            )
            self.main_layout.addWidget(self._description_label)

        self.content_layout = QtWidgets.QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(Sizes.SPACING_MEDIUM)
        self.main_layout.addLayout(self.content_layout)

    def add_content_widget(self, widget: QtWidgets.QWidget, *, stretch: int = 0) -> None:
        self.content_layout.addWidget(widget, stretch)

    def add_spacer(self) -> None:
        self.content_layout.addStretch(1)

    def set_content_margins(self, left: int, top: int, right: int, bottom: int) -> None:
        """调整卡片内部边距，用于需要内容铺满卡片宽度等特殊布局场景。"""
        self.content_layout.setContentsMargins(left, top, right, bottom)

    def set_title(self, title: str) -> None:
        """更新卡片标题文本，供库页面等根据上下文动态切换文案。"""
        if self._title_label is None:
            if not title:
                return
            self._title_label = QtWidgets.QLabel(title)
            title_font = self._title_label.font()
            title_font.setPointSize(Sizes.FONT_LARGE)
            title_font.setBold(True)
            self._title_label.setFont(title_font)
            self._title_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
            self.main_layout.insertWidget(0, self._title_label)
            return
        self._title_label.setText(title)
        self._title_label.setVisible(bool(title))

    def set_description(self, description: str) -> None:
        """更新卡片描述文本，保持标题区与内容区布局不变。"""
        if self._description_label is None:
            if not description:
                return
            self._description_label = QtWidgets.QLabel(description)
            self._description_label.setWordWrap(True)
            self._description_label.setStyleSheet(
                f"color: {Colors.TEXT_SECONDARY}; font-size: {Sizes.FONT_NORMAL}px;"
            )
            insert_index = 1 if self._title_label is not None else 0
            self.main_layout.insertWidget(insert_index, self._description_label)
            return
        self._description_label.setVisible(bool(description))
        self._description_label.setText(description)


class StatusBadge(QtWidgets.QLabel):
    """标准状态徽章，统一样式与配色。"""

    def __init__(self, text: str, *, object_name: str) -> None:
        super().__init__(text)
        self.setObjectName(object_name)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)

    def apply_palette(self, background_color: str, text_color: str) -> None:
        self.setStyleSheet(
            f"""
            QLabel#{self.objectName()} {{
                background-color: {background_color};
                color: {text_color};
                border-radius: {Sizes.RADIUS_MEDIUM}px;
                font-weight: bold;
                padding: {Sizes.PADDING_SMALL}px {Sizes.PADDING_MEDIUM}px;
            }}
        """
        )


def build_scrollable_column(
    parent: QtWidgets.QWidget,
    *,
    spacing: int = Sizes.SPACING_SMALL,
    margins: tuple[int, int, int, int] = (0, 0, 0, 0),
    alignment: QtCore.Qt.AlignmentFlag = QtCore.Qt.AlignmentFlag.AlignTop,
    add_trailing_stretch: bool = True,
) -> tuple[QtWidgets.QScrollArea, QtWidgets.QWidget, QtWidgets.QVBoxLayout]:
    """构建顶对齐的滚动列容器，避免内容在可用高度内居中分散。

    返回值：scroll_area, content_widget, content_layout。
    - scroll_area：无边框且关闭水平滚动；
    - content_layout：VBox，统一 spacing/margins，可选末尾添加 stretch 保持顶对齐。
    """
    scroll_area = QtWidgets.QScrollArea(parent)
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll_area.setAlignment(alignment)

    content_widget = QtWidgets.QWidget(scroll_area)
    content_layout = QtWidgets.QVBoxLayout(content_widget)
    content_layout.setContentsMargins(*margins)
    content_layout.setSpacing(spacing)

    if add_trailing_stretch:
        content_layout.addStretch(1)

    scroll_area.setWidget(content_widget)
    return scroll_area, content_widget, content_layout
