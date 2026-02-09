"""Atomic QSS snippets for reusable widgets."""

from app.ui.foundation.theme.tokens import Colors, Sizes, Gradients


def card_style(border_radius: int | None = None) -> str:
    radius = border_radius if border_radius is not None else Sizes.RADIUS_LARGE
    return f"""
        QWidget {{
            background: {Gradients.card()};
            border-radius: {radius}px;
            border: 1px solid {Colors.BORDER_LIGHT};
        }}
    """


def button_style() -> str:
    return f"""
        QPushButton {{
            background-color: {Colors.PRIMARY};
            color: {Colors.TEXT_ON_PRIMARY};
            border: none;
            border-radius: {Sizes.RADIUS_SMALL}px;
            padding: {Sizes.PADDING_SMALL}px {Sizes.PADDING_MEDIUM}px;
            font-size: {Sizes.FONT_NORMAL}px;
            min-height: {Sizes.BUTTON_HEIGHT}px;
        }}
        QPushButton:hover {{
            background-color: {Colors.PRIMARY_DARK};
        }}
        QPushButton:pressed {{
            background-color: {Colors.PRIMARY_DARK};
            color: {Colors.TEXT_ON_PRIMARY};
        }}

        /* 变体按钮：通过动态属性 kind 统一管理（primary/secondary/danger） */
        QPushButton[kind="secondary"] {{
            background-color: {Colors.BG_CARD};
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BORDER_LIGHT};
        }}
        QPushButton[kind="secondary"]:hover {{
            background-color: {Colors.BG_CARD_HOVER};
            border: 1px solid {Colors.BORDER_NORMAL};
        }}
        QPushButton[kind="secondary"]:pressed {{
            background-color: {Colors.BG_SELECTED_HOVER};
        }}

        QPushButton[kind="danger"] {{
            background-color: {Colors.ERROR};
            color: {Colors.TEXT_ON_PRIMARY};
            border: none;
        }}
        QPushButton[kind="danger"]:hover {{
            background-color: {Colors.ERROR_LIGHT};
        }}
        QPushButton[kind="danger"]:pressed {{
            background-color: {Colors.ERROR};
        }}

        QPushButton:disabled {{
            background-color: {Colors.BG_DISABLED};
            color: {Colors.TEXT_DISABLED};
        }}
    """


def input_style() -> str:
    return f"""
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: {Colors.BG_INPUT};
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BORDER_LIGHT};
            border-radius: {Sizes.RADIUS_SMALL}px;
            padding: {Sizes.PADDING_SMALL}px;
            font-size: {Sizes.FONT_NORMAL}px;
            selection-background-color: {Colors.BG_SELECTED};
            selection-color: {Colors.TEXT_PRIMARY};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: 1px solid {Colors.BORDER_FOCUS};
        }}
        QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
            background-color: {Colors.BG_DISABLED};
            color: {Colors.TEXT_DISABLED};
        }}
    """


def tree_style() -> str:
    return f"""
        QTreeWidget {{
            background-color: {Colors.BG_CARD};
            color: {Colors.TEXT_PRIMARY};
            alternate-background-color: {Colors.BG_CARD_HOVER};
            border: none;
            border-radius: {Sizes.RADIUS_MEDIUM}px;
            outline: none;
            padding: {Sizes.PADDING_SMALL}px;
            font-size: {Sizes.FONT_NORMAL}px;
        }}
        QTreeWidget::item {{
            padding: {Sizes.PADDING_SMALL}px;
            border-radius: 0px;
            margin: 0px;
            color: {Colors.TEXT_PRIMARY};
        }}
        QTreeWidget::item:hover {{
            background-color: {Colors.BG_CARD_HOVER};
        }}
        QTreeWidget::item:selected {{
            background: {Gradients.primary_vertical()};
            color: {Colors.TEXT_ON_PRIMARY};
        }}
    """


