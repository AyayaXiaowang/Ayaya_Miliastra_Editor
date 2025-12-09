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
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from engine.configs.resource_types import ResourceType
from engine.graph.utils.metadata_extractor import load_graph_metadata_from_file
from engine.resources.management_naming_rules import (
    get_id_and_display_name_fields,
)
from engine.utils.logging.logger import log_info
from engine.utils.cache.cache_paths import get_resource_cache_dir, get_resource_index_cache_file
from engine.utils.name_utils import sanitize_resource_filename


CheckAndSyncNameFn = Callable[[Path, ResourceType, str, str, Optional[dict]], bool]


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
            workspace_path: 工作空间根目录（Graph_Generater）
            resource_library_dir: 资源库根目录（通常为 assets/资源库）
        """
        self.workspace_path = workspace_path
        self.resource_library_dir = resource_library_dir

    def compute_resources_fingerprint(self) -> str:
        """计算当前资源库的指纹（文件数 + 最新修改时间）。"""
        return self._compute_resources_fingerprint()

    # ===== 对外 API =====

    def try_load_from_cache(self) -> Optional[ResourceIndexData]:
        """尝试从持久化缓存恢复资源索引。

        Returns:
            命中缓存时返回 ResourceIndexData，否则返回 None。
        """
        cache_file = self._get_resource_index_cache_file()
        if not cache_file.exists():
            return None

        with open(cache_file, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)

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

        # 额外健壮性校验：对于 **JSON 资源类型**，如果当前磁盘上的文件数量
        # 大于缓存中记录的条目数量，则认为缓存已过期，回退到全量扫描。
        # 这样可以覆盖“外部脚本直接在资源库目录新增 JSON，但未通过 ResourceManager
        # 触发索引重建”的情况。
        parsed_counts = self._parse_resources_fingerprint(current_fingerprint)
        for resource_type, (file_count, _latest_mtime) in parsed_counts.items():
            # 节点图 / 结构体定义 / 信号等类型使用 `.py` 并有各自的过滤与解析规则，
            # 文件数与索引条目数天然可能不同，这里仅对“顶层 JSON 资源类型”做数量一致性校验。
            if resource_type in {
                ResourceType.GRAPH,
                ResourceType.STRUCT_DEFINITION,
                ResourceType.SIGNAL,
            }:
                continue
            if file_count <= 0:
                continue
            bucket = resource_index.get(resource_type, {})
            if len(bucket) < file_count:
                return None

        # 额外健壮性校验：如果缓存中的任何资源路径已不存在，则视为缓存失效，回退到全量扫描。
        for resource_type, id_map in resource_index.items():
            for resource_id, resource_path in id_map.items():
                if not resource_path.exists():
                    return None

        # 兼容过滤：移除任何指向以下划线开头 .py 文件的“节点图”条目（如 _prelude.py）
        if ResourceType.GRAPH in resource_index:
            to_remove: List[str] = []
            for resource_id, path in resource_index[ResourceType.GRAPH].items():
                try:
                    if path.name.startswith("_"):
                        to_remove.append(resource_id)
                except Exception:
                    # 无法判断路径名称时不移除
                    pass
            if to_remove:
                for resource_id in to_remove:
                    resource_index[ResourceType.GRAPH].pop(resource_id, None)
                    if ResourceType.GRAPH in id_to_filename_cache:
                        id_to_filename_cache[ResourceType.GRAPH].pop(resource_id, None)
                    if ResourceType.GRAPH in name_to_id_index:
                        name_map = name_to_id_index[ResourceType.GRAPH]
                        keys_to_delete: List[str] = [
                            key for key, value in name_map.items() if value == resource_id
                        ]
                        for key in keys_to_delete:
                            name_map.pop(key, None)

        total = sum(len(value) for value in resource_index.values())
        log_info("[OK] 资源索引缓存命中，共 {} 个资源（跳过全量扫描）", total)

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

        for resource_type in ResourceType:
            resource_index[resource_type] = {}
            name_to_id_index[resource_type] = {}
            id_to_filename_cache[resource_type] = {}
            resource_dir = self._get_resource_directory(resource_type)

            if not resource_dir.exists():
                continue

            # 节点图需要递归扫描子文件夹（支持 server/client 子目录）
            if resource_type == ResourceType.GRAPH:
                # 节点图只使用 .py 文件（类结构 Python 文件）
                for py_file in resource_dir.rglob("*.py"):
                    # 跳过以 "_" 开头的保留/辅助文件（例如 _prelude.py）
                    if py_file.name.startswith("_"):
                        continue
                    # 跳过校验脚本（如 校验节点图.py），这些不是真正的节点图文件
                    if "校验" in py_file.stem:
                        continue
                    filename_without_ext = py_file.stem

                    # 读取文件获取 graph_id（从 docstring 元数据中）
                    resource_id = self._extract_graph_id_from_file(py_file)
                    if not resource_id:
                        # 如果无法从文件中提取 ID，使用文件名作为 ID
                        resource_id = filename_without_ext

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
            else:
                # 其他资源类型只扫描直接子文件
                for json_file in resource_dir.glob("*.json"):
                    filename_without_ext = json_file.stem

                    # 读取 JSON 文件获取 ID 和 name
                    resource_id, resource_name, resource_payload = self._extract_id_and_name_from_json(
                        json_file, resource_type
                    )
                    if not resource_id:
                        # 如果无法从文件中提取 ID，使用文件名作为 ID
                        resource_id = filename_without_ext

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

    def _get_resource_directory(self, resource_type: ResourceType) -> Path:
        """获取资源类型对应的目录路径。"""
        return self.resource_library_dir / resource_type.value

    def _compute_resources_fingerprint(self) -> str:
        """计算资源库整体指纹（用于索引缓存失效判断）。

        规则：对每类资源统计"目标扩展名的文件数 + 最新修改时间（取最大）"。
        - 节点图：递归统计 .py
        - 结构体定义：递归统计 .py（与节点图类似，使用 Python 代码定义）
        - 信号：递归统计 .py（与节点图类似，使用 Python 代码定义）
        - 其他：仅统计顶层目录下的 .json（与索引构建策略一致）
        """
        # 使用 .py 文件且需要递归扫描的资源类型
        py_recursive_types = {
            ResourceType.GRAPH,
            ResourceType.STRUCT_DEFINITION,
            ResourceType.SIGNAL,
        }
        
        parts: List[str] = []
        for resource_type in ResourceType:
            base_dir = self._get_resource_directory(resource_type)
            file_count = 0
            latest_mtime = 0.0
            if base_dir.exists():
                if resource_type in py_recursive_types:
                    for path in base_dir.rglob("*.py"):
                        stat = path.stat()
                        file_count += 1
                        if stat.st_mtime > latest_mtime:
                            latest_mtime = stat.st_mtime
                else:
                    for path in base_dir.glob("*.json"):
                        stat = path.stat()
                        file_count += 1
                        if stat.st_mtime > latest_mtime:
                            latest_mtime = stat.st_mtime
            parts.append(f"{resource_type.name}:{file_count}:{round(latest_mtime, 3)}")
        return "|".join(parts)

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
        cache_file = self._get_resource_index_cache_file()
        payload = {
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
        with open(cache_file, "w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False, indent=2)

    @staticmethod
    def _extract_graph_id_from_file(py_file: Path) -> Optional[str]:
        """从节点图文件的 docstring 中提取 graph_id。"""
        metadata = load_graph_metadata_from_file(py_file)
        return metadata.graph_id or None

    @staticmethod
    def _extract_id_and_name_from_json(
        json_file: Path, resource_type: ResourceType
    ) -> Tuple[Optional[str], Optional[str], dict]:
        """从 JSON 文件中提取资源 ID、名称及原始数据。
        
        约定：
        - 模板/实例使用各自的 *_id 字段；
        - 聊天频道等管理配置可使用各自领域内约定的 ID 字段；
        - 其余资源优先使用通用的 `id` / `resource_id` / `preset_id` / `config_id`；
        - 名称优先读取通用 `name` 字段，对部分管理配置（如聊天频道）回退到业务字段。
        
        设计目标：
        - 索引扫描仅依赖 JSON 内容中的 ID 与名称字段，与物理文件名解耦；
        - 当类型专用 ID 字段缺失时，自动回退到通用 ID 字段，兼容“仅写 id 字段、
          使用人类可读名称作为文件名”的资源文件。
        """
        with open(json_file, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)

        id_field, explicit_name_field = get_id_and_display_name_fields(resource_type)

        # 统一的 ID 提取规则：
        # 1. 若为该资源类型声明了专用 ID 字段，则优先使用该字段；
        # 2. 当专用 ID 字段缺失或为空时，回退到通用 ID 字段：
        #    - `id` / `resource_id` / `preset_id` / `config_id`
        #    这样可以兼容“仅写通用 id 字段、文件名使用名称”的场景。
        candidate_id_field = id_field if id_field is not None else "id"

        resource_id: Optional[str] = None
        raw_candidate_value = data.get(candidate_id_field)
        if isinstance(raw_candidate_value, str) and raw_candidate_value.strip():
            resource_id = raw_candidate_value.strip()

        if resource_id is None:
            for possible_id in ["id", "resource_id", "preset_id", "config_id"]:
                raw_value = data.get(possible_id)
                if isinstance(raw_value, str) and raw_value.strip():
                    resource_id = raw_value.strip()
                    break

        # 名称：通用 `name` 字段优先，其次回退到各资源类型约定的显示名字段
        # （例如 timer_name / variable_name / resource_name 等）。
        resource_name = data.get("name")
        if not resource_name and explicit_name_field:
            resource_name = data.get(explicit_name_field)

        return resource_id, resource_name, data

    @staticmethod
    def _find_resource_type_by_name(type_name: str) -> Optional[ResourceType]:
        for resource_type in ResourceType:
            if resource_type.name == type_name:
                return resource_type
        return None


