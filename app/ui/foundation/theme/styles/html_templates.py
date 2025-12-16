"""HTML style templates reused across panels."""

from app.ui.foundation.theme.tokens import Colors, Sizes


class HTMLStyles:
    """富文本 HTML 片段模板。"""

    @staticmethod
    def base_style() -> str:
        return f"""
        <html>
        <head>
        <style>
            body {{
                background-color: {Colors.BG_CARD};
                color: {Colors.TEXT_PRIMARY};
                font-size: {Sizes.FONT_SMALL}pt;
                line-height: {Sizes.LINE_HEIGHT_NORMAL};
                margin: 0;
                padding: {Sizes.PADDING_MEDIUM}px;
            }}
            h1, h2, h3 {{
                color: {Colors.PRIMARY};
                margin-top: {Sizes.SPACING_MEDIUM}px;
                margin-bottom: {Sizes.SPACING_SMALL}px;
            }}
            p {{
                color: {Colors.TEXT_PRIMARY};
                margin: {Sizes.SPACING_SMALL}px 0;
            }}
            code {{
                background-color: {Colors.BG_MAIN};
                color: {Colors.ERROR};
                padding: 2px 6px;
                border-radius: {Sizes.RADIUS_SMALL}px;
                font-family: 'Consolas', monospace;
            }}
            table {{
                background-color: {Colors.BG_CARD};
                color: {Colors.TEXT_PRIMARY};
                border-collapse: collapse;
                width: 100%;
                margin: {Sizes.SPACING_MEDIUM}px 0;
            }}
            th, td {{
                color: {Colors.TEXT_PRIMARY};
                padding: {Sizes.PADDING_SMALL}px;
                text-align: left;
                border-bottom: 1px solid {Colors.DIVIDER};
            }}
            th {{
                background-color: {Colors.BG_HEADER};
                font-weight: bold;
            }}
            tr:hover {{
                background-color: {Colors.BG_CARD_HOVER};
            }}
            ul, ol {{
                color: {Colors.TEXT_PRIMARY};
                margin: {Sizes.SPACING_MEDIUM}px 0;
                padding-left: 25px;
            }}
            li {{
                color: {Colors.TEXT_PRIMARY};
                margin: {Sizes.SPACING_SMALL}px 0;
            }}
            b, strong {{
                color: {Colors.PRIMARY_DARK};
            }}
            .info-box {{
                background-color: {Colors.INFO_BG};
                border-left: 4px solid {Colors.INFO};
                padding: {Sizes.PADDING_MEDIUM}px;
                border-radius: {Sizes.RADIUS_SMALL}px;
                margin: {Sizes.SPACING_MEDIUM}px 0;
            }}
            .success-box {{
                background-color: {Colors.SUCCESS_BG};
                border-left: 4px solid {Colors.SUCCESS};
                padding: {Sizes.PADDING_MEDIUM}px;
                border-radius: {Sizes.RADIUS_SMALL}px;
                margin: {Sizes.SPACING_MEDIUM}px 0;
            }}
            .warning-box {{
                background-color: {Colors.WARNING_BG};
                border-left: 4px solid {Colors.WARNING};
                padding: {Sizes.PADDING_MEDIUM}px;
                border-radius: {Sizes.RADIUS_SMALL}px;
                margin: {Sizes.SPACING_MEDIUM}px 0;
            }}
            .error-box {{
                background-color: {Colors.ERROR_BG};
                border-left: 4px solid {Colors.ERROR};
                padding: {Sizes.PADDING_MEDIUM}px;
                border-radius: {Sizes.RADIUS_SMALL}px;
                margin: {Sizes.SPACING_MEDIUM}px 0;
            }}
            .badge {{
                background-color: {Colors.INFO};
                color: {Colors.TEXT_ON_PRIMARY};
                padding: 4px 8px;
                border-radius: {Sizes.RADIUS_SMALL}px;
                display: inline-block;
                font-size: {Sizes.FONT_SMALL}pt;
            }}
        </style>
        </head>
        <body>
        """

    @staticmethod
    def footer() -> str:
        return """
        </body>
        </html>
        """


