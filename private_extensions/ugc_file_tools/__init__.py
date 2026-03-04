from __future__ import annotations

"""
ugc_file_tools

这不是一个“纯库项目”，而是工具集合：多数能力以 CLI 的形式提供。

推荐入口：
- 统一入口：`python -X utf8 -m ugc_file_tools --help`
- 单工具入口：见 `ugc_file_tools/tools/工具索引.md`
"""

def _ensure_importable_as_top_level_package() -> None:
    """
    兼容两种导入方式：
    - canonical：`import ugc_file_tools.*`（需要 `private_extensions/` 在 sys.path 中）
    - 研发期：`import private_extensions.ugc_file_tools.*`

    部分模块使用 `ugc_file_tools.*` 的绝对导入；当以 `private_extensions.ugc_file_tools.*` 方式导入时，
    这里会将当前包 alias 到 `sys.modules['ugc_file_tools']`，避免加载第二份重复模块树。
    """
    import sys
    from pathlib import Path

    # 若当前包名为 private_extensions.ugc_file_tools，则把其 alias 成顶层 ugc_file_tools
    if not str(__name__).startswith("private_extensions."):
        return

    sys.modules.setdefault("ugc_file_tools", sys.modules[__name__])

    # 同时补齐 import root（仅用于少数“从 repo root 直接运行某个私有脚本”的场景）
    private_extensions_root = Path(__file__).resolve().parents[1]
    workspace_root = private_extensions_root.parent
    for p in (private_extensions_root, workspace_root):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)


_ensure_importable_as_top_level_package()


