from __future__ import annotations

from pathlib import Path
from typing import List

from engine.nodes.composite_file_policy import discover_scoped_composite_definition_files
from engine.utils.runtime_scope import get_active_package_id


def discover_composite_files(workspace_path: Path) -> List[Path]:
    """
    发现复合节点定义文件（不导入）。

    路径约定：任一资源根目录下 `复合节点库/**/*.py`：
    - `assets/资源库/共享/复合节点库/**/*.py`
    - `assets/资源库/项目存档/<package_id>/复合节点库/**/*.py`

    注意：实际发现范围遵循运行期作用域 `active_package_id`（共享根 + 当前项目存档根）：
    - active_package_id=None：仅共享根
    - active_package_id=str：共享根 + 指定项目存档根
    """
    # 关键：复合节点按“共享根 + 当前项目存档根”作用域加载，避免跨项目存档重复节点名/ID
    # 在 NodeRegistry 构建阶段产生冲突或误覆盖。
    active_package_id = get_active_package_id()
    return discover_scoped_composite_definition_files(
        workspace_path,
        active_package_id=active_package_id,
    )

