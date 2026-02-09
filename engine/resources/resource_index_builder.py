"""资源索引构建与持久化缓存管理。

本模块将原先 `ResourceManager` 中与“资源目录扫描 + 索引缓存”相关的职责
提取为独立的协作类，职责包括：

- 按 `ResourceType` 扫描资源库目录，构建索引与 name/id 映射
- 计算资源库指纹（文件数 + 最新修改时间）
- 读写磁盘上的持久化索引缓存

设计约束：
- 不依赖 UI，仅依赖文件系统与 `ResourceType`
- 不关心具体资源内容，仅关心 ID、文件名与路径
- 不操作内存数据缓存（由 `ResourceManager` 自己维护）
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from engine.configs.resource_types import ResourceType
from engine.graph.utils.metadata_extractor import load_graph_metadata_from_file
from engine.resources.management_naming_rules import (
    get_id_and_display_name_fields,
)
from engine.utils.logging.logger import log_debug, log_info, log_warn
from engine.utils.cache.cache_paths import get_resource_cache_dir, get_resource_index_cache_file
from engine.utils.name_utils import sanitize_resource_filename
from engine.utils.resource_library_layout import (
    get_packages_root_dir,
    get_shared_root_dir,
)
from .atomic_json import atomic_write_json


CheckAndSyncNameFn = Callable[[Path, ResourceType, str, str, Optional[dict]], bool]

RESOURCE_INDEX_CACHE_SCHEMA = "resource_index_cache/v1"
RESOURCE_INDEX_CACHE_SCHEMA_VERSION = 2


@dataclass
class ResourceIndexData:
    """资源索引构建结果."""

    resource_index: Dict[ResourceType, Dict[str, Path]]
    name_to_id_index: Dict[ResourceType, Dict[str, str]]
    id_to_filename_cache: Dict[ResourceType, Dict[str, str]]
    synced_file_count: int


class ResourceIndexBuilder:
    """资源索引构建器。

    负责：
    - 扫描资源库目录，构建索引
    - 维护资源指纹并读写持久化索引缓存
    """

    def __init__(self, workspace_path: Path, resource_library_dir: Path) -> None:
        """
        Args:
            workspace_path: 工作区根目录（workspace_root）
            resource_library_dir: 资源库根目录（通常为 assets/资源库，支持子树：共享/项目存档）
        """
        self.workspace_path = workspace_path
        self.resource_library_dir = resource_library_dir
        # 资源索引的扫描作用域：默认仅扫描共享根；当 UI 选择某个项目存档后，
        # 由上层显式设置 active_package_id，使索引切换为“共享 + 当前项目存档”。
        self._active_package_id: str | None = None

    def set_active_package_id(self, package_id: str | None) -> None:
        """设置当前资源索引扫描的项目存档作用域（package_id）。

        - None/空字符串：仅扫描共享根目录；
        - 非空字符串：扫描共享根 + `项目存档/<package_id>/` 根目录。
        """
        normalized = str(package_id or "").strip()
        self._active_package_id = normalized or None

    def compute_resources_fingerprint(
        self,
        *,
        should_abort: Optional[Callable[[], bool]] = None,
    ) -> str:
        """计算当前资源库的指纹（文件数 + 最新修改时间）。"""
        return self._compute_resources_fingerprint(should_abort=should_abort)

    # ===== 对外 API =====

    def try_load_from_cache(self) -> Optional[ResourceIndexData]:
        """尝试从持久化缓存恢复资源索引。

        Returns:
            命中缓存时返回 ResourceIndexData，否则返回 None。
        """
        cache_file = self._select_latest_resource_index_cache_file()
        if cache_file is None:
            return None

        with open(cache_file, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)

        manifest = data.get("__manifest__")
        if manifest is not None:
            if not isinstance(manifest, dict):
                return None
            schema_value = manifest.get("schema")
            version_value = manifest.get("schema_version")
            if schema_value != RESOURCE_INDEX_CACHE_SCHEMA:
                return None
            if version_value != RESOURCE_INDEX_CACHE_SCHEMA_VERSION:
                return None

        if (
            "resources_fp" not in data
            or "resource_index" not in data
            or "name_to_id_index" not in data
            or "id_to_filename_cache" not in data
        ):
            return None

        saved_fingerprint = data.get("resources_fp", "")
        current_fingerprint = self.compute_resources_fingerprint()
        if saved_fingerprint != current_fingerprint:
            return None

        # 反序列化索引结构
        resource_index_raw: Dict[str, Dict[str, str]] = data["resource_index"]
        resource_index: Dict[ResourceType, Dict[str, Path]] = {}
        for type_name, id_map in resource_index_raw.items():
            resource_type = self._find_resource_type_by_name(type_name)
            if resource_type is None:
                continue
            resource_index[resource_type] = {
                resource_id: Path(path_str) for resource_id, path_str in id_map.items()
            }

        name_to_id_raw: Dict[str, Dict[str, str]] = data["name_to_id_index"]
        name_to_id_index: Dict[ResourceType, Dict[str, str]] = {}
        for type_name, name_map in name_to_id_raw.items():
            resource_type = self._find_resource_type_by_name(type_name)
            if resource_type is None:
                continue
            name_to_id_index[resource_type] = dict(name_map)

        id_to_filename_raw: Dict[str, Dict[str, str]] = data["id_to_filename_cache"]
        id_to_filename_cache: Dict[ResourceType, Dict[str, str]] = {}
        for type_name, id_map in id_to_filename_raw.items():
            resource_type = self._find_resource_type_by_name(type_name)
            if resource_type is None:
                continue
            id_to_filename_cache[resource_type] = dict(id_map)

        # 额外健壮性校验：如果缓存中的任何资源路径已不存在，则视为缓存失效，回退到全量扫描。
        for resource_type, id_map in resource_index.items():
            for resource_id, resource_path in id_map.items():
                if not resource_path.exists():
                    return None

        # 额外健壮性校验（shared-only）：防止磁盘上的 JSON 已增加/缓存写入被截断，
        # 但 resources_fp 仍“看似一致”导致错误命中缓存并丢资源条目。
        #
        # 注意：在 active_package 作用域下允许“共享根 + 项目存档根”存在相同 ID 的覆盖语义，
        # file_count（指纹）会统计两份文件，但索引 bucket 仅保留一份，因此不能用简单计数判定。
        if self._active_package_id is None:
            parsed_fp = self._parse_resources_fingerprint(current_fingerprint)
            expected_item_file_count, _ = parsed_fp.get(ResourceType.ITEM, (0, 0.0))
            cached_item_bucket = resource_index.get(ResourceType.ITEM, {})
            cached_item_count = len(cached_item_bucket) if isinstance(cached_item_bucket, dict) else 0
            if expected_item_file_count > 0 and cached_item_count < expected_item_file_count:
                return None

        # 额外健壮性校验：索引中不应包含以下划线开头的 .py（例如 __init__.py）。
        # 若命中则视为旧缓存污染，回退到全量扫描重建（而不是在此处做“兼容过滤”）。
        cached_graph_bucket = resource_index.get(ResourceType.GRAPH)
        if isinstance(cached_graph_bucket, dict):
            for path in cached_graph_bucket.values():
                if path.name.startswith("_"):
                    return None

        total = sum(len(value) for value in resource_index.values())
        log_debug("[INDEX] 资源索引缓存命中，共 {} 个资源（跳过全量扫描）", total)

        return ResourceIndexData(
            resource_index=resource_index,
            name_to_id_index=name_to_id_index,
            id_to_filename_cache=id_to_filename_cache,
            synced_file_count=0,
        )

    def build_index(self, check_and_sync_name: CheckAndSyncNameFn) -> ResourceIndexData:
        """扫描资源库目录，构建资源索引和名称映射。

        Args:
            check_and_sync_name: 回调，用于在扫描过程中进行 name 与文件名的同步。

        Returns:
            ResourceIndexData，包含索引与同步数量。
        """
        resource_index: Dict[ResourceType, Dict[str, Path]] = {}
        name_to_id_index: Dict[ResourceType, Dict[str, str]] = {}
        id_to_filename_cache: Dict[ResourceType, Dict[str, str]] = {}
        synced_file_count = 0

        # 允许“不同项目存档内存在相同 resource_id”的同时，资源索引需要具备稳定的覆盖优先级：
        # - 若同一 resource_id 同时出现在共享根与当前项目存档根，优先使用当前项目存档版本；
        # - 若重复发生在同一根目录内（共享根内部或某项目存档内部），仍视为错误（歧义不可解）。
        shared_root_dir = get_shared_root_dir(self.resource_library_dir).resolve()
        active_package_id = str(self._active_package_id or "").strip()
        package_root_dir: Path | None = None
        if active_package_id:
            package_root_dir = (get_packages_root_dir(self.resource_library_dir) / active_package_id).resolve()

        def infer_scope(file_path: Path) -> str:
            resolved = file_path.resolve()
            if package_root_dir is not None:
                package_parts = package_root_dir.parts
                if resolved.parts[: len(package_parts)] == package_parts:
                    return "package"
            shared_parts = shared_root_dir.parts
            if resolved.parts[: len(shared_parts)] == shared_parts:
                return "shared"
            return "unknown"

        # 记录资源索引构建过程中可恢复的问题：
        # - 同一根目录内重复 ID：索引歧义（包内必须唯一），但不应阻断 UI 启动与资源库浏览。
        # - 代码级资源缺少 ID 常量：无法入索引（应在校验中提示修复），但同样不应阻断启动。
        duplicate_id_conflicts: List[Tuple[ResourceType, str, Path, Path, str]] = []
        missing_code_resource_ids: List[Tuple[ResourceType, Path, str]] = []
        missing_json_resource_ids: List[Tuple[ResourceType, Path, str]] = []

        for resource_type in ResourceType:
            resource_index[resource_type] = {}
            name_to_id_index[resource_type] = {}
            id_to_filename_cache[resource_type] = {}
            resource_dirs = self._get_resource_directories(resource_type)

            for resource_dir in resource_dirs:
                if not resource_dir.exists():
                    continue

                py_recursive_types = {
                    ResourceType.GRAPH,
                    ResourceType.STRUCT_DEFINITION,
                    ResourceType.SIGNAL,
                }

                # 节点图/结构体定义/信号：Python 代码资源，需要递归扫描子文件夹。
                if resource_type in py_recursive_types:
                    py_files = sorted(
                        list(resource_dir.rglob("*.py")),
                        key=lambda path: path.as_posix().casefold(),
                    )
                    for py_file in py_files:
                        # 跳过以 "_" 开头的保留/辅助文件（例如 __init__.py）
                        if py_file.name.startswith("_"):
                            continue
                        # 跳过校验脚本（如 校验结构体定义.py / 校验信号.py / 校验节点图.py）
                        if "校验" in py_file.stem:
                            continue
                        if py_file.parent.name == "__pycache__":
                            continue
                        # 资源库可能在扫描期间被外部工具删除/移动文件：不存在的文件直接跳过，
                        # 避免索引构建因 FileNotFoundError 中断，导致 UI 自动刷新链路崩溃。
                        if not py_file.exists():
                            continue

                        filename_without_ext = py_file.stem

                        if resource_type == ResourceType.GRAPH:
                            # graph_id 来自 docstring 元数据
                            resource_id = self._extract_graph_id_from_file(py_file)
                            if not resource_id:
                                # 如果无法从文件中提取 ID，使用文件名作为 ID
                                resource_id = filename_without_ext
                        elif resource_type == ResourceType.SIGNAL:
                            resource_id = self._extract_python_string_constant(
                                py_file,
                                constant_name="SIGNAL_ID",
                            )
                            if not resource_id:
                                missing_code_resource_ids.append(
                                    (resource_type, py_file, "SIGNAL_ID")
                                )
                                continue
                        else:
                            # ResourceType.STRUCT_DEFINITION
                            resource_id = self._extract_python_string_constant(
                                py_file,
                                constant_name="STRUCT_ID",
                            )
                            if not resource_id:
                                missing_code_resource_ids.append(
                                    (resource_type, py_file, "STRUCT_ID")
                                )
                                continue

                        existing_path = resource_index[resource_type].get(resource_id)
                        if existing_path is not None:
                            if existing_path.resolve() == py_file.resolve():
                                continue

                            existing_scope = infer_scope(existing_path)
                            current_scope = infer_scope(py_file)

                            # 同一根目录内出现重复 ID：视为歧义错误（同一项目存档内必须唯一）
                            if existing_scope == current_scope:
                                duplicate_id_conflicts.append(
                                    (
                                        resource_type,
                                        str(resource_id),
                                        existing_path,
                                        py_file,
                                        str(current_scope),
                                    )
                                )
                                # 保持稳定行为：扫描顺序已排序，遇到冲突时保留“先进入索引”的那一份。
                                continue

                            # 跨根重复：当前项目存档版本覆盖共享版本（稳定覆盖语义）
                            if not (current_scope == "package" and existing_scope == "shared"):
                                continue

                            # 覆盖前清理旧的“文件名 -> graph_id”映射，避免残留错误路径的反查。
                            old_filename = id_to_filename_cache[resource_type].get(resource_id, existing_path.stem)
                            if old_filename:
                                name_to_id_index[resource_type].pop(old_filename, None)

                        resource_index[resource_type][resource_id] = py_file
                        id_to_filename_cache[resource_type][resource_id] = filename_without_ext
                        name_to_id_index[resource_type][filename_without_ext] = resource_id

                        if check_and_sync_name(
                            py_file,
                            resource_type,
                            resource_id,
                            filename_without_ext,
                            None,
                        ):
                            synced_file_count += 1

                    continue

                # 其他资源类型：JSON 资源，只扫描直接子文件
                json_files = sorted(
                    list(resource_dir.glob("*.json")),
                    key=lambda path: path.as_posix().casefold(),
                )
                for json_file in json_files:
                    # 资源库可能在扫描期间被外部工具删除/移动文件：不存在的文件直接跳过，
                    # 避免索引构建因 FileNotFoundError 中断。
                    if not json_file.exists():
                        continue
                    filename_without_ext = json_file.stem

                    # 读取 JSON 文件获取 ID 和 name
                    resource_id, resource_name, resource_payload = self._extract_id_and_name_from_json(
                        json_file, resource_type
                    )
                    # 顶层非 object（dict）的 JSON 文件不是“资源实体”，跳过索引（常见：工具输出的 *_index.json / 自研_*.json）。
                    if resource_payload is None:
                        continue
                    if not resource_id:
                        id_field, _ = get_id_and_display_name_fields(resource_type)
                        expected_id_field = id_field if id_field is not None else "id"
                        missing_json_resource_ids.append(
                            (resource_type, json_file, expected_id_field)
                        )
                        continue

                    existing_path = resource_index[resource_type].get(resource_id)
                    if existing_path is not None:
                        if existing_path.resolve() == json_file.resolve():
                            continue

                        existing_scope = infer_scope(existing_path)
                        current_scope = infer_scope(json_file)

                        # 同一根目录内出现重复 ID：视为歧义错误（同一项目存档内必须唯一）
                        if existing_scope == current_scope:
                            duplicate_id_conflicts.append(
                                (
                                    resource_type,
                                    str(resource_id),
                                    existing_path,
                                    json_file,
                                    str(current_scope),
                                )
                            )
                            # 保持稳定行为：扫描顺序已排序，遇到冲突时保留“先进入索引”的那一份。
                            continue

                        # 跨根重复：当前项目存档版本覆盖共享版本（稳定覆盖语义）
                        if not (current_scope == "package" and existing_scope == "shared"):
                            continue

                        # 覆盖时清理旧的“name -> id”映射（同一 id 可能对应多个 name，统一移除后重建）。
                        old_name_map = name_to_id_index[resource_type]
                        keys_to_delete = [key for key, value in old_name_map.items() if value == resource_id]
                        for key in keys_to_delete:
                            old_name_map.pop(key, None)

                    resource_index[resource_type][resource_id] = json_file
                    id_to_filename_cache[resource_type][resource_id] = filename_without_ext
                    if resource_name:
                        sanitized_name = sanitize_resource_filename(resource_name)
                        name_to_id_index[resource_type][sanitized_name] = resource_id

                    # 检查文件名与内部 name 是否一致，如果不一致则同步
                    if check_and_sync_name(
                        json_file,
                        resource_type,
                        resource_id,
                        filename_without_ext,
                        resource_payload,
                    ):
                        synced_file_count += 1

        if duplicate_id_conflicts:
            preview_limit = 3
            preview_lines: List[str] = []
            for i, (rtype, rid, p1, p2, scope) in enumerate(duplicate_id_conflicts[:preview_limit]):
                preview_lines.append(
                    f"- scope={scope} type={rtype.name} id={rid}\n  - {p1}\n  - {p2}"
                )
            more = ""
            if len(duplicate_id_conflicts) > preview_limit:
                more = f"\n- ... 还有 {len(duplicate_id_conflicts) - preview_limit} 个"
            log_warn(
                "资源索引扫描发现“同一根目录内重复 ID”冲突：count={}\n{}{}",
                len(duplicate_id_conflicts),
                "\n".join(preview_lines),
                more,
            )

        if missing_code_resource_ids:
            preview_limit = 3
            preview_lines: List[str] = []
            for rtype, path, constant_name in missing_code_resource_ids[:preview_limit]:
                preview_lines.append(f"- type={rtype.name} missing={constant_name} file={path}")
            more = ""
            if len(missing_code_resource_ids) > preview_limit:
                more = f"\n- ... 还有 {len(missing_code_resource_ids) - preview_limit} 个"
            log_warn(
                "资源索引扫描发现“代码级资源缺少 ID 常量”，已跳过入索引：count={}\n{}{}",
                len(missing_code_resource_ids),
                "\n".join(preview_lines),
                more,
            )

        if missing_json_resource_ids:
            preview_limit = 3
            preview_lines: List[str] = []
            for rtype, path, id_field in missing_json_resource_ids[:preview_limit]:
                preview_lines.append(f"- type={rtype.name} missing={id_field} file={path}")
            more = ""
            if len(missing_json_resource_ids) > preview_limit:
                more = f"\n- ... 还有 {len(missing_json_resource_ids) - preview_limit} 个"
            log_warn(
                "资源索引扫描发现“JSON 资源缺少稳定 ID 字段”，已跳过入索引：count={}\n{}{}",
                len(missing_json_resource_ids),
                "\n".join(preview_lines),
                more,
            )

        # 将索引写入持久化缓存
        self._save_persistent_resource_index(
            resource_index=resource_index,
            name_to_id_index=name_to_id_index,
            id_to_filename_cache=id_to_filename_cache,
        )

        return ResourceIndexData(
            resource_index=resource_index,
            name_to_id_index=name_to_id_index,
            id_to_filename_cache=id_to_filename_cache,
            synced_file_count=synced_file_count,
        )

    def clear_persistent_cache(self) -> int:
        """清空磁盘上的资源索引缓存。

        Returns:
            被删除的缓存文件数量。
        """
        cache_dir = self._get_resource_index_cache_dir()
        if not cache_dir.exists():
            return 0
        removed = 0
        for json_file in cache_dir.glob("*.json"):
            json_file.unlink()
            removed += 1
        if not any(cache_dir.iterdir()):
            cache_dir.rmdir()
        return removed

    # ===== 内部工具方法 =====

    def _get_resource_index_cache_dir(self) -> Path:
        return get_resource_cache_dir(self.workspace_path)

    def _get_resource_index_cache_file(self) -> Path:
        return get_resource_index_cache_file(self.workspace_path)

    def _select_latest_resource_index_cache_file(self) -> Path | None:
        """选择最新的资源索引缓存文件。

        背景（Windows）：
        - 覆盖写固定文件名 `resource_index.json` 时，`os.replace` 可能因外部短暂占用触发 WinError 5；
        - 资源索引缓存属于“可重建缓存”，因此采用“写入新文件、读取最新”的策略避免覆盖写冲突。

        兼容：
        - 若目录中存在旧版 `resource_index.json`，仍会参与候选（按 mtime 排序）。
        """
        cache_dir = self._get_resource_index_cache_dir()
        if not cache_dir.exists():
            return None

        candidates = sorted(
            [p for p in cache_dir.glob("resource_index*.json") if p.is_file()],
            key=lambda p: (float(p.stat().st_mtime), p.name.casefold()),
            reverse=True,
        )
        return candidates[0] if candidates else None

    def _get_resource_directories(self, resource_type: ResourceType) -> List[Path]:
        """获取资源类型对应的目录路径列表（按当前项目存档作用域过滤）。"""
        roots: list[Path] = []

        # 共享根：对所有项目存档可见
        shared_root = get_shared_root_dir(self.resource_library_dir)
        if shared_root.exists() and shared_root.is_dir():
            roots.append(shared_root)

        # 当前项目存档根：仅在显式指定 active_package_id 时纳入扫描
        active_package_id = str(self._active_package_id or "").strip()
        if active_package_id:
            packages_root = get_packages_root_dir(self.resource_library_dir)
            package_root_dir = packages_root / active_package_id
            if package_root_dir.exists() and package_root_dir.is_dir():
                roots.append(package_root_dir)

        directories = [root / resource_type.value for root in roots]

        return directories

    def _compute_resources_fingerprint(
        self,
        *,
        should_abort: Optional[Callable[[], bool]] = None,
    ) -> str:
        """计算资源库整体指纹（用于索引缓存失效判断）。

        规则：对每类资源统计"目标扩展名的文件数 + 最新修改时间（取最大）"。
        - 节点图：递归统计 .py
        - 结构体定义：递归统计 .py（与节点图类似，使用 Python 代码定义）
        - 信号：递归统计 .py（与节点图类似，使用 Python 代码定义）
        - 其他：仅统计顶层目录下的 .json（与索引构建策略一致）
        """
        # 重要：指纹需要包含“当前项目存档作用域”，避免不同项目存档内容相同/mtime 相同
        # 时错误命中同一份资源索引缓存。
        scope_label = str(self._active_package_id or "shared_only").strip() or "shared_only"
        parts: List[str] = [f"SCOPE:{scope_label}:0"]
        for resource_type in ResourceType:
            if should_abort is not None and should_abort():
                return "|".join(parts)
            file_count, latest_mtime = self._compute_resource_type_fingerprint_stats(
                resource_type,
                should_abort=should_abort,
            )
            parts.append(f"{resource_type.name}:{int(file_count)}:{round(float(latest_mtime), 3)}")
        return "|".join(parts)

    @staticmethod
    def _scan_dir_for_fingerprint(
        root_dir: Path,
        *,
        file_suffix: str,
        recursive: bool,
        should_abort: Optional[Callable[[], bool]] = None,
    ) -> tuple[int, float]:
        """扫描目录并统计符合后缀的文件数量与最新 mtime（尽量减少 Path 对象创建开销）。"""
        if should_abort is not None and should_abort():
            return 0, 0.0
        if not root_dir.exists() or not root_dir.is_dir():
            return 0, 0.0

        file_count = 0
        latest_mtime = 0.0

        # 使用字符串路径作为栈元素，减少频繁创建 Path 对象的开销。
        stack: list[str] = [str(root_dir)]
        while stack:
            if should_abort is not None and should_abort():
                break
            current_dir = stack.pop()
            if not os.path.isdir(current_dir):
                continue
            with os.scandir(current_dir) as entries:
                for entry in entries:
                    if should_abort is not None and should_abort():
                        break
                    if entry.is_dir(follow_symlinks=False):
                        if recursive:
                            stack.append(entry.path)
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    if not entry.name.endswith(file_suffix):
                        continue
                    if not os.path.exists(entry.path):
                        continue
                    stat_result = entry.stat(follow_symlinks=False)
                    file_count += 1
                    mtime = float(stat_result.st_mtime)
                    if mtime > latest_mtime:
                        latest_mtime = mtime

        return int(file_count), float(latest_mtime)

    def _compute_resource_type_fingerprint_stats(
        self,
        resource_type: ResourceType,
        *,
        should_abort: Optional[Callable[[], bool]] = None,
    ) -> tuple[int, float]:
        """计算单个资源类型在当前作用域下的 (file_count, latest_mtime)。"""
        py_recursive_types = {
            ResourceType.GRAPH,
            ResourceType.STRUCT_DEFINITION,
            ResourceType.SIGNAL,
        }
        is_recursive = resource_type in py_recursive_types
        file_suffix = ".py" if is_recursive else ".json"

        file_count = 0
        latest_mtime = 0.0
        for base_dir in self._get_resource_directories(resource_type):
            if should_abort is not None and should_abort():
                break
            count, mtime = self._scan_dir_for_fingerprint(
                base_dir,
                file_suffix=file_suffix,
                recursive=bool(is_recursive),
                should_abort=should_abort,
            )
            file_count += int(count)
            if float(mtime) > latest_mtime:
                latest_mtime = float(mtime)

        return int(file_count), float(latest_mtime)

    @staticmethod
    def _parse_resources_fingerprint(fingerprint: str) -> Dict[ResourceType, Tuple[int, float]]:
        """
        将指纹字符串解析为 {ResourceType: (file_count, latest_mtime)} 形式。

        指纹格式示例：
        TEMPLATE:4:1764757166.98|INSTANCE:5:1764987035.256|...
        """
        result: Dict[ResourceType, Tuple[int, float]] = {}
        if not fingerprint:
            return result

        for part in fingerprint.split("|"):
            if not part:
                continue
            segments = part.split(":")
            if len(segments) != 3:
                continue
            type_name, count_str, mtime_str = segments
            resource_type = ResourceIndexBuilder._find_resource_type_by_name(type_name)
            if resource_type is None:
                continue
            try:
                file_count = int(float(count_str))
                latest_mtime = float(mtime_str)
            except ValueError:
                continue
            result[resource_type] = (file_count, latest_mtime)
        return result

    def _save_persistent_resource_index(
        self,
        resource_index: Dict[ResourceType, Dict[str, Path]],
        name_to_id_index: Dict[ResourceType, Dict[str, str]],
        id_to_filename_cache: Dict[ResourceType, Dict[str, str]],
    ) -> None:
        """将当前索引写入磁盘缓存。"""
        cache_dir = self._get_resource_index_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        # 重要：写入“带时间戳的新文件”，避免覆盖写固定文件名在 Windows 下触发 WinError 5（外部短暂占用）。
        # 读取时会选择 mtime 最新的一个作为缓存命中候选。
        now = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        cache_file = (cache_dir / f"resource_index.{now}.{os.getpid()}.json").resolve()
        payload = {
            "__manifest__": {
                "schema": RESOURCE_INDEX_CACHE_SCHEMA,
                "schema_version": RESOURCE_INDEX_CACHE_SCHEMA_VERSION,
                "generated_at": datetime.now().isoformat(),
                "source": "engine.resources.ResourceIndexBuilder",
            },
            "resources_fp": self.compute_resources_fingerprint(),
            "resource_index": {
                resource_type.name: {
                    resource_id: str(path) for resource_id, path in id_map.items()
                }
                for resource_type, id_map in resource_index.items()
            },
            "name_to_id_index": {
                resource_type.name: mapping for resource_type, mapping in name_to_id_index.items()
            },
            "id_to_filename_cache": {
                resource_type.name: mapping
                for resource_type, mapping in id_to_filename_cache.items()
            },
            "cached_at": datetime.now().isoformat(),
        }
        atomic_write_json(cache_file, payload, ensure_ascii=False, indent=2)

    @staticmethod
    def _extract_graph_id_from_file(py_file: Path) -> Optional[str]:
        """从节点图文件的 docstring 中提取 graph_id。"""
        metadata = load_graph_metadata_from_file(py_file)
        return metadata.graph_id or None

    @staticmethod
    def _extract_python_string_constant(py_file: Path, *, constant_name: str) -> Optional[str]:
        """从 Python 源文件中解析形如 `CONSTANT = "value"` 的字符串常量值。

        约定：结构体/信号定义文件使用“顶层字符串字面量赋值”声明 ID：
        - `STRUCT_ID = "xxx"`
        - `SIGNAL_ID = "xxx"`

        允许行尾附带注释：`SIGNAL_ID = "xxx"  # comment`
        """
        constant_name_text = str(constant_name or "").strip()
        if not constant_name_text:
            return None

        code_text = py_file.read_text(encoding="utf-8")
        # 兼容两种声明形式：
        # - STRUCT_ID = "xxx"
        # - STRUCT_ID: str = "xxx"
        pattern = re.compile(
            rf"^\s*{re.escape(constant_name_text)}\s*(?::\s*[^=]+)?=\s*(?P<quote>['\"])(?P<value>[^'\"]+)(?P=quote)\s*(?:#.*)?$",
            flags=re.MULTILINE,
        )
        match = pattern.search(code_text)
        if not match:
            return None
        value_text = str(match.group("value") or "").strip()
        return value_text or None

    @staticmethod
    def _extract_id_and_name_from_json(
        json_file: Path, resource_type: ResourceType
    ) -> Tuple[Optional[str], Optional[str], Optional[dict]]:
        """从 JSON 文件中提取资源 ID、名称及原始数据。
        
        约定：
        - 若该资源类型在 `management_naming_rules.py` 中声明了专用 ID 字段（如 timer_id），则只使用该字段；
        - 否则仅使用通用 `id` 字段；
        - 名称仅使用通用 `name` 字段。
        
        设计目标：
        - 索引扫描仅依赖 JSON 内容中的 ID 与名称字段，与物理文件名解耦；
        - 不再对历史别名字段或文件名做回退：缺少稳定 ID 字段的资源将不会入索引，并在扫描日志中提示修复。

        注意：
        - 若 JSON 顶层不是 object（dict），该文件不会被视作“资源实体”，返回 (None, None, None)，由上层跳过。
        """
        with open(json_file, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
        if not isinstance(data, dict):
            return None, None, None

        id_field, _explicit_name_field = get_id_and_display_name_fields(resource_type)

        # 统一的 ID 提取规则：
        # - 若为该资源类型声明了专用 ID 字段，则只使用该字段；
        # - 否则仅使用通用 `id` 字段；
        # 不再对 `resource_id/preset_id/config_id` 等历史别名做回退。
        candidate_id_field = id_field if id_field is not None else "id"

        resource_id: Optional[str] = None
        raw_candidate_value = data.get(candidate_id_field)
        if isinstance(raw_candidate_value, str) and raw_candidate_value.strip():
            resource_id = raw_candidate_value.strip()

        # 名称：仅使用通用 `name` 字段（不再回退到各资源类型的业务显示名字段）。
        resource_name = data.get("name")

        return resource_id, resource_name, data

    @staticmethod
    def _find_resource_type_by_name(type_name: str) -> Optional[ResourceType]:
        for resource_type in ResourceType:
            if resource_type.name == type_name:
                return resource_type
        return None


