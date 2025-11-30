"""战斗预设相关的表单对话框。"""

from typing import Optional

from PyQt6 import QtWidgets

from ui.foundation.base_widgets import FormDialog


class NewPlayerTemplateDialog(FormDialog):
    """玩家模板表单对话框。"""

    def __init__(
        self,
        parent=None,
        *,
        title: Optional[str] = None,
        initial_data: Optional[dict[str, object]] = None,
    ):
        self._initial_data = dict(initial_data or {})
        super().__init__(title=title or "新建玩家模板", width=500, height=380, parent=parent)
        self._setup_form()
        self._apply_initial_data()

    def _setup_form(self) -> None:
        """初始化表单控件。"""
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("例如：默认玩家模板")
        self.add_form_field("模板名称*:", self.name_edit, "name")

        self.level_spin = QtWidgets.QSpinBox()
        self.level_spin.setRange(1, 999)
        self.level_spin.setValue(1)
        self.add_form_field("初始等级:", self.level_spin, "level")

        self.profession_edit = QtWidgets.QLineEdit()
        self.profession_edit.setPlaceholderText("例如：warrior_001")
        self.add_form_field("默认职业ID:", self.profession_edit, "default_profession_id")

        desc_group = self.add_group_box("描述")
        desc_layout = QtWidgets.QVBoxLayout(desc_group)
        self.desc_edit = QtWidgets.QTextEdit()
        self.desc_edit.setPlaceholderText("描述这个玩家模板的用途...")
        self.desc_edit.setMaximumHeight(100)
        desc_layout.addWidget(self.desc_edit)

    def _apply_initial_data(self) -> None:
        if not self._initial_data:
            return
        self.name_edit.setText(str(self._initial_data.get("template_name", "")).strip())
        level_value = self._initial_data.get("level")
        if level_value is not None:
            self.level_spin.setValue(int(level_value))
        self.profession_edit.setText(str(self._initial_data.get("default_profession_id", "")).strip())
        self.desc_edit.setPlainText(str(self._initial_data.get("description", "")).strip())

    def validate(self) -> bool:
        """验证输入。"""
        name = self.name_edit.text().strip()
        if not name:
            self.show_error("请输入模板名称")
            return False
        return True

    def get_data(self) -> dict:
        """返回对话框数据。"""
        return {
            "template_name": self.name_edit.text().strip(),
            "level": self.level_spin.value(),
            "default_profession_id": self.profession_edit.text().strip(),
            "description": self.desc_edit.toPlainText().strip(),
        }


class NewPlayerClassDialog(FormDialog):
    """职业表单对话框。"""
    
    def __init__(
        self,
        parent=None,
        *,
        title: Optional[str] = None,
        initial_data: Optional[dict[str, object]] = None,
    ):
        self._initial_data = dict(initial_data or {})
        super().__init__(title=title or "新建职业", width=500, height=450, parent=parent)
        self._setup_form()
        self._apply_initial_data()

    def _setup_form(self) -> None:
        """初始化表单控件。"""
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("例如：战士")
        self.add_form_field("职业名称*:", self.name_edit, "name")

        self.health_spin = QtWidgets.QDoubleSpinBox()
        self.health_spin.setRange(1, 9999)
        self.health_spin.setValue(100)
        self.add_form_field("基础生命:", self.health_spin, "health")

        self.attack_spin = QtWidgets.QDoubleSpinBox()
        self.attack_spin.setRange(0, 9999)
        self.attack_spin.setValue(10)
        self.add_form_field("基础攻击:", self.attack_spin, "attack")

        self.defense_spin = QtWidgets.QDoubleSpinBox()
        self.defense_spin.setRange(0, 9999)
        self.defense_spin.setValue(5)
        self.add_form_field("基础防御:", self.defense_spin, "defense")

        self.speed_spin = QtWidgets.QDoubleSpinBox()
        self.speed_spin.setRange(0, 100)
        self.speed_spin.setValue(5)
        self.add_form_field("基础速度:", self.speed_spin, "speed")

        desc_group = self.add_group_box("描述")
        desc_layout = QtWidgets.QVBoxLayout(desc_group)
        self.desc_edit = QtWidgets.QTextEdit()
        self.desc_edit.setPlaceholderText("描述这个职业的特点...")
        self.desc_edit.setMaximumHeight(100)
        desc_layout.addWidget(self.desc_edit)
    
    def _apply_initial_data(self) -> None:
        if not self._initial_data:
            return
        self.name_edit.setText(str(self._initial_data.get("class_name", "")).strip())
        base_health = self._initial_data.get("base_health")
        if base_health is not None:
            self.health_spin.setValue(float(base_health))
        base_attack = self._initial_data.get("base_attack")
        if base_attack is not None:
            self.attack_spin.setValue(float(base_attack))
        base_defense = self._initial_data.get("base_defense")
        if base_defense is not None:
            self.defense_spin.setValue(float(base_defense))
        base_speed = self._initial_data.get("base_speed")
        if base_speed is not None:
            self.speed_spin.setValue(float(base_speed))
        self.desc_edit.setPlainText(str(self._initial_data.get("description", "")).strip())

    def validate(self) -> bool:
        """验证输入。"""
        name = self.name_edit.text().strip()
        if not name:
            self.show_error("请输入职业名称")
            return False
        return True

    def get_data(self) -> dict:
        """返回对话框数据。"""
        return {
            "class_name": self.name_edit.text().strip(),
            "base_health": self.health_spin.value(),
            "base_attack": self.attack_spin.value(),
            "base_defense": self.defense_spin.value(),
            "base_speed": self.speed_spin.value(),
            "description": self.desc_edit.toPlainText().strip(),
        }


