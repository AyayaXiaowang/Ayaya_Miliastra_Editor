"""端口类型匹配相关规则（门面）。

为降低单文件体积，规则实现已拆分到：
- `code_port_types_match_port_types_rule.py`：`PortTypesMatchRule`
- `code_port_types_match_same_type_rule.py`：`SameTypeInputsRule`
- `code_port_types_match_shared.py`：AST/类型相关共享工具

本文件保留稳定导入路径：
`from engine.validate.rules.code_port_types_match import PortTypesMatchRule, SameTypeInputsRule`
"""

from __future__ import annotations

from .code_port_types_match_port_types_rule import PortTypesMatchRule
from .code_port_types_match_same_type_rule import SameTypeInputsRule

__all__ = ["PortTypesMatchRule", "SameTypeInputsRule"]

