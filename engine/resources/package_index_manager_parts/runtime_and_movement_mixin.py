"""PackageIndexManager：运行期状态 + 资源归属移动职责拆分。"""

from __future__ import annotations

import json
from pathlib import Path

from engine.configs.resource_types import ResourceType
from engine.resources.atomic_json import atomic_write_json
from engine.utils.resource_library_layout import (
    find_containing_resource_root,
    get_default_unclassified_package_root_dir,
    get_packages_root_dir,
    get_shared_root_dir,
)


class PackageIndexRuntimeAndMovementMixin:
    def set_last_opened_package(self, package_id: str | None) -> None:
        """设置最近打开的存档。"""
        state = self._load_runtime_package_state()
        previous_last_opened = state.get("last_opened_package_id")
        if previous_last_opened == package_id:
            return

        state["last_opened_package_id"] = package_id
        self._save_runtime_package_state(state)

    def get_last_opened_package(self) -> str | None:
        """获取最近打开的存档ID。"""
        state = self._load_runtime_package_state()
        last_package_id = state.get("last_opened_package_id")

        # 支持特殊视图（不需要在存档列表中验证存在性）
        if last_package_id == "global_view":
            return last_package_id

        # 验证这个存档是否还存在
        if last_package_id:
            package_info = self.get_package_info(last_package_id)
            if package_info:
                return last_package_id

        return None

    def _load_runtime_package_state(self) -> dict:
        if self._package_state_file.exists():
            with open(self._package_state_file, "r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
            return data if isinstance(data, dict) else {}
        return {}

    def _save_runtime_package_state(self, data: dict) -> None:
        normalized = data if isinstance(data, dict) else {}
        atomic_write_json(self._package_state_file, normalized, ensure_ascii=False, indent=2)

    def add_resource_to_package(self, package_id: str, resource_type: str, resource_id: str) -> bool:
        """添加资源到存档（目录即存档：语义等价于把文件移动到该存档根目录）。"""
        target_root = self._packages_root_dir / str(package_id)
        if not target_root.exists() or not target_root.is_dir():
            return False
        return self._move_resource_file_to_target_root(
            resource_type=resource_type,
            resource_id=resource_id,
            target_root=target_root,
        )

    def move_resource_to_root(self, target_root_id: str, resource_type: str, resource_id: str) -> bool:
        """将资源移动到指定“资源根目录”。

        约定：
        - target_root_id == "shared"：移动到 `assets/资源库/共享/`
        - 其它值：视为项目存档目录名，移动到 `assets/资源库/项目存档/<package_id>/`
        """
        resource_library_root = self.workspace_path / "assets" / "资源库"
        target_root_id_text = str(target_root_id or "").strip()
        if not target_root_id_text:
            return False

        if target_root_id_text == "shared":
            target_root = get_shared_root_dir(resource_library_root)
            target_root.mkdir(parents=True, exist_ok=True)
        else:
            target_root = self._packages_root_dir / target_root_id_text
            if not target_root.exists() or not target_root.is_dir():
                return False

        current_owner = self.get_resource_owner_root_id(resource_type=resource_type, resource_id=resource_id)
        if current_owner and current_owner == target_root_id_text:
            # 已在目标根目录下：不需要执行移动，避免触发去重逻辑误删源文件。
            return True

        return self._move_resource_file_to_target_root(
            resource_type=resource_type,
            resource_id=resource_id,
            target_root=target_root,
        )

    def get_resource_owner_root_id(self, *, resource_type: str, resource_id: str) -> str:
        """返回资源当前所属的资源根目录 ID（用于 UI 的“归属位置”选择器）。"""
        file_path = self._resolve_physical_file_path(resource_type=resource_type, resource_id=resource_id)
        if file_path is None or not file_path.exists():
            return ""

        resource_library_root = self.workspace_path / "assets" / "资源库"
        containing_root = find_containing_resource_root(resource_library_root, file_path)
        if containing_root is None:
            return ""

        shared_root = get_shared_root_dir(resource_library_root)
        if containing_root.resolve() == shared_root.resolve():
            return "shared"

        packages_root = get_packages_root_dir(resource_library_root)
        if containing_root.parent.resolve() == packages_root.resolve():
            return containing_root.name

        return ""

    def remove_resource_from_package(self, package_id: str, resource_type: str, resource_id: str) -> bool:
        """从存档移除资源（目录即存档：语义等价于移动到默认归档项目存档）。"""
        _ = package_id
        target_root = get_default_unclassified_package_root_dir(self.workspace_path / "assets" / "资源库")
        target_root.mkdir(parents=True, exist_ok=True)
        return self._move_resource_file_to_target_root(
            resource_type=resource_type,
            resource_id=resource_id,
            target_root=target_root,
        )

    def _move_resource_file_to_target_root(self, *, resource_type: str, resource_id: str, target_root: Path) -> bool:
        """将给定资源的物理文件移动到目标项目存档根目录下，并保持其在资源根内的相对路径不变。"""
        file_path = self._resolve_physical_file_path(resource_type=resource_type, resource_id=resource_id)
        if file_path is None or not file_path.exists():
            return False

        resource_library_root = self.workspace_path / "assets" / "资源库"
        containing_root = find_containing_resource_root(resource_library_root, file_path)
        if containing_root is None:
            raise ValueError(f"无法判定资源文件所属的资源根目录：{file_path}")

        relative_path = file_path.resolve().relative_to(containing_root.resolve())
        target_path = (target_root / relative_path).resolve()

        # 目标路径与源路径一致：视为 no-op（避免命中“内容相同→删除源文件”的去重逻辑）。
        if target_path.resolve() == file_path.resolve():
            return True

        if target_path.exists():
            # 若内容完全相同则去重：删除源文件即可。
            if file_path.is_file() and target_path.is_file():
                if file_path.stat().st_size == target_path.stat().st_size:
                    if file_path.read_bytes() == target_path.read_bytes():
                        file_path.unlink()
                        self._after_resource_file_moved(resource_type=resource_type)
                        return True
            raise ValueError(f"目标文件已存在且内容不同，拒绝覆盖：{target_path}")

        target_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.rename(target_path)
        self._after_resource_file_moved(resource_type=resource_type)
        return True

    def _after_resource_file_moved(self, *, resource_type: str) -> None:
        # 资源文件位置变化：刷新资源索引（JSON/Graph/信号/结构体等）
        self.resource_manager.rebuild_index()

        # 代码级 Schema/Repository 需要显式失效，避免仍读取旧路径的缓存
        if resource_type == "management_level_variables":
            from engine.resources.level_variable_schema_view import invalidate_default_level_variable_cache

            invalidate_default_level_variable_cache()
        if resource_type == "management_save_points":
            from engine.resources.ingame_save_template_schema_view import (
                invalidate_default_ingame_save_template_cache,
            )

            invalidate_default_ingame_save_template_cache()
        if resource_type == "management_signals":
            from engine.signal import invalidate_default_signal_repository_cache

            invalidate_default_signal_repository_cache()
        if resource_type == "management_struct_definitions":
            from engine.struct import invalidate_default_struct_repository_cache

            invalidate_default_struct_repository_cache()

    def _resolve_physical_file_path(self, *, resource_type: str, resource_id: str) -> Path | None:
        """根据 UI 侧的 resource_type 文本与 resource_id，解析出磁盘上的物理文件路径。"""
        if not isinstance(resource_id, str) or not resource_id:
            return None

        if resource_type == "graph":
            return self.resource_manager.get_graph_file_path(resource_id)

        if resource_type == "template":
            return self.resource_manager.list_resource_file_paths(ResourceType.TEMPLATE).get(resource_id)
        if resource_type == "instance":
            return self.resource_manager.list_resource_file_paths(ResourceType.INSTANCE).get(resource_id)
        if resource_type.startswith("combat_"):
            preset_type = resource_type.replace("combat_", "")
            resource_type_enum = self._COMBAT_RESOURCE_TYPE_MAP.get(preset_type)
            if resource_type_enum is None:
                return None
            return self.resource_manager.list_resource_file_paths(resource_type_enum).get(resource_id)
        if resource_type.startswith("management_"):
            mgmt_type = resource_type.replace("management_", "")
            resource_type_enum = self._MANAGEMENT_RESOURCE_TYPE_MAP.get(mgmt_type)
            if mgmt_type == "level_variables":
                from engine.resources.level_variable_schema_view import get_default_level_variable_schema_view

                schema_view = get_default_level_variable_schema_view()
                file_info = schema_view.get_variable_file(resource_id)
                if file_info is None:
                    return None
                return getattr(file_info, "absolute_path", None)
            if mgmt_type == "save_points":
                from engine.resources.ingame_save_template_schema_view import (
                    get_default_ingame_save_template_schema_view,
                )

                schema_view = get_default_ingame_save_template_schema_view()
                return schema_view.get_template_file_path(resource_id)
            if resource_type_enum is None:
                return None
            return self.resource_manager.list_resource_file_paths(resource_type_enum).get(resource_id)

        if resource_type == "composite":
            # composite 不属于 ResourceType（不进 ResourceManager 索引），统一按 policy 扫描并匹配文件名。
            from engine.nodes.composite_file_policy import discover_composite_definition_files

            for path in discover_composite_definition_files(self.workspace_path):
                if path.stem == resource_id:
                    return path
            return None

        return None