class NewRoleDialog(FormDialog):
    """角色表单对话框。"""
    
    def __init__(
        self,
        parent=None,
        *,
        title: Optional[str] = None,
        initial_data: Optional[dict[str, object]] = None,
    ):
        self._initial_data = dict(initial_data or {})
        super().__init__(title=title or "新建角色", width=500, height=300, parent=parent)
        self._setup_form()
        self._apply_initial_data()

    def _setup_form(self) -> None:
        """初始化表单控件。"""
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("例如：守卫者")
        self.add_form_field("角色名称*:", self.name_edit, "name")

        desc_group = self.add_group_box("描述")
        desc_layout = QtWidgets.QVBoxLayout(desc_group)
        self.desc_edit = QtWidgets.QTextEdit()
        self.desc_edit.setPlaceholderText("描述这个角色...")
        self.desc_edit.setMaximumHeight(100)
        desc_layout.addWidget(self.desc_edit)
    
    def _apply_initial_data(self) -> None:
        if not self._initial_data:
            return
        self.name_edit.setText(str(self._initial_data.get("name", "")).strip())
        self.desc_edit.setPlainText(str(self._initial_data.get("description", "")).strip())

    def validate(self) -> bool:
        """验证输入。"""
        name = self.name_edit.text().strip()
        if not name:
            self.show_error("请输入角色名称")
            return False
        return True

    def get_data(self) -> dict:
        """返回对话框数据。"""
        return {
            "name": self.name_edit.text().strip(),
            "description": self.desc_edit.toPlainText().strip(),
        }


class NewSkillDialog(FormDialog):
    """技能表单对话框。"""
    
    def __init__(
        self,
        parent=None,
        *,
        title: Optional[str] = None,
        initial_data: Optional[dict[str, object]] = None,
    ):
        self._initial_data = dict(initial_data or {})
        super().__init__(title=title or "新建技能", width=500, height=500, parent=parent)
        self._setup_form()
        self._apply_initial_data()

    def _setup_form(self) -> None:
        """初始化表单控件。"""
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("例如：火球术")
        self.add_form_field("技能名称*:", self.name_edit, "name")

        self.cooldown_spin = QtWidgets.QDoubleSpinBox()
        self.cooldown_spin.setRange(0, 9999)
        self.cooldown_spin.setValue(5)
        self.cooldown_spin.setSuffix(" 秒")
        self.add_form_field("冷却时间:", self.cooldown_spin)

        self.cost_type_combo = QtWidgets.QComboBox()
        self.cost_type_combo.addItems(["mana", "stamina", "health", "none"])
        self.add_form_field("消耗类型:", self.cost_type_combo)

        self.cost_value_spin = QtWidgets.QDoubleSpinBox()
        self.cost_value_spin.setRange(0, 9999)
        self.cost_value_spin.setValue(10)
        self.add_form_field("消耗值:", self.cost_value_spin)

        self.damage_spin = QtWidgets.QDoubleSpinBox()
        self.damage_spin.setRange(0, 99999)
        self.damage_spin.setValue(20)
        self.add_form_field("伤害:", self.damage_spin)

        self.range_spin = QtWidgets.QDoubleSpinBox()
        self.range_spin.setRange(0, 100)
        self.range_spin.setValue(5)
        self.add_form_field("范围:", self.range_spin)

        desc_group = self.add_group_box("描述")
        desc_layout = QtWidgets.QVBoxLayout(desc_group)
        self.desc_edit = QtWidgets.QTextEdit()
        self.desc_edit.setPlaceholderText("描述这个技能的效果...")
        self.desc_edit.setMaximumHeight(100)
        desc_layout.addWidget(self.desc_edit)
    
    def _apply_initial_data(self) -> None:
        if not self._initial_data:
            return
        self.name_edit.setText(str(self._initial_data.get("skill_name", "")).strip())
        cooldown = self._initial_data.get("cooldown")
        if cooldown is not None:
            self.cooldown_spin.setValue(float(cooldown))
        cost_type = self._initial_data.get("cost_type")
        if cost_type:
            self.cost_type_combo.setCurrentText(str(cost_type))
        cost_value = self._initial_data.get("cost_value")
        if cost_value is not None:
            self.cost_value_spin.setValue(float(cost_value))
        damage = self._initial_data.get("damage")
        if damage is not None:
            self.damage_spin.setValue(float(damage))
        range_value = self._initial_data.get("range_value")
        if range_value is not None:
            self.range_spin.setValue(float(range_value))
        self.desc_edit.setPlainText(str(self._initial_data.get("description", "")).strip())

    def validate(self) -> bool:
        """验证输入。"""
        name = self.name_edit.text().strip()
        if not name:
            self.show_error("请输入技能名称")
            return False
        return True

    def get_data(self) -> dict:
        """返回对话框数据。"""
        return {
            "skill_name": self.name_edit.text().strip(),
            "cooldown": self.cooldown_spin.value(),
            "cost_type": self.cost_type_combo.currentText(),
            "cost_value": self.cost_value_spin.value(),
            "damage": self.damage_spin.value(),
            "range_value": self.range_spin.value(),
            "description": self.desc_edit.toPlainText().strip(),
        }


