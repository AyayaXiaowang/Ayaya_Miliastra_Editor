"""存档索引管理器 - 管理轻量级存档索引的持久化"""

from __future__ import annotations
import json
from pathlib import Path
from typing import List, Optional, Dict, TYPE_CHECKING
from datetime import datetime

from engine.configs.resource_types import ResourceType
from engine.resources.package_index import PackageIndex, PackageResources
from engine.graph.models.package_model import InstanceConfig
from engine.utils.logging.logger import log_info
from engine.utils.name_utils import sanitize_package_filename
from .atomic_json import atomic_write_json

if TYPE_CHECKING:
    from engine.resources.resource_manager import ResourceManager


PACKAGES_LIST_SCHEMA = "package_list/v1"
PACKAGES_LIST_SCHEMA_VERSION = 1


class PackageIndexManager:
    """存档索引管理器"""
    _COMBAT_RESOURCE_TYPE_MAP: Dict[str, ResourceType] = {
        "player_templates": ResourceType.PLAYER_TEMPLATE,
        "player_classes": ResourceType.PLAYER_CLASS,
        "unit_statuses": ResourceType.UNIT_STATUS,
        "skills": ResourceType.SKILL,
        "projectiles": ResourceType.PROJECTILE,
        "items": ResourceType.ITEM,
    }

    _MANAGEMENT_RESOURCE_TYPE_MAP: Dict[str, ResourceType] = {
        "timers": ResourceType.TIMER,
        "level_variables": ResourceType.LEVEL_VARIABLE,
        "preset_points": ResourceType.PRESET_POINT,
        "skill_resources": ResourceType.SKILL_RESOURCE,
        "currency_backpack": ResourceType.CURRENCY_BACKPACK,
        "equipment_data": ResourceType.EQUIPMENT_DATA,
        "shop_templates": ResourceType.SHOP_TEMPLATE,
        "ui_layouts": ResourceType.UI_LAYOUT,
        "ui_widget_templates": ResourceType.UI_WIDGET_TEMPLATE,
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
    
    def __init__(self, workspace_path: Path, resource_manager: 'ResourceManager'):
        """初始化存档索引管理器
        
        Args:
            workspace_path: 工作空间路径（Graph_Generater目录）
            resource_manager: 资源管理器（用于创建关卡实体等资源）
        """
        self.workspace_path = workspace_path
        self.resource_manager = resource_manager
        # 功能包索引物理位置：assets/资源库/功能包索引
        # 注意：此路径必须与资源库文档中的说明保持一致，否则 UI 将在启动时看不到任何存档包。
        self.index_dir = workspace_path / "assets" / "资源库" / "功能包索引"
        self.index_dir.mkdir(parents=True, exist_ok=True)

        # Todo 勾选状态为编辑器运行期状态，单独保存在 app/runtime/todo_states 下，
        # 不写回功能包索引 JSON，避免污染存档包结构。
        self.todo_state_dir = workspace_path / "app" / "runtime" / "todo_states"
        self.todo_state_dir.mkdir(parents=True, exist_ok=True)
        
        self.packages_file = self.index_dir / "packages.json"
        
        # ID到文件名的映射缓存：{package_id: filename_without_ext}
        self.package_id_to_filename: Dict[str, str] = {}
        
        self._ensure_packages_file()
        self._build_package_filename_index()
        self._ensure_packages_list_consistent()

    def _compute_packages_list_fingerprint(self) -> str:
        """计算存档包清单指纹（pkg_*.json 文件数 + 最新修改时间）。"""
        file_count = 0
        latest_mtime = 0.0
        for json_file in self.index_dir.glob("pkg_*.json"):
            stat = json_file.stat()
            file_count += 1
            if stat.st_mtime > latest_mtime:
                latest_mtime = stat.st_mtime
        return f"pkg_index:{file_count}:{round(latest_mtime, 3)}"

    def _read_packages_list_data(self) -> dict:
        """读取 packages.json 原始内容（不做一致性修复）。"""
        if self.packages_file.exists():
            with open(self.packages_file, "r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
            if isinstance(data, dict):
                packages_value = data.get("packages")
                last_opened_value = data.get("last_opened_package_id")
                manifest_value = data.get("__manifest__")
                return {
                    "packages": packages_value if isinstance(packages_value, list) else [],
                    "last_opened_package_id": last_opened_value if isinstance(last_opened_value, (str, type(None))) else None,
                    "__manifest__": manifest_value if isinstance(manifest_value, dict) else {},
                }
        return {"packages": [], "last_opened_package_id": None, "__manifest__": {}}

    def _rebuild_packages_list_data(self, previous_last_opened: Optional[str]) -> dict:
        """从 pkg_*.json 重建 packages.json 的 packages 列表（派生数据）。"""
        packages: List[dict] = []
        for json_file in self.index_dir.glob("pkg_*.json"):
            if json_file.name == "packages.json":
                continue
            with open(json_file, "r", encoding="utf-8") as file_obj:
                pkg_data = json.load(file_obj)
            if not isinstance(pkg_data, dict):
                continue
            package_id_value = pkg_data.get("package_id")
            if not isinstance(package_id_value, str) or not package_id_value:
                continue
            packages.append(
                {
                    "package_id": package_id_value,
                    "name": pkg_data.get("name", ""),
                    "description": pkg_data.get("description", ""),
                    "created_at": pkg_data.get("created_at", ""),
                    "updated_at": pkg_data.get("updated_at", ""),
                }
            )

        # 排序：优先按更新时间（字符串 ISO），再按 package_id 兜底，保证稳定输出
        packages.sort(key=lambda item: (str(item.get("updated_at", "")), str(item.get("package_id", ""))), reverse=True)

        # last_opened 只存“选择状态”，若指向不存在的包则清空（特殊视图保留）
        last_opened = previous_last_opened
        if isinstance(last_opened, str) and last_opened not in ("global_view", "unclassified_view"):
            valid_ids = {pkg.get("package_id") for pkg in packages if isinstance(pkg, dict)}
            if last_opened not in valid_ids:
                last_opened = None

        return {
            "packages": packages,
            "last_opened_package_id": last_opened,
        }

    def _ensure_packages_list_consistent(self) -> None:
        """确保 packages.json 与当前 index_dir 的 pkg_*.json 集合一致。"""
        current_fp = self._compute_packages_list_fingerprint()
        raw = self._read_packages_list_data()
        manifest = raw.get("__manifest__")
        if not isinstance(manifest, dict):
            manifest = {}
        saved_schema = manifest.get("schema")
        saved_version = manifest.get("schema_version")
        saved_fp = manifest.get("packages_fp")

        if saved_schema != PACKAGES_LIST_SCHEMA or saved_version != PACKAGES_LIST_SCHEMA_VERSION or saved_fp != current_fp:
            rebuilt = self._rebuild_packages_list_data(raw.get("last_opened_package_id"))
            self._save_packages_list_data(rebuilt)

    def _load_packages_list_data(self) -> dict:
        """加载存档列表数据（保证一致性）。"""
        self._ensure_packages_file()
        self._ensure_packages_list_consistent()
        return self._read_packages_list_data()

    def _save_packages_list_data(self, data: dict) -> None:
        """保存存档列表数据（写入派生 manifest）。"""
        packages_value = data.get("packages")
        last_opened_value = data.get("last_opened_package_id")
        normalized = {
            "packages": packages_value if isinstance(packages_value, list) else [],
            "last_opened_package_id": last_opened_value if isinstance(last_opened_value, (str, type(None))) else None,
        }
        normalized["__manifest__"] = {
            "schema": PACKAGES_LIST_SCHEMA,
            "schema_version": PACKAGES_LIST_SCHEMA_VERSION,
            "packages_fp": self._compute_packages_list_fingerprint(),
            "generated_at": datetime.now().isoformat(),
            "source": "engine.resources.PackageIndexManager",
        }
        atomic_write_json(self.packages_file, normalized, ensure_ascii=False, indent=2)

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
        - 内容为 {todo_id: bool} 映射，仅供编辑器 UI 使用，不参与功能包导出。
        """
        todo_file_path = self._get_todo_state_file_path(package_index.package_id)
        atomic_write_json(todo_file_path, package_index.todo_states, ensure_ascii=False, indent=2)
    
    def _ensure_packages_file(self) -> None:
        """确保存档列表文件存在"""
        if not self.packages_file.exists():
            self._save_packages_list_data(
                {"packages": [], "last_opened_package_id": None}
            )
    
    def _build_package_filename_index(self) -> None:
        """扫描存档索引目录，构建ID到文件名的映射，并同步name字段"""
        self.package_id_to_filename.clear()
        sync_count = 0
        
        for json_file in self.index_dir.glob("pkg_*.json"):
            # 跳过packages.json
            if json_file.name == "packages.json":
                continue
            
            # 读取文件获取package_id
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                package_id = data.get("package_id")
                if package_id:
                    filename_without_ext = json_file.stem
                    self.package_id_to_filename[package_id] = filename_without_ext
                    
                    # 检查文件名与内部name是否一致
                    if self._check_and_sync_package_name(json_file, data, filename_without_ext):
                        sync_count += 1
        
        if sync_count > 0:
            log_info("[同步] 自动同步了 {} 个存档的name字段（文件名已被手动修改）", sync_count)
            # name 同步会写回 pkg_*.json，清单文件应视为派生数据，统一重建一次以保持一致。
            self._ensure_packages_list_consistent()
    
    @staticmethod
    def _sanitize_package_filename(name: str) -> str:
        """清理存档文件名（无前缀）。"""
        return sanitize_package_filename(name)
    
    def _check_and_sync_package_name(self, file_path: Path, data: dict, filename_without_ext: str) -> bool:
        """检查存档文件名与内部name字段是否一致，如果不一致则同步
        
        Args:
            file_path: 文件路径
            data: 已加载的存档数据
            filename_without_ext: 文件名（不含扩展名，包含pkg_前缀）
        
        Returns:
            是否进行了同步
        """
        internal_name = data.get("name", "")
        if not internal_name:
            return False
        
        # 从文件名中提取显示名（去掉pkg_前缀）
        if filename_without_ext.startswith("pkg_"):
            display_name_from_file = filename_without_ext[4:]  # 去掉"pkg_"
        else:
            return False
        
        # 比较清理后的名称
        sanitized_internal_name = self._sanitize_package_filename(internal_name)
        if sanitized_internal_name != display_name_from_file:
            # 名称不一致，以文件名为准，更新内部name
            data["name"] = display_name_from_file
            data["updated_at"] = datetime.now().isoformat()
            
            # 保存更新后的文件（原子写，避免中断导致索引 JSON 半写入）
            atomic_write_json(file_path, data, ensure_ascii=False, indent=2)

            log_info(
                "  [文件名同步] {}: name字段 '{}' -> '{}'",
                file_path.name,
                internal_name,
                display_name_from_file,
            )
            return True
        
        return False
    
    def _resolve_display_name(self, resource_type: ResourceType, resource_id: str) -> str:
        """根据资源类型解析可读名称，未命名时回退到ID。"""
        metadata = self.resource_manager.get_resource_metadata(resource_type, resource_id)
        if metadata:
            raw_name = metadata.get("name")
            if isinstance(raw_name, str):
                cleaned_name = raw_name.strip()
                if cleaned_name:
                    return cleaned_name
        return resource_id

    def _build_resource_names(self, package_index: PackageIndex) -> Dict[str, dict]:
        """为当前存档引用的资源生成 ID->可读名 映射。"""
        resource_names: Dict[str, dict] = {
            "templates": {},
            "instances": {},
            "graphs": {},
            "composites": {},
            "combat_presets": {key: {} for key in self._COMBAT_RESOURCE_TYPE_MAP},
            "management": {key: {} for key in self._MANAGEMENT_RESOURCE_TYPE_MAP},
        }

        def fill_bucket(target: Dict[str, str], resource_ids: List[str], resource_type: Optional[ResourceType]) -> None:
            for resource_id in resource_ids:
                if not isinstance(resource_id, str) or not resource_id:
                    continue
                if resource_type is None:
                    target[resource_id] = resource_id
                else:
                    target[resource_id] = self._resolve_display_name(resource_type, resource_id)

        fill_bucket(resource_names["templates"], package_index.resources.templates, ResourceType.TEMPLATE)
        fill_bucket(resource_names["instances"], package_index.resources.instances, ResourceType.INSTANCE)
        fill_bucket(resource_names["graphs"], package_index.resources.graphs, ResourceType.GRAPH)
        fill_bucket(resource_names["composites"], package_index.resources.composites, None)

        for bucket_name, resource_type in self._COMBAT_RESOURCE_TYPE_MAP.items():
            bucket_ids = package_index.resources.combat_presets.get(bucket_name, [])
            fill_bucket(resource_names["combat_presets"][bucket_name], bucket_ids, resource_type)

        for bucket_name, resource_type in self._MANAGEMENT_RESOURCE_TYPE_MAP.items():
            bucket_ids = package_index.resources.management.get(bucket_name, [])
            fill_bucket(resource_names["management"][bucket_name], bucket_ids, resource_type)

        return resource_names

    def _refresh_resource_names(self, package_index: PackageIndex) -> bool:
        """刷新并写回资源名称映射，返回是否发生变更。"""
        latest_names = self._build_resource_names(package_index)
        if package_index.resource_names != latest_names:
            package_index.resource_names = latest_names
            return True
        return False
    
    def _get_package_file_path(self, package_id: str, package_name: str = None) -> Path:
        """获取存档索引文件路径（优先使用name命名）
        
        Args:
            package_id: 存档ID
            package_name: 存档名称（如果提供，使用name作为文件名）
        
        Returns:
            存档索引文件路径
        """
        # 1. 先尝试从缓存获取
        if package_id in self.package_id_to_filename:
            filename = self.package_id_to_filename[package_id]
            return self.index_dir / f"{filename}.json"
        
        # 2. 如果提供了name，使用清理后的名称
        if package_name:
            sanitized_name = self._sanitize_package_filename(package_name)
            filename = f"pkg_{sanitized_name}"
            # 处理重名冲突
            counter = 2
            while (self.index_dir / f"{filename}.json").exists():
                # 检查是否是同一个包
                existing_file = self.index_dir / f"{filename}.json"
                with open(existing_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get("package_id") == package_id:
                        # 是同一个包，直接返回
                        return existing_file
                filename = f"pkg_{sanitized_name}_{counter}"
                counter += 1
            return self.index_dir / f"{filename}.json"
        
        # 3. 回退到使用ID命名
        return self.index_dir / f"{package_id}.json"
    
    def list_packages(self) -> List[dict]:
        """列出所有存档的基本信息
        
        Returns:
            存档信息列表
        """
        data = self._load_packages_list_data()
        return data.get("packages", [])
    
    def create_package(self, name: str, description: str = "") -> str:
        """创建新存档
        
        Args:
            name: 存档名称
            description: 存档描述
        
        Returns:
            存档ID
        """
        # 生成唯一ID
        package_id = datetime.now().strftime("pkg_%Y%m%d_%H%M%S_%f")
        
        # 创建关卡实体实例
        level_entity_id = f"level_{package_id}"
        level_entity = InstanceConfig(
            instance_id=level_entity_id,
            name="关卡实体",
            template_id=level_entity_id,  # 关卡实体的template_id和instance_id相同
            position=[0.0, 0.0, 0.0],
            rotation=[0.0, 0.0, 0.0],
            override_variables=[],
            additional_graphs=[],
            additional_components=[],
            metadata={"is_level_entity": True, "entity_type": "关卡"},
            graph_variable_overrides={}
        )
        
        # 保存关卡实体到资源库
        level_entity_data = level_entity.serialize()
        self.resource_manager.save_resource(ResourceType.INSTANCE, level_entity_id, level_entity_data)
        
        # 创建存档索引
        package_index = PackageIndex(
            package_id=package_id,
            name=name,
            description=description,
            level_entity_id=level_entity_id
        )
        
        # 关卡实体ID添加到实例列表
        package_index.add_instance(level_entity_id)
        
        # 保存索引文件
        self.save_package_index(package_index)
        
        # 更新存档列表
        packages_data = self._load_packages_list_data()
        package_info = {
            "package_id": package_id,
            "name": name,
            "description": description,
            "created_at": package_index.created_at,
            "updated_at": package_index.updated_at
        }
        packages_data["packages"].append(package_info)
        self._save_packages_list_data(packages_data)
        
        return package_id
    
    def save_package_index(self, package_index: PackageIndex) -> None:
        """保存存档索引
        
        Args:
            package_index: 存档索引对象
        """
        self._refresh_resource_names(package_index)
        package_index.updated_at = datetime.now().isoformat()
        
        # 使用name作为文件名
        index_file = self._get_package_file_path(package_index.package_id, package_index.name)
        
        # 删除旧文件（如果文件名改变了）
        if package_index.package_id in self.package_id_to_filename:
            old_filename = self.package_id_to_filename[package_index.package_id]
            old_file = self.index_dir / f"{old_filename}.json"
            if old_file.exists() and old_file != index_file:
                old_file.unlink()
                log_info("  [重命名] 已删除旧存档文件: {}", old_file.name)
        
        # 保存索引文件（原子写）
        atomic_write_json(index_file, package_index.serialize(), ensure_ascii=False, indent=2)

        # 单独保存 Todo 勾选状态到运行期状态目录
        self._save_todo_states(package_index)
        
        # 更新文件名缓存
        self.package_id_to_filename[package_index.package_id] = index_file.stem
        
        # 更新存档列表中的信息
        packages_data = self._load_packages_list_data()
        for pkg_info in packages_data["packages"]:
            if pkg_info["package_id"] == package_index.package_id:
                pkg_info["name"] = package_index.name
                pkg_info["description"] = package_index.description
                pkg_info["updated_at"] = package_index.updated_at
                break
        self._save_packages_list_data(packages_data)
    
    def load_package_index(self, package_id: str) -> Optional[PackageIndex]:
        """加载存档索引
        
        Args:
            package_id: 存档ID
        
        Returns:
            存档索引对象，如果不存在返回None
        """
        # 优先从缓存查找
        index_file = self._get_package_file_path(package_id)
        
        if not index_file.exists():
            # 尝试查找旧的ID命名格式
            old_format_file = self.index_dir / f"{package_id}.json"
            if old_format_file.exists():
                index_file = old_format_file
            else:
                return None
        
        with open(index_file, 'r', encoding='utf-8') as file:
            data = json.load(file)

        package_index = PackageIndex.deserialize(data)

        # 加载或迁移 Todo 勾选状态到运行期状态目录：
        # - 首选 app/runtime/todo_states/<package_id>.json；
        # - 若不存在且旧索引中携带 todo_states 字段，则立即迁移并写入新位置。
        loaded_todo_states = self._load_todo_states(package_index.package_id)
        if loaded_todo_states:
            package_index.todo_states = loaded_todo_states
        else:
            inline_todo_states = data.get("todo_states")
            if isinstance(inline_todo_states, dict) and inline_todo_states:
                package_index.todo_states = dict(inline_todo_states)
                self._save_todo_states(package_index)
        
        if self._refresh_resource_names(package_index):
            self.save_package_index(package_index)
        
        # 更新缓存
        if package_id not in self.package_id_to_filename:
            self.package_id_to_filename[package_id] = index_file.stem
        
        return package_index
    
    def delete_package(self, package_id: str) -> None:
        """删除存档
        
        Args:
            package_id: 存档ID
        """
        # 删除索引文件（使用缓存中的文件名）
        index_file = self._get_package_file_path(package_id)
        if index_file.exists():
            index_file.unlink()
        
        # 从缓存中删除
        if package_id in self.package_id_to_filename:
            del self.package_id_to_filename[package_id]
        
        # 从存档列表中删除
        packages_data = self._load_packages_list_data()
        packages_data["packages"] = [
            pkg for pkg in packages_data["packages"] 
            if pkg["package_id"] != package_id
        ]
        self._save_packages_list_data(packages_data)
    
    def rename_package(self, package_id: str, new_name: str) -> None:
        """重命名存档
        
        Args:
            package_id: 存档ID
            new_name: 新名称
        """
        package_index = self.load_package_index(package_id)
        if package_index:
            package_index.name = new_name
            self.save_package_index(package_index)
    
    def update_description(self, package_id: str, new_description: str) -> None:
        """更新存档描述
        
        Args:
            package_id: 存档ID
            new_description: 新描述
        """
        package_index = self.load_package_index(package_id)
        if package_index:
            package_index.description = new_description
            self.save_package_index(package_index)
    
    def get_package_info(self, package_id: str) -> Optional[dict]:
        """获取存档基本信息
        
        Args:
            package_id: 存档ID
        
        Returns:
            存档信息字典
        """
        packages = self.list_packages()
        for pkg_info in packages:
            if pkg_info["package_id"] == package_id:
                return pkg_info
        return None
    
    def set_last_opened_package(self, package_id: Optional[str]) -> None:
        """设置最近打开的存档
        
        Args:
            package_id: 存档ID
        """
        packages_data = self._load_packages_list_data()
        previous_last_opened = packages_data.get("last_opened_package_id")
        if previous_last_opened == package_id:
            return

        packages_data["last_opened_package_id"] = package_id
        self._save_packages_list_data(packages_data)
        self.resource_manager.refresh_resource_library_fingerprint()
    
    def get_last_opened_package(self) -> Optional[str]:
        """获取最近打开的存档ID
        
        Returns:
            存档ID，如果没有返回None
        """
        packages_data = self._load_packages_list_data()
        last_package_id = packages_data.get("last_opened_package_id")
        
        # 支持特殊视图（不需要在存档列表中验证存在性）
        if last_package_id in ("global_view", "unclassified_view"):
            return last_package_id

        # 验证这个存档是否还存在
        if last_package_id:
            package_info = self.get_package_info(last_package_id)
            if package_info:
                return last_package_id
        
        return None
    
    def add_resource_to_package(self, package_id: str, resource_type: str, resource_id: str) -> bool:
        """添加资源到存档
        
        Args:
            package_id: 存档ID
            resource_type: 资源类型（template, instance, graph等）
            resource_id: 资源ID
        
        Returns:
            是否添加成功
        """
        package_index = self.load_package_index(package_id)
        if not package_index:
            return False
        
        # 根据资源类型添加引用
        if resource_type == "template":
            package_index.add_template(resource_id)
        elif resource_type == "instance":
            package_index.add_instance(resource_id)
        elif resource_type == "graph":
            package_index.add_graph(resource_id)
        elif resource_type == "composite":
            package_index.add_composite(resource_id)
        elif resource_type.startswith("combat_"):
            preset_type = resource_type.replace("combat_", "")
            package_index.add_combat_preset(preset_type, resource_id)
        elif resource_type.startswith("management_"):
            mgmt_type = resource_type.replace("management_", "")
            package_index.add_management_resource(mgmt_type, resource_id)
        else:
            return False
        
        self.save_package_index(package_index)
        return True
    
    def remove_resource_from_package(self, package_id: str, resource_type: str, resource_id: str) -> bool:
        """从存档移除资源
        
        Args:
            package_id: 存档ID
            resource_type: 资源类型
            resource_id: 资源ID
        
        Returns:
            是否移除成功
        """
        package_index = self.load_package_index(package_id)
        if not package_index:
            return False
        
        # 根据资源类型移除引用
        if resource_type == "template":
            package_index.remove_template(resource_id)
        elif resource_type == "instance":
            package_index.remove_instance(resource_id)
        elif resource_type == "graph":
            package_index.remove_graph(resource_id)
        elif resource_type == "composite":
            package_index.remove_composite(resource_id)
        elif resource_type.startswith("combat_"):
            preset_type = resource_type.replace("combat_", "")
            package_index.remove_combat_preset(preset_type, resource_id)
        elif resource_type.startswith("management_"):
            mgmt_type = resource_type.replace("management_", "")
            package_index.remove_management_resource(mgmt_type, resource_id)
        else:
            return False
        
        self.save_package_index(package_index)
        return True
    
    def get_package_resources(self, package_id: str) -> Optional[PackageResources]:
        """获取存档的所有资源引用
        
        Args:
            package_id: 存档ID
        
        Returns:
            资源引用对象
        """
        package_index = self.load_package_index(package_id)
        if not package_index:
            return None
        
        return package_index.resources

