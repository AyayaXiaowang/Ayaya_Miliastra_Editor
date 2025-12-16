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
    return f"color: {Colors.TEXT_PLACEHOLDER}; padding: 10px; background-color: {Colors.BG_DARK};"


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
    """Toast 内容卡片样式。"""
    return f"""
        #toastContent {{
            background-color: {Colors.BG_CARD};
            border: 1px solid {Colors.BORDER_LIGHT};
            border-radius: {Sizes.RADIUS_MEDIUM}px;
        }}
    """


