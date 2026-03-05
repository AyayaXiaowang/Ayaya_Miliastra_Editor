from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def generate_graph_code_for_package_root(package_root_path: Path, *, overwrite: bool) -> Dict[str, Any]:
    """
    稳定 API：从项目存档目录生成 Graph Code（Python）。

    说明：
    - 具体实现位于库层 `ugc_file_tools.graph.code_generation_impl`；
    - `commands/generate_graph_code_from_package.py` 仅保留 CLI 薄入口。
    """
    from ugc_file_tools.graph.code_generation_impl import (
        generate_graph_code_for_package_root as _impl,
    )

    return _impl(Path(package_root_path), overwrite=bool(overwrite))


