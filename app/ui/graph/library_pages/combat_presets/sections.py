"""战斗预设分类处理逻辑。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Tuple, Union

from PyQt6 import QtWidgets

from engine.configs.combat.combat_presets_model import (
    ItemConfig,
    PlayerClassConfig,
    PlayerTemplateConfig,
    ProjectileConfig,
    SkillConfig,
    UnitStatusConfig,
)
from engine.configs.resource_types import ResourceType
from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_view import PackageView
from engine.utils.resource_library_layout import get_packages_root_dir, get_shared_root_dir
from app.ui.graph.library_pages.combat_presets.dialogs import (
    NewItemDialog,
    NewPlayerClassDialog,
    NewPlayerTemplateDialog,
    NewProjectileDialog,
    NewRoleDialog,
    NewSkillDialog,
    NewUnitStatusDialog,
)
from app.ui.foundation.id_generator import generate_prefixed_id

PresetPackage = Union[PackageView, GlobalResourceView]


@dataclass
class TableRowData:
    """描述表格行所需的数据。"""

    name: str
    type_name: str
    attr1: str
    attr2: str
    attr3: str
    description: str
    last_modified: str
    user_data: Tuple[str, str]


class BaseCombatPresetSection:
    """每个战斗预设分类的通用接口。"""

    category_key: str
    tree_label: str
    selection_label: str
    type_name: str

    def iter_rows(self, package: PresetPackage) -> Iterable[TableRowData]:
        raise NotImplementedError

    def create_item(self, parent_widget: QtWidgets.QWidget, package: PresetPackage) -> bool:
        raise NotImplementedError

    def edit_item(self, parent_widget: QtWidgets.QWidget, package: PresetPackage, item_id: str) -> bool:
        raise NotImplementedError

    def delete_item(self, package: PresetPackage, item_id: str) -> bool:
        raise NotImplementedError

    @staticmethod
    def _current_timestamp() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _save_resource_for_package(
        package: PresetPackage,
        resource_type: ResourceType,
        resource_id: str,
        payload: dict,
    ) -> None:
        """将战斗预设资源立即写入资源库。

        设计约定：
        - 资源本体以 JSON 文件形式落盘；
        - 目录即项目存档模式下，需要把“新建资源”的默认落点写入正确的资源根目录：
          - PackageView：写入当前项目存档根目录；
          - GlobalResourceView：写入共享根目录；
        - 若不指定落点，资源层会默认写入“测试项目”等默认归档项目，导致当前视图刷新后不可见。
        """
        resource_manager = getattr(package, "resource_manager", None)
        if resource_manager is None:
            raise ValueError("当前视图未提供 resource_manager，无法保存战斗预设资源")

        existing_file = resource_manager.list_resource_file_paths(resource_type).get(
            str(resource_id)
        )
        if existing_file is None:
            if isinstance(package, PackageView):
                package_id = str(getattr(package, "package_id", "") or "").strip()
                if not package_id:
                    raise ValueError("无法解析 PackageView.package_id，无法写入战斗预设资源")
                package_root_dir = (
                    get_packages_root_dir(resource_manager.resource_library_dir) / package_id
                )
                resource_manager.save_resource(
                    resource_type,
                    resource_id,
                    payload,
                    resource_root_dir=package_root_dir,
                )
                return

            if isinstance(package, GlobalResourceView):
                shared_root_dir = get_shared_root_dir(resource_manager.resource_library_dir)
                resource_manager.save_resource(
                    resource_type,
                    resource_id,
                    payload,
                    resource_root_dir=shared_root_dir,
                )
                return

        # 已存在资源：保持其原有资源根目录不变。
        resource_manager.save_resource(resource_type, resource_id, payload)


class PlayerTemplateSection(BaseCombatPresetSection):
    category_key = "player_template"
    tree_label = "🧍 玩家模板"
    selection_label = "玩家模板"
    type_name = "玩家模板"

    def iter_rows(self, package: PresetPackage) -> Iterable[TableRowData]:
        for template_id, template_data in package.combat_presets.player_templates.items():
            yield TableRowData(
                name=template_data.get("template_name", "未命名"),
                type_name=self.type_name,
                attr1=f"等级:{template_data.get('level', 1)}",
                attr2=f"默认职业:{template_data.get('default_profession_id', '') or '-'}",
                attr3="-",
                description=template_data.get("description", ""),
                last_modified=template_data.get("last_modified", ""),
                user_data=(self.category_key, template_id),
            )

    def create_item(self, parent_widget: QtWidgets.QWidget, package: PresetPackage) -> bool:
        _ = parent_widget

        player_templates = package.combat_presets.player_templates
        if not isinstance(player_templates, dict):
            player_templates = {}
            package.combat_presets.player_templates = player_templates  # type: ignore[assignment]

        before_count = len(player_templates)
        template_id = generate_prefixed_id("player")
        default_name = f"玩家模板{len(player_templates) + 1}"

        player_template = PlayerTemplateConfig(
            template_id=template_id,
            template_name=default_name,
        )
        template_dict = player_template.serialize()
        # 规范化通用 ID 字段，便于资源层与工具脚本统一处理
        template_dict["id"] = template_id
        template_dict["last_modified"] = self._current_timestamp()
        player_templates[template_id] = template_dict
        after_count = len(player_templates)
        package_id_repr = getattr(package, "package_id", "<no-package-id>")
        print(
            "[COMBAT-PRESETS] 新建玩家模板：",
            f"package_id={package_id_repr!r}, template_id={template_id!r}, ",
            f"name={default_name!r}, before_count={before_count}, after_count={after_count}",
        )

        # 资源立即落盘到统一战斗预设目录，不依赖具体存档索引。
        self._save_resource_for_package(
            package,
            ResourceType.PLAYER_TEMPLATE,
            template_id,
            dict(template_dict),
        )
        return True

    def edit_item(self, parent_widget: QtWidgets.QWidget, package: PresetPackage, item_id: str) -> bool:
        template_data = package.combat_presets.player_templates[item_id]
        dialog = NewPlayerTemplateDialog(
            parent=parent_widget,
            title="编辑玩家模板",
            initial_data=template_data,
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return False
        updated = dialog.get_data()
        template_data["template_name"] = updated["template_name"]
        template_data["level"] = updated["level"]
        template_data["default_profession_id"] = updated["default_profession_id"]
        template_data["description"] = updated["description"]
        template_data["last_modified"] = self._current_timestamp()
        return True

    def delete_item(self, package: PresetPackage, item_id: str) -> bool:
        del package.combat_presets.player_templates[item_id]
        return True


class PlayerClassSection(BaseCombatPresetSection):
    category_key = "player_class"
    tree_label = "👤 职业"
    selection_label = "职业"
    type_name = "职业"

    def iter_rows(self, package: PresetPackage) -> Iterable[TableRowData]:
        for class_id, class_data in package.combat_presets.player_classes.items():
            yield TableRowData(
                name=class_data.get("class_name", "未命名"),
                type_name=self.type_name,
                attr1=f"生命:{class_data.get('base_health', 100)}",
                attr2=f"攻击:{class_data.get('base_attack', 10)}",
                attr3=f"防御:{class_data.get('base_defense', 5)}",
                description=class_data.get("description", ""),
                last_modified=class_data.get("last_modified", ""),
                user_data=(self.category_key, class_id),
            )

    def create_item(self, parent_widget: QtWidgets.QWidget, package: PresetPackage) -> bool:
        _ = parent_widget

        player_classes = package.combat_presets.player_classes
        if not isinstance(player_classes, dict):
            player_classes = {}
            package.combat_presets.player_classes = player_classes  # type: ignore[assignment]

        before_count = len(player_classes)
        class_id = generate_prefixed_id("class")
        default_name = f"职业{len(player_classes) + 1}"

        player_class = PlayerClassConfig(
            class_id=class_id,
            class_name=default_name,
        )
        class_dict = player_class.serialize()
        # 为职业资源补充通用 ID 字段
        class_dict["id"] = class_id
        class_dict["last_modified"] = self._current_timestamp()
        player_classes[class_id] = class_dict
        after_count = len(player_classes)
        package_id_repr = getattr(package, "package_id", "<no-package-id>")
        print(
            "[COMBAT-PRESETS] 新建职业：",
            f"package_id={package_id_repr!r}, class_id={class_id!r}, ",
            f"name={default_name!r}, before_count={before_count}, after_count={after_count}",
        )

        self._save_resource_for_package(
            package,
            ResourceType.PLAYER_CLASS,
            class_id,
            dict(class_dict),
        )
        return True

    def edit_item(self, parent_widget: QtWidgets.QWidget, package: PresetPackage, item_id: str) -> bool:
        class_data = package.combat_presets.player_classes[item_id]
        dialog = NewPlayerClassDialog(
            parent=parent_widget,
            title="编辑职业",
            initial_data=class_data,
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return False
        updated = dialog.get_data()
        class_data["class_name"] = updated["class_name"]
        class_data["base_health"] = updated["base_health"]
        class_data["base_attack"] = updated["base_attack"]
        class_data["base_defense"] = updated["base_defense"]
        class_data["base_speed"] = updated["base_speed"]
        class_data["description"] = updated["description"]
        class_data["last_modified"] = self._current_timestamp()
        return True

    def delete_item(self, package: PresetPackage, item_id: str) -> bool:
        del package.combat_presets.player_classes[item_id]
        return True


class SkillSection(BaseCombatPresetSection):
    category_key = "skill"
    tree_label = "⚔️ 技能"
    selection_label = "技能"
    type_name = "技能"

    def iter_rows(self, package: PresetPackage) -> Iterable[TableRowData]:
        for skill_id, skill_data in package.combat_presets.skills.items():
            yield TableRowData(
                name=skill_data.get("skill_name", "未命名"),
                type_name=self.type_name,
                attr1=f"冷却:{skill_data.get('cooldown', 5)}秒",
                attr2=f"消耗:{skill_data.get('cost_value', 10)}{skill_data.get('cost_type', 'mana')}",
                attr3=f"伤害:{skill_data.get('damage', 20)}",
                description=skill_data.get("description", ""),
                last_modified=skill_data.get("last_modified", ""),
                user_data=(self.category_key, skill_id),
            )

    def create_item(self, parent_widget: QtWidgets.QWidget, package: PresetPackage) -> bool:
        _ = parent_widget

        skills = package.combat_presets.skills
        if not isinstance(skills, dict):
            skills = {}
            package.combat_presets.skills = skills  # type: ignore[assignment]

        before_count = len(skills)
        skill_id = generate_prefixed_id("skill")
        default_name = f"技能{len(skills) + 1}"

        skill = SkillConfig(
            skill_id=skill_id,
            skill_name=default_name,
        )
        skill_dict = skill.serialize()
        # 为技能资源补充通用 ID 字段
        skill_dict["id"] = skill_id
        skill_dict["last_modified"] = self._current_timestamp()
        skills[skill_id] = skill_dict
        after_count = len(skills)
        package_id_repr = getattr(package, "package_id", "<no-package-id>")
        print(
            "[COMBAT-PRESETS] 新建技能：",
            f"package_id={package_id_repr!r}, skill_id={skill_id!r}, ",
            f"name={default_name!r}, before_count={before_count}, after_count={after_count}",
        )

        self._save_resource_for_package(
            package,
            ResourceType.SKILL,
            skill_id,
            dict(skill_dict),
        )
        return True

    def edit_item(self, parent_widget: QtWidgets.QWidget, package: PresetPackage, item_id: str) -> bool:
        skill_data = package.combat_presets.skills[item_id]
        dialog = NewSkillDialog(
            parent=parent_widget,
            title="编辑技能",
            initial_data=skill_data,
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return False
        updated = dialog.get_data()
        skill_data["skill_name"] = updated["skill_name"]
        skill_data["cooldown"] = updated["cooldown"]
        skill_data["cost_type"] = updated["cost_type"]
        skill_data["cost_value"] = updated["cost_value"]
        skill_data["damage"] = updated["damage"]
        skill_data["range_value"] = updated["range_value"]
        skill_data["description"] = updated["description"]
        skill_data["last_modified"] = self._current_timestamp()
        return True

    def delete_item(self, package: PresetPackage, item_id: str) -> bool:
        del package.combat_presets.skills[item_id]
        return True


class ProjectileSection(BaseCombatPresetSection):
    category_key = "projectile"
    tree_label = "💥 本地投射物"
    selection_label = "本地投射物"
    type_name = "本地投射物"

    def iter_rows(self, package: PresetPackage) -> Iterable[TableRowData]:
        for projectile_id, projectile_data in package.combat_presets.projectiles.items():
            yield TableRowData(
                name=projectile_data.get("projectile_name", "未命名"),
                type_name=self.type_name,
                attr1=f"速度:{projectile_data.get('speed', 10)}",
                attr2=f"生命:{projectile_data.get('lifetime', 5)}秒",
                attr3=f"命中:{'是' if projectile_data.get('hit_detection_enabled', True) else '否'}",
                description=projectile_data.get("description", ""),
                last_modified=projectile_data.get("last_modified", ""),
                user_data=(self.category_key, projectile_id),
            )

    def create_item(self, parent_widget: QtWidgets.QWidget, package: PresetPackage) -> bool:
        _ = parent_widget

        projectiles = package.combat_presets.projectiles
        if not isinstance(projectiles, dict):
            projectiles = {}
            package.combat_presets.projectiles = projectiles  # type: ignore[assignment]

        before_count = len(projectiles)
        projectile_id = generate_prefixed_id("projectile")
        default_name = f"投射物{len(projectiles) + 1}"

        projectile = ProjectileConfig(
            projectile_id=projectile_id,
            projectile_name=default_name,
        )
        projectile_dict = projectile.serialize()
        # 为投射物资源补充通用 ID 字段
        projectile_dict["id"] = projectile_id
        projectile_dict["last_modified"] = self._current_timestamp()
        projectiles[projectile_id] = projectile_dict
        after_count = len(projectiles)
        package_id_repr = getattr(package, "package_id", "<no-package-id>")
        print(
            "[COMBAT-PRESETS] 新建本地投射物：",
            f"package_id={package_id_repr!r}, projectile_id={projectile_id!r}, ",
            f"name={default_name!r}, before_count={before_count}, after_count={after_count}",
        )

        self._save_resource_for_package(
            package,
            ResourceType.PROJECTILE,
            projectile_id,
            dict(projectile_dict),
        )
        return True

    def edit_item(self, parent_widget: QtWidgets.QWidget, package: PresetPackage, item_id: str) -> bool:
        projectile_data = package.combat_presets.projectiles[item_id]
        dialog = NewProjectileDialog(
            parent=parent_widget,
            title="编辑投射物",
            initial_data=projectile_data,
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return False
        updated = dialog.get_data()
        projectile_data["projectile_name"] = updated["projectile_name"]
        projectile_data["speed"] = updated["speed"]
        projectile_data["lifetime"] = updated["lifetime"]
        projectile_data["hit_detection_enabled"] = updated["hit_detection_enabled"]
        projectile_data["description"] = updated["description"]
        projectile_data["last_modified"] = self._current_timestamp()
        return True

    def delete_item(self, package: PresetPackage, item_id: str) -> bool:
        del package.combat_presets.projectiles[item_id]
        return True


class UnitStatusSection(BaseCombatPresetSection):
    category_key = "unit_status"
    tree_label = "💊 单位状态"
    selection_label = "单位状态"
    type_name = "单位状态"

    def iter_rows(self, package: PresetPackage) -> Iterable[TableRowData]:
        for status_id, status_data in package.combat_presets.unit_statuses.items():
            yield TableRowData(
                name=status_data.get("status_name", "未命名"),
                type_name=self.type_name,
                attr1=f"持续:{status_data.get('duration', 0)}秒",
                attr2=f"类型:{status_data.get('effect_type', 'buff')}",
                attr3=f"堆叠:{'是' if status_data.get('is_stackable', False) else '否'}",
                description=status_data.get("description", ""),
                last_modified=status_data.get("last_modified", ""),
                user_data=(self.category_key, status_id),
            )

    def create_item(self, parent_widget: QtWidgets.QWidget, package: PresetPackage) -> bool:
        _ = parent_widget

        unit_statuses = package.combat_presets.unit_statuses
        if not isinstance(unit_statuses, dict):
            unit_statuses = {}
            package.combat_presets.unit_statuses = unit_statuses  # type: ignore[assignment]

        before_count = len(unit_statuses)
        status_id = generate_prefixed_id("status")
        default_name = f"单位状态{len(unit_statuses) + 1}"

        unit_status = UnitStatusConfig(
            status_id=status_id,
            status_name=default_name,
        )
        status_dict = unit_status.serialize()
        # 为单位状态资源补充通用 ID 字段
        status_dict["id"] = status_id
        status_dict["last_modified"] = self._current_timestamp()
        unit_statuses[status_id] = status_dict
        after_count = len(unit_statuses)
        package_id_repr = getattr(package, "package_id", "<no-package-id>")
        print(
            "[COMBAT-PRESETS] 新建单位状态：",
            f"package_id={package_id_repr!r}, status_id={status_id!r}, ",
            f"name={default_name!r}, before_count={before_count}, after_count={after_count}",
        )

        self._save_resource_for_package(
            package,
            ResourceType.UNIT_STATUS,
            status_id,
            dict(status_dict),
        )
        return True

    def edit_item(self, parent_widget: QtWidgets.QWidget, package: PresetPackage, item_id: str) -> bool:
        status_data = package.combat_presets.unit_statuses[item_id]
        dialog = NewUnitStatusDialog(
            parent=parent_widget,
            title="编辑状态",
            initial_data=status_data,
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return False
        updated = dialog.get_data()
        status_data["status_name"] = updated["status_name"]
        status_data["duration"] = updated["duration"]
        status_data["effect_type"] = updated["effect_type"]
        status_data["is_stackable"] = updated["is_stackable"]
        status_data["description"] = updated["description"]
        status_data["last_modified"] = self._current_timestamp()
        return True

    def delete_item(self, package: PresetPackage, item_id: str) -> bool:
        del package.combat_presets.unit_statuses[item_id]
        return True


class ItemSection(BaseCombatPresetSection):
    category_key = "item"
    tree_label = "🎁 道具"
    selection_label = "道具"
    type_name = "道具"

    def iter_rows(self, package: PresetPackage) -> Iterable[TableRowData]:
        for item_id, item_data in package.combat_presets.items.items():
            yield TableRowData(
                name=item_data.get("item_name", "未命名"),
                type_name=self.type_name,
                attr1=f"类型:{item_data.get('item_type', 'consumable')}",
                attr2=f"稀有度:{item_data.get('rarity', 'common')}",
                attr3=f"堆叠:{item_data.get('max_stack', 99)}",
                description=item_data.get("description", ""),
                last_modified=item_data.get("last_modified", ""),
                user_data=(self.category_key, item_id),
            )

    def create_item(self, parent_widget: QtWidgets.QWidget, package: PresetPackage) -> bool:
        _ = parent_widget

        items = package.combat_presets.items
        if not isinstance(items, dict):
            items = {}
            package.combat_presets.items = items  # type: ignore[assignment]

        before_count = len(items)
        item_id = generate_prefixed_id("item")
        default_name = f"道具{len(items) + 1}"

        item = ItemConfig(
            item_id=item_id,
            item_name=default_name,
        )
        item_dict = item.serialize()
        # 为道具资源补充通用 ID 字段
        item_dict["id"] = item_id
        item_dict["last_modified"] = self._current_timestamp()
        items[item_id] = item_dict
        after_count = len(items)
        package_id_repr = getattr(package, "package_id", "<no-package-id>")
        print(
            "[COMBAT-PRESETS] 新建道具：",
            f"package_id={package_id_repr!r}, item_id={item_id!r}, ",
            f"name={default_name!r}, before_count={before_count}, after_count={after_count}",
        )

        self._save_resource_for_package(
            package,
            ResourceType.ITEM,
            item_id,
            dict(item_dict),
        )
        return True

    def edit_item(self, parent_widget: QtWidgets.QWidget, package: PresetPackage, item_id: str) -> bool:
        item_data = package.combat_presets.items[item_id]
        dialog = NewItemDialog(
            parent=parent_widget,
            title="编辑道具",
            initial_data=item_data,
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return False
        updated = dialog.get_data()
        item_data["item_name"] = updated["item_name"]
        item_data["item_type"] = updated["item_type"]
        item_data["rarity"] = updated["rarity"]
        item_data["max_stack"] = updated["max_stack"]
        item_data["description"] = updated["description"]
        item_data["last_modified"] = self._current_timestamp()
        return True

    def delete_item(self, package: PresetPackage, item_id: str) -> bool:
        del package.combat_presets.items[item_id]
        return True


SECTION_SEQUENCE: Tuple[BaseCombatPresetSection, ...] = (
    PlayerTemplateSection(),
    PlayerClassSection(),
    SkillSection(),
    ProjectileSection(),
    UnitStatusSection(),
    ItemSection(),
)

SECTION_MAP = {section.category_key: section for section in SECTION_SEQUENCE}
SECTION_SELECTION_LABELS: Tuple[str, ...] = tuple(section.selection_label for section in SECTION_SEQUENCE)


def get_section_by_key(category_key: str) -> BaseCombatPresetSection | None:
    """根据分类键查找 Section。"""
    return SECTION_MAP.get(category_key)


def get_section_by_selection_label(selection_label: str) -> BaseCombatPresetSection | None:
    """根据展示名称查找 Section。"""
    for section in SECTION_SEQUENCE:
        if section.selection_label == selection_label:
            return section
    return None