def list_style() -> str:
    return f"""
        QListWidget {{
            background-color: {Colors.BG_CARD};
            color: {Colors.TEXT_PRIMARY};
            border: none;
            border-radius: {Sizes.RADIUS_MEDIUM}px;
            outline: none;
            padding: {Sizes.PADDING_SMALL}px;
            font-size: {Sizes.FONT_NORMAL}px;
        }}
        QListWidget::item {{
            padding: {Sizes.PADDING_SMALL}px;
            border-radius: {Sizes.RADIUS_SMALL}px;
            margin: 2px 0px;
            color: {Colors.TEXT_PRIMARY};
        }}
        QListWidget::item:hover {{
            background-color: {Colors.BG_CARD_HOVER};
        }}
        QListWidget::item:selected {{
            background: {Gradients.primary_vertical()};
            color: {Colors.TEXT_ON_PRIMARY};
        }}
    """


def graph_search_overlay_style() -> str:
    """GraphView 画布搜索浮层（GraphSearchOverlay）的专用样式。

    说明：
    - 该样式只使用 objectName 定位，避免污染其它列表/按钮控件；
    - 选中态沿用主题主色系垂直渐变 + TEXT_ON_PRIMARY，保证可读性。
    """
    return f"""
        QFrame#graphSearchOverlay {{
            background-color: {Colors.BG_CARD};
            border: 1px solid {Colors.BORDER_LIGHT};
            border-radius: {Sizes.RADIUS_MEDIUM}px;
        }}

        QLabel#graphSearchCount {{
            color: {Colors.TEXT_SECONDARY};
        }}

        QLabel#graphSearchPageLabel {{
            color: {Colors.TEXT_SECONDARY};
        }}

        /* 图标按钮：Overlay 内统一的 toolbutton 交互风格 */
        QFrame#graphSearchOverlay QToolButton {{
            border: none;
            padding: 4px;
            border-radius: {Sizes.RADIUS_SMALL}px;
        }}
        QFrame#graphSearchOverlay QToolButton:hover {{
            background-color: {Colors.BG_CARD_HOVER};
        }}
        QFrame#graphSearchOverlay QToolButton:pressed {{
            background-color: {Colors.BG_SELECTED_HOVER};
        }}

        /* 结果列表：以“整条结果组件”为单位，行高由 item.sizeHint 控制 */
        /* 注意：GraphSearchOverlay 的结果项使用 setItemWidget(...) 自绘。
           Qt 会把该 widget 放到 SE_ItemViewItemText 的 rect 中，若这里设置 item padding，
           会“吃掉” editor 的可用高度并导致三行文本被裁切。
           因此 padding 由结果项 widget 内部 layout 的 margins 提供，这里保持 0。 */
        QListWidget#graphSearchResults {{
            background-color: transparent;
            border: 1px solid {Colors.BORDER_LIGHT};
            border-radius: {Sizes.RADIUS_SMALL}px;
            outline: none;
            padding: 0px;
        }}
        QListWidget#graphSearchResults::item {{
            padding: 0px;
            margin: 0px;
            border-radius: {Sizes.RADIUS_SMALL}px;
            color: {Colors.TEXT_PRIMARY};
        }}
        QListWidget#graphSearchResults::item:hover {{
            background-color: {Colors.BG_CARD_HOVER};
        }}
        QListWidget#graphSearchResults::item:selected {{
            background: {Gradients.primary_vertical()};
            color: {Colors.TEXT_ON_PRIMARY};
        }}
    """


