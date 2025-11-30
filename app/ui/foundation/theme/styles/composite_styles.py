"""Composite QSS snippets assembled from component styles."""

from collections.abc import Iterable

from ui.foundation.theme.styles import component_styles
from ui.foundation.theme.tokens import Colors, Sizes


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
    return _merge_segments(
        [
            "QWidget { background-color: #FFFFFF; }",
            component_styles.input_style(),
            component_styles.button_style(),
            component_styles.list_style(),
            component_styles.table_style(),
            component_styles.scrollbar_style(),
        ]
    )


def global_style() -> str:
    return _merge_segments(
        [
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


