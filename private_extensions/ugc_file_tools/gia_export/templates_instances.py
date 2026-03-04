from __future__ import annotations

"""
ugc_file_tools.gia_export.templates_instances

“元件模板 + 实体摆放(实例)”类 `.gia` bundle 的导出/写回门面：
- component_to_entity / entity_to_component 双向转换（wire-level）
"""

from ugc_file_tools.gia.wire_templates_instances_convert import (  # noqa: F401
    convert_component_entity_bundle_gia_wire,
)

__all__ = ["convert_component_entity_bundle_gia_wire"]