def graph_card_widget_style() -> str:
    """GraphLibrary 列表卡片（GraphCardWidget）内部控件样式。

    说明：
    - 仅通过 objectName / 动态属性选择器生效，避免污染全局按钮样式；
    - 选中态文字颜色通过 `selected` 动态属性切换，配合卡片自身的高亮渐变背景。
    """
    return f"""
        QLabel#graphCardSharedBadge {{
            background-color: {Colors.ACCENT};
            color: {Colors.TEXT_ON_PRIMARY};
            border-radius: 9px;
            padding: 2px 8px;
        }}

        QPushButton#graphCardVariablesButton {{
            background-color: {Colors.SECONDARY};
            color: {Colors.TEXT_ON_PRIMARY};
            border: 1px solid {Colors.SECONDARY};
            border-radius: {Sizes.RADIUS_MEDIUM}px;
            padding: 2px 10px;
        }}
        QPushButton#graphCardVariablesButton:hover {{
            background-color: {Colors.SECONDARY_DARK};
            color: {Colors.TEXT_ON_PRIMARY};
        }}
        QPushButton#graphCardVariablesButton:pressed {{
            background-color: {Colors.SECONDARY_DARK};
        }}

        QPushButton#graphCardEditButton {{
            background-color: {Colors.PRIMARY};
            color: {Colors.TEXT_ON_PRIMARY};
            border: 1px solid {Colors.PRIMARY};
            border-radius: {Sizes.RADIUS_MEDIUM}px;
            padding: 2px 10px;
        }}
        QPushButton#graphCardEditButton:hover {{
            background-color: {Colors.PRIMARY_DARK};
            color: {Colors.TEXT_ON_PRIMARY};
        }}
        QPushButton#graphCardEditButton:pressed {{
            background-color: {Colors.PRIMARY_DARK};
        }}

        QPushButton#graphCardRefButton {{
            background-color: {Colors.SECONDARY_DARK};
            color: {Colors.TEXT_ON_PRIMARY};
            border: 1px solid {Colors.SECONDARY_DARK};
            border-radius: 10px;
            padding: 2px 10px;
        }}
        QPushButton#graphCardRefButton:hover {{
            background-color: {Colors.SECONDARY};
            color: {Colors.TEXT_ON_PRIMARY};
        }}

        QLabel#graphCardName[selected="false"] {{
            color: {Colors.TEXT_PRIMARY};
        }}
        QLabel#graphCardTime[selected="false"] {{
            color: {Colors.TEXT_SECONDARY};
        }}
        QLabel#graphCardDescription[selected="false"] {{
            color: {Colors.TEXT_DISABLED};
            font-style: italic;
        }}

        QLabel#graphCardName[selected="true"] {{
            color: {Colors.TEXT_ON_PRIMARY};
        }}
        QLabel#graphCardTime[selected="true"] {{
            color: {Colors.TEXT_ON_PRIMARY};
        }}
        QLabel#graphCardDescription[selected="true"] {{
            color: {Colors.TEXT_ON_PRIMARY};
            font-style: italic;
        }}
    """


def left_panel_style() -> str:
    return f"""
        QTreeWidget#leftPanel, QTreeView#leftPanel, QListWidget#leftPanel {{
            background-color: {Colors.BG_CARD};
            color: {Colors.TEXT_PRIMARY};
            border: none;
            outline: none;
            selection-background-color: transparent;
            padding: {Sizes.PADDING_SMALL}px 0;
        }}

        QTreeWidget#leftPanel::branch,
        QTreeView#leftPanel::branch {{
            background-color: transparent;
        }}

        QTreeWidget#leftPanel::branch:selected,
        QTreeView#leftPanel::branch:selected {{
            background-color: transparent;
        }}

        QTreeWidget#leftPanel::item,
        QTreeView#leftPanel::item,
        QListWidget#leftPanel::item {{
            padding: {Sizes.PADDING_SMALL}px {Sizes.PADDING_MEDIUM}px;
            margin: 2px {Sizes.PADDING_SMALL}px;
            border-radius: {Sizes.RADIUS_SMALL}px;
            color: {Colors.TEXT_PRIMARY};
        }}

        QTreeWidget#leftPanel::item:hover,
        QTreeView#leftPanel::item:hover,
        QListWidget#leftPanel::item:hover {{
            background-color: {Colors.BG_CARD_HOVER};
        }}

        QTreeWidget#leftPanel::item:selected,
        QTreeView#leftPanel::item:selected,
        QListWidget#leftPanel::item:selected,
        QTreeWidget#leftPanel::item:selected:!active,
        QTreeView#leftPanel::item:selected:!active,
        QListWidget#leftPanel::item:selected:!active {{
            background: {Gradients.primary_horizontal()};
            color: {Colors.TEXT_ON_PRIMARY};
        }}
    """


