from __future__ import annotations

# UI domain package marker.

"""
UI domain package.

约定：
- UI records / guid resolution / readable dump 等“UI 域逻辑”集中放在这里。
- 与 Graph_Generater 运行时缓存（engine.utils.cache.*）等集成相关的代码，后续可按需下沉到 `integrations/` 子包。
"""

# Public facade functions are defined in individual modules (e.g. `readable_dump.py`).
