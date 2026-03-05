from __future__ import annotations

# 兼容路径：本文件仅作为薄门面层保留稳定导入路径。
# 变量类型推断/显式类型标注/自定义变量 item 构造的单一真源已迁移到 `ugc_file_tools.custom_variables.specs`。

from ugc_file_tools.custom_variables.specs import (  # noqa: PLC2701
    CustomVariableSpec,
    build_custom_variable_item_from_spec,
    extract_explicit_type_text_from_variable_name,
    infer_custom_variable_spec_from_default,
)

__all__ = [
    "CustomVariableSpec",
    "build_custom_variable_item_from_spec",
    "extract_explicit_type_text_from_variable_name",
    "infer_custom_variable_spec_from_default",
]