def table_style() -> str:
    return f"""
        QTableWidget {{
            background-color: {Colors.BG_CARD};
            color: {Colors.TEXT_PRIMARY};
            gridline-color: {Colors.DIVIDER};
            border: 1px solid {Colors.BORDER_LIGHT};
            border-radius: {Sizes.RADIUS_SMALL}px;
            selection-background-color: {Colors.BG_SELECTED};
            selection-color: {Colors.TEXT_PRIMARY};
        }}
        QTableWidget::item {{
            padding: {Sizes.PADDING_SMALL}px;
        }}
        /* 表格内联编辑：统一为“单元格直接编辑”的视觉效果，去掉内嵌控件的额外边框与内边距 */
        QTableWidget QLineEdit,
        QTableWidget QTextEdit,
        QTableWidget QPlainTextEdit,
        QTableView QLineEdit,
        QTableView QTextEdit,
        QTableView QPlainTextEdit {{
            background-color: transparent;
            border: none;
            padding: 0px;
            margin: 0px;
        }}
        QTableWidget QComboBox,
        QTableView QComboBox,
        QTableWidget QAbstractSpinBox,
        QTableView QAbstractSpinBox {{
            background-color: transparent;
            border: none;
            padding: 0px;
            margin: 0px;
        }}
        QTableWidget::item:hover {{
            background-color: {Colors.BG_CARD_HOVER};
        }}
        QHeaderView::section {{
            background-color: {Colors.BG_HEADER};
            color: {Colors.TEXT_PRIMARY};
            padding: {Sizes.PADDING_SMALL}px;
            border: none;
            border-bottom: 1px solid {Colors.DIVIDER};
            font-weight: bold;
        }}
    """


def scrollbar_style() -> str:
    return f"""
        QScrollBar:vertical {{
            background: {Colors.BG_MAIN};
            width: 12px;
            border-radius: {Sizes.RADIUS_SMALL}px;
        }}
        QScrollBar::handle:vertical {{
            background: {Colors.DIVIDER_DARK};
            border-radius: {Sizes.RADIUS_SMALL}px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {Colors.BORDER_DARK};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}

        QScrollBar:horizontal {{
            background: {Colors.BG_MAIN};
            height: 12px;
            border-radius: {Sizes.RADIUS_SMALL}px;
        }}
        QScrollBar::handle:horizontal {{
            background: {Colors.DIVIDER_DARK};
            border-radius: {Sizes.RADIUS_SMALL}px;
            min-width: 30px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {Colors.BORDER_DARK};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}
    """


def tab_style() -> str:
    return f"""
        QTabWidget::pane {{
            border: 1px solid {Colors.BORDER_LIGHT};
            border-radius: {Sizes.RADIUS_SMALL}px;
            background-color: {Colors.BG_CARD};
        }}
        QTabBar::tab {{
            background-color: {Colors.BG_HEADER};
            color: {Colors.TEXT_SECONDARY};
            padding: {Sizes.PADDING_SMALL}px {Sizes.PADDING_MEDIUM}px;
            border: 1px solid {Colors.BORDER_LIGHT};
            border-bottom: none;
            border-top-left-radius: {Sizes.RADIUS_SMALL}px;
            border-top-right-radius: {Sizes.RADIUS_SMALL}px;
            margin-right: 2px;
        }}
        QTabBar::tab:selected {{
            background: {Gradients.primary_horizontal()};
            color: {Colors.TEXT_ON_PRIMARY};
            font-weight: bold;
        }}
        QTabBar::tab:hover:!selected {{
            background-color: {Colors.BG_CARD_HOVER};
        }}
    """


