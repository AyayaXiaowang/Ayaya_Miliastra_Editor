"""资源文件命名迁移工具 - 将ID命名迁移到Name命名"""

from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Dict, List
from datetime import datetime

# 确保可以导入项目模块
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from engine.resources.resource_manager import ResourceManager, ResourceType
from engine.resources.management_naming_rules import get_display_name_field_for_type


class ResourceNamingMigrationTool:
    """资源命名迁移工具"""
    
    def __init__(self, workspace_path: Path):
        """初始化迁移工具
        
        Args:
            workspace_path: 工作空间路径（Graph_Generater目录）
        """
        self.workspace_path = workspace_path
        self.resource_library_dir = workspace_path / "assets" / "资源库"
        self.package_index_dir = workspace_path / "assets" / "资源库" / "地图索引"
        self.migration_log: List[str] = []
    
    def migrate_all(self, dry_run: bool = False) -> Dict[str, int]:
        """执行完整迁移
        
        Args:
            dry_run: 如果为True，只模拟迁移不实际执行
        
        Returns:
            迁移统计：{resource_type: count}
        """
        self.migration_log.clear()
        self._log("=" * 60)
        self._log("资源文件命名迁移工具")
        self._log(f"工作空间: {self.workspace_path}")
        self._log(f"模式: {'试运行（不实际修改文件）' if dry_run else '实际迁移'}")
        self._log("=" * 60)
        self._log("")
        
        stats = {}
        
        # 1. 迁移存档索引文件
        package_count = self._migrate_package_indexes(dry_run)
        stats["存档索引"] = package_count
        self._log("")
        
        # 2. 迁移模板文件
        template_count = self._migrate_resource_type(ResourceType.TEMPLATE, "template_id", dry_run)
        stats["模板"] = template_count
        self._log("")
        
        # 3. 迁移实例文件
        instance_count = self._migrate_resource_type(ResourceType.INSTANCE, "instance_id", dry_run)
        stats["实例"] = instance_count
        self._log("")
        
        # 4. 迁移其他资源类型（战斗预设、管理配置等）
        other_types = [
            (ResourceType.PLAYER_TEMPLATE, "玩家模板"),
            (ResourceType.PLAYER_CLASS, "职业"),
            (ResourceType.UNIT_STATUS, "单位状态"),
            (ResourceType.SKILL, "技能"),
            (ResourceType.PROJECTILE, "投射物"),
            (ResourceType.ITEM, "道具"),
            (ResourceType.TIMER, "计时器"),
            (ResourceType.LEVEL_VARIABLE, "关卡变量"),
            (ResourceType.UI_LAYOUT, "UI布局"),
            (ResourceType.UI_WIDGET_TEMPLATE, "UI控件模板"),
        ]
        
        for resource_type, type_name in other_types:
            count = self._migrate_resource_type(resource_type, "id", dry_run)
            if count > 0:
                stats[type_name] = count
                self._log("")
        
        # 总结
        self._log("=" * 60)
        self._log("迁移完成！")
        self._log("")
        self._log("迁移统计：")
        total = 0
        for resource_type, count in stats.items():
            if count > 0:
                self._log(f"  - {resource_type}: {count} 个文件")
                total += count
        self._log(f"  总计: {total} 个文件")
        self._log("=" * 60)
        
        # 保存日志
        self._save_migration_log()
        
        return stats
    
    def _migrate_package_indexes(self, dry_run: bool) -> int:
        """迁移存档索引文件
        
        Args:
            dry_run: 是否为试运行
        
        Returns:
            迁移的文件数量
        """
        self._log("[存档索引] 开始迁移...")
        count = 0
        
        if not self.package_index_dir.exists():
            self._log("  存档索引目录不存在，跳过")
            return 0
        
        # 查找所有pkg_开头的json文件（排除packages.json）
        for json_file in self.package_index_dir.glob("pkg_*.json"):
            if json_file.name == "packages.json":
                continue
            
            # 读取文件内容
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            package_id = data.get("package_id")
            package_name = data.get("name")
            
            if not package_id or not package_name:
                self._log(f"  跳过（缺少ID或名称）: {json_file.name}")
                continue
            
            # 检查文件名是否已经是name格式
            current_filename = json_file.stem
            if current_filename == package_id:
                # 需要迁移
                new_name = ResourceManager.sanitize_filename(package_name)
                new_filename = f"pkg_{new_name}"
                
                # 处理重名冲突
                counter = 2
                while (self.package_index_dir / f"{new_filename}.json").exists():
                    existing_file = self.package_index_dir / f"{new_filename}.json"
                    # 检查是否是同一个包
                    with open(existing_file, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                        if existing_data.get("package_id") == package_id:
                            # 已经存在，跳过
                            self._log(f"  跳过（已迁移）: {json_file.name}")
                            break
                    new_filename = f"pkg_{new_name}_{counter}"
                    counter += 1
                else:
                    new_file = self.package_index_dir / f"{new_filename}.json"
                    self._log(f"  {json_file.name} -> {new_file.name}")
                    
                    if not dry_run:
                        json_file.rename(new_file)
                    
                    count += 1
            else:
                self._log(f"  跳过（已使用name命名）: {json_file.name}")
        
        self._log(f"[存档索引] 迁移完成，共 {count} 个文件")
        return count
    
    def _migrate_resource_type(self, resource_type: ResourceType, id_field: str, dry_run: bool) -> int:
        """迁移特定类型的资源文件
        
        Args:
            resource_type: 资源类型
            id_field: ID字段名称
            dry_run: 是否为试运行
        
        Returns:
            迁移的文件数量
        """
        self._log(f"[{resource_type.value}] 开始迁移...")
        count = 0
        display_name_field = get_display_name_field_for_type(resource_type)
        
        resource_dir = self.resource_library_dir / resource_type.value
        if not resource_dir.exists():
            self._log(f"  目录不存在，跳过")
            return 0
        
        # 只处理JSON文件（节点图.py文件已经是name命名）
        for json_file in resource_dir.glob("*.json"):
            # 读取文件内容
            with open(json_file, 'r', encoding='utf-8') as file_object:
                data = json.load(file_object)
            
            resource_id = data.get(id_field)
            if not resource_id:
                self._log(f"  跳过（缺少ID）: {json_file.name}")
                continue

            resource_name = data.get("name")

            # 若通用 name 缺失或仍等于 ID，则尝试从各资源类型约定的显示名字段回填
            if (not resource_name or resource_name == resource_id) and display_name_field is not None:
                display_name_value = data.get(display_name_field)
                if isinstance(display_name_value, str):
                    stripped_display_name = display_name_value.strip()
                    if stripped_display_name:
                        resource_name = stripped_display_name
                        if not dry_run:
                            data["name"] = stripped_display_name
                            data["updated_at"] = datetime.now().isoformat()
                            with open(json_file, "w", encoding="utf-8") as output_file:
                                json.dump(data, output_file, ensure_ascii=False, indent=2)

            if not resource_name:
                self._log(f"  跳过（缺少名称）: {json_file.name}")
                continue
            
            # 特殊处理：关卡实体文件保持使用ID命名（避免重名冲突）
            is_level_entity = data.get("metadata", {}).get("is_level_entity", False)
            if is_level_entity:
                self._log(f"  跳过（关卡实体保持ID命名）: {json_file.name}")
                continue
            
            # 检查文件名是否已经是name格式
            current_filename = json_file.stem
            if current_filename == resource_id:
                # 需要迁移
                new_name = ResourceManager.sanitize_filename(resource_name)
                
                # 处理重名冲突
                new_filename = new_name
                counter = 2
                while (resource_dir / f"{new_filename}.json").exists():
                    existing_file = resource_dir / f"{new_filename}.json"
                    # 检查是否是同一个资源
                    with open(existing_file, 'r', encoding='utf-8') as existing_stream:
                        existing_data = json.load(existing_stream)
                        if existing_data.get(id_field) == resource_id:
                            # 已经存在，跳过
                            self._log(f"  跳过（已迁移）: {json_file.name}")
                            break
                    new_filename = f"{new_name}_{counter}"
                    counter += 1
                else:
                    new_file = resource_dir / f"{new_filename}.json"
                    self._log(f"  {json_file.name} -> {new_file.name}")
                    
                    if not dry_run:
                        json_file.rename(new_file)
                    
                    count += 1
            else:
                self._log(f"  跳过（已使用name命名）: {json_file.name}")
        
        self._log(f"[{resource_type.value}] 迁移完成，共 {count} 个文件")
        return count
    
    def _log(self, message: str) -> None:
        """记录日志
        
        Args:
            message: 日志消息
        """
        print(message)
        self.migration_log.append(message)
    
    def _save_migration_log(self) -> None:
        """保存迁移日志"""
        log_dir = self.workspace_path / ".migration_logs"
        log_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"migration_{timestamp}.log"
        
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(self.migration_log))
        
        print(f"\n迁移日志已保存: {log_file}")


def run_migration(workspace_path: Path, dry_run: bool = True):
    """运行迁移工具
    
    Args:
        workspace_path: 工作空间路径
        dry_run: 是否为试运行（默认为True，只模拟不实际修改）
    """
    tool = ResourceNamingMigrationTool(workspace_path)
    stats = tool.migrate_all(dry_run=dry_run)
    return stats


if __name__ == "__main__":
    import sys
    
    # 获取工作空间路径
    if len(sys.argv) > 1:
        workspace = Path(sys.argv[1])
    else:
        workspace = Path(__file__).parent.parent.parent
    
    # 检查是否为实际迁移模式
    actual_run = "--run" in sys.argv
    
    if actual_run:
        print("\n警告: 即将执行实际迁移，文件将被重命名！")
        confirm = input("确认继续吗？(输入 yes 继续): ")
        if confirm.lower() != "yes":
            print("已取消迁移")
            sys.exit(0)
    
    # 运行迁移
    run_migration(workspace, dry_run=not actual_run)

