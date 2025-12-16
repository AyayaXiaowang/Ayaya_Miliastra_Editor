"""Composite QSS snippets assembled from component styles."""

from collections.abc import Iterable

from app.ui.foundation.theme.styles import component_styles
from app.ui.foundation.theme.tokens import Colors, Sizes


def _merge_segments(segments: Iterable[str]) -> str:
    return "\n".join(segment.strip() for segment in segments if segment)


def dialog_surface_style(
    *,
    include_inputs: bool = True,
    include_tables: bool = False,
    include_scrollbars: bool = True,
) -> str:
    segments: list[str] = [
        component_styles.dialog_style(),
        component_styles.button_style(),
    ]
    if include_inputs:
        segments.extend(
            [
                component_styles.input_style(),
                component_styles.combo_box_style(),
                component_styles.spin_box_style(),
            ]
        )
    if include_tables:
        segments.append(component_styles.table_style())
    if include_scrollbars:
        segments.append(component_styles.scrollbar_style())
    return _merge_segments(segments)


def dialog_form_style() -> str:
    return f"""
        QDialog {{
            background-color: {Colors.BG_CARD};
        }}
        {component_styles.button_style()}
        {component_styles.input_style()}
        {component_styles.scrollbar_style()}
        {component_styles.combo_box_style()}
        {component_styles.spin_box_style()}
    """


def card_list_style() -> str:
    return f"""
        QWidget {{
            background-color: {Colors.BG_CARD};
            border: 1px solid {Colors.BORDER_LIGHT};
            border-radius: {Sizes.RADIUS_MEDIUM}px;
        }}
        QWidget:hover {{
            border-color: {Colors.PRIMARY};
            background-color: {Colors.BG_CARD_HOVER};
        }}
        {component_styles.scrollbar_style()}
    """


def panel_style() -> str:
    base_panel = f"""
        QWidget {{
            background-color: {Colors.BG_MAIN};
            color: {Colors.TEXT_PRIMARY};
        }}
        QLabel {{
            color: {Colors.TEXT_PRIMARY};
        }}
    """
    return _merge_segments(
        [
            base_panel,
            component_styles.input_style(),
            component_styles.button_style(),
            component_styles.list_style(),
            component_styles.table_style(),
            component_styles.scrollbar_style(),
        ]
    )


def global_style() -> str:
    base = f"""
        QLabel {{
            color: {Colors.TEXT_PRIMARY};
        }}
        QCheckBox, QRadioButton {{
            color: {Colors.TEXT_PRIMARY};
        }}
        QToolBar {{
            background-color: {Colors.BG_HEADER};
            border: none;
        }}
        QToolButton {{
            color: {Colors.TEXT_PRIMARY};
            background: transparent;
            padding: {Sizes.PADDING_SMALL}px {Sizes.PADDING_MEDIUM}px;
            border-radius: {Sizes.RADIUS_SMALL}px;
        }}
        QToolButton:hover {{
            background-color: {Colors.BG_CARD_HOVER};
        }}
        QToolButton:pressed {{
            background-color: {Colors.BG_SELECTED};
            color: {Colors.TEXT_ON_PRIMARY};
        }}
        QScrollArea {{
            background-color: {Colors.BG_MAIN};
            border: none;
        }}
        QScrollArea > QWidget {{
            background-color: {Colors.BG_MAIN};
        }}
        QScrollArea > QWidget > QWidget {{
            background-color: {Colors.BG_MAIN};
        }}
    """
    return _merge_segments(
        [
            base,
            component_styles.button_style(),
            component_styles.input_style(),
            component_styles.tree_style(),
            component_styles.list_style(),
            component_styles.left_panel_style(),
            component_styles.table_style(),
            component_styles.scrollbar_style(),
            component_styles.tab_style(),
            component_styles.splitter_style(),
            component_styles.combo_box_style(),
            component_styles.spin_box_style(),
            component_styles.group_box_style(),
            component_styles.dialog_style(),
        ]
    )


