from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional, Tuple
from uuid import uuid4

from engine.configs.components.ui_control_group_model import (
    UIControlGroupTemplate,
    UILayout,
    UIWidgetConfig,
    create_builtin_widget_templates,
    create_default_layout,
)


class UIControlGroupStore:
    """集中维护布局与模板数据，提供快速索引。"""

    def __init__(self) -> None:
        self.layouts: Dict[str, UILayout] = {}
        self.templates: Dict[str, UIControlGroupTemplate] = {}
        self.widget_index: Dict[str, Tuple[UIControlGroupTemplate, UIWidgetConfig]] = {}

    def load_from_package(self, package) -> None:
        self.layouts.clear()
        self.templates.clear()
        if not package:
            return

        layouts_data = package.management.ui_layouts or {}
        for layout_id, layout_data in layouts_data.items():
            self.layouts[layout_id] = UILayout.deserialize(layout_data)

        templates_data = package.management.ui_widget_templates or {}
        for template_id, template_data in templates_data.items():
            template = UIControlGroupTemplate.deserialize(template_data)
            if template is not None:
                self.templates[template_id] = template

        if not self.layouts:
            self._install_default_setup()

        self.rebuild_widget_index()

    def save_to_package(self, package) -> None:
        if not package:
            return
        package.management.ui_layouts = {
            layout_id: layout.serialize() for layout_id, layout in self.layouts.items()
        }
        package.management.ui_widget_templates = {
            template_id: template.serialize() for template_id, template in self.templates.items()
        }

    def rebuild_widget_index(self) -> None:
        self.widget_index.clear()
        for template in self.templates.values():
            for widget in template.widgets:
                self.widget_index[widget.widget_id] = (template, widget)

    def find_widget(self, widget_id: str) -> Tuple[Optional[UIControlGroupTemplate], Optional[UIWidgetConfig]]:
        return self.widget_index.get(widget_id, (None, None))

    def generate_layout_id(self) -> str:
        while True:
            candidate = f"layout_{uuid4().hex[:8]}"
            if candidate not in self.layouts:
                return candidate

    def generate_template_id(self, prefix: str = "template_custom") -> str:
        while True:
            candidate = f"{prefix}_{uuid4().hex[:8]}"
            if candidate not in self.templates:
                return candidate

    def _install_default_setup(self) -> None:
        default_layout = create_default_layout()
        builtin_templates = create_builtin_widget_templates()
        for template_id in builtin_templates.keys():
            default_layout.builtin_widgets.append(template_id)
        self.layouts[default_layout.layout_id] = default_layout
        self.templates.update(builtin_templates)

    def remove_template_from_layouts(self, template_id: str) -> bool:
        changed = False
        for layout in self.layouts.values():
            if template_id in layout.builtin_widgets:
                layout.builtin_widgets.remove(template_id)
                layout.visibility_overrides.pop(template_id, None)
                layout.updated_at = datetime.now().isoformat()
                changed = True
            if template_id in layout.custom_groups:
                layout.custom_groups.remove(template_id)
                layout.visibility_overrides.pop(template_id, None)
                layout.updated_at = datetime.now().isoformat()
                changed = True
        return changed