def right_side_tab_style() -> str:
    return f"""
        QTabWidget#sideTab::pane {{
            border-left: none;
            border-top: 1px solid {Colors.BORDER_LIGHT};
            border-right: 1px solid {Colors.BORDER_LIGHT};
            border-bottom: 1px solid {Colors.BORDER_LIGHT};
            border-top-left-radius: 0px;
            border-bottom-left-radius: 0px;
            border-top-right-radius: {Sizes.RADIUS_SMALL}px;
            border-bottom-right-radius: {Sizes.RADIUS_SMALL}px;
            background-color: {Colors.BG_CARD};
        }}
    """


def splitter_style() -> str:
    return f"""
        QSplitter {{
            background-color: {Colors.BG_MAIN};
        }}
        QSplitter::handle {{
            background-color: {Colors.DIVIDER};
        }}
        QSplitter::handle:horizontal {{
            width: {Sizes.SPLITTER_WIDTH}px;
        }}
        QSplitter::handle:vertical {{
            height: {Sizes.SPLITTER_WIDTH}px;
        }}
    """


def combo_box_style() -> str:
    return f"""
        QComboBox {{
            background-color: {Colors.BG_INPUT};
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BORDER_LIGHT};
            border-radius: {Sizes.RADIUS_SMALL}px;
            padding: {Sizes.PADDING_SMALL}px;
            font-size: {Sizes.FONT_NORMAL}px;
            min-height: {Sizes.INPUT_HEIGHT}px;
        }}
        QComboBox:hover {{
            border: 1px solid {Colors.BORDER_FOCUS};
        }}
        QComboBox QAbstractItemView {{
            background-color: {Colors.BG_CARD};
            border: 1px solid {Colors.BORDER_LIGHT};
            selection-background-color: {Colors.PRIMARY};
            selection-color: {Colors.TEXT_ON_PRIMARY};
        }}
        QComboBox QAbstractItemView::item:selected {{
            background: {Gradients.primary_vertical()};
            color: {Colors.TEXT_ON_PRIMARY};
        }}
    """


def spin_box_style() -> str:
    return f"""
        QSpinBox, QDoubleSpinBox {{
            background-color: {Colors.BG_INPUT};
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.BORDER_LIGHT};
            border-radius: {Sizes.RADIUS_SMALL}px;
            padding: {Sizes.PADDING_SMALL}px;
            font-size: {Sizes.FONT_NORMAL}px;
            min-height: {Sizes.INPUT_HEIGHT}px;
        }}
        QSpinBox:focus, QDoubleSpinBox:focus {{
            border: 1px solid {Colors.BORDER_FOCUS};
        }}
    """


def group_box_style() -> str:
    return f"""
        QGroupBox {{
            background-color: {Colors.BG_CARD};
            border: 1px solid {Colors.BORDER_LIGHT};
            border-radius: {Sizes.RADIUS_MEDIUM}px;
            margin-top: {Sizes.PADDING_MEDIUM}px;
            padding: {Sizes.PADDING_MEDIUM}px;
            font-weight: bold;
            color: {Colors.TEXT_PRIMARY};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 {Sizes.PADDING_SMALL}px;
            color: {Colors.PRIMARY};
        }}
    """


def dialog_style() -> str:
    return f"""
        QDialog {{
            background-color: {Colors.BG_CARD};
            border: 1px solid {Colors.BORDER_LIGHT};
            border-radius: {Sizes.RADIUS_LARGE}px;
        }}
    """


