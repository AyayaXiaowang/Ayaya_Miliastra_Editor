from __future__ import annotations

from typing import Dict, Optional

from engine.configs.components.ui_control_group_model import UIControlGroupTemplate
from ui.panels.ui_control_group_template_helpers import iter_template_preview_configs


def render_template_on_preview(
    preview_canvas,
    template: UIControlGroupTemplate,
    *,
    overrides: Optional[Dict[str, object]] = None,
    select_first: bool = False,
) -> None:
    """将模板绘制到预览画布，避免在多个面板重复逻辑。"""
    for widget_config in iter_template_preview_configs(template, overrides=overrides):
        preview_canvas.add_widget_preview(widget_config)
    if select_first and template.widgets:
        preview_canvas.select_widget(template.widgets[0].widget_id)