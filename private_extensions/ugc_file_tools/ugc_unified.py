from __future__ import annotations

import sys
from pathlib import Path

# 兼容：允许以脚本方式运行 `python ugc_file_tools/ugc_unified.py ...`
if __package__ is None:
    # 运行方式兼容：
    # - `engine` 位于仓库根目录
    # - `ugc_file_tools` 位于 `private_extensions/`
    this_file = Path(__file__).resolve()
    repo_root = this_file.parents[2]
    private_extensions = this_file.parents[1]
    for p in (repo_root, private_extensions):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

from ugc_file_tools.unified_cli import main

__all__ = ["main"]


if __name__ == "__main__":
    main()