def conflict_resolution_dialog_style() -> str:
    """节点图冲突解决对话框（ConflictResolutionDialog）局部样式。"""
    return f"""
        QLabel#conflictDialogTitle {{
            color: {Colors.WARNING};
        }}
        QLabel#conflictDialogDescription {{
            font-size: 13px;
            color: {Colors.TEXT_PRIMARY};
        }}
        QWidget#conflictTimeInfoBox {{
            background-color: {Colors.BG_MAIN};
            border-radius: 5px;
        }}
        QLabel#conflictTimeLabel {{
            font-size: 12px;
            color: {Colors.TEXT_SECONDARY};
        }}
        QLabel#conflictDialogHint {{
            font-size: 11px;
            color: {Colors.TEXT_HINT};
            margin-top: 5px;
        }}
    """


def context_menu_style() -> str:
    return f"""
        QMenu {{
            background-color: {Colors.BG_CARD};
            color: {Colors.TEXT_PRIMARY};
            border: 1px solid {Colors.DIVIDER};
            padding: 4px 0px;
        }}
        QMenu::item {{
            padding: 6px 12px;
            background: transparent;
        }}
        QMenu::item:selected {{
            background: {Gradients.primary_vertical()};
            color: {Colors.TEXT_ON_PRIMARY};
        }}
        QMenu::separator {{
            height: 1px;
            margin: 4px 8px;
            background: {Colors.DIVIDER};
        }}
    """


def info_label_style() -> str:
    return f"color: {Colors.TEXT_SECONDARY}; padding: 8px; background-color: {Colors.BG_DARK}; border-radius: {Sizes.RADIUS_SMALL}px;"


def info_label_simple_style() -> str:
    return f"color: {Colors.TEXT_SECONDARY}; padding: 10px;"


def info_label_dark_style() -> str:
    return (
        f"color: {Colors.TEXT_PLACEHOLDER};"
        f"padding: 10px;"
        f"background-color: {Colors.BG_DARK};"
        f"border-radius: {Sizes.RADIUS_SMALL}px;"
    )


def readonly_input_style() -> str:
    # 只读输入统一使用浅灰底 + 次要文字色，避免在深色背景上出现“黑底黑字”难以辨认的情况。
    # 典型场景：结构体名、配置 ID 等不可编辑字段。
    return (
        f"background-color: {Colors.BG_DISABLED};"
        f"color: {Colors.TEXT_SECONDARY};"
    )


def hint_text_style() -> str:
    return f"color: {Colors.TEXT_PLACEHOLDER}; font-size: 9pt; padding: 5px;"


def subtle_info_style() -> str:
    return f"color: {Colors.TEXT_PLACEHOLDER}; padding: 5px;"


def navigation_button_style() -> str:
    """左侧导航按钮专用样式。"""
    return f"""
        QPushButton {{
            border: none;
            background: transparent;
            outline: none;
            color: {Colors.TEXT_SECONDARY};
            font-size: {Sizes.FONT_SMALL}px;
            padding: {Sizes.PADDING_SMALL}px;
            border-radius: {Sizes.RADIUS_MEDIUM}px;
        }}
        QPushButton:hover:!checked {{
            background: {Colors.BG_SELECTED};
            color: {Colors.PRIMARY};
        }}
        QPushButton:checked {{
            background: {Gradients.primary_horizontal()};
            color: {Colors.TEXT_ON_PRIMARY};
            font-weight: bold;
        }}
    """


