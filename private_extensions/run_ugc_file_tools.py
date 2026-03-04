from __future__ import annotations

import sys
from pathlib import Path


def _ensure_private_extensions_importable() -> None:
    """
    让仓库根目录 + `private_extensions/` 均可作为 Python import root：
    - 使 `import engine/app/*` 与 `import ugc_file_tools.*` 在任意工作目录下都可用
    - 便于从仓库根目录稳定运行 ugc_file_tools 的 CLI（不依赖 PYTHONPATH）
    """
    private_extensions_root = Path(__file__).resolve().parent
    workspace_root = private_extensions_root.parent

    # 插入顺序：先插 private_extensions，再插 workspace_root，
    # 使得 workspace_root 最终位于 sys.path[0]（优先解析主程序代码，如 engine/app）。
    for import_root in (private_extensions_root, workspace_root):
        root_text = str(import_root)
        if root_text not in sys.path:
            sys.path.insert(0, root_text)


def main(argv: list[str] | None = None) -> None:
    _ensure_private_extensions_importable()

    from ugc_file_tools.unified_cli import main as unified_main

    unified_main(argv if argv is not None else sys.argv[1:])


if __name__ == "__main__":
    main()