class NewProjectileDialog(FormDialog):
    """投射物表单对话框。"""
    
    def __init__(
        self,
        parent=None,
        *,
        title: Optional[str] = None,
        initial_data: Optional[dict[str, object]] = None,
    ):
        self._initial_data = dict(initial_data or {})
        super().__init__(title=title or "新建投射物", width=500, height=400, parent=parent)
        self._setup_form()
        self._apply_initial_data()

    def _setup_form(self) -> None:
        """初始化表单控件。"""
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("例如：火焰箭")
        self.add_form_field("投射物名称*:", self.name_edit, "name")

        self.speed_spin = QtWidgets.QDoubleSpinBox()
        self.speed_spin.setRange(0, 100)
        self.speed_spin.setValue(10)
        self.add_form_field("速度:", self.speed_spin)

        self.lifetime_spin = QtWidgets.QDoubleSpinBox()
        self.lifetime_spin.setRange(0, 60)
        self.lifetime_spin.setValue(5)
        self.lifetime_spin.setSuffix(" 秒")
        self.add_form_field("生命周期:", self.lifetime_spin)

        self.hit_check = QtWidgets.QCheckBox()
        self.hit_check.setChecked(True)
        self.add_form_field("命中检测:", self.hit_check)

        desc_group = self.add_group_box("描述")
        desc_layout = QtWidgets.QVBoxLayout(desc_group)
        self.desc_edit = QtWidgets.QTextEdit()
        self.desc_edit.setPlaceholderText("描述这个投射物...")
        self.desc_edit.setMaximumHeight(100)
        desc_layout.addWidget(self.desc_edit)
    
    def _apply_initial_data(self) -> None:
        if not self._initial_data:
            return
        self.name_edit.setText(str(self._initial_data.get("projectile_name", "")).strip())
        speed_value = self._initial_data.get("speed")
        if speed_value is not None:
            self.speed_spin.setValue(float(speed_value))
        lifetime_value = self._initial_data.get("lifetime")
        if lifetime_value is not None:
            self.lifetime_spin.setValue(float(lifetime_value))
        if "hit_detection_enabled" in self._initial_data:
            self.hit_check.setChecked(bool(self._initial_data.get("hit_detection_enabled", True)))
        self.desc_edit.setPlainText(str(self._initial_data.get("description", "")).strip())

    def validate(self) -> bool:
        """验证输入。"""
        name = self.name_edit.text().strip()
        if not name:
            self.show_error("请输入投射物名称")
            return False
        return True

    def get_data(self) -> dict:
        """返回对话框数据。"""
        return {
            "projectile_name": self.name_edit.text().strip(),
            "speed": self.speed_spin.value(),
            "lifetime": self.lifetime_spin.value(),
            "hit_detection_enabled": self.hit_check.isChecked(),
            "description": self.desc_edit.toPlainText().strip(),
        }


