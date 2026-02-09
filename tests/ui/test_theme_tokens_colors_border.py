from __future__ import annotations

import pytest

from app.ui.foundation.theme.tokens.colors import Colors


@pytest.fixture
def restore_colors_tokens() -> None:
    before_tokens = {
        name: getattr(Colors, name)
        for name in dir(Colors)
        if name.isupper()
    }
    before_is_dark = Colors.IS_DARK

    yield

    for name, value in before_tokens.items():
        setattr(Colors, name, value)
    Colors.IS_DARK = before_is_dark


def test_colors_border_token_exists_and_follows_border_normal(restore_colors_tokens: None) -> None:
    assert hasattr(Colors, "BORDER")

    Colors.apply_theme_palette("light")
    assert Colors.BORDER == Colors.BORDER_NORMAL
    assert Colors.IS_DARK is False

    Colors.apply_theme_palette("dark")
    assert Colors.BORDER == Colors.BORDER_NORMAL
    assert Colors.IS_DARK is True

