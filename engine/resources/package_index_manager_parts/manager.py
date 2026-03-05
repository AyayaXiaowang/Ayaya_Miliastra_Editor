"""存档索引管理器（拆分后入口实现）。"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, TYPE_CHECKING

from engine.configs.resource_types import ResourceType
from engine.utils.resource_library_layout import get_packages_root_dir

from .index_cache_mixin import PackageIndexCacheMixin
from .naming_listing_mixin import PackageIndexNamingListingMixin
from .package_clone_mixin import PackageIndexCloneMixin
from .runtime_and_movement_mixin import PackageIndexRuntimeAndMovementMixin

if TYPE_CHECKING:
    from engine.resources.package_index import PackageIndex
    from engine.resources.resource_manager import ResourceManager


class PackageIndexManager(
    PackageIndexNamingListingMixin,
    PackageIndexCloneMixin,
    PackageIndexCacheMixin,
    PackageIndexRuntimeAndMovementMixin,
):
    """存档索引管理器（目录即项目存档模式）。

    对外 API 保持与旧 `engine.resources.package_index_manager.PackageIndexManager` 一致，
    实现拆分到同目录下的若干 mixin。
    """

    # 目录模式下的“新建项目”模板项目存档目录名
    TEMPLATE_PACKAGE_DIRNAME = "示例项目模板"

    # copytree 忽略：避免把运行期产物或字节码带入新项目
    # 注意：`共享文档` 目录名用于项目存档内的“共享文档 Junction”，复制时必须忽略；
    # 否则 copytree 可能把 Junction 当作普通目录展开复制，导致“零复制共享”失效或产生重复内容。
    _CLONE_IGNORE_PATTERNS = ("__pycache__", "*.pyc", "共享文档")
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

    def __init__(self, workspace_path: Path, resource_manager: "ResourceManager"):
        """初始化存档索引管理器

        Args:
            workspace_path: 工作空间路径（Graph_Generater目录）
            resource_manager: 资源管理器（用于创建关卡实体等资源）
        """
        self.workspace_path = workspace_path
        self.resource_manager = resource_manager

        resource_library_root = workspace_path / "assets" / "资源库"
        self._packages_root_dir = get_packages_root_dir(resource_library_root)

        # 彻底移除 legacy 索引文件（pkg_*.json / packages.json）支持：
        # - 项目存档以目录结构作为唯一真相源：assets/资源库/项目存档/<package_id>/...
        # - 若检测到旧索引文件，直接报错并要求迁移/清理，避免“静默回退到旧模式”。
        #
        # 注意：此处**禁止**使用 rglob 扫描整个资源库：
        # - `assets/资源库` 下允许存在外部工具的解析产物目录（例如 `存档包/`），可能包含大量 index.json/report.json；
        # - 目录模式下我们只拦截“旧式存档索引”文件本体（历史上固定落点），避免误伤外部产物。
        legacy_pkg_files = []
        legacy_pkg_files.extend(list(resource_library_root.glob("pkg_*.json")))
        legacy_pkg_files.extend(list(resource_library_root.glob("packages.json")))

        legacy_pkg_files = sorted(
            [path for path in legacy_pkg_files if path.exists() and path.is_file()],
            key=lambda path: path.as_posix().casefold(),
        )
        if legacy_pkg_files:
            file_list = "\n".join(
                f"- {path.relative_to(resource_library_root).as_posix()}" for path in legacy_pkg_files[:10]
            )
            more = ""
            if len(legacy_pkg_files) > 10:
                more = f"\n- ... 还有 {len(legacy_pkg_files) - 10} 个"
            raise ValueError(
                "已检测到旧模式存档索引文件（不再支持 pkg_*.json / packages.json）：\n"
                f"{file_list}{more}\n"
                "请迁移到目录结构（assets/资源库/项目存档/<package_id>/...）后再运行。"
            )

        # Todo 勾选状态为编辑器运行期状态，单独保存在 app/runtime/todo_states 下
        self.todo_state_dir = workspace_path / "app" / "runtime" / "todo_states"
        self.todo_state_dir.mkdir(parents=True, exist_ok=True)

        # 运行期包状态：用于存储 last_opened 等“仅编辑器需要”的轻量状态，不属于资源库资产。
        self._package_state_file = workspace_path / "app" / "runtime" / "package_state.json"
        self._package_state_file.parent.mkdir(parents=True, exist_ok=True)

        # 存档索引内存缓存：避免 UI 在枚举“所属存档”时对每个包反复读盘派生。
        # 目录模式下不存在单独的“索引文件”，因此缓存以 **项目存档根目录的 mtime** 作为一致性基线。
        self._package_index_cache: Dict[str, "PackageIndex"] = {}
        self._package_index_cache_mtime: Dict[str, float] = {}


