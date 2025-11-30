"""Inline text style helpers."""

from ui.foundation.theme.tokens import Colors, Sizes


def heading(level: int = 3) -> str:
    if level == 1:
        size = Sizes.FONT_DISPLAY
    elif level == 2:
        size = Sizes.FONT_HEADING
    elif level == 3:
        size = Sizes.FONT_TITLE
    else:
        size = Sizes.FONT_LARGE
    return f"font-weight: bold; font-size: {size}px;"


def semantic_success(font_size: int | None = None) -> str:
    size = font_size if font_size is not None else Sizes.FONT_LARGE
    return f"color: {Colors.SUCCESS}; font-weight: bold; font-size: {size}px;"


def semantic_error(font_size: int | None = None) -> str:
    size = font_size if font_size is not None else Sizes.FONT_LARGE
    return f"color: {Colors.ERROR}; font-weight: bold; font-size: {size}px;"


