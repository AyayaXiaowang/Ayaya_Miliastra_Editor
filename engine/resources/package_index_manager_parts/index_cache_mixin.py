"""PackageIndexManager：目录派生索引/缓存/Todo 状态职责拆分。"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from engine.configs.resource_types import ResourceType
from engine.resources.atomic_json import atomic_write_json
from engine.resources.package_index import PackageIndex, PackageResources


class PackageIndexCacheMixin:
    def _get_todo_state_file_path(self, package_id: str) -> Path:
        """获取指定存档的 Todo 状态文件路径。"""
        return self.todo_state_dir / f"{package_id}.json"

    def _load_todo_states(self, package_id: str) -> Dict[str, bool]:
        """从运行期状态目录加载指定存档的 Todo 勾选状态。

        若状态文件不存在，返回空字典；若存在则期望为 {todo_id: bool} 的映射。
        """
        todo_file_path = self._get_todo_state_file_path(package_id)
        if not todo_file_path.exists():
            return {}
        with open(todo_file_path, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
        if not isinstance(data, dict):
            return {}
        result: Dict[str, bool] = {}
        for key, value in data.items():
            if isinstance(key, str) and isinstance(value, bool):
                result[key] = value
        return result

    def _save_todo_states(self, package_index: PackageIndex) -> None:
        """将指定存档的 Todo 勾选状态写入运行期状态目录。

        约定：
        - 文件名与 package_id 一致：app/runtime/todo_states/<package_id>.json
        - 内容为 {todo_id: bool} 映射，仅供编辑器 UI 使用，不参与项目存档导出。
        """
        todo_file_path = self._get_todo_state_file_path(package_index.package_id)
        atomic_write_json(todo_file_path, package_index.todo_states, ensure_ascii=False, indent=2)

    def save_package_index(
        self,
        package_index: PackageIndex,
        *,
        expected_mtime: float | None = None,
        allow_overwrite_external: bool = False,
        refresh_resource_names: bool = True,
    ) -> bool:
        """保存存档索引（目录模式，无 pkg_*.json）。

        设计约定：
        - 项目存档以目录结构作为唯一真相源：`assets/资源库/项目存档/<package_id>/...`
        - PackageIndex 为派生视图：不再写回任何旧式索引 JSON（pkg_*.json / packages.json）。
        - 本方法仅用于写入运行期状态（Todo 勾选）与更新进程内缓存，始终返回 True。

        兼容说明：
        - 参数 expected_mtime/allow_overwrite_external 在目录模式下无意义，仅为保持 UI/测试调用接口稳定而保留。
        """
        _ = expected_mtime, allow_overwrite_external

        if bool(refresh_resource_names):
            self._refresh_resource_names(package_index)
        package_index.updated_at = datetime.now().isoformat()

        # Todo 状态仍需写入运行期目录
        self._save_todo_states(package_index)

        # 写入内存缓存（便于 UI 在枚举“所属存档”时复用）
        self._package_index_cache[package_index.package_id] = package_index
        package_root_dir = self._packages_root_dir / str(package_index.package_id)
        if package_root_dir.exists() and package_root_dir.is_dir():
            self._package_index_cache_mtime[package_index.package_id] = float(package_root_dir.stat().st_mtime)
        else:
            self._package_index_cache_mtime[package_index.package_id] = 0.0
        return True

    def load_package_index(self, package_id: str, *, refresh_resource_names: bool = True) -> Optional[PackageIndex]:
        """加载存档索引。

        Returns:
            存档索引对象，如果不存在返回 None
        """
        package_id_text = str(package_id or "").strip()
        if not package_id_text:
            return None

        package_root = self._packages_root_dir / package_id_text
        if not package_root.exists() or not package_root.is_dir():
            # 目录不存在：清理缓存并返回 None
            self._package_index_cache.pop(package_id_text, None)
            self._package_index_cache_mtime.pop(package_id_text, None)
            return None

        # 目录 mtime 作为缓存一致性基线（避免每次都派生 PackageIndex）
        current_dir_mtime = float(package_root.stat().st_mtime)
        cached_index = self._package_index_cache.get(package_id_text)
        cached_mtime = self._package_index_cache_mtime.get(package_id_text)

        if cached_index is not None and cached_mtime is not None:
            if abs(float(cached_mtime) - current_dir_mtime) < 0.001:
                if bool(refresh_resource_names):
                    self._refresh_resource_names(cached_index)
                return cached_index

        package_index = self._load_package_index_from_directory(package_id_text)
        if package_index is None:
            self._package_index_cache.pop(package_id_text, None)
            self._package_index_cache_mtime.pop(package_id_text, None)
            return None

        if bool(refresh_resource_names):
            self._refresh_resource_names(package_index)

        self._package_index_cache[package_id_text] = package_index
        self._package_index_cache_mtime[package_id_text] = current_dir_mtime
        return package_index

    def invalidate_package_index_cache(self, package_id: str | None = None) -> None:
        """失效（清空）PackageIndex 的进程内派生缓存。"""
        if package_id is None:
            self._package_index_cache.clear()
            self._package_index_cache_mtime.clear()
            return
        package_id_text = str(package_id or "").strip()
        if not package_id_text:
            return
        self._package_index_cache.pop(package_id_text, None)
        self._package_index_cache_mtime.pop(package_id_text, None)

    def _load_package_index_from_directory(self, package_id: str) -> PackageIndex | None:
        package_root = self._packages_root_dir / str(package_id)
        if not package_root.exists() or not package_root.is_dir():
            return None

        # ===== 基础元信息 =====
        # 项目显示名唯一真源：项目存档目录名（package_id）。
        # 注意：不再从包内“关卡实体文件名”等推断显示名，避免出现多个同名项或跨包误判。
        package_name = str(package_id)
        latest_mtime = self._get_latest_mtime_under_dir(package_root)
        updated_at = (
            datetime.fromtimestamp(latest_mtime).isoformat()
            if latest_mtime > 0
            else datetime.now().isoformat()
        )

        resources = PackageResources()

        # ===== 基础资源（JSON/Graph） =====
        resources.templates = sorted(self._collect_resource_ids_in_package(ResourceType.TEMPLATE, package_root))
        resources.instances = sorted(self._collect_resource_ids_in_package(ResourceType.INSTANCE, package_root))
        resources.graphs = sorted(self._collect_resource_ids_in_package(ResourceType.GRAPH, package_root))

        # ===== 复合节点（Python 文件名即 composite_id） =====
        composites_dir = package_root / "复合节点库"
        if composites_dir.exists() and composites_dir.is_dir():
            composite_ids: List[str] = []
            for py_path in composites_dir.rglob("*.py"):
                if not py_path.is_file():
                    continue
                if py_path.name.startswith("_") or "校验" in py_path.stem:
                    continue
                if py_path.stem.startswith("composite_"):
                    composite_ids.append(py_path.stem)
            resources.composites = sorted(composite_ids, key=lambda text: text.casefold())

        # ===== 战斗预设（JSON） =====
        for bucket_name, resource_type in self._COMBAT_RESOURCE_TYPE_MAP.items():
            resources.combat_presets[bucket_name] = sorted(
                self._collect_resource_ids_in_package(resource_type, package_root)
            )

        # ===== 管理配置（JSON + 代码资源） =====
        for bucket_name, resource_type in self._MANAGEMENT_RESOURCE_TYPE_MAP.items():
            if bucket_name == "level_variables":
                # 关卡变量（代码资源）：按 VARIABLE_FILE_ID 作为资源 ID
                from engine.resources.level_variable_schema_view import get_default_level_variable_schema_view

                schema_view = get_default_level_variable_schema_view()
                variable_files = schema_view.get_all_variable_files()
                file_ids: List[str] = []
                for file_id, info in variable_files.items():
                    abs_path = getattr(info, "absolute_path", None)
                    if isinstance(abs_path, Path) and self._is_path_under(package_root, abs_path):
                        file_ids.append(str(file_id))
                resources.management[bucket_name] = sorted(file_ids, key=lambda text: text.casefold())
                continue

            if bucket_name == "save_points":
                # 局内存档模板（代码资源）：按 template_id 作为资源 ID
                from engine.resources.ingame_save_template_schema_view import (
                    get_default_ingame_save_template_schema_view,
                )

                schema_view = get_default_ingame_save_template_schema_view()
                all_templates = schema_view.get_all_templates()
                template_ids: List[str] = []
                for template_id in all_templates.keys():
                    file_path = schema_view.get_template_file_path(str(template_id))
                    if isinstance(file_path, Path) and self._is_path_under(package_root, file_path):
                        template_ids.append(str(template_id))
                resources.management[bucket_name] = sorted(template_ids, key=lambda text: text.casefold())
                continue

            resources.management[bucket_name] = sorted(
                self._collect_resource_ids_in_package(resource_type, package_root)
            )

        # ===== 构造 PackageIndex（派生，不落盘） =====
        package_index = PackageIndex(
            package_id=str(package_id),
            name=str(package_name),
            description="",
            resources=resources,
            created_at="",
            updated_at=updated_at,
        )

        # 关卡实体：优先使用约定 ID（level_<package_id>）
        level_entity_id = f"level_{package_id}"
        if level_entity_id in resources.instances:
            package_index.level_entity_id = level_entity_id
        else:
            for instance_id in list(resources.instances):
                payload = self.resource_manager.load_resource(ResourceType.INSTANCE, str(instance_id))
                metadata = payload.get("metadata") if isinstance(payload, dict) else None
                if isinstance(metadata, dict) and metadata.get("is_level_entity"):
                    package_index.level_entity_id = str(instance_id)
                    break

        # 信号引用摘要：默认认为“包内信号定义文件即属于该包的信号集合”
        signal_ids = resources.management.get("signals", [])
        if isinstance(signal_ids, list) and signal_ids:
            package_index.signals = {
                str(signal_id): {}
                for signal_id in signal_ids
                if isinstance(signal_id, str) and signal_id
            }

        # Todo 勾选状态仍从运行期状态目录读取
        package_index.todo_states = self._load_todo_states(str(package_id))

        return package_index

    def _collect_resource_ids_in_package(self, resource_type: ResourceType, package_root: Path) -> List[str]:
        id_to_path = self.resource_manager.list_resource_file_paths(resource_type)
        results: List[str] = []
        for resource_id, file_path in id_to_path.items():
            if not isinstance(resource_id, str) or not resource_id:
                continue
            if not isinstance(file_path, Path):
                continue
            if self._is_path_under(package_root, file_path):
                results.append(resource_id)
        return results

    def delete_package(self, package_id: str) -> None:
        """删除存档（目录即存档：删除整个项目存档目录）。"""
        package_root = self._packages_root_dir / str(package_id)
        if package_root.exists() and package_root.is_dir():
            shutil.rmtree(package_root)

        # 清理运行期 Todo 状态
        todo_state_file = self._get_todo_state_file_path(str(package_id))
        if todo_state_file.exists():
            todo_state_file.unlink()

        # 清理缓存并刷新资源索引
        self._package_index_cache.pop(str(package_id), None)
        self._package_index_cache_mtime.pop(str(package_id), None)
        self.resource_manager.rebuild_index()

    def rename_package(self, package_id: str, new_name: str) -> None:
        """重命名存档（目录模式下仅调整“关卡实体文件名”的约定命名，不作为项目显示名真源）。"""
        package_root = self._packages_root_dir / str(package_id)
        if not package_root.exists() or not package_root.is_dir():
            return

        instances_dir = self._resolve_instance_dir(package_root)
        if not instances_dir.exists() or not instances_dir.is_dir():
            return

        sanitized_name = self._sanitize_package_filename(new_name)
        if not sanitized_name:
            return

        # 约定：关卡实体文件名尽量与项目目录名一致，便于人工识别与审计。
        level_entity_id = f"level_{package_id}"
        current_level_entity_file = self.resource_manager.list_resource_file_paths(ResourceType.INSTANCE).get(
            level_entity_id
        )
        if current_level_entity_file is None or not current_level_entity_file.exists():
            candidates = sorted(instances_dir.glob("*_关卡实体.json"), key=lambda path: path.name.casefold())
            if not candidates:
                return
            current_level_entity_file = candidates[0]

        target_file = current_level_entity_file.with_name(f"{sanitized_name}_关卡实体.json")
        if target_file.exists() and target_file.resolve() != current_level_entity_file.resolve():
            raise ValueError(f"目标关卡实体文件已存在，无法重命名：{target_file}")

        if target_file.resolve() != current_level_entity_file.resolve():
            current_level_entity_file.rename(target_file)
            self.resource_manager.rebuild_index()
        return

    def update_description(self, package_id: str, new_description: str) -> None:
        """更新存档描述（目录模式下仅更新运行期派生视图）。"""
        package_index = self.load_package_index(package_id)
        if package_index:
            package_index.description = new_description
            self.save_package_index(package_index)

    def get_package_info(self, package_id: str) -> Optional[dict]:
        """获取存档基本信息。"""
        packages = self.list_packages()
        for pkg_info in packages:
            if pkg_info["package_id"] == package_id:
                return pkg_info
        return None

    def get_package_resources(self, package_id: str) -> Optional[PackageResources]:
        """获取存档的所有资源引用。"""
        # 仅查询资源引用列表时不刷新派生的 resource_names，避免 UI 在枚举全部包时做多余元数据查询。
        package_index = self.load_package_index(package_id, refresh_resource_names=False)
        if not package_index:
            return None
        return package_index.resources



