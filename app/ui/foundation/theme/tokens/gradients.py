"""Gradient helpers represented as qlineargradient strings."""

from ui.foundation.theme.tokens.colors import Colors


class Gradients:
    """预定义渐变组合。"""

    @staticmethod
    def primary_horizontal() -> str:
        # 单色系水平渐变：从主色过渡到浅主色，整体更柔和
        return (
            f"qlineargradient("
            f"x1:0, y1:0, x2:1, y2:0, "
            f"stop:0 {Colors.PRIMARY}, stop:1 {Colors.PRIMARY_LIGHT}"
            f")"
        )

    @staticmethod
    def primary_vertical() -> str:
        # 单色系垂直渐变：顶部略深，底部略浅，但整体保持低饱和
        return (
            f"qlineargradient("
            f"x1:0, y1:0, x2:0, y2:1, "
            f"stop:0 {Colors.PRIMARY}, stop:1 {Colors.PRIMARY_LIGHT}"
            f")"
        )

    @staticmethod
    def card() -> str:
        return (
            f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {Colors.BG_CARD}, stop:1 {Colors.BG_CARD_HOVER})"
        )

    @staticmethod
    def badge() -> str:
        return (
            f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {Colors.PRIMARY}, stop:1 {Colors.INFO_LIGHT})"
        )

    @staticmethod
    def button() -> str:
        return (
            f"qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {Colors.PRIMARY_LIGHT}, stop:1 {Colors.PRIMARY})"
        )


