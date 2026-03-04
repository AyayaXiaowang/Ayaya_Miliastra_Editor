"""复合节点代码生成器（私有扩展侧薄转发）。

说明：
- `app/codegen/composite_code_generator.py` 是单一真源（主程序/工具层）。
- `ugc_file_tools` 侧不再维护一份重复实现，避免两处漂移。

注意：
- 该模块依赖仓库根目录在 `sys.path` 中（见 `private_extensions/run_ugc_file_tools.py` 的入口约定）。
"""

from __future__ import annotations

from app.codegen.composite_code_generator import CompositeCodeGenerator

__all__ = ["CompositeCodeGenerator"]