def toast_content_style() -> str:
    """Toast 内容卡片样式。

    说明：
    - 仅通过 objectName / 动态属性选择器生效，避免影响全局其它控件；
    - `toastType` 动态属性用于区分 info/warning/error/success 的强调色。
    """
    return f"""
        #toastContent {{
            background-color: {Colors.BG_CARD};
            border: 1px solid {Colors.BORDER_LIGHT};
            border-radius: {Sizes.RADIUS_MEDIUM}px;
        }}

        QWidget#toastBorder {{
            border-radius: 2px;
        }}
        QWidget#toastBorder[toastType="info"] {{ background: {Colors.INFO}; }}
        QWidget#toastBorder[toastType="warning"] {{ background: {Colors.WARNING}; }}
        QWidget#toastBorder[toastType="error"] {{ background: {Colors.ERROR}; }}
        QWidget#toastBorder[toastType="success"] {{ background: {Colors.SUCCESS}; }}

        QLabel#toastIcon {{
            font-size: {Sizes.FONT_LARGE}px;
        }}
        QLabel#toastIcon[toastType="info"] {{ color: {Colors.INFO}; }}
        QLabel#toastIcon[toastType="warning"] {{ color: {Colors.WARNING}; }}
        QLabel#toastIcon[toastType="error"] {{ color: {Colors.ERROR}; }}
        QLabel#toastIcon[toastType="success"] {{ color: {Colors.SUCCESS}; }}

        QLabel#toastMessage {{
            font-size: {Sizes.FONT_NORMAL}px;
            color: {Colors.TEXT_PRIMARY};
        }}
    """


def navigation_bar_style() -> str:
    """左侧模式导航栏（NavigationBar）容器样式。"""
    return f"""
        QWidget#navigationBar {{
            background-color: {Colors.BG_CARD};
            border-right: 1px solid {Colors.BORDER_LIGHT};
        }}
    """


def panel_scaffold_style() -> str:
    """右侧面板骨架（PanelScaffold / SectionCard）样式。

    仅通过 objectName 精确匹配，避免影响业务控件的局部风格。
    """
    return f"""
        QLabel#PanelScaffoldTitle {{
            color: {Colors.TEXT_PRIMARY};
        }}
        QLabel#PanelScaffoldDescription {{
            color: {Colors.TEXT_SECONDARY};
            font-size: {Sizes.FONT_NORMAL}px;
        }}
        QFrame#PanelScaffoldDivider {{
            background-color: {Colors.DIVIDER};
            color: {Colors.DIVIDER};
        }}

        QFrame#SectionCard {{
            background-color: {Colors.BG_CARD};
            border-radius: {Sizes.RADIUS_MEDIUM}px;
            border: 1px solid {Colors.BORDER_LIGHT};
        }}
        QLabel#SectionCardTitle {{
            color: {Colors.TEXT_PRIMARY};
        }}
        QLabel#SectionCardDescription {{
            color: {Colors.TEXT_SECONDARY};
            font-size: {Sizes.FONT_NORMAL}px;
        }}
    """


