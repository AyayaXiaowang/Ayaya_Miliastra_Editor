from __future__ import annotations

"""
兼容入口：
- 库代码与历史 import 仍以 `ugc_file_tools.decode_gil` 为准（避免核心库反向依赖 commands/）。
- 统一工具转发（`ugc_file_tools tool decode_gil ...`）要求工具模块位于 `ugc_file_tools.commands` 下，
  因此这里提供一个薄 wrapper，将 main 转发到包根实现。
"""

from ugc_file_tools.decode_gil import main

__all__ = ["main"]


if __name__ == "__main__":
    main()


