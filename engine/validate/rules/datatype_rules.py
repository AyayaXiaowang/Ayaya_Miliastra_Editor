"""验证层数据类型规则（兼容入口）。

说明：
- 历史上 validate/configs 各自维护过一份数据类型清单，容易漂移；
- 现在类型体系的唯一事实来源为 `engine.type_registry`；
- 本模块仅保留旧导入路径 `engine.validate.rules.datatype_rules`，避免历史代码/测试断链。
"""

from engine.type_registry import (  # noqa: F401
    BASE_TYPES,
    LIST_TYPES,
    TYPE_CONVERSIONS,
    can_convert_type,
    get_type_default,
    get_type_info,
)

