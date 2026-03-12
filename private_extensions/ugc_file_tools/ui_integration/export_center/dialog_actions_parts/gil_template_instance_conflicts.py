"""模板/实体冲突检查（兼容薄转发层）。"""

from .gil_instance_conflicts import resolve_gil_instance_conflicts
from .gil_template_conflicts import resolve_gil_template_conflicts

__all__ = ["resolve_gil_instance_conflicts", "resolve_gil_template_conflicts"]

