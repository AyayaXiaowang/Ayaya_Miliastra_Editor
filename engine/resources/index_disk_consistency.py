"""索引 vs 磁盘一致性检查（面向长期维护的诊断工具）。

术语约定：
- 索引（index）：当前运行期视图（`PackageIndex` 派生结果）。它可能受 ResourceManager 作用域、缓存与刷新时机影响。
- 磁盘（disk）：直接从项目存档目录扫描并解析得到的资源集合（不依赖 ResourceManager 当前索引）。

本模块输出三类不一致统计：
- 缺失资源（missing）：索引中引用了某资源 ID，但磁盘目录下不存在该资源文件（或无法解析为该 ID）。
- 孤儿资源（orphan）：磁盘目录下存在资源文件，但索引中未包含该资源 ID。
- 重复引用（duplicate）：同一资源 ID 在索引列表中重复出现，或在磁盘上对应多个文件路径（ID 冲突）。

注意：
- 不使用 try/except 吞错：解析失败直接抛出，让上层统一处理（UI 全局异常钩子/CLI 退出码）。
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from engine.configs.resource_types import ResourceType
from engine.graph.utils.metadata_extractor import load_graph_metadata_from_file
from engine.resources.management_naming_rules import get_id_field_for_type
from engine.utils.resource_library_layout import get_packages_root_dir


@dataclass(frozen=True, slots=True)
class DiskDuplicateEntry:
    """磁盘侧的重复资源 ID 条目（同一 ID 对应多个文件）。"""

    resource_id: str
    file_paths: Tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class ConsistencyCategoryReport:
    """单个逻辑分类（例如 templates / management:timers）的对比结果。"""

    category_key: str
    display_name: str

    index_count: int
    disk_count: int

    missing_ids: Tuple[str, ...]
    orphan_ids: Tuple[str, ...]
    duplicate_index_ids: Tuple[str, ...]
    duplicate_disk_entries: Tuple[DiskDuplicateEntry, ...]

    def has_issues(self) -> bool:
        return bool(
            self.missing_ids
            or self.orphan_ids
            or self.duplicate_index_ids
            or self.duplicate_disk_entries
        )


@dataclass(frozen=True, slots=True)
class PackageIndexDiskConsistencyReport:
    package_id: str
    package_root_dir: Path
    category_reports: Tuple[ConsistencyCategoryReport, ...]

    total_missing: int
    total_orphan: int
    total_duplicate_index: int
    total_duplicate_disk: int

    def has_issues(self) -> bool:
        return bool(self.total_missing or self.total_orphan or self.total_duplicate_index or self.total_duplicate_disk)

    def render_text(self, *, max_items_per_list: int = 50) -> str:
        """渲染为可复制的文本报告。"""
        lines: List[str] = []
        lines.append("索引 vs 磁盘一致性检查报告")
        lines.append("=" * 70)
        lines.append(f"package_id: {self.package_id}")
        lines.append(f"package_root: {self.package_root_dir}")
        lines.append(
            "summary: "
            f"missing={self.total_missing} orphan={self.total_orphan} "
            f"dup_index={self.total_duplicate_index} dup_disk={self.total_duplicate_disk}"
        )
        lines.append("")

        for category in self.category_reports:
            if not category.has_issues():
                continue
            lines.append("-" * 70)
            lines.append(
                f"[{category.category_key}] {category.display_name} | index={category.index_count} disk={category.disk_count}"
            )

            def render_id_list(label: str, values: Sequence[str]) -> None:
                if not values:
                    return
                shown = list(values)[: int(max_items_per_list)]
                more_count = max(0, len(values) - len(shown))
                lines.append(f"- {label} ({len(values)}): {', '.join(shown)}" + (f" ... +{more_count}" if more_count else ""))

            render_id_list("缺失（索引有、磁盘无）", category.missing_ids)
            render_id_list("孤儿（磁盘有、索引无）", category.orphan_ids)
            render_id_list("索引重复", category.duplicate_index_ids)

            if category.duplicate_disk_entries:
                lines.append(f"- 磁盘重复/冲突 ({len(category.duplicate_disk_entries)}):")
                for entry in category.duplicate_disk_entries[: int(max_items_per_list)]:
                    path_text = " | ".join(str(p) for p in entry.file_paths)
                    lines.append(f"  - {entry.resource_id}: {path_text}")
                if len(category.duplicate_disk_entries) > int(max_items_per_list):
                    lines.append(f"  - ... +{len(category.duplicate_disk_entries) - int(max_items_per_list)}")
        if not any(category.has_issues() for category in self.category_reports):
            lines.append("✅ 未发现索引/磁盘不一致。")
        lines.append("")
        return "\n".join(lines)


_COMBAT_BUCKET_TO_RESOURCE_TYPE: Dict[str, ResourceType] = {
    "player_templates": ResourceType.PLAYER_TEMPLATE,
    "player_classes": ResourceType.PLAYER_CLASS,
    "unit_statuses": ResourceType.UNIT_STATUS,
    "skills": ResourceType.SKILL,
    "projectiles": ResourceType.PROJECTILE,
    "items": ResourceType.ITEM,
}

_MANAGEMENT_BUCKET_TO_RESOURCE_TYPE: Dict[str, ResourceType] = {
    "timers": ResourceType.TIMER,
    "level_variables": ResourceType.LEVEL_VARIABLE,
    "preset_points": ResourceType.PRESET_POINT,
    "skill_resources": ResourceType.SKILL_RESOURCE,
    "currency_backpack": ResourceType.CURRENCY_BACKPACK,
    "equipment_data": ResourceType.EQUIPMENT_DATA,
    "shop_templates": ResourceType.SHOP_TEMPLATE,
    "ui_layouts": ResourceType.UI_LAYOUT,
    "ui_widget_templates": ResourceType.UI_WIDGET_TEMPLATE,
    "ui_pages": ResourceType.UI_PAGE,
    "multi_language": ResourceType.MULTI_LANGUAGE,
    "main_cameras": ResourceType.MAIN_CAMERA,
    "light_sources": ResourceType.LIGHT_SOURCE,
    "background_music": ResourceType.BACKGROUND_MUSIC,
    "paths": ResourceType.PATH,
    "entity_deployment_groups": ResourceType.ENTITY_DEPLOYMENT_GROUP,
    "unit_tags": ResourceType.UNIT_TAG,
    "scan_tags": ResourceType.SCAN_TAG,
    "shields": ResourceType.SHIELD,
    "peripheral_systems": ResourceType.PERIPHERAL_SYSTEM,
    "save_points": ResourceType.SAVE_POINT,
    "chat_channels": ResourceType.CHAT_CHANNEL,
    "level_settings": ResourceType.LEVEL_SETTINGS,
    "signals": ResourceType.SIGNAL,
    "struct_definitions": ResourceType.STRUCT_DEFINITION,
}


def _is_path_under(root_dir: Path, file_path: Path) -> bool:
    root_parts = root_dir.resolve().parts
    target_parts = file_path.resolve().parts
    if len(target_parts) < len(root_parts):
        return False
    return target_parts[: len(root_parts)] == root_parts


def _is_reserved_python_file(py_file: Path) -> bool:
    if py_file.parent.name == "__pycache__":
        return True
    if py_file.name.startswith("_"):
        return True
    if "校验" in py_file.stem:
        return True
    return False


def _extract_python_module_level_string_constant(file_path: Path, *, constant_name: str) -> str:
    code_text = file_path.read_text(encoding="utf-8")
    parsed_tree = ast.parse(code_text, filename=str(file_path))
    for node in parsed_tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id != constant_name:
                    continue
                value_node = node.value
                if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
                    return value_node.value.strip()
        if isinstance(node, ast.AnnAssign):
            target_node = node.target
            if not isinstance(target_node, ast.Name):
                continue
            if target_node.id != constant_name:
                continue
            value_node = node.value
            if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
                return value_node.value.strip()
    return ""


def _scan_disk_python_resources(
    *,
    package_root_dir: Path,
    resource_type: ResourceType,
) -> Dict[str, List[Path]]:
    resource_dir = package_root_dir / str(resource_type.value)
    if not resource_dir.exists() or not resource_dir.is_dir():
        return {}

    id_to_paths: Dict[str, List[Path]] = {}
    for py_file in resource_dir.rglob("*.py"):
        if not py_file.is_file():
            continue
        if _is_reserved_python_file(py_file):
            continue

        if resource_type == ResourceType.GRAPH:
            metadata = load_graph_metadata_from_file(py_file)
            resource_id = str(metadata.graph_id or "").strip() or py_file.stem
        elif resource_type == ResourceType.SIGNAL:
            resource_id = _extract_python_module_level_string_constant(
                py_file,
                constant_name="SIGNAL_ID",
            )
            if not resource_id:
                raise ValueError(f"无法从信号定义文件中解析 SIGNAL_ID：{py_file}")
        elif resource_type == ResourceType.STRUCT_DEFINITION:
            resource_id = _extract_python_module_level_string_constant(
                py_file,
                constant_name="STRUCT_ID",
            )
            if not resource_id:
                raise ValueError(f"无法从结构体定义文件中解析 STRUCT_ID：{py_file}")
        else:
            raise ValueError(f"不支持的 Python 资源类型：{resource_type}")

        id_to_paths.setdefault(resource_id, []).append(py_file)
    return id_to_paths


def _scan_disk_json_resources(
    *,
    package_root_dir: Path,
    resource_type: ResourceType,
) -> Dict[str, List[Path]]:
    directories_to_scan: List[Path] = [package_root_dir / str(resource_type.value)]
    if resource_type == ResourceType.INSTANCE:
        legacy_dir = package_root_dir / "实例"
        if legacy_dir.exists() and legacy_dir.is_dir():
            raise ValueError(
                f"检测到旧目录名 '实例'：{legacy_dir}。请将其改名为 '{resource_type.value}' 后重试。"
            )

    id_to_paths: Dict[str, List[Path]] = {}
    for resource_dir in directories_to_scan:
        if not resource_dir.exists() or not resource_dir.is_dir():
            continue
        for json_file in resource_dir.glob("*.json"):
            if not json_file.is_file():
                continue
            payload = json.loads(json_file.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                continue

            id_field = get_id_field_for_type(resource_type)
            resource_id = ""
            if id_field:
                raw_id = payload.get(id_field)
                if isinstance(raw_id, str):
                    resource_id = raw_id.strip()
            if not resource_id:
                resource_id = json_file.stem

            id_to_paths.setdefault(resource_id, []).append(json_file)
    return id_to_paths


def _scan_disk_composite_ids(*, package_root_dir: Path) -> Dict[str, List[Path]]:
    composites_dir = package_root_dir / "复合节点库"
    if not composites_dir.exists() or not composites_dir.is_dir():
        return {}
    id_to_paths: Dict[str, List[Path]] = {}
    for py_file in composites_dir.rglob("*.py"):
        if not py_file.is_file():
            continue
        if _is_reserved_python_file(py_file):
            continue
        if not py_file.stem.startswith("composite_"):
            continue
        composite_id = py_file.stem
        id_to_paths.setdefault(composite_id, []).append(py_file)
    return id_to_paths


def _scan_disk_level_variable_file_ids(*, package_root_dir: Path) -> List[str]:
    # 关卡变量（代码级 Schema）：以 VARIABLE_FILE_ID 作为资源 ID
    from engine.resources.level_variable_schema_view import get_default_level_variable_schema_view

    schema_view = get_default_level_variable_schema_view()
    variable_files = schema_view.get_all_variable_files()
    file_ids: List[str] = []
    for file_id, info in variable_files.items():
        absolute_path = getattr(info, "absolute_path", None)
        if isinstance(absolute_path, Path) and _is_path_under(package_root_dir, absolute_path):
            file_ids.append(str(file_id))
    file_ids.sort(key=lambda text: text.casefold())
    return file_ids


def _scan_disk_save_point_template_ids(*, package_root_dir: Path) -> List[str]:
    # 局内存档模板（代码级 Schema）：以 template_id 作为资源 ID
    from engine.resources.ingame_save_template_schema_view import get_default_ingame_save_template_schema_view

    schema_view = get_default_ingame_save_template_schema_view()
    all_templates = schema_view.get_all_templates()
    template_ids: List[str] = []
    for template_id in all_templates.keys():
        file_path = schema_view.get_template_file_path(str(template_id))
        if isinstance(file_path, Path) and _is_path_under(package_root_dir, file_path):
            template_ids.append(str(template_id))
    template_ids.sort(key=lambda text: text.casefold())
    return template_ids


def _find_duplicate_ids_in_index_list(resource_ids: Sequence[str]) -> List[str]:
    counts: Dict[str, int] = {}
    for resource_id in resource_ids:
        normalized = str(resource_id or "").strip()
        if not normalized:
            continue
        counts[normalized] = counts.get(normalized, 0) + 1
    duplicates = [resource_id for resource_id, count in counts.items() if count > 1]
    duplicates.sort(key=lambda text: text.casefold())
    return duplicates


def collect_package_index_disk_consistency(
    *,
    package_id: str,
    resource_manager,
    package_index_manager,
) -> PackageIndexDiskConsistencyReport:
    """对指定项目存档执行“索引 vs 磁盘”一致性检查并返回报告。"""
    normalized_package_id = str(package_id or "").strip()
    if not normalized_package_id:
        raise ValueError("package_id 不能为空")
    if normalized_package_id in {"global_view", "unclassified_view"}:
        raise ValueError(f"不支持的 package_id（特殊视图不参与该检查）：{normalized_package_id}")

    workspace_root = getattr(resource_manager, "workspace_path", None)
    if not isinstance(workspace_root, Path):
        raise ValueError("resource_manager.workspace_path 缺失或不是 Path")

    resource_library_root = workspace_root / "assets" / "资源库"
    packages_root_dir = get_packages_root_dir(resource_library_root)
    package_root_dir = packages_root_dir / normalized_package_id
    if not package_root_dir.exists() or not package_root_dir.is_dir():
        raise ValueError(f"项目存档目录不存在：{package_root_dir}")

    package_index = package_index_manager.load_package_index(
        normalized_package_id,
        refresh_resource_names=False,
    )
    if package_index is None:
        raise ValueError(f"无法加载 PackageIndex：{normalized_package_id}")

    # ------------------------------ 索引侧 ID 集合
    index_category_to_ids: Dict[str, List[str]] = {
        "templates": list(getattr(package_index.resources, "templates", []) or []),
        "instances": list(getattr(package_index.resources, "instances", []) or []),
        "graphs": list(getattr(package_index.resources, "graphs", []) or []),
        "composites": list(getattr(package_index.resources, "composites", []) or []),
    }

    combat_presets = getattr(package_index.resources, "combat_presets", {}) or {}
    for bucket_name in _COMBAT_BUCKET_TO_RESOURCE_TYPE.keys():
        key = f"combat:{bucket_name}"
        index_category_to_ids[key] = list(combat_presets.get(bucket_name, []) or [])

    management_resources = getattr(package_index.resources, "management", {}) or {}
    for bucket_name in _MANAGEMENT_BUCKET_TO_RESOURCE_TYPE.keys():
        key = f"management:{bucket_name}"
        index_category_to_ids[key] = list(management_resources.get(bucket_name, []) or [])

    # ------------------------------ 磁盘侧 ID 集合（直接扫描 package_root_dir）
    disk_category_to_id_paths: Dict[str, Dict[str, List[Path]]] = {}

    disk_category_to_id_paths["templates"] = _scan_disk_json_resources(
        package_root_dir=package_root_dir,
        resource_type=ResourceType.TEMPLATE,
    )
    disk_category_to_id_paths["instances"] = _scan_disk_json_resources(
        package_root_dir=package_root_dir,
        resource_type=ResourceType.INSTANCE,
    )
    disk_category_to_id_paths["graphs"] = _scan_disk_python_resources(
        package_root_dir=package_root_dir,
        resource_type=ResourceType.GRAPH,
    )
    disk_category_to_id_paths["composites"] = _scan_disk_composite_ids(
        package_root_dir=package_root_dir,
    )

    for bucket_name, resource_type in _COMBAT_BUCKET_TO_RESOURCE_TYPE.items():
        disk_category_to_id_paths[f"combat:{bucket_name}"] = _scan_disk_json_resources(
            package_root_dir=package_root_dir,
            resource_type=resource_type,
        )

    for bucket_name, resource_type in _MANAGEMENT_BUCKET_TO_RESOURCE_TYPE.items():
        category_key = f"management:{bucket_name}"
        if bucket_name == "level_variables":
            file_ids = _scan_disk_level_variable_file_ids(package_root_dir=package_root_dir)
            disk_category_to_id_paths[category_key] = {file_id: [package_root_dir] for file_id in file_ids}
            continue
        if bucket_name == "save_points":
            template_ids = _scan_disk_save_point_template_ids(package_root_dir=package_root_dir)
            disk_category_to_id_paths[category_key] = {template_id: [package_root_dir] for template_id in template_ids}
            continue
        if resource_type in (ResourceType.SIGNAL, ResourceType.STRUCT_DEFINITION):
            disk_category_to_id_paths[category_key] = _scan_disk_python_resources(
                package_root_dir=package_root_dir,
                resource_type=resource_type,
            )
            continue
        disk_category_to_id_paths[category_key] = _scan_disk_json_resources(
            package_root_dir=package_root_dir,
            resource_type=resource_type,
        )

    # ------------------------------ 组装报告
    category_reports: List[ConsistencyCategoryReport] = []
    total_missing = 0
    total_orphan = 0
    total_duplicate_index = 0
    total_duplicate_disk = 0

    def category_display_name(category_key: str) -> str:
        if category_key == "templates":
            return "元件"
        if category_key == "instances":
            return "实体摆放"
        if category_key == "graphs":
            return "节点图"
        if category_key == "composites":
            return "复合节点库"
        if category_key.startswith("combat:"):
            return f"战斗预设/{category_key.split(':', 1)[1]}"
        if category_key.startswith("management:"):
            return f"管理配置/{category_key.split(':', 1)[1]}"
        return category_key

    for category_key, index_ids in index_category_to_ids.items():
        disk_id_to_paths = disk_category_to_id_paths.get(category_key, {})
        index_id_list = [str(value or "").strip() for value in list(index_ids) if str(value or "").strip()]
        disk_ids = list(disk_id_to_paths.keys())

        index_id_set = set(index_id_list)
        disk_id_set = set(disk_ids)

        missing_ids = sorted(index_id_set - disk_id_set, key=lambda text: text.casefold())
        orphan_ids = sorted(disk_id_set - index_id_set, key=lambda text: text.casefold())

        duplicate_index_ids = _find_duplicate_ids_in_index_list(index_id_list)

        duplicate_disk_entries: List[DiskDuplicateEntry] = []
        for resource_id, file_paths in disk_id_to_paths.items():
            if len(file_paths) <= 1:
                continue
            resolved_paths = tuple(sorted((Path(path) for path in file_paths), key=lambda p: str(p).casefold()))
            duplicate_disk_entries.append(DiskDuplicateEntry(resource_id=str(resource_id), file_paths=resolved_paths))
        duplicate_disk_entries.sort(key=lambda entry: entry.resource_id.casefold())

        total_missing += len(missing_ids)
        total_orphan += len(orphan_ids)
        total_duplicate_index += len(duplicate_index_ids)
        total_duplicate_disk += len(duplicate_disk_entries)

        category_reports.append(
            ConsistencyCategoryReport(
                category_key=category_key,
                display_name=category_display_name(category_key),
                index_count=len(index_id_list),
                disk_count=len(disk_id_set),
                missing_ids=tuple(missing_ids),
                orphan_ids=tuple(orphan_ids),
                duplicate_index_ids=tuple(duplicate_index_ids),
                duplicate_disk_entries=tuple(duplicate_disk_entries),
            )
        )

    category_reports.sort(key=lambda report: report.category_key.casefold())

    return PackageIndexDiskConsistencyReport(
        package_id=normalized_package_id,
        package_root_dir=package_root_dir,
        category_reports=tuple(category_reports),
        total_missing=int(total_missing),
        total_orphan=int(total_orphan),
        total_duplicate_index=int(total_duplicate_index),
        total_duplicate_disk=int(total_duplicate_disk),
    )


