# -*- coding: utf-8 -*-
"""
port_type_inference: 端口类型推断官方入口层（facade）。

说明：
- 原始的端口类型推断逻辑拆分在多个子模块中（`port_type_common` / `port_type_context`
  / `port_type_generics` / `port_type_dicts`），这些子模块属于 `app.automation.ports` 包内部实现；
- 本模块作为对外唯一推荐的导入入口，统一 re-export 这些子模块通过各自 `__all__`
  暴露的公共符号，并保持 `app.automation.ports.port_type_inference` 路径的长期稳定；
- `app.automation.ports` 以外的模块，如需使用端口类型推断相关工具，应始终从本模块导入；
- 在本包内部，若只需要公共 API，亦推荐优先经由本模块导入，只有在需要访问下划线
  工具或更细粒度实现细节时才直接依赖子模块。
"""

from __future__ import annotations

from typing import List

from app.automation.ports import port_type_common as _port_type_common
from app.automation.ports import port_type_context as _port_type_context
from app.automation.ports import port_type_generics as _port_type_generics
from app.automation.ports import port_type_dicts as _port_type_dicts
from app.automation.ports import _struct_field_types as _struct_field_types

# 通过子模块的 __all__ 定义统一聚合公共 API，并在本模块命名空间下 re-export。
# 这样新增公共函数时只需在子模块维护一次 __all__，本入口层会自动跟进。
from app.automation.ports.port_type_common import *  # noqa: F401,F403
from app.automation.ports.port_type_context import *  # noqa: F401,F403
from app.automation.ports.port_type_generics import *  # noqa: F401,F403
from app.automation.ports.port_type_dicts import *  # noqa: F401,F403
from app.automation.ports._struct_field_types import *  # noqa: F401,F403


def _collect_public_names() -> List[str]:
    modules = [
        _port_type_common,
        _port_type_context,
        _port_type_generics,
        _port_type_dicts,
        _struct_field_types,
    ]
    names: List[str] = []
    for module in modules:
        module_all = getattr(module, "__all__", [])
        if not isinstance(module_all, (list, tuple)):
            continue
        for item in module_all:
            if not isinstance(item, str):
                continue
            text = item.strip()
            if text == "":
                continue
            names.append(text)
    # 通过通用工具按首次出现顺序去重，保证导出符号顺序稳定。
    return _port_type_common.unique_preserve_order(names)


__all__ = _collect_public_names()

# 避免在模块外部误用内部聚合辅助函数
del _collect_public_names


