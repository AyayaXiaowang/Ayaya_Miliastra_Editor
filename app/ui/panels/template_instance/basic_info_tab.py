"""通用属性 Inspector（元件/实体/关卡实体通用）。

本标签页实现：
- 头部字段：名字 / GUID / 类型
- Accordion 模块：
  - 变换（Transform）
  - 模型（Model）
  - 原生碰撞（Native Collision）
  - 可见性 & 创建设置（Visibility & Lifecycle）
  - 阵营（Faction）
  - 单位标签（Unit Tags）
  - 负载优化（Load Optimization）
  - 备注（Notes）
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from PyQt6 import QtCore, QtGui, QtWidgets

from app.runtime.services.json_cache_service import get_shared_json_cache_service
from app.ui.foundation import dialog_utils, input_dialogs
from app.ui.foundation.theme_manager import Colors, Sizes, ThemeManager
from app.ui.foundation.toggle_switch import ToggleSwitch
from app.ui.panels.panel_dict_utils import ensure_dict_field, ensure_nested_dict, ensure_list_field
from app.ui.panels.ui.ui_control_group_collapsible_section import CollapsibleSection
from app.ui.panels.template_instance.tab_base import (
    TemplateInstanceTabBase,
    is_drop_template_config,
)
from app.ui.panels.template_instance.decoration_editor_dialog import DecorationEditorDialog
from app.ui.panels.template_instance.socket_editor_dialog import SocketEditorDialog, ROOT_SOCKET_NAME
from app.ui.panels.template_instance.vector3_editor import Vector3Editor, safe_float_list3
from engine.configs.entities.creature_models import (
    get_creature_model_category_for_name,
    get_creature_model_display_pairs,
)
from engine.graph.models.package_model import InstanceConfig, TemplateConfig
from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_view import PackageView
from engine.resources.resource_manager import ResourceManager

_INSPECTOR_METADATA_KEY = "common_inspector"
_ACCORDION_STATE_CACHE_PATH = "ui/template_instance_common_inspector_accordion.json"


def _safe_strip_text(value: object) -> str:
    return str(value).strip() if value is not None else ""

class _TagChip(QtWidgets.QFrame):
    """标签胶囊（Badge），支持删除按钮。"""

    removed = QtCore.pyqtSignal(str)

    def __init__(self, tag_id: str, display_text: str, *, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._tag_id = tag_id
        self.setObjectName("UnitTagChip")
        self.setStyleSheet(
            f"""
            QFrame#UnitTagChip {{
                background-color: {Colors.BG_SELECTED};
                border: 1px solid {Colors.BORDER_LIGHT};
                border-radius: 999px;
            }}
            """
        )
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 6, 2)
        layout.setSpacing(6)

        label = QtWidgets.QLabel(display_text, self)
        label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY};")
        layout.addWidget(label)

        remove_btn = QtWidgets.QToolButton(self)
        remove_btn.setText("×")
        remove_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        remove_btn.setAutoRaise(True)
        remove_btn.clicked.connect(lambda: self.removed.emit(self._tag_id))
        layout.addWidget(remove_btn)


class BasicInfoTab(TemplateInstanceTabBase):
    """属性（Common Attribute Inspector）标签页。"""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._updating_ui = False
        self._is_read_only = False
        self._debounce_timer = QtCore.QTimer(self)
        self._debounce_timer.setInterval(250)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._apply_from_ui_and_emit)

        self._sections: dict[str, CollapsibleSection] = {}
        self._build_ui()

    # --------------------------------------------------------------------- UI build
    def _build_ui(self) -> None:
        root_layout = QtWidgets.QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QtWidgets.QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(ThemeManager.scrollbar_style())

        container = QtWidgets.QWidget(scroll)
        container_layout = QtWidgets.QVBoxLayout(container)
        container_layout.setContentsMargins(
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
            Sizes.SPACING_MEDIUM,
        )
        container_layout.setSpacing(Sizes.SPACING_MEDIUM)

        # 头部：名字 / GUID / 类型
        header = QtWidgets.QFrame(container)
        header.setObjectName("CommonInspectorHeader")
        header.setStyleSheet(ThemeManager.card_style())
        header_layout = QtWidgets.QFormLayout(header)
        header_layout.setContentsMargins(
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
        )
        header_layout.setHorizontalSpacing(Sizes.SPACING_SMALL)
        header_layout.setVerticalSpacing(Sizes.SPACING_SMALL)

        self.name_edit = QtWidgets.QLineEdit(header)
        self.name_edit.setStyleSheet(ThemeManager.input_style())
        self.name_edit.textEdited.connect(self._schedule_apply)

        self.guid_edit = QtWidgets.QLineEdit(header)
        self.guid_edit.setStyleSheet(ThemeManager.input_style())
        self.guid_edit.setPlaceholderText("仅数字，可留空")
        guid_regex = QtCore.QRegularExpression(r"[0-9]{0,20}")
        self.guid_edit.setValidator(QtGui.QRegularExpressionValidator(guid_regex, self))
        self.guid_edit.textEdited.connect(self._schedule_apply)

        self.type_label = QtWidgets.QLabel("-", header)
        self.type_label.setStyleSheet(
            f"color: {Colors.PRIMARY}; font-weight: bold; padding: {Sizes.PADDING_SMALL}px;"
        )
        self.type_label.setWordWrap(True)

        header_layout.addRow("名字", self.name_edit)
        header_layout.addRow("GUID", self.guid_edit)
        header_layout.addRow("类型", self.type_label)

        container_layout.addWidget(header)

        # Accordion sections
        container_layout.addWidget(self._build_transform_section(container))
        container_layout.addWidget(self._build_model_section(container))
        container_layout.addWidget(self._build_collision_section(container))
        container_layout.addWidget(self._build_visibility_section(container))
        container_layout.addWidget(self._build_faction_section(container))
        container_layout.addWidget(self._build_unit_tags_section(container))
        container_layout.addWidget(self._build_optimization_section(container))
        container_layout.addWidget(self._build_notes_section(container))
        container_layout.addStretch(1)

        scroll.setWidget(container)
        root_layout.addWidget(scroll, 1)

        # 初次加载折叠状态
        self._restore_accordion_state()

    def _register_section(self, section_id: str, section: CollapsibleSection) -> CollapsibleSection:
        self._sections[section_id] = section

        def _persist_later() -> None:
            QtCore.QTimer.singleShot(
                0,
                lambda: self._persist_section_collapsed(section_id, section.is_collapsed),
            )

        section.header.clicked.connect(_persist_later)
        return section

    # --------------------------------------------------------------------- Sections
    def _build_transform_section(self, parent: QtWidgets.QWidget) -> CollapsibleSection:
        section = self._register_section("transform", CollapsibleSection("变换", parent))

        # 锁定变换
        lock_row = QtWidgets.QWidget(section.content_widget)
        lock_layout = QtWidgets.QHBoxLayout(lock_row)
        lock_layout.setContentsMargins(0, 0, 0, 0)
        lock_layout.setSpacing(Sizes.SPACING_SMALL)

        lock_label = QtWidgets.QLabel("锁定变换", lock_row)
        self.transform_lock_switch = ToggleSwitch(lock_row)
        self.transform_lock_switch.toggled.connect(self._on_transform_lock_toggled)

        lock_layout.addWidget(lock_label)
        lock_layout.addStretch(1)
        lock_layout.addWidget(self.transform_lock_switch)
        section.add_widget(lock_row)

        # Position / Rotation / Scale
        self.position_editor = Vector3Editor(
            minimum=-10000.0,
            maximum=10000.0,
            decimals=2,
            single_step=0.1,
            parent=section.content_widget,
        )
        self.rotation_editor = Vector3Editor(
            minimum=-360.0,
            maximum=360.0,
            decimals=2,
            single_step=1.0,
            parent=section.content_widget,
        )
        self.scale_editor = Vector3Editor(
            minimum=0.0,
            maximum=1000.0,
            decimals=2,
            single_step=0.1,
            parent=section.content_widget,
        )

        self.position_editor.value_changed.connect(self._apply_from_ui_and_emit)
        self.rotation_editor.value_changed.connect(self._apply_from_ui_and_emit)
        self.scale_editor.value_changed.connect(self._apply_from_ui_and_emit)

        section.add_widget(self._wrap_labeled_row("位置", self.position_editor))
        section.add_widget(self._wrap_labeled_row("旋转", self.rotation_editor))
        section.add_widget(self._wrap_labeled_row("缩放", self.scale_editor))

        self._transform_hint = QtWidgets.QLabel(
            "提示：模板不包含实例变换；请在“实体摆放/关卡实体”中编辑位置、旋转与缩放。",
            section.content_widget,
        )
        self._transform_hint.setWordWrap(True)
        self._transform_hint.setStyleSheet(f"color: {Colors.TEXT_HINT};")
        section.add_widget(self._transform_hint)

        return section

    def _build_model_section(self, parent: QtWidgets.QWidget) -> CollapsibleSection:
        section = self._register_section("model", CollapsibleSection("模型", parent))

        # 主模型卡片
        card = QtWidgets.QFrame(section.content_widget)
        card.setObjectName("ModelAssetCard")
        card.setStyleSheet(
            f"""
            QFrame#ModelAssetCard {{
                background-color: {Colors.BG_CARD};
                border: 1px solid {Colors.BORDER_LIGHT};
                border-radius: {Sizes.RADIUS_MEDIUM}px;
            }}
            """
        )
        card_layout = QtWidgets.QHBoxLayout(card)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.setSpacing(Sizes.SPACING_SMALL)

        self.model_preview_icon = QtWidgets.QLabel("📦", card)
        self.model_preview_icon.setFixedSize(28, 28)
        self.model_preview_icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.model_preview_icon.setStyleSheet(
            f"background-color: {Colors.BG_SELECTED}; border-radius: 6px; color: {Colors.TEXT_PRIMARY};"
        )
        card_layout.addWidget(self.model_preview_icon)

        text_col = QtWidgets.QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        self.model_name_label = QtWidgets.QLabel("未设置模型", card)
        self.model_name_label.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-weight: bold;")
        self.model_id_label = QtWidgets.QLabel("ID: -", card)
        self.model_id_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")

        text_col.addWidget(self.model_name_label)
        text_col.addWidget(self.model_id_label)
        card_layout.addLayout(text_col, 1)

        self.model_more_btn = QtWidgets.QToolButton(card)
        self.model_more_btn.setText("⋯")
        self.model_more_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.model_more_btn.setAutoRaise(True)
        self.model_more_btn.clicked.connect(self._on_model_more_clicked)
        card_layout.addWidget(self.model_more_btn)

        section.add_widget(card)

        # 单位挂接点 / 装饰物
        mount_row = QtWidgets.QWidget(section.content_widget)
        mount_layout = QtWidgets.QHBoxLayout(mount_row)
        mount_layout.setContentsMargins(0, 0, 0, 0)
        mount_layout.setSpacing(Sizes.SPACING_SMALL)

        self.mount_points_label = QtWidgets.QLabel("单位挂接点（0）", mount_row)
        self.mount_points_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        mount_layout.addWidget(self.mount_points_label)
        mount_layout.addStretch(1)

        self.edit_mount_points_btn = QtWidgets.QPushButton("编辑挂接点", mount_row)
        self.edit_mount_points_btn.setStyleSheet(ThemeManager.button_style())
        self.edit_mount_points_btn.clicked.connect(self._on_edit_mount_points_clicked)
        mount_layout.addWidget(self.edit_mount_points_btn)

        section.add_widget(mount_row)

        deco_row = QtWidgets.QWidget(section.content_widget)
        deco_layout = QtWidgets.QHBoxLayout(deco_row)
        deco_layout.setContentsMargins(0, 0, 0, 0)
        deco_layout.setSpacing(Sizes.SPACING_SMALL)

        self.decorations_label = QtWidgets.QLabel("装饰物列表（0）", deco_row)
        self.decorations_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        deco_layout.addWidget(self.decorations_label)
        deco_layout.addStretch(1)

        self.edit_decorations_btn = QtWidgets.QPushButton("编辑装饰物", deco_row)
        self.edit_decorations_btn.setStyleSheet(ThemeManager.button_style())
        self.edit_decorations_btn.clicked.connect(self._on_edit_decorations_clicked)
        deco_layout.addWidget(self.edit_decorations_btn)

        self.split_decorations_btn = QtWidgets.QPushButton("打散为元件", deco_row)
        self.split_decorations_btn.setStyleSheet(ThemeManager.button_style())
        self.split_decorations_btn.setToolTip(
            "将当前对象的 decorations 列表打散：\n"
            "- 每个装饰物生成一个独立的元件模板（空模型载体 + 单个装饰物）\n"
            "- 新元件写入当前项目存档的 `元件库/`"
        )
        self.split_decorations_btn.clicked.connect(self._on_split_decorations_clicked)
        deco_layout.addWidget(self.split_decorations_btn)

        section.add_widget(deco_row)

        return section

    def _build_collision_section(self, parent: QtWidgets.QWidget) -> CollapsibleSection:
        section = self._register_section("physics", CollapsibleSection("原生碰撞", parent))

        self.collision_initial_active = ToggleSwitch(section.content_widget)
        self.collision_is_climbable = ToggleSwitch(section.content_widget)
        self.collision_show_gizmos = ToggleSwitch(section.content_widget)

        self.collision_initial_active.toggled.connect(self._apply_from_ui_and_emit)
        self.collision_is_climbable.toggled.connect(self._apply_from_ui_and_emit)
        self.collision_show_gizmos.toggled.connect(self._apply_from_ui_and_emit)

        section.add_widget(self._wrap_toggle_row("初始生效", self.collision_initial_active))
        section.add_widget(self._wrap_toggle_row("是否可攀爬", self.collision_is_climbable))
        section.add_widget(self._wrap_toggle_row("原生碰撞预览", self.collision_show_gizmos))
        return section

    def _build_visibility_section(self, parent: QtWidgets.QWidget) -> CollapsibleSection:
        section = self._register_section("visibility", CollapsibleSection("可见性 & 创建设置", parent))

        self.render_visible = ToggleSwitch(section.content_widget)
        self.spawn_on_load = ToggleSwitch(section.content_widget)
        self.render_visible.toggled.connect(self._apply_from_ui_and_emit)
        self.spawn_on_load.toggled.connect(self._apply_from_ui_and_emit)

        section.add_widget(self._wrap_toggle_row("模型可见性", self.render_visible))
        section.add_widget(self._wrap_toggle_row("初始创建", self.spawn_on_load))
        return section

    def _build_faction_section(self, parent: QtWidgets.QWidget) -> CollapsibleSection:
        section = self._register_section("faction", CollapsibleSection("阵营", parent))

        self.faction_combo = QtWidgets.QComboBox(section.content_widget)
        self.faction_combo.setStyleSheet(ThemeManager.combo_box_style())
        options = [
            ("📍 跟随默认阵营配置", 0),
            ("📍 初始玩家阵营", 1),
            ("📍 初始物件阵营", 2),
            ("📍 初始造物阵营", 3),
        ]
        for label, value in options:
            self.faction_combo.addItem(label, value)
        self.faction_combo.currentIndexChanged.connect(self._apply_from_ui_and_emit)

        section.add_widget(self._wrap_labeled_row("选择阵营", self.faction_combo))
        return section

    def _build_unit_tags_section(self, parent: QtWidgets.QWidget) -> CollapsibleSection:
        section = self._register_section("unit_tags", CollapsibleSection("单位标签", parent))

        self._unit_tags_container = QtWidgets.QWidget(section.content_widget)
        self._unit_tags_layout = QtWidgets.QVBoxLayout(self._unit_tags_container)
        self._unit_tags_layout.setContentsMargins(0, 0, 0, 0)
        self._unit_tags_layout.setSpacing(Sizes.SPACING_TINY)
        section.add_widget(self._unit_tags_container)

        self.add_unit_tag_btn = QtWidgets.QPushButton("添加单位标签", section.content_widget)
        self.add_unit_tag_btn.setStyleSheet(ThemeManager.button_style())
        self.add_unit_tag_btn.clicked.connect(self._on_add_unit_tag_clicked)
        section.add_widget(self.add_unit_tag_btn)

        return section

    def _build_optimization_section(self, parent: QtWidgets.QWidget) -> CollapsibleSection:
        section = self._register_section("optimization", CollapsibleSection("负载优化", parent))

        self.cull_out_of_range = ToggleSwitch(section.content_widget)
        self.cull_out_of_range.toggled.connect(self._apply_from_ui_and_emit)
        section.add_widget(self._wrap_toggle_row("超出范围不运行", self.cull_out_of_range))
        return section

    def _build_notes_section(self, parent: QtWidgets.QWidget) -> CollapsibleSection:
        section = self._register_section("notes", CollapsibleSection("备注", parent))

        self.notes_edit = QtWidgets.QPlainTextEdit(section.content_widget)
        self.notes_edit.setStyleSheet(ThemeManager.input_style())
        self.notes_edit.setPlaceholderText("填写开发备注...")
        self.notes_edit.setMinimumHeight(140)
        self.notes_edit.setMaximumHeight(600)
        self.notes_edit.textChanged.connect(self._schedule_apply)
        section.add_widget(self.notes_edit)
        return section

    # --------------------------------------------------------------------- Layout helpers
    @staticmethod
    def _wrap_labeled_row(label_text: str, widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        row = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Sizes.SPACING_SMALL)
        label = QtWidgets.QLabel(label_text, row)
        label.setFixedWidth(80)
        layout.addWidget(label)
        layout.addWidget(widget, 1)
        return row

    @staticmethod
    def _wrap_toggle_row(label_text: str, switch: ToggleSwitch) -> QtWidgets.QWidget:
        row = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Sizes.SPACING_SMALL)
        label = QtWidgets.QLabel(label_text, row)
        layout.addWidget(label)
        layout.addStretch(1)
        layout.addWidget(switch)
        return row

    # --------------------------------------------------------------------- State (accordion)
    def _restore_accordion_state(self) -> None:
        service = self._get_cache_service()
        if service is None:
            return
        for section_id, section in self._sections.items():
            raw = service.get_kv_value(_ACCORDION_STATE_CACHE_PATH, section_id, default=False)
            collapsed = bool(raw) if isinstance(raw, bool) else False
            section.setCollapsed(collapsed)

    def _persist_section_collapsed(self, section_id: str, collapsed: bool) -> None:
        service = self._get_cache_service()
        if service is None:
            return
        service.set_kv_value(_ACCORDION_STATE_CACHE_PATH, section_id, bool(collapsed))

    def _get_cache_service(self):
        resource_manager = self.resource_manager
        workspace_path = getattr(resource_manager, "workspace_path", None)
        if workspace_path is None:
            return None
        return get_shared_json_cache_service(workspace_path)

    # --------------------------------------------------------------------- Data helpers (read)
    def _current_template_for_instance(self) -> Optional[TemplateConfig]:
        obj = self.current_object
        package = self.current_package
        if not isinstance(obj, InstanceConfig):
            return None
        if not isinstance(package, (PackageView, GlobalResourceView)):
            return None
        return package.get_template(obj.template_id)

    def _resolve_entity_type_text(self) -> str:
        obj = self.current_object
        if obj is None:
            return "-"
        if self.object_type == "template" and isinstance(obj, TemplateConfig):
            if is_drop_template_config(obj):
                return "掉落物"
            return f"元件 - {obj.entity_type}"
        if self.object_type == "level_entity":
            return "关卡实体（唯一，承载关卡逻辑）"
        if self.object_type == "instance" and isinstance(obj, InstanceConfig):
            template = self._current_template_for_instance()
            if is_drop_template_config(template):
                return "实体 - 掉落物"
            if template is not None:
                return f"实体 - {template.entity_type}"
            inferred = ""
            metadata = getattr(obj, "metadata", {}) or {}
            if isinstance(metadata, dict):
                inferred = _safe_strip_text(metadata.get("entity_type"))
            return f"实体 - {inferred or '未知'}"
        return "-"

    def _read_metadata_dict(self) -> dict:
        obj = self.current_object
        if obj is None:
            return {}
        metadata = getattr(obj, "metadata", None)
        return metadata if isinstance(metadata, dict) else {}

    def _read_inspector_dict(self, metadata: dict) -> dict:
        value = metadata.get(_INSPECTOR_METADATA_KEY)
        return value if isinstance(value, dict) else {}

    def _read_inspector_bool(self, metadata: dict, path: Sequence[str], default: bool) -> bool:
        current: Any = self._read_inspector_dict(metadata)
        for key in path:
            if not isinstance(current, dict):
                return default
            current = current.get(key)
        return bool(current) if isinstance(current, bool) else bool(default)

    def _read_inspector_int(self, metadata: dict, path: Sequence[str], default: int) -> int:
        current: Any = self._read_inspector_dict(metadata)
        for key in path:
            if not isinstance(current, dict):
                return int(default)
            current = current.get(key)
        if isinstance(current, int) and not isinstance(current, bool):
            return int(current)
        return int(default)

    def _read_inspector_str(self, metadata: dict, path: Sequence[str], default: str) -> str:
        current: Any = self._read_inspector_dict(metadata)
        for key in path:
            if not isinstance(current, dict):
                return default
            current = current.get(key)
        return str(current) if isinstance(current, str) else default

    def _read_inspector_list_str(self, metadata: dict, path: Sequence[str]) -> list[str]:
        current: Any = self._read_inspector_dict(metadata)
        for key in path:
            if not isinstance(current, dict):
                return []
            current = current.get(key)
        if not isinstance(current, list):
            return []
        result: list[str] = []
        for item in current:
            text = _safe_strip_text(item)
            if text:
                result.append(text)
        return result

    # --------------------------------------------------------------------- Data helpers (write)
    def _ensure_metadata(self) -> dict:
        obj = self.current_object
        if obj is None:
            return {}
        metadata = getattr(obj, "metadata", None)
        if isinstance(metadata, dict):
            return metadata
        metadata = {}
        setattr(obj, "metadata", metadata)
        return metadata

    def _ensure_inspector(self, metadata: dict) -> dict:
        return ensure_dict_field(metadata, _INSPECTOR_METADATA_KEY)

    # --------------------------------------------------------------------- Core lifecycle
    def _reset_ui(self) -> None:
        self._updating_ui = True
        self.name_edit.clear()
        self.guid_edit.clear()
        self.type_label.setText("-")
        self.transform_lock_switch.setChecked(False)
        self.position_editor.set_values([0.0, 0.0, 0.0])
        self.rotation_editor.set_values([0.0, 0.0, 0.0])
        self.scale_editor.set_values([1.0, 1.0, 1.0])
        self.model_name_label.setText("未设置模型")
        self.model_id_label.setText("ID: -")
        self.mount_points_label.setText("单位挂接点（0）")
        self.decorations_label.setText("装饰物列表（0）")
        self.collision_initial_active.setChecked(True)
        self.collision_is_climbable.setChecked(False)
        self.collision_show_gizmos.setChecked(False)
        self.render_visible.setChecked(True)
        self.spawn_on_load.setChecked(True)
        self.faction_combo.setCurrentIndex(0)
        self.cull_out_of_range.setChecked(False)
        self.notes_edit.clear()
        self._rebuild_unit_tag_chips([])
        self._updating_ui = False

    def _refresh_ui(self) -> None:
        self._updating_ui = True
        obj = self.current_object
        package = self.current_package
        if obj is None:
            self._reset_ui()
            self._updating_ui = False
            return

        # Header fields
        self.name_edit.setText(_safe_strip_text(getattr(obj, "name", "")))

        metadata = self._read_metadata_dict()
        self.guid_edit.setText(_safe_strip_text(metadata.get("guid")))
        self.type_label.setText(self._resolve_entity_type_text())

        # Transform
        is_transform_context = self.object_type in {"instance", "level_entity"} and isinstance(obj, InstanceConfig)
        self._transform_hint.setVisible(not is_transform_context)
        self.position_editor.setVisible(is_transform_context)
        self.rotation_editor.setVisible(is_transform_context)
        self.scale_editor.setVisible(is_transform_context)

        locked = self._read_inspector_bool(metadata, ("transform", "isLocked"), False)
        self.transform_lock_switch.setChecked(bool(locked))
        if is_transform_context:
            instance = obj
            self.position_editor.set_values(safe_float_list3(instance.position, [0.0, 0.0, 0.0]))
            self.rotation_editor.set_values(safe_float_list3(instance.rotation, [0.0, 0.0, 0.0]))
            self.scale_editor.set_values(safe_float_list3(getattr(instance, "scale", None), [1.0, 1.0, 1.0]))
        self._update_transform_editable_state()

        # Model
        self._refresh_model_card()

        # Physics / visibility / lifecycle / faction / optimization
        self.collision_initial_active.setChecked(
            self._read_inspector_bool(metadata, ("physics", "initiallyActive"), True)
        )
        self.collision_is_climbable.setChecked(
            self._read_inspector_bool(metadata, ("physics", "isClimbable"), False)
        )
        self.collision_show_gizmos.setChecked(
            self._read_inspector_bool(metadata, ("physics", "showGizmos"), False)
        )
        self.render_visible.setChecked(
            self._read_inspector_bool(metadata, ("rendering", "isVisible"), True)
        )
        self.spawn_on_load.setChecked(
            self._read_inspector_bool(metadata, ("lifecycle", "spawnOnLoad"), True)
        )

        faction_value = self._read_inspector_int(metadata, ("logic", "factionType"), 0)
        for index in range(self.faction_combo.count()):
            item_value = self.faction_combo.itemData(index)
            if isinstance(item_value, int) and item_value == faction_value:
                self.faction_combo.setCurrentIndex(index)
                break

        self.cull_out_of_range.setChecked(
            self._read_inspector_bool(metadata, ("logic", "optimization", "cullOutOfRange"), False)
        )

        # Unit tags
        tags = self._read_inspector_list_str(metadata, ("logic", "tags"))
        self._rebuild_unit_tag_chips(tags)

        # Notes
        notes_text = ""
        if isinstance(obj, TemplateConfig):
            notes_text = _safe_strip_text(getattr(obj, "description", ""))
        else:
            notes_text = self._read_inspector_str(metadata, ("logic", "notes"), "")
        self.notes_edit.setPlainText(notes_text)

        self._apply_read_only_state()
        self._updating_ui = False

    # --------------------------------------------------------------------- Apply changes
    def _schedule_apply(self) -> None:
        if self._updating_ui or self._is_read_only:
            return
        self._debounce_timer.start()

    def _apply_from_ui_and_emit(self) -> None:
        if self._updating_ui or self._is_read_only:
            return
        self._apply_from_ui()
        self.data_changed.emit()

    def _apply_from_ui(self) -> None:
        obj = self.current_object
        if obj is None:
            return

        # name
        new_name = self.name_edit.text().strip()
        if hasattr(obj, "name"):
            obj.name = new_name

        # guid (统一写入 metadata["guid"]；仅在变化时写回，避免无意义写入与日志噪音)
        guid_text = self.guid_edit.text().strip()
        metadata_snapshot = self._read_metadata_dict()
        previous_guid = _safe_strip_text(metadata_snapshot.get("guid"))
        if previous_guid != guid_text:
            if self.service is not None:
                self.service.apply_guid(obj, guid_text)
            else:
                metadata = self._ensure_metadata()
                if guid_text:
                    metadata["guid"] = guid_text
                else:
                    metadata.pop("guid", None)

        # inspector dict
        metadata = self._ensure_metadata()
        inspector = self._ensure_inspector(metadata)

        # transform lock
        transform_dict = ensure_nested_dict(inspector, "transform")
        transform_dict["isLocked"] = bool(self.transform_lock_switch.isChecked())

        # transform values (实例/关卡实体才写回)
        if self.object_type in {"instance", "level_entity"} and isinstance(obj, InstanceConfig):
            obj.position = self.position_editor.get_values()
            obj.rotation = self.rotation_editor.get_values()
            obj.scale = self.scale_editor.get_values()

            transform_dict["position"] = {"x": obj.position[0], "y": obj.position[1], "z": obj.position[2]}
            transform_dict["rotation"] = {"x": obj.rotation[0], "y": obj.rotation[1], "z": obj.rotation[2]}
            transform_dict["scale"] = {"x": obj.scale[0], "y": obj.scale[1], "z": obj.scale[2]}

        # physics
        physics = ensure_nested_dict(inspector, "physics")
        physics["initiallyActive"] = bool(self.collision_initial_active.isChecked())
        physics["isClimbable"] = bool(self.collision_is_climbable.isChecked())
        physics["showGizmos"] = bool(self.collision_show_gizmos.isChecked())

        # rendering / lifecycle
        rendering = ensure_nested_dict(inspector, "rendering")
        rendering["isVisible"] = bool(self.render_visible.isChecked())
        lifecycle = ensure_nested_dict(inspector, "lifecycle")
        lifecycle["spawnOnLoad"] = bool(self.spawn_on_load.isChecked())

        # logic
        logic = ensure_nested_dict(inspector, "logic")
        faction_value = self.faction_combo.currentData()
        if isinstance(faction_value, int) and not isinstance(faction_value, bool):
            logic["factionType"] = int(faction_value)
        else:
            logic["factionType"] = 0

        optimization = ensure_nested_dict(logic, "optimization")
        optimization["cullOutOfRange"] = bool(self.cull_out_of_range.isChecked())

        # notes
        notes_text = self.notes_edit.toPlainText().strip()
        if isinstance(obj, TemplateConfig):
            obj.description = notes_text
            logic["notes"] = notes_text
        else:
            logic["notes"] = notes_text

    def flush_pending_changes(self) -> None:
        if self._updating_ui or self._is_read_only:
            return
        if self._debounce_timer.isActive():
            self._debounce_timer.stop()
            self._apply_from_ui()

    # --------------------------------------------------------------------- Transform lock
    def _on_transform_lock_toggled(self, checked: bool) -> None:
        if self._updating_ui:
            return
        self._update_transform_editable_state()
        self._apply_from_ui_and_emit()

    def _update_transform_editable_state(self) -> None:
        editable = not self.transform_lock_switch.isChecked() and not self._is_read_only
        self.position_editor.set_editable(editable)
        self.rotation_editor.set_editable(editable)
        self.scale_editor.set_editable(editable)

    # --------------------------------------------------------------------- Model section (minimal)
    def _refresh_model_card(self) -> None:
        obj = self.current_object
        if obj is None:
            self.model_name_label.setText("未设置模型")
            self.model_id_label.setText("ID: -")
            return

        # 模型信息优先读当前对象 metadata；若实例未设置则回退到模板
        metadata = self._read_metadata_dict()
        template_for_instance = self._current_template_for_instance()

        is_drop_context = False
        if isinstance(obj, TemplateConfig):
            is_drop_context = is_drop_template_config(obj)
        elif isinstance(obj, InstanceConfig):
            is_drop_context = is_drop_template_config(template_for_instance)

        display_name = ""
        display_id = ""

        if is_drop_context:
            drop_id = metadata.get("drop_model_id")
            if drop_id is None and template_for_instance is not None:
                tpl_md = getattr(template_for_instance, "metadata", {}) or {}
                if isinstance(tpl_md, dict):
                    drop_id = tpl_md.get("drop_model_id")
            display_name = "掉落物模型"
            display_id = _safe_strip_text(drop_id) or "-"
        else:
            creature_name = _safe_strip_text(metadata.get("creature_model_name"))
            object_name = _safe_strip_text(metadata.get("object_model_name"))
            if not creature_name and not object_name and template_for_instance is not None:
                tpl_md = getattr(template_for_instance, "metadata", {}) or {}
                if isinstance(tpl_md, dict):
                    creature_name = _safe_strip_text(tpl_md.get("creature_model_name"))
                    object_name = _safe_strip_text(tpl_md.get("object_model_name"))
            display_name = creature_name or object_name or "空模型"
            display_id = display_name

        self.model_name_label.setText(display_name)
        self.model_id_label.setText(f"ID: {display_id}")

        # mount/decorations 计数（来自 inspector.model.*）
        inspector = self._read_inspector_dict(metadata)
        model = inspector.get("model") if isinstance(inspector, dict) else {}
        mount_points_raw = model.get("mountPoints") if isinstance(model, dict) else None
        decorations_raw = model.get("decorations") if isinstance(model, dict) else None
        mount_count = len(mount_points_raw) if isinstance(mount_points_raw, list) else 0
        decoration_count = len(decorations_raw) if isinstance(decorations_raw, list) else 0

        self.mount_points_label.setText(f"单位挂接点（{mount_count}）")
        self.decorations_label.setText(f"装饰物列表（{decoration_count}）")

    def _on_model_more_clicked(self) -> None:
        if self._is_read_only or self.current_object is None:
            return

        obj = self.current_object
        template_for_instance = self._current_template_for_instance()

        is_drop_context = False
        entity_type_value = ""
        if isinstance(obj, TemplateConfig):
            is_drop_context = is_drop_template_config(obj)
            entity_type_value = obj.entity_type
        elif isinstance(obj, InstanceConfig):
            is_drop_context = is_drop_template_config(template_for_instance)
            if template_for_instance is not None:
                entity_type_value = template_for_instance.entity_type

        if is_drop_context:
            metadata = self._ensure_metadata()
            current_id = metadata.get("drop_model_id")
            current_int = int(current_id) if isinstance(current_id, int) and not isinstance(current_id, bool) else 0
            picked = input_dialogs.prompt_int(
                self,
                "设置模型ID",
                "模型ID:",
                value=current_int,
                minimum=0,
                maximum=999_999_999,
                step=1,
            )
            if picked is None:
                return
            if self.service is not None:
                self.service.apply_drop_metadata(
                    obj,
                    {
                        "template_category": "掉落物",
                        "is_drop_item": True,
                        "drop_model_id": int(picked),
                    },
                )
            else:
                metadata["drop_model_id"] = int(picked)
                metadata["template_category"] = "掉落物"
                metadata["is_drop_item"] = True
            self._refresh_model_card()
            self.data_changed.emit()
            return

        if entity_type_value == "造物":
            pairs = get_creature_model_display_pairs()
            labels = [display for display, _ in pairs]
            selected = input_dialogs.prompt_item(
                self,
                "选择模型",
                "造物模型:",
                labels,
                current_index=0,
                editable=False,
            )
            if selected is None:
                return
            model_name = ""
            for display, name in pairs:
                if display == selected:
                    model_name = name
                    break
            if not model_name:
                return
            category = get_creature_model_category_for_name(model_name) or ""
            metadata = self._ensure_metadata()
            metadata["creature_model_name"] = model_name
            metadata["creature_model_category"] = category
            self._refresh_model_card()
            self.data_changed.emit()
            return

        # 物件：自由输入模型名称（当前无全量资源库下拉）
        current_name = _safe_strip_text(self._read_metadata_dict().get("object_model_name"))
        text = input_dialogs.prompt_text(
            self,
            "设置模型",
            "模型名称:",
            placeholder="例如：石质元素立方体",
            text=current_name,
        )
        if text is None:
            return
        metadata = self._ensure_metadata()
        metadata["object_model_name"] = text
        self._refresh_model_card()
        self.data_changed.emit()

    def _on_edit_decorations_clicked(self) -> None:
        if self._is_read_only or self.current_object is None:
            return
        metadata = self._ensure_metadata()
        inspector = self._ensure_inspector(metadata)
        model = ensure_nested_dict(inspector, "model")

        raw_mount_points = model.get("mountPoints")
        unit_sockets = (
            [str(x).strip() for x in raw_mount_points if str(x).strip()]
            if isinstance(raw_mount_points, list)
            else []
        )

        raw_attachment_points = model.get("attachmentPoints")
        attachment_points = (
            [x for x in raw_attachment_points if isinstance(x, dict)]
            if isinstance(raw_attachment_points, list)
            else []
        )

        available_sockets: list[str] = [ROOT_SOCKET_NAME]
        for name in unit_sockets:
            if name and name not in available_sockets:
                available_sockets.append(name)
        for ap in attachment_points:
            ap_name = str(ap.get("name") or "").strip()
            if ap_name and ap_name not in available_sockets:
                available_sockets.append(ap_name)

        raw_decorations = model.get("decorations")
        decorations: list[dict[str, object]] = []
        if isinstance(raw_decorations, list):
            for entry in raw_decorations:
                if isinstance(entry, dict):
                    decorations.append(entry)
                elif isinstance(entry, str) and entry.strip():
                    # 兼容旧的字符串列表：将字符串视为 displayName
                    from app.ui.foundation.id_generator import generate_prefixed_id

                    decorations.append(
                        {
                            "instanceId": generate_prefixed_id("deco"),
                            "displayName": entry.strip(),
                            "isVisible": True,
                            "assetId": 0,
                            "parentId": ROOT_SOCKET_NAME,
                            "transform": {
                                "pos": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "rot": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "scale": {"x": 1.0, "y": 1.0, "z": 1.0},
                                "isLocked": False,
                            },
                            "physics": {
                                "enableCollision": True,
                                "isClimbable": True,
                                "showPreview": False,
                            },
                        }
                    )

        dialog = DecorationEditorDialog(
            decorations=decorations,
            available_parent_sockets=available_sockets,
            parent=self,
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        model["decorations"] = dialog.get_decorations()
        self._refresh_model_card()
        self.data_changed.emit()

    def _on_split_decorations_clicked(self) -> None:
        if self._is_read_only or self.current_object is None:
            return
        if self.service is None:
            return
        resource_manager = getattr(self, "resource_manager", None)
        if not isinstance(resource_manager, ResourceManager):
            return
        package = self.current_package
        if not isinstance(package, PackageView):
            dialog_utils.show_warning_dialog(
                self,
                "需要项目存档上下文",
                "当前视图不是“项目存档视图”，无法将新元件写入项目存档目录。\n"
                "请切换到某个具体项目存档后再使用该功能。",
            )
            return

        metadata = self._read_metadata_dict()
        inspector = self._read_inspector_dict(metadata)
        model = inspector.get("model") if isinstance(inspector, dict) else None
        raw_decorations = model.get("decorations") if isinstance(model, dict) else None
        if not isinstance(raw_decorations, list) or not raw_decorations:
            dialog_utils.show_info_dialog(
                self,
                "无装饰物",
                "当前对象的 `metadata.common_inspector.model.decorations` 为空，无法打散。",
            )
            return

        decoration_count = len(raw_decorations)
        confirmed = dialog_utils.ask_yes_no_dialog(
            self,
            "确认打散装饰物",
            "即将执行：\n"
            f"- 装饰物数量：{decoration_count}\n"
            f"- 生成元件数量：{decoration_count}\n"
            "- 写入位置：当前项目存档的 `元件库/`\n\n"
            "是否继续？",
            default_yes=False,
        )
        if not confirmed:
            return

        created_template_ids = self.service.split_decorations_to_templates(
            source=self.current_object,
            object_type=self.object_type,
            package=package,
            resource_manager=resource_manager,
        )
        if not created_template_ids:
            dialog_utils.show_info_dialog(self, "已完成", "未生成任何新元件（可能装饰物列表不包含有效条目）。")
            return

        # 触发左侧库页刷新（不依赖“属性改动→脏标记”链路，避免误导保存状态）
        main_window = self.window()
        template_widget = getattr(main_window, "template_widget", None)
        refresh = getattr(template_widget, "refresh_templates", None)
        if callable(refresh):
            refresh()

        preview_ids = created_template_ids[:8]
        more = "" if len(created_template_ids) <= 8 else f"\n... 以及另外 {len(created_template_ids) - 8} 个"
        dialog_utils.show_info_dialog(
            self,
            "打散完成",
            "已生成装饰物元件：\n"
            + "\n".join([f"- {tid}" for tid in preview_ids])
            + more,
        )

    def _on_edit_mount_points_clicked(self) -> None:
        if self._is_read_only or self.current_object is None:
            return
        metadata = self._ensure_metadata()
        inspector = self._ensure_inspector(metadata)
        model = ensure_nested_dict(inspector, "model")

        raw_mount_points = model.get("mountPoints")
        unit_sockets = (
            [str(x).strip() for x in raw_mount_points if str(x).strip()]
            if isinstance(raw_mount_points, list)
            else []
        )

        raw_previews = model.get("mountPointPreviews")
        unit_previews = (
            [str(x).strip() for x in raw_previews if str(x).strip()]
            if isinstance(raw_previews, list)
            else []
        )

        raw_attachment_points = model.get("attachmentPoints")
        attachment_points = (
            [x for x in raw_attachment_points if isinstance(x, dict)]
            if isinstance(raw_attachment_points, list)
            else []
        )

        dialog = SocketEditorDialog(
            unit_sockets=unit_sockets,
            attachment_points=attachment_points,
            unit_socket_previews=unit_previews,
            parent=self,
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        model["mountPointPreviews"] = dialog.get_unit_socket_previews()
        model["attachmentPoints"] = dialog.get_attachment_points()
        self._refresh_model_card()
        self.data_changed.emit()

    # --------------------------------------------------------------------- Unit tags
    def _rebuild_unit_tag_chips(self, tag_ids: Sequence[str]) -> None:
        while self._unit_tags_layout.count():
            item = self._unit_tags_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not tag_ids:
            placeholder = QtWidgets.QLabel("当前列表为空。", self._unit_tags_container)
            placeholder.setStyleSheet(f"color: {Colors.TEXT_HINT};")
            self._unit_tags_layout.addWidget(placeholder)
            return

        name_map = self._get_unit_tag_name_map()
        for tag_id in tag_ids:
            display = name_map.get(tag_id) or tag_id
            chip = _TagChip(tag_id, display, parent=self._unit_tags_container)
            chip.removed.connect(self._remove_unit_tag_by_id)
            chip.setEnabled(not self._is_read_only)
            self._unit_tags_layout.addWidget(chip)

    def _get_unit_tag_name_map(self) -> dict[str, str]:
        package = self.current_package
        management = getattr(package, "management", None) if package is not None else None
        mapping = getattr(management, "unit_tags", None) if management is not None else None
        if not isinstance(mapping, dict):
            return {}
        result: dict[str, str] = {}
        for tag_id, payload in mapping.items():
            if not isinstance(payload, dict):
                continue
            name_text = _safe_strip_text(payload.get("tag_name"))
            if name_text:
                result[str(tag_id)] = name_text
        return result

    def _on_add_unit_tag_clicked(self) -> None:
        if self._is_read_only:
            return
        metadata = self._ensure_metadata()
        inspector = self._ensure_inspector(metadata)
        tags_list = ensure_list_field(ensure_nested_dict(inspector, "logic"), "tags")

        name_map = self._get_unit_tag_name_map()
        if name_map:
            labels: list[str] = []
            label_to_id: dict[str, str] = {}
            for tag_id, tag_name in name_map.items():
                label = f"{tag_name} ({tag_id})"
                labels.append(label)
                label_to_id[label] = tag_id
            labels.sort(key=lambda t: t.casefold())
            selected = input_dialogs.prompt_item(
                self,
                "添加单位标签",
                "选择标签:",
                labels,
                current_index=0,
                editable=False,
            )
            if selected is None:
                return
            tag_id = label_to_id.get(selected, "")
            if not tag_id:
                return
        else:
            tag_id = input_dialogs.prompt_text(
                self,
                "添加单位标签",
                "标签ID/名称:",
                placeholder="例如：unit_tag_001 或 自定义文本",
            )
            if tag_id is None:
                return

        if tag_id in tags_list:
            self._rebuild_unit_tag_chips([_safe_strip_text(t) for t in tags_list if _safe_strip_text(t)])
            return
        tags_list.append(tag_id)
        self._rebuild_unit_tag_chips([_safe_strip_text(t) for t in tags_list if _safe_strip_text(t)])
        self.data_changed.emit()

    def _remove_unit_tag_by_id(self, tag_id: str) -> None:
        if self._is_read_only:
            return
        metadata = self._ensure_metadata()
        inspector = self._ensure_inspector(metadata)
        tags_list = ensure_list_field(ensure_nested_dict(inspector, "logic"), "tags")
        if tag_id in tags_list:
            tags_list.remove(tag_id)
        self._rebuild_unit_tag_chips([_safe_strip_text(t) for t in tags_list if _safe_strip_text(t)])
        self.data_changed.emit()

    # --------------------------------------------------------------------- Read-only
    def set_read_only(self, read_only: bool) -> None:
        self._is_read_only = bool(read_only)
        self._apply_read_only_state()

    def _apply_read_only_state(self) -> None:
        self.name_edit.setReadOnly(self._is_read_only)
        self.guid_edit.setReadOnly(self._is_read_only)
        self.notes_edit.setReadOnly(self._is_read_only)

        self.transform_lock_switch.setEnabled(not self._is_read_only)
        self.collision_initial_active.setEnabled(not self._is_read_only)
        self.collision_is_climbable.setEnabled(not self._is_read_only)
        self.collision_show_gizmos.setEnabled(not self._is_read_only)
        self.render_visible.setEnabled(not self._is_read_only)
        self.spawn_on_load.setEnabled(not self._is_read_only)
        self.faction_combo.setEnabled(not self._is_read_only)
        self.cull_out_of_range.setEnabled(not self._is_read_only)
        self.add_unit_tag_btn.setEnabled(not self._is_read_only)
        self.model_more_btn.setEnabled(not self._is_read_only)
        self.edit_mount_points_btn.setEnabled(not self._is_read_only)
        self.edit_decorations_btn.setEnabled(not self._is_read_only)
        self.split_decorations_btn.setEnabled(not self._is_read_only)

        self._update_transform_editable_state()


__all__ = ["BasicInfoTab"]