class NewUnitStatusDialog(FormDialog):
    """单位状态表单对话框。"""
    
    def __init__(
        self,
        parent=None,
        *,
        title: Optional[str] = None,
        initial_data: Optional[dict[str, object]] = None,
    ):
        self._initial_data = dict(initial_data or {})
        super().__init__(title=title or "新建单位状态", width=500, height=400, parent=parent)
        self._setup_form()
        self._apply_initial_data()

    def _setup_form(self) -> None:
        """初始化表单控件。"""
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("例如：中毒")
        self.add_form_field("状态名称*:", self.name_edit, "name")

        self.duration_spin = QtWidgets.QDoubleSpinBox()
        self.duration_spin.setRange(0, 9999)
        self.duration_spin.setValue(0)
        self.duration_spin.setSuffix(" 秒")
        self.add_form_field("持续时间:", self.duration_spin)

        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItems(["buff", "debuff", "特殊"])
        self.add_form_field("效果类型:", self.type_combo)

        self.stackable_check = QtWidgets.QCheckBox()
        self.stackable_check.setChecked(False)
        self.add_form_field("可堆叠:", self.stackable_check)

        desc_group = self.add_group_box("描述")
        desc_layout = QtWidgets.QVBoxLayout(desc_group)
        self.desc_edit = QtWidgets.QTextEdit()
        self.desc_edit.setPlaceholderText("描述这个状态的效果...")
        self.desc_edit.setMaximumHeight(100)
        desc_layout.addWidget(self.desc_edit)
    
    def _apply_initial_data(self) -> None:
        if not self._initial_data:
            return
        self.name_edit.setText(str(self._initial_data.get("status_name", "")).strip())
        duration_value = self._initial_data.get("duration")
        if duration_value is not None:
            self.duration_spin.setValue(float(duration_value))
        effect_type = self._initial_data.get("effect_type")
        if effect_type:
            self.type_combo.setCurrentText(str(effect_type))
        if "is_stackable" in self._initial_data:
            self.stackable_check.setChecked(bool(self._initial_data.get("is_stackable", False)))
        self.desc_edit.setPlainText(str(self._initial_data.get("description", "")).strip())

    def validate(self) -> bool:
        """验证输入。"""
        name = self.name_edit.text().strip()
        if not name:
            self.show_error("请输入状态名称")
            return False
        return True

    def get_data(self) -> dict:
        """返回对话框数据。"""
        return {
            "status_name": self.name_edit.text().strip(),
            "duration": self.duration_spin.value(),
            "effect_type": self.type_combo.currentText(),
            "is_stackable": self.stackable_check.isChecked(),
            "description": self.desc_edit.toPlainText().strip(),
        }


class NewItemDialog(FormDialog):
    """道具表单对话框。"""
    
    def __init__(
        self,
        parent=None,
        *,
        title: Optional[str] = None,
        initial_data: Optional[dict[str, object]] = None,
    ):
        self._initial_data = dict(initial_data or {})
        super().__init__(title=title or "新建道具", width=500, height=450, parent=parent)
        self._setup_form()
        self._apply_initial_data()

    def _setup_form(self) -> None:
        """初始化表单控件。"""
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.setPlaceholderText("例如：生命药水")
        self.add_form_field("道具名称*:", self.name_edit, "name")

        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItems(["consumable", "equipment", "material", "quest"])
        self.add_form_field("道具类型:", self.type_combo)

        self.rarity_combo = QtWidgets.QComboBox()
        self.rarity_combo.addItems(["common", "uncommon", "rare", "epic", "legendary"])
        self.add_form_field("稀有度:", self.rarity_combo)

        self.max_stack_spin = QtWidgets.QSpinBox()
        self.max_stack_spin.setRange(1, 9999)
        self.max_stack_spin.setValue(99)
        self.add_form_field("最大堆叠:", self.max_stack_spin)

        desc_group = self.add_group_box("描述")
        desc_layout = QtWidgets.QVBoxLayout(desc_group)
        self.desc_edit = QtWidgets.QTextEdit()
        self.desc_edit.setPlaceholderText("描述这个道具的用途...")
        self.desc_edit.setMaximumHeight(100)
        desc_layout.addWidget(self.desc_edit)
    
    def _apply_initial_data(self) -> None:
        if not self._initial_data:
            return
        self.name_edit.setText(str(self._initial_data.get("item_name", "")).strip())
        item_type = self._initial_data.get("item_type")
        if item_type:
            self.type_combo.setCurrentText(str(item_type))
        rarity = self._initial_data.get("rarity")
        if rarity:
            self.rarity_combo.setCurrentText(str(rarity))
        max_stack = self._initial_data.get("max_stack")
        if max_stack is not None:
            self.max_stack_spin.setValue(int(max_stack))
        self.desc_edit.setPlainText(str(self._initial_data.get("description", "")).strip())

    def validate(self) -> bool:
        """验证输入。"""
        name = self.name_edit.text().strip()
        if not name:
            self.show_error("请输入道具名称")
            return False
        return True

    def get_data(self) -> dict:
        """返回对话框数据。"""
        return {
            "item_name": self.name_edit.text().strip(),
            "item_type": self.type_combo.currentText(),
            "rarity": self.rarity_combo.currentText(),
            "max_stack": self.max_stack_spin.value(),
            "description": self.desc_edit.toPlainText().strip(),
        }


