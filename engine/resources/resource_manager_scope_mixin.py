from __future__ import annotations

from pathlib import Path
from typing import List

from engine.utils.resource_library_layout import get_packages_root_dir, get_shared_root_dir


class ResourceManagerScopeMixin:
    """ResourceManager 的作用域（active_package_id）相关方法。"""

    def set_active_package_id(self, package_id: str | None) -> None:
        """切换资源索引的项目存档作用域。

        设计约定：
        - 目录即项目存档：资源 ID 只要求在“共享根”或“单个项目存档根目录”内唯一；
        - 因此 ResourceManager 的资源索引必须在“共享 + 当前项目存档”范围内构建。

        注意：该方法仅更新作用域与清理进程内缓存；调用方如需立即生效，应随后调用 `rebuild_index()`。
        """
        normalized = str(package_id or "").strip()
        # UI 特殊视图 ID：不绑定任何项目存档，只扫描共享根目录
        if normalized in {"global_view", "unclassified_view"}:
            normalized = ""

        normalized_or_none: str | None = normalized or None
        if normalized_or_none == self._active_package_id:
            return

        self._active_package_id = normalized_or_none
        self._resource_index_builder.set_active_package_id(self._active_package_id)

        # 同步运行期作用域（进程内全局）：供复合节点扫描、节点指纹等模块读取。
        from engine.utils.runtime_scope import set_active_package_id as set_runtime_active_package_id

        set_runtime_active_package_id(self._active_package_id)

        # 同步代码级 Schema 作用域（结构体/信号等）：避免跨项目存档重复 ID 导致的歧义与启动期崩溃。
        # 说明：DefinitionSchemaView 自身会在作用域变化时失效缓存；这里同时失效仓库级派生缓存，避免复用旧 payload。
        from engine.resources.definition_schema_view import (
            set_default_definition_schema_view_active_package_id,
        )
        from engine.resources.level_variable_schema_view import (
            set_default_level_variable_schema_view_active_package_id,
        )
        from engine.resources.ingame_save_template_schema_view import (
            set_default_ingame_save_template_schema_view_active_package_id,
        )
        from engine.signal import invalidate_default_signal_repository_cache
        from engine.struct import invalidate_default_struct_repository_cache

        set_default_definition_schema_view_active_package_id(self._active_package_id)
        set_default_level_variable_schema_view_active_package_id(self._active_package_id)
        set_default_ingame_save_template_schema_view_active_package_id(self._active_package_id)
        invalidate_default_signal_repository_cache()
        invalidate_default_struct_repository_cache()

        # 关键：跨项目存档允许同 ID 后，缓存必须随作用域切换清空，否则会复用到上一项目的 payload。
        self.clear_cache()

    def get_current_resource_roots(self) -> List[Path]:
        """返回当前 ResourceManager 作用域内的资源根目录列表。

        设计约定：
        - 目录即项目存档：资源索引与列表/加载操作应限定在（共享根 + 当前项目存档根）范围内；
        - global_view / unclassified_view：仅使用共享根目录。

        Returns:
            资源根目录列表（顺序稳定：共享根在前，项目存档根在后）。
        """
        roots: List[Path] = []
        shared_root = get_shared_root_dir(self.resource_library_dir)
        roots.append(shared_root)

        active_package_id = str(self._active_package_id or "").strip()
        if active_package_id:
            package_root_dir = get_packages_root_dir(self.resource_library_dir) / active_package_id
            roots.append(package_root_dir)

        return roots



