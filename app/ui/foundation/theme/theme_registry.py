"""Central registry exposing theme tokens."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

from ui.foundation.theme.tokens import Colors, Sizes, Icons, Gradients


TokenKind = Literal["colors", "sizes", "icons", "gradients"]


@dataclass(frozen=True)
class ThemePalette:
    """Typed view of the token namespaces."""

    colors: type[Colors]
    sizes: type[Sizes]
    icons: type[Icons]
    gradients: type[Gradients]


class ThemeRegistry:
    """Global registry for theme tokens and palette accessors."""

    colors: type[Colors] = Colors
    sizes: type[Sizes] = Sizes
    icons: type[Icons] = Icons
    gradients: type[Gradients] = Gradients

    _palette = ThemePalette(colors=colors, sizes=sizes, icons=icons, gradients=gradients)
    _token_aliases: Mapping[str, TokenKind] = {
        "color": "colors",
        "size": "sizes",
        "icon": "icons",
        "gradient": "gradients",
    }

    @classmethod
    def palette(cls) -> ThemePalette:
        """Return the aggregate palette."""
        return cls._palette

    @classmethod
    def resolve(cls, token_kind: TokenKind | str):
        """Resolve a token namespace by name."""
        if token_kind in ("colors", "sizes", "icons", "gradients"):
            return getattr(cls, token_kind)
        alias = cls._token_aliases.get(token_kind)
        if alias:
            return getattr(cls, alias)
        raise KeyError(f"Unknown theme token namespace: {token_kind}")