def composite_pin_widgets_style() -> str:
    """复合节点虚拟引脚相关控件样式（PinCardWidget / PinListPanel）。

    说明：
    - 仅通过 objectName / 动态属性选择器生效；
    - 通过 `pinKind/isUnset` 等属性承载少量状态差异，避免在业务代码内拼接 QSS。
    """
    return f"""
        QWidget#pinCard {{
            background-color: {Colors.BG_CARD};
            border: 1px solid {Colors.BORDER_LIGHT};
            border-radius: {Sizes.RADIUS_MEDIUM}px;
        }}
        QWidget#pinCard:hover {{
            border-color: {Colors.PRIMARY};
            background-color: {Colors.BG_CARD_HOVER};
        }}

        QLabel#pinTypeIcon {{
            font-size: 16px;
            color: {Colors.TEXT_SECONDARY};
        }}
        QLabel#pinNameLabel {{
            font-size: 13px;
            color: {Colors.TEXT_PRIMARY};
            font-weight: bold;
        }}
        QLabel#pinMappingLabel {{
            color: {Colors.TEXT_SECONDARY};
            font-size: 11px;
        }}

        QLabel#pinNumberBadge {{
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 {Colors.ACCENT_LIGHT},
                stop:1 {Colors.ACCENT}
            );
            color: {Colors.TEXT_ON_PRIMARY};
            font-weight: bold;
            font-size: 11px;
            border: 2px solid {Colors.ACCENT};
        }}
        QLabel#pinNumberBadge[pinKind="flow"] {{
            border-radius: 3px;
        }}
        QLabel#pinNumberBadge[pinKind="data"] {{
            border-radius: 14px;
        }}

        QToolButton#pinCopyButton {{
            border: 1px solid {Colors.BORDER_LIGHT};
            border-radius: 6px;
            background-color: {Colors.BG_HEADER};
            color: {Colors.TEXT_SECONDARY};
            padding: 0px;
        }}
        QToolButton#pinCopyButton:hover {{
            border-color: {Colors.PRIMARY};
            background-color: {Colors.BG_CARD_HOVER};
            color: {Colors.TEXT_PRIMARY};
        }}

        QLabel#pinTypeTag {{
            background-color: {Colors.BG_HEADER};
            color: {Colors.TEXT_SECONDARY};
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 10px;
            border: 1px solid {Colors.BORDER_LIGHT};
        }}
        QLabel#pinTypeTag[isUnset="true"] {{
            border: 1px solid {Colors.WARNING};
            color: {Colors.WARNING};
        }}

        QComboBox#pinTypeCombo {{
            background-color: {Colors.BG_HEADER};
            color: {Colors.TEXT_SECONDARY};
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 10px;
            border: 1px solid {Colors.BORDER_LIGHT};
        }}
        QComboBox#pinTypeCombo:focus {{
            border-color: {Colors.PRIMARY};
        }}
        QComboBox#pinTypeCombo QAbstractItemView {{
            background-color: {Colors.BG_CARD};
            color: {Colors.TEXT_PRIMARY};
            selection-background-color: {Colors.BG_CARD_HOVER};
        }}

        QLineEdit#pinNameEdit {{
            font-size: 13px;
            color: {Colors.TEXT_PRIMARY};
            font-weight: bold;
            border: 1px solid {Colors.PRIMARY};
            background-color: {Colors.BG_INPUT};
            padding: 2px 4px;
        }}

        QWidget#pinListPanel {{
            background-color: {Colors.BG_CARD};
        }}
        QLabel#pinListTitle {{
            font-size: 12px;
            font-weight: bold;
            padding: 5px;
            color: {Colors.TEXT_PRIMARY};
        }}
        QScrollArea#pinListScrollArea {{
            background-color: transparent;
            border: none;
        }}
        QLabel#pinListHeaderPrefix {{
            color: {Colors.TEXT_SECONDARY};
            font-size: 11px;
        }}
        QLabel#pinListHeaderName {{
            color: {Colors.TEXT_PRIMARY};
            font-size: 12px;
            font-weight: bold;
        }}
        QLabel#pinListGroupLabel {{
            font-size: 11px;
            font-weight: bold;
            color: {Colors.TEXT_SECONDARY};
            padding: 8px 4px 4px 4px;
        }}
    """


def execution_monitor_style() -> str:
    """执行监控面板（ExecutionMonitorPanel）专用紧凑样式。

    说明：
    - 仅命中 ExecutionMonitorPanel 范围内的控件，不影响其它页面；
    - 按钮配色由全局 `button_style()` 的 `kind` 变体统一管理，这里只做“紧凑尺寸/小控件”收敛。
    """
    return f"""
        ExecutionMonitorPanel QPushButton {{
            padding: 2px 10px;
            font-size: 11px;
            min-height: 28px;
        }}

        ExecutionMonitorPanel QCheckBox {{
            font-size: 11px;
            padding: 0px 4px;
            margin-left: 4px;
        }}

        ExecutionMonitorPanel QToolButton {{
            border: 1px solid {Colors.BORDER_LIGHT};
            background-color: {Colors.BG_CARD};
            color: {Colors.TEXT_PRIMARY};
            border-radius: 6px;
            padding: 4px 8px;
            font-size: 11px;
            font-weight: bold;
        }}
        ExecutionMonitorPanel QToolButton:hover {{
            background-color: {Colors.BG_CARD_HOVER};
        }}

        ExecutionMonitorPanel QLabel[muted="true"] {{
            color: {Colors.TEXT_SECONDARY};
        }}
    """


