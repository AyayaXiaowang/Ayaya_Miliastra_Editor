from __future__ import annotations

from pathlib import Path

from app.cli.auto_custom_variable_data_store_sync import AutoCustomVarSyncAction
from app.cli.auto_custom_variable_registry_refs_sync import (
    sync_auto_custom_variable_refs_from_registry,
)


def sync_auto_custom_variables_from_registry(
    *,
    workspace_root: Path,
    package_id: str,
    dry_run: bool,
) -> list[AutoCustomVarSyncAction]:
    """同步自定义变量注册表（refs-only）。

    说明：
    - 变量 Schema 真源为『自定义变量注册表.py』，引擎侧会派生虚拟变量文件；
    - 本命令只负责同步引用点（玩家模板/关卡实体/第三方存放实体）与必要的数据存放资源；
    - 不再生成/写入『自动分配_*.py』变量文件。
    """
    return sync_auto_custom_variable_refs_from_registry(
        workspace_root=workspace_root,
        package_id=package_id,
        dry_run=dry_run,
    )


__all__ = [
    "AutoCustomVarSyncAction",
    "sync_auto_custom_variables_from_registry",
]

